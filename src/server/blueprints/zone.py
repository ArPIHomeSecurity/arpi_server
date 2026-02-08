from flask import jsonify, request
from flask.blueprints import Blueprint
from flask.helpers import make_response

from server.database import db
from server.decorators import authenticated, registered, restrict_host
from server.ipc import IPCClient
from server.services.base import (ConfigChangesNotAllowed, ObjectNotChanged,
                                  ObjectNotFound)
from server.services.zone import ZoneService
from server.tools import process_ipc_response
from utils.constants import ROLE_USER
from utils.models import Zone

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
    """
    Create a new zone.
    """
    try:
        zone_service = ZoneService(db.session)
        new_zone = zone_service.create_zone(
            name=request.json["name"],
            description=request.json.get("description", ""),
            disarmed_delay=request.json.get("disarmedDelay"),
            away_alert_delay=request.json.get("awayAlertDelay", 0),
            stay_alert_delay=request.json.get("stayAlertDelay", 0),
            away_arm_delay=request.json.get("awayArmDelay", 0),
            stay_arm_delay=request.json.get("stayArmDelay", 0),
        )
        return jsonify(new_zone.serialized), 201
    except ConfigChangesNotAllowed:
        return make_response(jsonify({"error": "Configuration changes are not allowed currently"}), 409)


@zone_blueprint.route("/api/zone/<int:zone_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def manage_zone(zone_id):
    """
    Manage zones.
    """
    try:
        zone_service = ZoneService(db.session)
        if request.method == "GET":
            zone = zone_service.get_zone(zone_id)
            return jsonify(zone.serialized)
        elif request.method == "PUT":
            updated_zone = zone_service.update_zone(zone_id,
                name=request.json["name"],
                description=request.json.get("description", ""),
                disarmed_delay=request.json.get("disarmedDelay"),
                away_alert_delay=request.json.get("awayAlertDelay", 0),
                stay_alert_delay=request.json.get("stayAlertDelay", 0),
                away_arm_delay=request.json.get("awayArmDelay", 0),
                stay_arm_delay=request.json.get("stayArmDelay", 0),
            )
            return jsonify(updated_zone.serialized)
        elif request.method == "DELETE":
            zone_service.delete_zone(zone_id)
            return make_response("Deleted", 204)

        return make_response(jsonify({"error": "Method not allowed"}), 405)
    except ConfigChangesNotAllowed:
        return make_response(jsonify({"error": "Configuration changes are not allowed in the current state"}), 409)
    except ObjectNotFound:
        return make_response(jsonify({"error": "Zone not found"}), 404)
    except ObjectNotChanged:
        return make_response(jsonify({"info": "No changes made"}), 204)


@zone_blueprint.route("/api/zones/reorder", methods=["PUT"])
@registered
@restrict_host
def reorder_zones():
    """
    Change only the ui_order of the zones
    """
    for zone_data in request.json:
        db.session.query(Zone).get(zone_data["id"]).update_record(
            ["ui_order"], zone_data
        )

    db.session.commit()

    return make_response("", 200)
