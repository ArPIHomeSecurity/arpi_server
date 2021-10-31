from flask.blueprints import Blueprint
from flask import jsonify
from models import Alert

from monitoring.constants import ROLE_USER
from server.database import db
from server.decorators import authenticated, registered, restrict_host

alert_blueprint = Blueprint("alert", __name__)


@alert_blueprint.route("/api/alerts", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_alerts():
    return jsonify([i.serialize for i in db.session.query(Alert).order_by(Alert.start_time.desc())])


@alert_blueprint.route("/api/alert", methods=["GET"])
@registered
@restrict_host
def get_alert():
    alert = db.session.query(Alert).filter_by(end_time=None).order_by(Alert.start_time.desc()).first()
    if alert:
        return jsonify(alert.serialize)
    else:
        return jsonify(None)
