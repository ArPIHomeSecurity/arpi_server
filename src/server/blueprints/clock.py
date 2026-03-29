from flask import request
from flask.blueprints import Blueprint
from flask.json import jsonify

from server.decorators import authenticated, restrict_host
from server.services.clock import ClockService
from server.tools import process_ipc_response


clock_blueprint = Blueprint("clock", __name__)


@clock_blueprint.route("/api/clock", methods=["GET"])
@authenticated()
@restrict_host
def get_clock():
    return jsonify(ClockService().get_clock_info())


@clock_blueprint.route("/api/clock", methods=["PUT"])
@restrict_host
def set_clock():
    return process_ipc_response(ClockService().set_clock(request.json))


# disabled (time-sync service and hwclock cron job is running)
# @clock_blueprint.route("/api/clock/sync", methods=["PUT"])
# def sync_clock():
#     ipc_client = IPCClient()
#     ipc_client.sync_clock()

#     return jsonify(True)
