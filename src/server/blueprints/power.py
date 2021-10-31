from flask.blueprints import Blueprint
from server.tools import process_ipc_response
from server.decorators import registered
from server.ipc import IPCClient

power_blueprint = Blueprint("power", __name__)


@power_blueprint.route("/api/power", methods=["GET"])
@registered
def power_state():
    return process_ipc_response(IPCClient().get_power_state())
