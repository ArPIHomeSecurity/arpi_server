from flask import jsonify, request
from flask.blueprints import Blueprint
from flask.helpers import make_response


from server.services.base import ConfigChangesNotAllowed, ObjectNotChanged, ObjectNotFound
from server.services.output import OutputService
from utils.constants import ROLE_USER
from utils.models import Output
from server.database import db
from server.decorators import authenticated, registered, restrict_host
from server.ipc import IPCClient
from server.tools import process_ipc_response

output_blueprint = Blueprint("output", __name__)


@output_blueprint.route("/api/outputs/", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_outputs():
    return jsonify([i.serialized for i in db.session.query(Output).all()])


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
        return make_response(
            jsonify({"error": "Configuration changes are not allowed currently"}), 409
        )


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
            data = request.json
            updated_output = output_service.update_output(
                output_id,
                name=data.get("name"),
                description=data.get("description"),
                channel=data.get("channel"),
                trigger_type=data.get("triggerType"),
                area_id=data.get("areaId"),
                delay=data.get("delay"),
                duration=data.get("duration"),
                default_state=data.get("defaultState"),
                enabled=data.get("enabled"),
            )
            return jsonify(updated_output.serialized)
        elif request.method == "DELETE":
            output_service.delete_output(output_id)
            return make_response("Deleted", 204)

        make_response(jsonify({"error": "Method not allowed"}), 405)
    except ConfigChangesNotAllowed:
        return make_response(
            jsonify({"error": "Configuration changes are not allowed currently"}), 409
        )
    except ObjectNotChanged:
        return make_response(jsonify({"info": "No changes made"}), 204)
    except ObjectNotFound:
        return make_response(jsonify({"error": "Output not found"}), 404)


@output_blueprint.route("/api/output/<int:output_id>/activate", methods=["PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def activate_output(output_id):
    db_output = db.session.query(Output).get(output_id)
    if not db_output:
        return make_response(jsonify({"error": "Output not found"}), 404)

    return process_ipc_response(IPCClient().activate_output(output_id))


@output_blueprint.route("/api/output/<int:output_id>/deactivate", methods=["PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def deactivate_output(output_id):
    db_output = db.session.query(Output).get(output_id)
    if not db_output:
        return make_response(jsonify({"error": "Output not found"}), 404)

    return process_ipc_response(IPCClient().deactivate_output(output_id))


@output_blueprint.route("/api/output/reorder", methods=["PUT"])
@registered
@restrict_host
def reorder_outputs():
    """
    Change only the ui_order of the outputs
    """
    for output_data in request.json:
        db.session.query(Output).get(output_data["id"]).update_record(
            ["ui_order"], output_data
        )

    db.session.commit()

    return make_response("", 200)
