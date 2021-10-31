from flask.blueprints import Blueprint
from flask import jsonify, request
from flask.helpers import make_response
from models import Zone
from monitoring.constants import ROLE_USER

from server.database import db
from server.decorators import authenticated, restrict_host
from server.ipc import IPCClient
from server.tools import process_ipc_response

zone_blueprint = Blueprint("zone", __name__)


@zone_blueprint.route("/api/zones/", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_zones():
    return jsonify([i.serialize for i in db.session.query(Zone).filter_by(deleted=False).all()])


@zone_blueprint.route("/api/zones/", methods=["POST"])
@authenticated()
@restrict_host
def create_zone():
    zone = Zone()
    zone.update(request.json)
    if not zone.description:
        zone.description = zone.name
    db.session.add(zone)
    db.session.commit()
    IPCClient().update_configuration()
    return jsonify(zone.serialize)


@zone_blueprint.route("/api/zone/<int:zone_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def zone(zone_id):
    if request.method == "GET":
        zone = db.session.query(Zone).get(zone_id)
        if zone:
            return jsonify(zone.serialize)

        return make_response(jsonify({"error": "Zone not found"}), 404)
    elif request.method == "DELETE":
        zone = db.session.query(Zone).get(zone_id)
        if zone:
            zone.deleted = True
            db.session.commit()
            return process_ipc_response(IPCClient().update_configuration())

        return make_response(jsonify({"error": "Zone not found"}), 404)
    elif request.method == "PUT":
        zone = db.session.query(Zone).get(zone_id)
        if not zone:
            return make_response(jsonify({"error": "Zone not found"}), 404)

        if not zone.update(request.json):
            return make_response("", 204)

        db.session.commit()
        return process_ipc_response(IPCClient().update_configuration())
    return make_response(jsonify({"error": "Unknown action"}), 400)
