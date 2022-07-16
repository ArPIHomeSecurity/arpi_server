import functools
import json
import logging
import os

from datetime import datetime as dt
from urllib.parse import urlparse
from dateutil.tz import UTC
import flask
from flask.globals import request
from flask.json import jsonify
from jose import jwt
import jose

from models import Option
from constants import ROLE_ADMIN, ROLE_USER, USER_TOKEN_EXPIRY
from server.database import db


logger = logging.getLogger("server")


def baseurl(parsed_url):
    return f"{parsed_url.scheme}://{parsed_url.netloc}:{parsed_url.port}"


def restrict_host(request_handler):
    """
    Allow connections only for the same web application
    example.com <==> localhost
    Configurable option in the networking section.
    """
    @functools.wraps(request_handler)
    def _restrict_host(*args, **kws):
        noip_config = db.session.query(Option).filter_by(name="network", section="dyndns").first()
        if noip_config:
            noip_config = json.loads(noip_config.value)

        if noip_config and noip_config.get("restrict_host", False):
            auth_header = request.headers.get("Authorization")
            raw_token = auth_header.split(" ")[1] if auth_header else ""
            try:
                token = jwt.decode(raw_token, os.environ.get("SECRET"), algorithms="HS256")
            except jose.exceptions.JWTError:
                token = {}

            # HTTP_ORIGIN is not always sent
            referer = urlparse(request.environ.get("HTTP_REFERER", ""))
            origin = noip_config.get("hostname", "")
            if origin != "":
                logger.debug("Origin -> Referer: '%s' -> '%s'", origin.geturl(), referer.geturl())
                if origin.netloc != referer.netloc:
                    return jsonify({
                        "error": "invalid origin",
                        "reason": f"{origin.netloc} <> {referer.netloc}"
                    }), 401
            else:
                origin = urlparse(token.get("origin", ""))
                logger.debug("Origin -> Referer: '%s' -> '%s'", origin.geturl(), referer.geturl())
                if origin.scheme != referer.scheme or origin.netloc != referer.netloc or origin.port != referer.port:
                    return jsonify({
                        "error": "invalid origin",
                        "reason": f"{baseurl(origin)} <> {baseurl(referer)}"
                    }), 401

        return request_handler(*args, **kws)

    return _restrict_host


def registered(request_handler):
    """ Allow access only for registered devices """
    @functools.wraps(request_handler)
    def _registered(*args, **kws):
        auth_header = request.headers.get("Authorization")
        logger.debug("Header: %s", auth_header)
        raw_token = auth_header.split(" ")[1] if auth_header else ""
        if raw_token:
            try:
                device_token = jwt.decode(raw_token, os.environ.get("SECRET"), algorithms="HS256")
                logger.debug("Token: %s", device_token)
                return request_handler(*args, **kws)
            except jose.exceptions.JWTError:
                logger.warn("Bad token (%s) from %s", raw_token, request.remote_addr)
                return jsonify({"error": "invalid device token"}), 403
        else:
            logger.info("Request without authentication info from %s", request.remote_addr)
            return jsonify({"error": "missing device token"}), 403

    return _registered


def generate_user_token(id, name, role, origin):
    token = {"id": id, "name": name, "role": role, "origin": origin, "timestamp": int(dt.now(tz=UTC).timestamp())}

    return jwt.encode(token, os.environ.get("SECRET"), algorithm="HS256")


def authenticated(role=ROLE_ADMIN):
    """ Allow access only for users with given role """
    def _authenticated(request_handler):
        @functools.wraps(request_handler)
        def check_access(*args, **kws):
            auth_header = request.headers.get("Authorization")
            logger.debug("Header: %s", auth_header)
            remote_address = request.environ.get("HTTP_X_REAL_IP", request.remote_addr)
            logger.debug("Request from '%s': '%s'", remote_address, request.get_json(silent=True))

            raw_token = auth_header.split(" ")[1] if auth_header else ""
            if raw_token:
                try:
                    user_token = jwt.decode(raw_token, os.environ.get("SECRET"), algorithms="HS256")
                    logger.debug("Token: %s", user_token)
                    if int(user_token.get("timestamp", 0)) < int(dt.now(tz=UTC).timestamp()) - USER_TOKEN_EXPIRY:
                        return jsonify({"error": "token expired"}), 401

                    if (role == ROLE_USER and user_token["role"] not in (ROLE_USER, ROLE_ADMIN)) or (
                        role == ROLE_ADMIN and user_token["role"] not in (ROLE_ADMIN,)
                    ):
                        logger.info(
                            "Operation %s not permitted for user='%s/%s' from %s",
                            request,
                            user_token["name"],
                            user_token["role"],
                            user_token["origin"],
                            remote_address,
                        )
                        return jsonify({"error": "operation not permitted (role)"}), 403

                    flask.request.environ["requester_id"] = user_token["id"]
                    flask.request.environ["requester_role"] = user_token["role"]
                    response = request_handler(*args, **kws)
                    # generate new user token to extend the user session
                    referer = urlparse(request.environ.get("HTTP_REFERER", ""))
                    response.headers["User-Token"] = generate_user_token(
                        user_token["id"], user_token["name"], user_token["role"], f"{referer.scheme}://{referer.netloc}"
                    )
                    return response
                except jose.exceptions.JWTError:
                    logger.warn("Bad token (%s) from %s", raw_token, remote_address)
                    return jsonify({"error": "operation not permitted (wrong token)"}), 403
            else:
                logger.warn("Request without authentication info from %s", remote_address)
                return jsonify({"error": "operation not permitted (missing token)"}), 403

        return check_access

    return _authenticated
