from datetime import datetime as dt
import os
from dateutil.tz.tz import tzlocal

from flask.blueprints import Blueprint
from flask.helpers import make_response
from flask import jsonify, request, current_app
from jose import jwt

from constants import ROLE_ADMIN, ROLE_USER
from models import User, hash_code
from server.database import db
from server.decorators import (
    authenticated,
    generate_user_token,
    registered,
    restrict_host,
)
from server.ipc import IPCClient
from server.tools import process_ipc_response
from tools.ssh_keymanager import SSHKeyManager

user_blueprint = Blueprint("user", __name__)


@user_blueprint.route("/api/users", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_users():
    return jsonify(
        [i.serialized for i in db.session.query(User).order_by(User.role).all()]
    )


@user_blueprint.route("/api/users", methods=["POST"])
@authenticated()
@restrict_host
def create_user():
    data = request.json
    db_user: User = User(
        name=data["name"], role=data["role"], access_code=data["accessCode"]
    )
    db.session.add(db_user)
    db.session.commit()

    return jsonify(None)


@user_blueprint.route("/api/user/<int:user_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def user(user_id):
    db_user: User = db.session.query(User).get(user_id)
    if not db_user:
        return make_response(jsonify({"error": "User not found"}), 404)

    if request.method == "GET":
        return jsonify(db_user.serialized)
    elif request.method == "PUT":
        if not db_user.update(request.json):
            return make_response("", 204)

        db.session.commit()
        return jsonify(None)
    elif request.method == "DELETE":
        db.session.delete(db_user)
        db.session.commit()
        return jsonify(None)

    return make_response(jsonify({"error": "Unknown action"}), 400)


@user_blueprint.route(
    "/api/user/<int:user_id>/registration_code", methods=["GET", "DELETE"]
)
@authenticated()
@restrict_host
def registration_code(user_id):
    remote_ip = request.environ.get("HTTP_X_REAL_IP", request.remote_addr)
    current_app.logger.debug(
        "Input from '%s' on '%s': '%s'",
        remote_ip,
        request.environ.get("HTTP_ORIGIN", ""),
        request.get_json(silent=True),
    )

    if request.method == "GET":
        db_user: User = db.session.query(User).get(user_id)
        if db_user:
            if db_user.registration_code:
                return make_response(
                    jsonify({"error": "Already has registration code"}), 400
                )

            expiry = (
                int(request.args.get("expiry")) if request.args.get("expiry") else None
            )
            code = db_user.add_registration_code(expiry=expiry)
            db.session.commit()
            return jsonify({"code": code})

        return make_response(jsonify({"error": "User not found"}), 404)
    elif request.method == "DELETE":
        db_user: User = db.session.query(User).get(user_id)
        if db_user:
            db_user.registration_code = None
            db_user.registration_expiry = None
            db.session.commit()
            return jsonify(None)
        else:
            return make_response(jsonify({"error": "User not found"}), 404)

    return make_response(jsonify({"error": "Unknown action"}), 400)


@user_blueprint.route("/api/user/register_device", methods=["POST"])
@restrict_host
def register_device():
    current_app.logger.debug("Authenticating...")
    remote_ip = request.environ.get("HTTP_X_REAL_IP", request.remote_addr)
    current_app.logger.debug(
        "Input from '%s' on '%s': '%s'",
        remote_ip,
        request.environ.get("HTTP_ORIGIN", ""),
        request.json,
    )

    if request.json["registration_code"]:
        db_user: User = (
            db.session.query(User)
            .filter_by(
                registration_code=hash_code(request.json["registration_code"].upper())
            )
            .first()
        )

        if db_user:
            if (
                db_user.registration_expiry
                and dt.now(tzlocal()) > db_user.registration_expiry
            ):
                return make_response(
                    jsonify(
                        {
                            "error": "Failed to register device",
                            "reason": "Expired registration code",
                        }
                    ),
                    400,
                )

            db_user.registration_code = None
            db.session.commit()
            token = {
                "ip": remote_ip,
                "origin": request.environ["HTTP_ORIGIN"],
                "user_id": db_user.id,
            }
            return jsonify(
                {
                    "device_token": jwt.encode(
                        token, os.environ.get("SECRET"), algorithm="HS256"
                    )
                }
            )
        else:
            return make_response(
                jsonify(
                    {"error": "Failed to register device", "reason": "User not found"}
                ),
                400,
            )

    return make_response(
        jsonify(
            {
                "error": "Failed to register device",
                "reason": "Missing registration code",
            }
        ),
        400,
    )


@user_blueprint.route("/api/user/authenticate", methods=["POST"])
@registered
@restrict_host
def authenticate():
    current_app.logger.debug("Authenticating...")

    # device token must be valid because of the @registered decorator
    device_token = jwt.decode(
        request.json["device_token"], os.environ.get("SECRET"), algorithms="HS256"
    )
    db_user: User = db.session.query(User).get(device_token["user_id"])
    if db_user and db_user.access_code == hash_code(request.json["access_code"]):
        return jsonify(
            {
                "user_token": generate_user_token(
                    db_user.id,
                    db_user.name,
                    db_user.role,
                    request.environ["HTTP_ORIGIN"],
                ),
            }
        )
    elif not db_user:
        current_app.logger.warn("Invalid user id %s", device_token["user_id"])
        return jsonify({"error": "invalid user id"}), 400

    return jsonify(False)


@user_blueprint.route("/api/user/<int:user_id>/register_card", methods=["PUT"])
@authenticated()
@restrict_host
def register_card(user_id):
    for db_user in db.session.query(User).all():
        db_user.card_registration_expiry = None
    db_user: User = db.session.query(User).get(user_id)
    db_user.set_card_registration()
    db.session.commit()

    return process_ipc_response(IPCClient().register_card())


@user_blueprint.route("/api/user/<int:user_id>/cards", methods=["GET"])
def cards(user_id):
    db_user: User = db.session.query(User).get(user_id)
    return jsonify([i.serialized for i in db_user.cards])


@user_blueprint.route("/api/user/<int:user_id>/has_ssh_key", methods=["GET"])
@authenticated(ROLE_ADMIN)
@restrict_host
def has_ssh_key(user_id):
    db_user: User = db.session.query(User).get(user_id)
    if db_user:
        key_manager = SSHKeyManager()
        key_name = SSHKeyManager.get_key_name(db_user.id, db_user.name)
        current_app.logger.debug("Checking key for user %s", key_name)
        key_exists = key_manager.check_key_exists(key_name)
        return jsonify(key_exists)

    return make_response(jsonify({"error": "User not found"}), 404)


@user_blueprint.route("/api/user/<int:user_id>/ssh_key", methods=["DELETE"])
@authenticated(ROLE_ADMIN)
@restrict_host
def delete_ssh_key(user_id):
    db_user: User = db.session.query(User).get(user_id)
    if db_user:
        key_manager = SSHKeyManager()
        key_name = SSHKeyManager.get_key_name(db_user.id, db_user.name)
        current_app.logger.debug("Deleting key for user %s", key_name)
        key_manager.remove_public_key(key_name)
        return jsonify(True)

    return make_response(jsonify({"error": "User not found"}), 404)


@user_blueprint.route("/api/user/<int:user_id>/ssh_key", methods=["POST"])
@authenticated(ROLE_ADMIN)
@restrict_host
def generate_ssh_key(user_id):
    db_user: User = db.session.query(User).get(user_id)
    if db_user:
        key_manager = SSHKeyManager()
        key_name = SSHKeyManager.get_key_name(db_user.id, db_user.name)
        current_app.logger.debug("Generating key for user %s", key_name)
        private_key, public_key = key_manager.generate_ssh_keys(
            key_type=request.json["keyType"],
            key_name=key_name,
            passphrase=request.json["passphrase"],
        )

        # add public key to authorized_keys
        key_manager.set_public_key(public_key, key_name)

        return jsonify(private_key)

    return make_response(jsonify({"error": "User not found"}), 404)

@user_blueprint.route("/api/user/<int:user_id>/ssh_key", methods=["PUT"])
@authenticated(ROLE_ADMIN)
@restrict_host
def set_public_key(user_id):
    db_user: User = db.session.query(User).get(user_id)
    if db_user:
        key_manager = SSHKeyManager()
        key_name = SSHKeyManager.get_key_name(db_user.id, db_user.name)
        current_app.logger.debug("Generating key for user %s", key_name)

        # add public key to authorized_keys
        key_manager.set_public_key(request.json["publicKey"], key_name)

        return jsonify(True)

    return make_response(jsonify({"error": "User not found"}), 404)
