import hashlib
import json
import os
from dataclasses import asdict

from flask import Response, jsonify, request
from flask.blueprints import Blueprint

from monitor.config.models import (
    AlertSensitivityConfig,
    DyndnsConfig,
    GSMConfig,
    MQTTConfigExternalPublish,
    MQTTConfigInternalPublish,
    MQTTConfigInternalRead,
    MQTTConnection,
    SMTPConfig,
    SSHConfig,
    SubscriptionsConfig,
    SyrenConfig,
)
from server.database import db
from server.decorators import authenticated, restrict_host
from server.ipc import IPCClient
from server.services.base import TestingNotAllowed
from server.services.option import (
    AlertSensitivityService,
    DyndnsService,
    GSMService,
    MQTTService,
    SMTPService,
    SSHService,
    SubscriptionsService,
    SyrenService,
)
from server.tools import process_ipc_response
from tools.certbot import Certbot
from utils.models import Option

config_blueprint = Blueprint("configuration", __name__)


@config_blueprint.route("/api/config/<string:option_name>/<string:section>", methods=["GET"])
@authenticated()
@restrict_host
def option_get(option_name, section) -> Response:
    value = None
    if option_name == SyrenConfig.OPTION_NAME and section == SyrenConfig.SECTION_NAME:
        value = asdict(SyrenService(db.session).get_syren_config())
    elif (
        option_name == AlertSensitivityConfig.OPTION_NAME
        and section == AlertSensitivityConfig.SECTION_NAME
    ):
        value = asdict(AlertSensitivityService(db.session).get_alert_sensitivity_config())
    elif option_name == SMTPConfig.OPTION_NAME and section == SMTPConfig.SECTION_NAME:
        value = asdict(SMTPService(db.session).get_smtp_config())
    elif (
        option_name == SubscriptionsConfig.OPTION_NAME
        and section == SubscriptionsConfig.SECTION_NAME
    ):
        value = asdict(SubscriptionsService(db.session).get_subscriptions_config())
    elif option_name == GSMConfig.OPTION_NAME and section == GSMConfig.SECTION_NAME:
        value = asdict(GSMService(db.session).get_gsm_config())
    elif option_name == SSHConfig.OPTION_NAME and section == SSHConfig.SECTION_NAME:
        value = asdict(SSHService(db.session).get_ssh_config())
    elif option_name == MQTTConnection.OPTION_NAME and section == MQTTConnection.SECTION_NAME:
        value = asdict(MQTTService(db.session).get_connection_config())
    elif (
        option_name == MQTTConfigExternalPublish.OPTION_NAME
        and section == MQTTConfigExternalPublish.SECTION_NAME
    ):
        value = asdict(MQTTService(db.session).get_external_publish_config())
    elif (
        option_name == MQTTConfigInternalPublish.OPTION_NAME
        and section == MQTTConfigInternalPublish.SECTION_NAME
    ):
        value = asdict(MQTTService(db.session).get_connection_config())
    elif (
        option_name == MQTTConfigInternalRead.OPTION_NAME
        and section == MQTTConfigInternalRead.SECTION_NAME
    ):
        value = asdict(MQTTService(db.session).get_internal_read_config())
    elif option_name == DyndnsConfig.OPTION_NAME and section == DyndnsConfig.SECTION_NAME:
        value = asdict(DyndnsService(db.session).get_dyndns_config())

    if value is not None:
        return jsonify(
            {
                "name": option_name,
                "section": section,
                "value": value,
            }
        )

    db_option = db.session.query(Option).filter_by(name=option_name, section=section).first()
    return jsonify(db_option.serialized) if db_option else jsonify(None), 404


@config_blueprint.route("/api/config/<string:option_name>/<string:section>", methods=["PUT"])
@authenticated()
@restrict_host
def option_put(option_name, section) -> Response:
    # handle syren configuration separately
    # we will move all the other options to services later
    if option_name == SyrenConfig.OPTION_NAME and section == SyrenConfig.SECTION_NAME:
        syren_service = SyrenService(db.session)
        syren_service.set_syren_config(SyrenConfig(**request.json))
        return ""
    elif (
        option_name == AlertSensitivityConfig.OPTION_NAME
        and section == AlertSensitivityConfig.SECTION_NAME
    ):
        alert_sensitivity_service = AlertSensitivityService(db.session)
        alert_sensitivity_service.set_alert_sensitivity_config(
            AlertSensitivityConfig(**request.json)
        )
        return ""
    elif option_name == SMTPConfig.OPTION_NAME and section == SMTPConfig.SECTION_NAME:
        smtp_service = SMTPService(db.session)
        smtp_service.set_smtp_config(SMTPConfig(**request.json))
        return ""
    elif (
        option_name == SubscriptionsConfig.OPTION_NAME
        and section == SubscriptionsConfig.SECTION_NAME
    ):
        subscriptions_service = SubscriptionsService(db.session)
        subscriptions_service.set_subscriptions_config(SubscriptionsConfig(**request.json))
        return ""
    elif option_name == GSMConfig.OPTION_NAME and section == GSMConfig.SECTION_NAME:
        gsm_service = GSMService(db.session)
        gsm_service.set_gsm_config(GSMConfig(**request.json))
        return ""
    elif option_name == SSHConfig.OPTION_NAME and section == SSHConfig.SECTION_NAME:
        ssh_service = SSHService(db.session)
        ssh_service.set_ssh_config(SSHConfig(**request.json))
        return ""
    elif option_name == MQTTConnection.OPTION_NAME and section == MQTTConnection.SECTION_NAME:
        mqtt_service = MQTTService(db.session)
        mqtt_service.set_connection_config(MQTTConnection(**request.json))
        return ""
    elif (
        option_name == MQTTConfigExternalPublish.OPTION_NAME
        and section == MQTTConfigExternalPublish.SECTION_NAME
    ):
        mqtt_service = MQTTService(db.session)
        mqtt_service.set_external_publish_config(MQTTConfigExternalPublish(**request.json))
        return ""
    elif option_name == DyndnsConfig.OPTION_NAME and section == DyndnsConfig.SECTION_NAME:
        dyndns_service = DyndnsService(db.session)
        dyndns_service.set_dyndns_config(DyndnsConfig(**request.json))
        return ""

    # handle other options
    db_option = db.session.query(Option).filter_by(name=option_name, section=section).first()
    if not db_option:
        # create the new option
        db_option = Option(name=option_name, section=section, value="")
        db.session.add(db_option)

    # do update
    changed = db_option.update_value(request.json)
    db.session.commit()

    if option_name == "notifications":
        if changed:
            return process_ipc_response(IPCClient().update_configuration())
    return ""


@config_blueprint.route("/api/config/test_email", methods=["GET"])
@authenticated()
@restrict_host
def test_email():
    try:
        smtp_service = SMTPService(db.session)
        return process_ipc_response(smtp_service.test_email())
    except TestingNotAllowed:
        return jsonify({"result": False, "message": "Testing is not allowed currently."}), 403


@config_blueprint.route("/api/config/test_sms", methods=["GET"])
@authenticated()
@restrict_host
def test_sms():
    try:
        gsm_service = GSMService(db.session)
        return process_ipc_response(gsm_service.test_sms())
    except TestingNotAllowed:
        return jsonify({"result": False, "message": "Testing is not allowed currently."}), 403


@config_blueprint.route("/api/config/test_call", methods=["GET"])
@authenticated()
@restrict_host
def test_call():
    try:
        gsm_service = GSMService(db.session)
        return process_ipc_response(gsm_service.test_call())
    except TestingNotAllowed:
        return jsonify({"result": False, "message": "Testing is not allowed currently."}), 403


@config_blueprint.route("/api/config/test_syren", methods=["GET"])
@authenticated()
@restrict_host
def test_syren():
    try:
        option_service = SyrenService(db.session)
        return process_ipc_response(option_service.test_syren(duration=5))
    except TestingNotAllowed:
        return jsonify({"result": False, "message": "Testing is not allowed currently."}), 403


@config_blueprint.route("/api/config/sms", methods=["GET"])
@authenticated()
@restrict_host
def get_sms_messages():
    if request.method == "GET":
        # get sms messages without using process_ipc_response
        # to be able to return a list of messages instead of a dictionary
        messages = IPCClient().get_sms_messages()
        if messages:
            return jsonify(messages["value"])

        return jsonify(None)

    return jsonify({"result": False, "message": "Something went wrong"}), 500


@config_blueprint.route("/api/config/sms/<int:message_id>", methods=["DELETE"])
@authenticated()
@restrict_host
def delete_sms_messages(message_id):
    if request.method == "DELETE":
        return process_ipc_response(IPCClient().delete_sms_message(message_id))

    return jsonify({"result": False, "message": "Something went wrong"}), 500


@config_blueprint.route("/api/config/public_access", methods=["GET"])
@authenticated()
@restrict_host
def public_access():
    """
    Check if the public access is possible.
    * dyndns is configured
    * certificate exists
    * nginx listens on port 443
    """
    if Certbot().check_certificate_exists():
        return jsonify(True)

    return jsonify(False)


@config_blueprint.route("/api/config/installation", methods=["GET"])
def get_installation():
    dyndns = db.session.query(Option).filter_by(name="network", section="dyndns").first()

    if dyndns:
        dyndns = json.loads(dyndns.value)

        # TODO: find out if use localhost or arpi.local
        return jsonify(
            {
                "primaryDomain": dyndns.get("hostname", "localhost") or "localhost",
                "secondaryDomain": "localhost",
            }
        )


@config_blueprint.route("/api/config/installation_id", methods=["GET"])
def get_installation_id():
    """
    Get the installation id which identifies the installation by a hash.

    The hash is from:
    * SECRET
    """
    secret = os.environ["SECRET"]
    return hashlib.sha256(f"{secret}".encode()).hexdigest()
