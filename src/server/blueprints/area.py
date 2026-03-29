from flask import jsonify, request
from flask.blueprints import Blueprint

from server.database import db
from server.decorators import authenticated, registered, restrict_host
from server.ipc import IPCClient
from server.services.area import AreaService
from server.services.base import (ConfigChangesNotAllowed, ObjectNotChanged,
                                  ObjectNotFound)
from server.tools import process_ipc_response
from utils.constants import ROLE_USER
from utils.models import Area

area_blueprint = Blueprint("area", __name__)


@area_blueprint.route("/api/areas/", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_areas():
    """
    Retrieve all existing areas.
    """
    area_service = AreaService(db.session)
    return jsonify(
        [area.serialized for area in area_service.get_areas()]
    )

@area_blueprint.route("/api/areas/", methods=["POST"])
@authenticated()
@restrict_host
def create_area():
    """
    Create a new area.
    """
    try:
        area_service = AreaService(db.session)
        area = area_service.create_area(request.json.get("name"))
        return jsonify(area.serialized), 201
    except ConfigChangesNotAllowed:
        return jsonify({"error": "Configuration changes are not allowed in the current state"}), 409


@area_blueprint.route("/api/area/<int:area_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def manage_area(area_id):
    """
    Manage areas.
    """
    try:
        area_service = AreaService(db.session)
        if request.method == "GET":
            area = area_service.get_area(area_id)
            return jsonify(area.serialized)
        elif request.method == "PUT":
            area = area_service.update_area(area_id, request.json.get("name"))
            return jsonify(area.serialized)
        elif request.method == "DELETE":
            area_service.delete_area(area_id)
            return "Deleted", 204

        return jsonify({"error": "Unknown action"}), 405
    except ConfigChangesNotAllowed:
        return jsonify({"error": "Configuration changes are not allowed in the current state"}), 409
    except ObjectNotFound:
        return jsonify({"error": "Area not found"}), 404
    except ObjectNotChanged:
        return jsonify({"info": "No changes made"}), 204


@area_blueprint.route("/api/area/arm", methods=["PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def put_arm():
    try:
        area_service = AreaService(db.session)
        return process_ipc_response(
            area_service.arm(
                area_id=request.args["area_id"],
                arm_type=request.args.get("type"),
                user_id=request.environ["requester_id"],
            )
        )
    except ObjectNotFound:
        return jsonify({"error": "Area not found"}), 404


@area_blueprint.route("/api/area/disarm", methods=["PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def put_disarm():
    try:
        area_service = AreaService(db.session)
        return process_ipc_response(
            area_service.disarm(
                area_id=request.args["area_id"],
                user_id=request.environ["requester_id"],
            )
        )
    except ObjectNotFound:
        return jsonify({"error": "Area not found"}), 404


@area_blueprint.route("/api/areas/reorder", methods=["PUT"])
@registered
@restrict_host
def reorder_areas():
    """
    Change only the ui_order of the areas
    """
    for area_data in request.json:
        db.session.query(Area).get(area_data["id"]).update_record(
            ["ui_order"], area_data
        )

    db.session.commit()

    return ""
