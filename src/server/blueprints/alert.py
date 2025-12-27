import logging

from datetime import datetime, timedelta

from flask.blueprints import Blueprint
from flask import jsonify, request, current_app
from sqlalchemy import or_
from sqlalchemy.dialects import postgresql

from utils.constants import ROLE_USER, ARM_DISARM
from utils.models import Alert, Arm, Disarm, ArmSensor
from server.database import db
from server.decorators import authenticated, registered, restrict_host

alert_blueprint = Blueprint("alert", __name__)


@alert_blueprint.route("/api/alerts", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_alerts():
    return jsonify([i.serialized for i in db.session.query(Alert).order_by(Alert.start_time.desc())])


@alert_blueprint.route("/api/alert", methods=["GET"])
@registered
@restrict_host
def get_alert():
    alert = (
        db.session.query(Alert).filter_by(end_time=None).order_by(Alert.start_time.desc()).first()
    )
    return jsonify(alert.serialized) if alert else jsonify(None)
