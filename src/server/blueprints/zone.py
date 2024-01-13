from flask.blueprints import Blueprint
from flask import jsonify, request
from flask.helpers import make_response
from models import Zone
from constants import ROLE_USER

from server.database import db
from server.decorators import authenticated, restrict_host, registered
from server.ipc import IPCClient
from server.tools import process_ipc_response

zone_blueprint = Blueprint("zone", __name__)


@zone_blueprint.route("/api/zones/", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_zones():
    return jsonify(
        [i.serialized for i in db.session.query(Zone).filter_by(deleted=False).all()]
    )


@zone_blueprint.route("/api/zones/", methods=["POST"])
@authenticated()
@restrict_host
def create_zone():
    db_zone = Zone()
    db_zone.update(request.json)
    if not db_zone.description:
        db_zone.description = db_zone.name
    db.session.add(db_zone)
    db.session.commit()
    IPCClient().update_configuration()
    return jsonify(db_zone.serialized)


@zone_blueprint.route("/api/zone/<int:zone_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def zone(zone_id):
    if request.method == "GET":
        db_zone = db.session.query(Zone).get(zone_id)
        if db_zone:
            return jsonify(db_zone.serialized)

        return make_response(jsonify({"error": "Zone not found"}), 404)
    elif request.method == "DELETE":
        db_zone = db.session.query(Zone).get(zone_id)
        if db_zone:
            db_zone.deleted = True
            db.session.commit()
            return process_ipc_response(IPCClient().update_configuration())

        return make_response(jsonify({"error": "Zone not found"}), 404)
    elif request.method == "PUT":
        db_zone = db.session.query(Zone).get(zone_id)
        if not db_zone:
            return make_response(jsonify({"error": "Zone not found"}), 404)

        if not db_zone.update(request.json):
            return make_response("", 204)

        db.session.commit()
        return process_ipc_response(IPCClient().update_configuration())
    return make_response(jsonify({"error": "Unknown action"}), 400)
