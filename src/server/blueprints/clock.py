from datetime import datetime as dt

from flask import request
from flask.blueprints import Blueprint
from flask.json import jsonify

from server.decorators import authenticated, restrict_host
from server.ipc import IPCClient
from server.tools import process_ipc_response
from tools.clock import Clock


clock_blueprint = Blueprint("clock", __name__)


@clock_blueprint.route("/api/clock", methods=["GET"])
@authenticated()
@restrict_host
def get_clock():
    clock = Clock()
    result = {
        "timezone": clock.get_timezone(),
        "system": dt.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        "hw": clock.get_time_hw(),
        "network": clock.get_time_ntp(),
        "uptime": clock.get_uptime(),
        "uptime_server": clock.get_service_uptime("argus_server.service"),
        "uptime_monitor": clock.get_service_uptime("argus_monitor.service"),
        "uptime_nginx": clock.get_service_uptime("nginx.service"),
    }

    return jsonify(result)


@clock_blueprint.route("/api/clock", methods=["PUT"])
@restrict_host
def set_clock():
    return process_ipc_response(IPCClient().set_clock(request.json))


# disabled (time-sync service and hwclock cron job is running)
# @clock_blueprint.route("/api/clock/sync", methods=["PUT"])
# def sync_clock():
#     ipc_client = IPCClient()
#     ipc_client.sync_clock()

#     return jsonify(True)
