from flask import jsonify, request
from flask.blueprints import Blueprint

from server.database import db
from server.decorators import authenticated, restrict_host
from server.services.base import ConfigChangesNotAllowed, ObjectNotChanged, ObjectNotFound
from server.services.zigbee import ZigbeeService

zigbee_blueprint = Blueprint("zigbee", __name__)


@zigbee_blueprint.route("/api/zigbee-devices/", methods=["GET"])
@authenticated()
@restrict_host
def get_zigbee_devices():
    devices = ZigbeeService(db.session).get_devices()
    return jsonify([device.serialized for device in devices])


@zigbee_blueprint.route("/api/zigbee-device/<int:device_id>", methods=["GET"])
@authenticated()
@restrict_host
def get_zigbee_device(device_id):
    try:
        service = ZigbeeService(db.session)
        return jsonify(service.get_device(device_id).serialized)
    except ObjectNotFound:
        return jsonify({"error": "Zigbee device not found"}), 404
    except ObjectNotChanged as error:
        return jsonify({"info": str(error)}), 204
    
@zigbee_blueprint.route("/api/zigbee-device/<int:device_id>", methods=["PUT"])
@authenticated()
@restrict_host
def update_zigbee_device(device_id):
    try:
        service = ZigbeeService(db.session)
        return jsonify(service.update_device(device_id, **request.json).serialized)
    except ConfigChangesNotAllowed:
        return jsonify({"error": "Configuration changes are not allowed currently"}), 409
    except ObjectNotFound:
        return jsonify({"error": "Zigbee device not found"}), 404
    except ObjectNotChanged as error:
        return jsonify({"info": str(error)}), 204


@zigbee_blueprint.route("/api/zigbee-device/<int:device_id>", methods=["DELETE"])
@authenticated()
@restrict_host
def delete_zigbee_device(device_id):
    try:
        service = ZigbeeService(db.session)
        service.delete_device(device_id)
        return jsonify({"message": "Deleted"}), 204
    except ConfigChangesNotAllowed:
        return jsonify({"error": "Configuration changes are not allowed currently"}), 409
    except ObjectNotFound:
        return jsonify({"error": "Zigbee device not found"}), 404
    except ObjectNotChanged as error:
        return jsonify({"info": str(error)}), 204
