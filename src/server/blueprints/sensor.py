from flask.blueprints import Blueprint
from flask import jsonify, request, current_app
from flask.helpers import make_response
from models import Sensor, SensorType, Zone, Area

from constants import ROLE_USER

from server.database import db
from server.decorators import authenticated, registered, restrict_host
from server.ipc import IPCClient
from server.tools import process_ipc_response

sensor_blueprint = Blueprint("sensor", __name__)


@sensor_blueprint.route("/api/sensors/", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def view_sensors():
    current_app.logger.debug("Request->alerting: %s", request.args.get("alerting"))
    if not request.args.get("alerting"):
        return jsonify(
            [i.serialized for i in db.session.query(Sensor).filter_by(deleted=False).order_by(Sensor.channel.asc())]
        )
    return jsonify([i.serialized for i in db.session.query(Sensor).filter_by(alert=True).all()])


@sensor_blueprint.route("/api/sensors/", methods=["POST"])
@authenticated()
@restrict_host
def create_sensor():
    data = request.json
    zone = db.session.query(Zone).get(request.json["zoneId"])
    area = db.session.query(Area).get(request.json["areaId"])
    sensor_type = db.session.query(SensorType).get(data["typeId"])
    sensor = Sensor(
        channel=data["channel"],
        zone=zone,
        area=area,
        sensor_type=sensor_type,
        description=data["description"],
        enabled=data["enabled"],
    )
    db.session.add(sensor)
    db.session.commit()

    return process_ipc_response(IPCClient().update_configuration())


@sensor_blueprint.route("/api/sensors/reset-references", methods=["PUT"])
@authenticated()
@restrict_host
def sensors_reset_references():
    if request.method == "PUT":
        for sensor in db.session.query(Sensor).all():
            sensor.reference_value = None

        db.session.commit()

        return process_ipc_response(IPCClient().update_configuration())

    return make_response(jsonify({"error": "Unknown action"}), 400)


@sensor_blueprint.route("/api/sensor/<int:sensor_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def sensor(sensor_id):
    if request.method == "GET":
        sensor = db.session.query(Sensor).filter_by(id=sensor_id, deleted=False).first()
        if sensor:
            return jsonify(sensor.serialized)
        return jsonify({"error": "Sensor not found"}), (404)
    elif request.method == "DELETE":
        sensor = db.session.query(Sensor).get(sensor_id)
        sensor.deleted = True
        db.session.commit()
        return process_ipc_response(IPCClient().update_configuration())
    elif request.method == "PUT":
        sensor = db.session.query(Sensor).get(sensor_id)
        if not sensor:
            return jsonify({"error": "Sensor not found"}), (404)

        if not sensor.update(request.json):
            return make_response("", 204)

        db.session.commit()
        return process_ipc_response(IPCClient().update_configuration())

    return make_response(jsonify({"error": "Unknown action"}), 400)


@sensor_blueprint.route("/api/sensortypes")
@authenticated(role=ROLE_USER)
@restrict_host
def sensor_types():
    return jsonify([i.serialized for i in db.session.query(SensorType).all()])


@sensor_blueprint.route("/api/sensor/alert", methods=["GET"])
@registered
@restrict_host
def get_sensor_alert():
    if request.args.get("sensorId"):
        return jsonify(
            db.session.query(Sensor).filter_by(id=request.args.get("sensorId"), enabled=True, alert=True).first() is not None
        )
    else:
        return jsonify(db.session.query(Sensor).filter_by(enabled=True, alert=True).first() is not None)
