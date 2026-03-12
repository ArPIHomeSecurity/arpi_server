from flask import jsonify, request
from flask.blueprints import Blueprint

from server.database import db
from server.decorators import authenticated, restrict_host
from server.services.base import ObjectNotChanged, ObjectNotFound
from server.services.keypad import KeypadService
from server.tools import process_ipc_response
from utils.constants import ROLE_USER

keypad_blueprint = Blueprint("keypad", __name__)


@keypad_blueprint.route("/api/keypads/", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_keypads():
    keypad_service = KeypadService(db.session)
    return jsonify([i.serialized for i in keypad_service.get_keypads()])


@keypad_blueprint.route("/api/keypad/<int:keypad_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def manage_keypad(keypad_id):
    """
    Limited to handle only one keypad!
    """
    keypad_service = KeypadService(db.session)
    try:
        if request.method == "GET":
            return jsonify(keypad_service.get_keypad(keypad_id).serialized)
        elif request.method == "DELETE":
            return process_ipc_response(keypad_service.delete_keypad(keypad_id))
        elif request.method == "PUT":
            try:
                return process_ipc_response(keypad_service.update_keypad(keypad_id, **request.json))
            except ObjectNotFound:
                return process_ipc_response(keypad_service.create_keypad(
                    type_id=request.json["typeId"],
                    enabled=request.json.get("enabled", True),
                ))
        return jsonify({"error": "Unknown action"}), 405
    except ObjectNotFound:
        return jsonify({"error": "Keypad not found"}), 404
    except ObjectNotChanged:
        return jsonify({"error": "No changes made"}), 409


@keypad_blueprint.route("/api/keypadtypes", methods=["GET"])
@authenticated()
@restrict_host
def keypadtypes():
    keypad_service = KeypadService(db.session)
    return jsonify([i.serialized for i in keypad_service.get_keypad_types()])
