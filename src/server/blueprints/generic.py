
from flask.blueprints import Blueprint
from server.decorators import restrict_host
from server.version import __version__

generic_blueprint = Blueprint("generic", __name__)


@generic_blueprint.route("/api/version", methods=["GET"])
@restrict_host
def version():
    return __version__
