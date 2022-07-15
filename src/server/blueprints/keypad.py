from flask.blueprints import Blueprint
from flask import jsonify, request, make_response
from models import Keypad, KeypadType

from constants import ROLE_USER
from server.database import db
from server.decorators import authenticated, restrict_host
from server.ipc import IPCClient
from server.tools import process_ipc_response

keypad_blueprint = Blueprint("keypad", __name__)


@keypad_blueprint.route("/api/keypads/", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_keypads():
    # return jsonify([i.serialize for i in db.session.query(Keypad).filter_by(deleted=False).all()])
    return jsonify([i.serialize for i in db.session.query(Keypad).all()])


@keypad_blueprint.route("/api/keypad/<int:keypad_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def keypad(keypad_id):
    """
    Limited to handle only one keypad!
    """
    if request.method == "GET":
        keypad = db.session.query(Keypad).first()
        if keypad:
            return jsonify(keypad.serialize)

        return make_response(jsonify({"error": "Option not found"}), 404)
    elif request.method == "DELETE":
        keypad = db.session.query(Keypad).get(keypad_id)
        if keypad:
            keypad.deleted = True
            db.session.commit()
            return process_ipc_response(IPCClient().update_keypad())

        return make_response(jsonify({"error": "Option not found"}), 404)
    elif request.method == "PUT":
        keypad = db.session.query(Keypad).get(keypad_id)
        if not keypad:
            # create the new keypad
            keypad = Keypad(keypad_type=db.session.query(KeypadType).get(request.json["typeId"]))

        if not keypad.update(request.json):
            return make_response("", 204)

        db.session.commit()
        return process_ipc_response(IPCClient().update_keypad())
    return make_response(jsonify({"error": "Unknown action"}), 400)


@keypad_blueprint.route("/api/keypadtypes", methods=["GET"])
@authenticated()
@restrict_host
def keypadtypes():
    return jsonify([i.serialize for i in db.session.query(KeypadType).all()])
