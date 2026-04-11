from flask.blueprints import Blueprint
from flask import jsonify, request

from utils.constants import ROLE_USER
from server.database import db
from server.decorators import authenticated, restrict_host
from server.services.arm import ArmService

arm_blueprint = Blueprint("arm", __name__)


@arm_blueprint.route("/api/arms", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_arms():
    """
    Get arm/disarm events with optional filters.
    """
    # TODO: add on going sabotage event
    # on going sabotage event only has an alert without arm or disarm
    arm_service = ArmService(db.session)
    has_alert = None
    if request.args.get("has_alert") == "true":
        has_alert = True
    elif request.args.get("has_alert") == "false":
        has_alert = False

    results = arm_service.get_arms(
        has_alert=has_alert,
        user_id=request.args.get("user_id", type=int),
        keypad_id=request.args.get("keypad_id", type=int),
        arm_type=request.args.get("arm_type"),
        start=request.args.get("start"),
        end=request.args.get("end"),
        limit=request.args.get("limit", 10, type=int),
        offset=request.args.get("offset", 0, type=int),
    )
    return jsonify(results)


@arm_blueprint.route("/api/arms/count", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_arms_count():
    """
    Get count of arm/disarm events with optional filters.
    """
    arm_service = ArmService(db.session)
    has_alert = None
    if request.args.get("has_alert") == "true":
        has_alert = True
    elif request.args.get("has_alert") == "false":
        has_alert = False

    return jsonify(
        arm_service.get_arms_count(
            has_alert=has_alert,
            user_id=request.args.get("user_id", type=int),
            keypad_id=request.args.get("keypad_id", type=int),
            arm_type=request.args.get("arm_type"),
            start=request.args.get("start"),
            end=request.args.get("end"),
        )
    )
