from flask import request
from flask.blueprints import Blueprint
from flask.helpers import make_response
from flask.json import jsonify

from constants import ROLE_USER
from server.database import db
from server.decorators import authenticated, registered, restrict_host
from server.ipc import IPCClient
from server.tools import process_ipc_response
from tools.queries import get_arm_state

monitor_blueprint = Blueprint("monitor", __name__)


@monitor_blueprint.route("/api/monitoring/arm", methods=["GET"])
@registered
@restrict_host
def get_arm():
    return make_response(jsonify({"type": get_arm_state(db.session)}))


@monitor_blueprint.route("/api/monitoring/arm", methods=["PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def put_arm():
    return process_ipc_response(IPCClient().arm(request.args.get("type"), request.environ["requester_id"]))


@monitor_blueprint.route("/api/monitoring/disarm", methods=["PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def disarm():
    return process_ipc_response(IPCClient().disarm(request.environ["requester_id"]))


@monitor_blueprint.route("/api/monitoring/state", methods=["GET"])
@registered
@restrict_host
def get_state():
    return process_ipc_response(IPCClient().get_state())
