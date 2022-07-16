from genericpath import isfile
import os
from posixpath import join
import re

from flask import current_app
from flask.blueprints import Blueprint
from flask.helpers import send_from_directory

from server.decorators import restrict_host
from server.version import __version__


generic_blueprint = Blueprint("generic", __name__)


@generic_blueprint.route("/")
def root():
    current_app.logger.debug("ROOT: return index.html")
    return send_from_directory(current_app.config["WEBAPP_SOURCE"], "index.html")


@generic_blueprint.route("/api/version", methods=["GET"])
@restrict_host
def version():
    return __version__


@generic_blueprint.route("/", defaults={"path": ""})
@generic_blueprint.route("/<path:path>")
def catch_all(path):
    current_app.logger.debug("Working in: %s", os.environ.get("SERVER_STATIC_FOLDER", ""))
    current_app.logger.debug("FALLBACK for path: %s", path)

    # check compression
    compress = os.environ["COMPRESS"].lower() == "true"
    if compress and (path.endswith(".js") or path.endswith(".css")):
        current_app.logger.debug("Use compression")
        path += ".gz"
    else:
        compress = False

    # detect language from url path (en|hu)
    languages = os.environ["LANGUAGES"].split(" ")
    result = re.search("(" + "|".join(languages) + ")", path)
    language = result[0] if result else ""

    current_app.logger.debug("Language: %s from %s", language or "No language in URL", languages)

    if language == "en":
        path = path.replace("en/", "")

    current_app.logger.debug("FALLBACK for path processed: %s", path)

    # return with file if exists
    current_app.logger.debug("Checking for %s", path)
    if isfile(join(current_app.config["WEBAPP_SOURCE"], path)):
        current_app.logger.debug("Path exists without language: %s", path)
        response = send_from_directory(current_app.config["WEBAPP_SOURCE"], path)
        if compress:
            response.headers["Content-Encoding"] = "gzip"
        return response
    elif language and isfile(join(current_app.config["WEBAPP_SOURCE"], language, "index.html")):
        current_app.logger.debug("Path exists with language: %s", join(language, "index.html"))
        return send_from_directory(join(current_app.config["WEBAPP_SOURCE"], language), "index.html")

    # or return with the index file
    current_app.logger.debug("INDEX without language: %s", join(language, "index.html"))
    return send_from_directory(current_app.config["WEBAPP_SOURCE"], "index.html")
