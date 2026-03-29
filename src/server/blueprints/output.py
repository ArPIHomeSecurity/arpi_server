from flask import jsonify, request
from flask.blueprints import Blueprint

from server.services.base import ConfigChangesNotAllowed, ObjectNotChanged, ObjectNotFound
from server.services.output import OutputService
from utils.constants import ROLE_USER
from utils.models import Output
from server.database import db
from server.decorators import authenticated, registered, restrict_host
from server.tools import process_ipc_response

output_blueprint = Blueprint("output", __name__)


@output_blueprint.route("/api/outputs/", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_outputs():
    output_service = OutputService(db.session)
    return jsonify([i.serialized for i in output_service.get_outputs()])


@output_blueprint.route("/api/outputs/", methods=["POST"])
@authenticated()
@restrict_host
def create_output():
    """
    Create a new output.
    """
    try:
        output_service = OutputService(db.session)
        data = request.json
        # set attributes name, description, channel, trigger_type, area_id, delay, duration, default_state, enabled
        # we need to do the mapping from camelCase to snake_case here
        output = output_service.create_output(
            name=data["name"],
            description=data["description"],
            channel=data["channel"],
            trigger_type=data["triggerType"],
            area_id=data["areaId"],
            delay=data["delay"],
            duration=data["duration"],
            default_state=data["defaultState"],
            enabled=data["enabled"],
        )
        return jsonify(output.serialized), 201
    except ConfigChangesNotAllowed:
        return jsonify({"error": "Configuration changes are not allowed currently"}), 409


@output_blueprint.route("/api/output/<int:output_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def manage_output(output_id):
    """
    Manage outputs.
    """
    try:
        output_service = OutputService(db.session)
        if request.method == "GET":
            output = output_service.get_output_by_id(output_id)
            return jsonify(output.serialized)
        elif request.method == "PUT":
            updated_output = output_service.update_output(output_id=output_id, **request.json)
            return jsonify(updated_output.serialized)
        elif request.method == "DELETE":
            output_service.delete_output(output_id)
            return jsonify({"message": "Deleted"}), 204

        return jsonify({"error": "Method not allowed"}), 405
    except ConfigChangesNotAllowed:
        return jsonify({"error": "Configuration changes are not allowed currently"}), 409
    except ObjectNotChanged:
        return jsonify({"info": "No changes made"}), 204
    except ObjectNotFound:
        return jsonify({"error": "Output not found"}), 404


@output_blueprint.route("/api/output/<int:output_id>/activate", methods=["PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def activate_output(output_id):
    try:
        output_service = OutputService(db.session)
        return process_ipc_response(output_service.activate_output(output_id))
    except ObjectNotFound:
        return jsonify({"error": "Output not found"}), 404
    except ObjectNotChanged as error:
        return jsonify({"error": str(error)}), 409


@output_blueprint.route("/api/output/<int:output_id>/deactivate", methods=["PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def deactivate_output(output_id):
    try:
        output_service = OutputService(db.session)
        return process_ipc_response(output_service.deactivate_output(output_id))
    except ObjectNotFound:
        return jsonify({"error": "Output not found"}), 404
    except ObjectNotChanged as error:
        return jsonify({"error": str(error)}), 409


@output_blueprint.route("/api/output/reorder", methods=["PUT"])
@registered
@restrict_host
def reorder_outputs():
    """
    Change only the ui_order of the outputs
    """
    for output_data in request.json:
        db.session.query(Output).get(output_data["id"]).update_record(["ui_order"], output_data)

    db.session.commit()

    return ""
