from flask import jsonify
from flask.blueprints import Blueprint
from sqlalchemy import select

from server.database import db
from server.decorators import authenticated, registered, restrict_host
from utils.constants import ROLE_USER
from utils.models import Alert

alert_blueprint = Blueprint("alert", __name__)


@alert_blueprint.route("/api/alerts", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_alerts():
    return jsonify(
        [i.serialized for i in db.session.scalars(select(Alert).order_by(Alert.start_time.desc()))]
    )


@alert_blueprint.route("/api/alert", methods=["GET"])
@registered
@restrict_host
def get_alert():
    alert = db.session.scalar(
        select(Alert).where(Alert.end_time.is_(None)).order_by(Alert.start_time.desc())
    )
    return jsonify(alert.serialized) if alert else jsonify(None)
