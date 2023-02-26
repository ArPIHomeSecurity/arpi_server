import logging
import os

from flask import jsonify, request, current_app
from flask.blueprints import Blueprint
from flask.helpers import make_response
from models import Option

from server.decorators import authenticated, restrict_host
from server.database import db
from server.ipc import IPCClient
from server.tools import process_ipc_response


config_blueprint = Blueprint("configuration", __name__)


@config_blueprint.route("/api/config/<string:option>/<string:section>", methods=["GET", "PUT"])
@authenticated()
@restrict_host
def option(option, section):
    if request.method == "GET":
        db_option = db.session.query(Option).filter_by(name=option, section=section).first()
        if db_option:
            return jsonify(db_option.serialize) if db_option else jsonify(None)

        return make_response(jsonify({}), 200)
    elif request.method == "PUT":
        db_option = db.session.query(Option).filter_by(name=option, section=section).first()
        if not db_option:
            # create the new option
            db_option = Option(name=option, section=section, value="")
            db.session.add(db_option)

        # do update
        changed = db_option.update_value(request.json)
        db.session.commit()

        if option == "notifications":
            if changed:
                return process_ipc_response(IPCClient().update_configuration())
        elif db_option.name == "network" and db_option.section == "dyndns":
            if os.environ.get("ARGUS_DEVELOPMENT", "0") == "0":
                return process_ipc_response(IPCClient().update_dyndns())
        elif db_option.name == "network" and db_option.section == "access":
            if os.environ.get("ARGUS_DEVELOPMENT", "0") == "0":
                return process_ipc_response(IPCClient().update_ssh())

        return make_response("", 204)

    return make_response(jsonify({"error": "Unknown action"}), 400)


@config_blueprint.route("/api/config/test_email", methods=["GET"])
@authenticated()
@restrict_host
def test_email():
    if request.method == "GET":
        return process_ipc_response(IPCClient().send_test_email())

    return make_response(jsonify({"result": False, "message": "Something went wrong"}), 500)


@config_blueprint.route("/api/config/test_sms", methods=["GET"])
@authenticated()
@restrict_host
def test_sms():
    if request.method == "GET":
        return process_ipc_response(IPCClient().send_test_sms())

    return make_response(jsonify({"result": False, "message": "Something went wrong"}), 500)
