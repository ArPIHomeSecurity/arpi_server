
import os
from time import sleep
from flask.blueprints import Blueprint
from server.decorators import restrict_host
from server.version import __version__

generic_blueprint = Blueprint("generic", __name__)


@generic_blueprint.route("/api/version", methods=["GET"])
@restrict_host
def version():
    """
    Get the software version.
    """
    return __version__


@generic_blueprint.route("/api/board_version", methods=["GET"])
@restrict_host
def board_version():
    """
    Get the board version.

    The same software version should be able to run on multiple board versions.
    """
    return os.environ["BOARD_VERSION"]
