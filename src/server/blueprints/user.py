import os
from datetime import datetime as dt
from time import sleep
from dateutil.tz.tz import tzlocal

from flask.blueprints import Blueprint
from flask import jsonify, request, current_app
from jose import jwt

from utils.constants import ROLE_ADMIN, ROLE_USER
from utils.models import User
from server.database import db
from server.decorators import (
    authenticated,
    generate_mcp_token,
    generate_user_token,
    registered,
    restrict_host,
)
from server.ipc import IPCClient
from server.tools import process_ipc_response
from tools.ssh_keymanager import SSHKeyManager
from sqlalchemy import inspect

user_blueprint = Blueprint("user", __name__)


@user_blueprint.route("/api/users", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_users():
    return jsonify([i.serialized for i in db.session.query(User).order_by(User.role).all()])


@user_blueprint.route("/api/users", methods=["POST"])
@authenticated()
@restrict_host
def create_user():
    data = request.json
    db_user: User = User(
        name=data["name"],
        role=data["role"],
        access_code=data["accessCode"],
        comment=data.get("comment"),
    )
    db.session.add(db_user)
    db.session.commit()

    return jsonify(None)


@user_blueprint.route("/api/user/<int:user_id>", methods=["GET", "PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def user(user_id, request_user_id=None, requester_role=None):
    """
    Get or update a user
    """
    if (
        request.environ.get("requester_role") == ROLE_USER
        and request.environ.get("requester_id") != user_id
    ):
        return jsonify({"error": "Unauthorized"}), 401

    db_user: User = db.session.query(User).get(user_id)
    if not db_user:
        return jsonify({"error": "User not found"}), 404

    if request.method == "GET":
        return jsonify(db_user.serialized)
    elif request.method == "PUT":
        user_data = request.json
        if user_data.get("newAccessCode"):
            # only admin or the user itself can change the access code
            if requester_role != ROLE_ADMIN and user_id != request_user_id:
                return jsonify({"error": "Cannot change access code of other users"}), 403

            # at this point only admin or the user itself can change the access code

            if requester_role == ROLE_ADMIN and user_id != request_user_id:
                # admin can change any user's access code without the old access code
                pass
            elif user_id == request_user_id:
                # users can only change their own access code with the correct old access code
                if not db_user.check_access_code(user_data["oldAccessCode"]):
                    return jsonify({"error": "Invalid old access code"}), 400

                state = inspect(db_user)
                if state.modified:
                    db.session.commit()

            user_data["accessCode"] = user_data["newAccessCode"]
            del user_data["newAccessCode"]
            del user_data["oldAccessCode"]

        if "role" in user_data and user_data["role"] != db_user.role:
            # only admin can change roles
            if requester_role != ROLE_ADMIN:
                return jsonify({"error": "Cannot change user role"}), 403

        current_app.logger.debug("Updating user %s", db_user)
        if not db_user.update(request.json):
            # nothing changed
            return "", 204

        current_app.logger.debug("Updated user %s", db_user)
        db.session.commit()
        return jsonify(None)


@user_blueprint.route("/api/user/<int:user_id>", methods=["DELETE"])
@authenticated()
@restrict_host
def delete_user(user_id):
    db_user: User = db.session.query(User).get(user_id)
    if not db_user:
        return jsonify({"error": "User not found"}), 404

    db.session.delete(db_user)
    db.session.commit()
    return jsonify(None)


@user_blueprint.route("/api/user/<int:user_id>/name", methods=["GET"])
@registered
@restrict_host
def get_user_name(user_id):
    db_user: User = db.session.query(User).get(user_id)
    return jsonify(db_user.name)


@user_blueprint.route("/api/user/<int:user_id>/registration_code", methods=["GET", "DELETE"])
@authenticated(role=ROLE_USER)
@restrict_host
def registration_code(user_id):
    remote_ip = request.environ.get("HTTP_X_REAL_IP", request.remote_addr)
    current_app.logger.debug(
        "Input from '%s' on '%s': '%s'",
        remote_ip,
        request.environ.get("HTTP_ORIGIN", ""),
        request.get_json(silent=True),
    )

    # only the user itself or an admin can manage the registration code
    if (
        request.environ.get("requester_role") == ROLE_USER
        and request.environ.get("requester_id") != user_id
    ):
        return jsonify({"error": "Unauthorized"}), 401

    if request.method == "GET":
        db_user: User = db.session.query(User).get(user_id)
        if db_user:
            if db_user.registration_code:
                return jsonify({"error": "Already has registration code"}), 400

            expiry = int(request.args.get("expiry")) if request.args.get("expiry") else None
            code = db_user.add_registration_code(expiry=expiry)
            db.session.commit()
            return jsonify({"code": code})

        return jsonify({"error": "User not found"}), 404
    elif request.method == "DELETE":
        db_user: User = db.session.query(User).get(user_id)
        if db_user:
            db_user.registration_code = None
            db_user.registration_expiry = None
            db.session.commit()
            return jsonify(None)
        else:
            return jsonify({"error": "User not found"}), 404

    return jsonify({"error": "Unknown action"}), 405


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
        users = db.session.query(User).all()
        db_user = None
        for tmp_user in users:
            if tmp_user.check_registration_code(request.json["registration_code"]):
                db_user = tmp_user
                break

        if db_user:
            if db_user.registration_expiry and dt.now(tzlocal()) > db_user.registration_expiry:
                sleep(5)
                return jsonify(
                    {
                        "error": "Failed to register device",
                        "reason": "Expired registration code",
                    }
                ), 400

            db_user.registration_code = None
            db.session.commit()
            token = {
                "ip": remote_ip,
                "origin": request.environ["HTTP_ORIGIN"],
                "user_id": db_user.id,
            }
            return jsonify(
                {"device_token": jwt.encode(token, os.environ.get("SECRET"), algorithm="HS256")}
            )
        else:
            sleep(5)
            return jsonify({"error": "Failed to register device", "reason": "User not found"}), 400
            

    sleep(5)
    return jsonify(
            {
                "error": "Failed to register device",
                "reason": "Missing registration code",
            }
        ), 400


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
    if db_user:
        if db_user.check_access_code(request.json["access_code"]):
            # check if anything changed that needs to be saved
            state = inspect(db_user)
            if state.modified:
                db.session.commit()

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
        sleep(2)
        current_app.logger.warning("Invalid user id %s", device_token["user_id"])
        return jsonify({"error": "invalid user id"}), 400

    sleep(2)
    return jsonify(False)


@user_blueprint.route("/api/user/<int:user_id>/mcp_token", methods=["POST"])
@authenticated()
@restrict_host
def get_mcp_token(user_id: int):
    """
    Generate a token for accessing MCP Server with the given TTL (in seconds).

    Args:
        user_id: The ID of the user for whom to generate the token
        ttl: Time to live for the token in seconds (optional, default is 0 for no expiration)
    """
    ttl = int(request.args.get("ttl", 0))
    requester_role = request.environ.get("requester_role")
    if requester_role == ROLE_ADMIN:
        db_user: User = db.session.query(User).get(user_id)
        if not db_user:
            return jsonify({"error": "User not found"}), 404

        if db_user.mcp_key is None:
            # generate a random key if not set
            db_user.mcp_key = os.urandom(32).hex().upper()
            db.session.commit()

        token = generate_mcp_token(
            user_id=db_user.id,
            key=db_user.mcp_key,
            ttl=ttl,
        )
        return jsonify(token)
    else:
        return jsonify({"error": "Only admin users can generate MCP tokens"}), 403


@user_blueprint.route("/api/user/<int:user_id>/mcp_token", methods=["GET"])
@authenticated()
@restrict_host
def has_mcp_token(user_id: int):
    """
    Check if the user has an MCP token.
    """
    requester_role = request.environ.get("requester_role")
    if requester_role == ROLE_ADMIN:
        db_user: User = db.session.query(User).get(user_id)
        if not db_user:
            return jsonify({"error": "User not found"}), 404

        return jsonify({
            "has_mcp_token": db_user.mcp_key is not None
        })
    else:
        return jsonify({"error": "operation not permitted"}), 403


@user_blueprint.route("/api/user/<int:user_id>/mcp_token", methods=["DELETE"])
@authenticated()
@restrict_host
def remove_mcp_token(user_id: int):
    """
    Remove the user's MCP token.
    """
    requester_role = request.environ.get("requester_role")
    if requester_role == ROLE_ADMIN:
        db_user: User = db.session.query(User).get(user_id)
        if not db_user:
            return jsonify({"error": "User not found"}), 404

        db_user.mcp_key = None
        db.session.commit()
        return jsonify(None)
    else:
        return jsonify({"error": "operation not permitted"}), 403


@user_blueprint.route("/api/user/<int:user_id>/register_card", methods=["PUT"])
@authenticated(role=ROLE_USER)
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

    return jsonify({"error": "User not found"}), 404


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

    return jsonify({"error": "User not found"}), 404


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

    return jsonify({"error": "User not found"}), 404


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

    return jsonify({"error": "User not found"}), 404
