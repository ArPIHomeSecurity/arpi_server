from flask.blueprints import Blueprint
from flask import jsonify, request
from flask.helpers import make_response
from models import Area
from constants import ROLE_USER

from server.database import db
from server.decorators import authenticated, restrict_host, registered
from server.ipc import IPCClient
from server.tools import process_ipc_response

area_blueprint = Blueprint("area", __name__)


@area_blueprint.route("/api/areas/", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_areas():
    return jsonify(
        [
            i.serialized
            for i in db.session.query(Area)
            .filter_by(deleted=False)
            .order_by(Area.id.asc())
            .all()
        ]
    )


@area_blueprint.route("/api/areas/", methods=["POST"])
@authenticated()
@restrict_host
def create_area():
    area = Area()
    area.update(request.json)
    db.session.add(area)
    db.session.commit()
    IPCClient().update_configuration()
    return jsonify(area.serialized)


@area_blueprint.route("/api/area/<int:area_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def area(area_id):
    if request.method == "GET":
        area = db.session.query(Area).get(area_id)
        if area:
            return jsonify(area.serialized)

        return make_response(jsonify({"error": "Area not found"}), 404)
    elif request.method == "DELETE":
        area = db.session.query(Area).get(area_id)
        if area:
            area.deleted = True
            db.session.commit()
            return process_ipc_response(IPCClient().update_configuration())

        return make_response(jsonify({"error": "Area not found"}), 404)
    elif request.method == "PUT":
        area = db.session.query(Area).get(area_id)
        if not area:
            return make_response(jsonify({"error": "Area not found"}), 404)

        if not area.update(request.json):
            return make_response("", 204)

        db.session.commit()
        return process_ipc_response(IPCClient().update_configuration())
    return make_response(jsonify({"error": "Unknown action"}), 400)


@area_blueprint.route("/api/area/arm", methods=["PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def put_arm():
    return process_ipc_response(
        IPCClient().arm(
            arm_type=request.args.get("type"),
            user_id=request.environ["requester_id"],
            area_id=request.args["area_id"],
        )
    )


@area_blueprint.route("/api/area/disarm", methods=["PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def put_disarm():
    return process_ipc_response(
        IPCClient().disarm(request.environ["requester_id"], request.args["area_id"])
    )


@area_blueprint.route("/api/areas/reorder", methods=["PUT"])
@registered
@restrict_host
def reorder_zones():
    """
    Change only the ui_order of the zones
    """
    for area_data in request.json:
        db.session.query(Area).get(area_data["id"]).update_record(
            ["ui_order"], area_data
        )

    db.session.commit()

    return make_response("", 200)
