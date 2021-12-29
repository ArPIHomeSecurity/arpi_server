from datetime import datetime as dt
import os
from dateutil.tz.tz import tzlocal

from flask.blueprints import Blueprint
from flask.helpers import make_response
from flask import jsonify, request, current_app
from jose import jwt

from models import User, hash_code
from server.database import db
from server.decorators import authenticated, generate_user_token, registered, restrict_host
from server.ipc import IPCClient
from server.tools import process_ipc_response

user_blueprint = Blueprint("user", __name__)


@user_blueprint.route("/api/users", methods=["GET", "POST"])
@authenticated()
@restrict_host
def users():
    if request.method == "GET":
        return jsonify([i.serialize for i in db.session.query(User).order_by(User.role).all()])
    elif request.method == "POST":
        data = request.json
        user = User(name=data["name"], role=data["role"], access_code=data["accessCode"])
        db.session.add(user)
        db.session.commit()

    return jsonify(None)


@user_blueprint.route("/api/user/<int:user_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def user(user_id):
    if request.method == "GET":
        user = db.session.query(User).get(user_id)
        if user:
            return jsonify(user.serialize)

        return make_response(jsonify({"error": "User not found"}), 404)
    elif request.method == "PUT":
        user = db.session.query(User).get(user_id)
        if user:
            if not user.update(request.json):
                return make_response("", 204)

            db.session.commit()
            return jsonify(None)
        return make_response(jsonify({"error": "User not found"}), 404)
    elif request.method == "DELETE":
        user = db.session.query(User).get(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()
            return jsonify(None)
        else:
            return make_response(jsonify({"error": "User not found"}), 404)

    return make_response(jsonify({"error": "Unknown action"}), 400)


@user_blueprint.route("/api/user/<int:user_id>/registration_code", methods=["GET", "DELETE"])
@authenticated()
@restrict_host
def registration_code(user_id):
    remote_ip = request.environ.get("HTTP_X_REAL_IP", request.remote_addr)
    current_app.logger.debug(
        "Input from '%s' on '%s': '%s'", remote_ip, request.environ.get("HTTP_ORIGIN", ""), request.json
    )

    if request.method == "GET":
        user = db.session.query(User).get(user_id)
        if user:
            if user.registration_code:
                return make_response(jsonify({"error": "Already has registration code"}), 400)

            expiry = int(request.args.get("expiry")) if request.args.get("expiry") else None
            code = user.add_registration_code(expiry=expiry)
            db.session.commit()
            return jsonify({"code": code})

        return make_response(jsonify({"error": "User not found"}), 404)
    elif request.method == "DELETE":
        user = db.session.query(User).get(user_id)
        if user:
            user.registration_code = None
            user.registration_expiry = None
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
        "Input from '%s' on '%s': '%s'", remote_ip, request.environ.get("HTTP_ORIGIN", ""), request.json
    )

    if request.json["registration_code"]:
        user = (
            db.session.query(User)
            .filter_by(registration_code=hash_code(request.json["registration_code"].upper()))
            .first()
        )

        if user:
            if user.registration_expiry and dt.now(tzlocal()) > user.registration_expiry:
                return make_response(
                    jsonify({"error": "Failed to register device", "reason": "Expired registration code"}), 400
                )

            user.registration_code = None
            db.session.commit()
            token = {"ip": remote_ip, "origin": request.environ["HTTP_ORIGIN"], "user_id": user.id}
            return jsonify({"device_token": jwt.encode(token, os.environ.get("SECRET"), algorithm="HS256")})
        else:
            return make_response(jsonify({"error": "Failed to register device", "reason": "User not found"}), 400)

    return make_response(jsonify({"error": "Failed to register device", "reason": "Missing registration code"}), 400)


@user_blueprint.route("/api/user/authenticate", methods=["POST"])
@registered
@restrict_host
def authenticate():
    current_app.logger.debug("Authenticating...")

    # device token must be valid because of the @registered decorator
    device_token = jwt.decode(request.json["device_token"], os.environ.get("SECRET"), algorithms="HS256")
    user = db.session.query(User).get(device_token["user_id"])
    if user and user.access_code == hash_code(request.json["access_code"]):
        return jsonify({
            "user_token": generate_user_token(user.id, user.name, user.role, request.environ["HTTP_ORIGIN"]),
        })
    elif not user:
        current_app.logger.warn("Invalid user id %s", device_token["user_id"])
        return jsonify({"error": "invalid user id"}), 400

    return jsonify(False)


@user_blueprint.route("/api/user/<int:user_id>/register_card", methods=["PUT"])
@authenticated()
@restrict_host
def register_card(user_id):
    for user in db.session.query(User).all():
        user.card_registration_expiry = None
    user = db.session.query(User).get(user_id)
    user.set_card_registration()
    db.session.commit()

    return process_ipc_response(IPCClient().register_card())


@user_blueprint.route("/api/user/<int:user_id>/cards", methods=["GET"])
def cards(user_id):
    user = db.session.query(User).get(user_id)
    return jsonify([i.serialize for i in user.cards])
