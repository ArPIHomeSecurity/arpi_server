from flask import current_app, jsonify, request
from flask.blueprints import Blueprint

from server.database import db
from server.decorators import authenticated, registered, restrict_host
from server.ipc import IPCClient
from server.services.base import ConfigChangesNotAllowed, ObjectNotChanged, ObjectNotFound
from server.services.sensor import ChannelConflictError, SensorService
from server.tools import process_ipc_response
from utils.constants import ROLE_USER
from utils.models import Sensor, SensorType

sensor_blueprint = Blueprint("sensor", __name__)


@sensor_blueprint.route("/api/sensors/", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_sensors():
    """
    Retrieve all or alerting sensors from the database.
    """
    current_app.logger.debug("Request->alerting: %s", request.args.get("alerting"))
    sensors = SensorService(db.session).get_sensors(alerting=request.args.get("alerting") == "true")
    return jsonify([i.serialized for i in sensors])


@sensor_blueprint.route("/api/sensors/", methods=["POST"])
@authenticated()
@restrict_host
def create_sensor():
    """
    Create a new sensor.
    """
    try:
        sensor_service = SensorService(db.session)
        # we need to do the mapping from camelCase to snake_case here
        sensor_data = request.json
        new_sensor = sensor_service.create_sensor(
            name=sensor_data["name"],
            description=sensor_data.get("description"),
            area_id=sensor_data["areaId"],
            zone_id=sensor_data["zoneId"],
            channel=sensor_data["channel"],
            channel_type=sensor_data.get("channelType"),
            enabled=sensor_data["enabled"],
            sensor_contact_type=sensor_data.get("sensorContactType"),
            sensor_eol_count=sensor_data.get("sensorEolCount"),
            sensor_type_id=sensor_data["typeId"],
        )
        return jsonify(new_sensor.serialized), 201
    except ConfigChangesNotAllowed:
        return jsonify({"error": "Configuration changes are not allowed currently"}), 409


@sensor_blueprint.route("/api/sensor/<int:sensor_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def manage_sensor(sensor_id):
    """
    Manage sensors.
    """
    try:
        sensor_service = SensorService(db.session)
        if request.method == "GET":
            sensor = sensor_service.get_sensor(sensor_id)
            return jsonify(sensor.serialized)
        elif request.method == "PUT":
            updated_sensor = sensor_service.update_sensor(sensor_id=sensor_id, **request.json)
            return jsonify(updated_sensor.serialized)
        elif request.method == "DELETE":
            sensor_service.delete_sensor(sensor_id)
            return jsonify({"message": "Deleted"}), 204

        return jsonify({"error": "Method not allowed"}), 405
    except ConfigChangesNotAllowed:
        return jsonify({"error": "Configuration changes are not allowed currently"}), 409
    except ChannelConflictError:
        return jsonify({"error": "Channel conflict with existing sensors"}), 409
    except ObjectNotChanged:
        return jsonify({"info": "No changes made"}), 204
    except ObjectNotFound:
        return jsonify({"error": "Sensor not found"}), 404


@sensor_blueprint.route("/api/sensor/<int:sensor_id>/reset-reference", methods=["PUT"])
@sensor_blueprint.route("/api/sensors/reset-references", methods=["PUT"])
@authenticated()
@restrict_host
def sensors_reset_references(sensor_id=None):
    """
    Reset the reference value of a specific sensor or all sensors.
    
    - If sensor_id is provided, reset the reference value of that specific sensor.
    - If sensor_id is not provided, reset the reference values of all sensors.
    """
    try:
        sensor_service = SensorService(db.session)
        return process_ipc_response(sensor_service.reset_references(sensor_id=sensor_id))
    except ConfigChangesNotAllowed:
        return jsonify({"error": "Configuration changes are not allowed currently"}), 409
    except ObjectNotFound:
        return jsonify({"error": "Sensor not found"}), 404
    except ObjectNotChanged:
        return jsonify({"info": "No changes made"}), 204

@sensor_blueprint.route("/api/sensortypes")
@authenticated(role=ROLE_USER)
@restrict_host
def sensor_types():
    """
    Get all sensor types.
    """
    sensor_service = SensorService(db.session)
    return jsonify([i.serialized for i in sensor_service.get_sensor_types()])


@sensor_blueprint.route("/api/sensor/alert", methods=["GET"])
@registered
@restrict_host
def get_sensor_alert():
    """
    Get the alert status of a specific sensor or all sensors.
    """
    sensor_service = SensorService(db.session)
    return jsonify(sensor_service.get_sensor_alert(sensor_id=request.args.get("sensorId")))


@sensor_blueprint.route("/api/sensor/error", methods=["GET"])
@registered
@restrict_host
def get_sensor_error():
    """
    Get the error status of a specific sensor or all sensors.
    """
    sensor_service = SensorService(db.session)
    return jsonify(sensor_service.get_sensor_error(sensor_id=request.args.get("sensorId")))

@sensor_blueprint.route("/api/sensor/reorder", methods=["PUT"])
@registered
@restrict_host
def reorder_sensors():
    """
    Change only the ui_order of the sensors
    """
    for sensor_data in request.json:
        db.session.query(Sensor).get(sensor_data["id"]).update_record(["ui_order"], sensor_data)

    db.session.commit()

    return ""
