from flask import jsonify, request
from flask.blueprints import Blueprint
from flask.helpers import make_response


from constants import ROLE_USER
from models import Output
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
    data = request.json
    # set attributes name, description, channel, trigger_type, area_id, delay, duration, default_state, enabled
    output = Output(
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
    db.session.add(output)
    db.session.commit()

    return process_ipc_response(IPCClient().update_configuration())


@output_blueprint.route("/api/output/<int:output_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def manage_output(output_id):
    if request.method == "GET":
        db_output = db.session.query(Output).filter_by(id=output_id).first()
        if db_output:
            return jsonify(db_output.serialized)
        return jsonify({"error": "Output not found"}), 404
    elif request.method == "PUT":
        db_output = db.session.query(Output).get(output_id)
        if not db_output:
            return jsonify({"error": "Output not found"}), 404

        if not db_output.update(request.json):
            return make_response("", 204)

        db.session.commit()
        return process_ipc_response(IPCClient().update_configuration())
    elif request.method == "DELETE":
        db_output = db.session.query(Output).get(output_id)
        db.session.delete(db_output)
        db.session.commit()
        return process_ipc_response(IPCClient().update_configuration())

    return make_response(jsonify({"error": "Unknown action"}), 400)


@output_blueprint.route("/api/output/<int:output_id>/activate", methods=["PUT"])
@authenticated()
@restrict_host
def activate_output(output_id):
    db_output = db.session.query(Output).get(output_id)
    if not db_output:
        return jsonify({"error": "Output not found"}), 404

    return process_ipc_response(IPCClient().activate_output(output_id))


@output_blueprint.route("/api/output/<int:output_id>/deactivate", methods=["PUT"])
@authenticated()
@restrict_host
def deactivate_output(output_id):
    db_output = db.session.query(Output).get(output_id)
    if not db_output:
        return jsonify({"error": "Output not found"}), 404

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
