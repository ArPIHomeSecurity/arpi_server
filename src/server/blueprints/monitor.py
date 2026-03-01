from flask import request
from flask.blueprints import Blueprint
from flask.json import jsonify

from server.services.monitor import MonitoringService
from utils.constants import ROLE_USER
from server.database import db
from server.decorators import authenticated, registered, restrict_host
from server.ipc import IPCClient
from server.tools import process_ipc_response
from utils.queries import get_arm_state

monitor_blueprint = Blueprint("monitor", __name__)


@monitor_blueprint.route("/api/monitoring/arm", methods=["GET"])
@registered
@restrict_host
def get_arm():
    """
    Get the current arm state of the monitoring system.
    """
    monitoring_service = MonitoringService(db.session)
    return jsonify({"type": monitoring_service.get_arm_state()})


@monitor_blueprint.route("/api/monitoring/arm", methods=["PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def put_arm(request_user_id: int):
    """
    Arm the monitoring system.
    """
    monitoring_service = MonitoringService(db.session)
    return process_ipc_response(monitoring_service.arm(request.args.get("type"), request_user_id))


@monitor_blueprint.route("/api/monitoring/disarm", methods=["PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def disarm(request_user_id: int):
    """
    Disarm the monitoring system.
    """
    monitoring_service = MonitoringService(db.session)
    return process_ipc_response(monitoring_service.disarm(request_user_id))


@monitor_blueprint.route("/api/monitoring/state", methods=["GET"])
@registered
@restrict_host
def get_state():
    """
    Get the current monitoring state.
    """
    monitoring_service = MonitoringService(db.session)
    return process_ipc_response(monitoring_service.get_state())
