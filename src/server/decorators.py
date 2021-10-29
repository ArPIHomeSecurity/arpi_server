# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:06:00
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-26 09:43:09
import functools
import json
import logging
import os

from datetime import datetime as dt
from urllib.parse import urlparse
from dateutil.tz import UTC
from flask.globals import request
from flask.json import jsonify
from jose import jwt
import jose

from models import Option
from monitoring.constants import ROLE_ADMIN, ROLE_USER, USER_TOKEN_EXPIRY
from server.database import db


logger = logging.getLogger("server")


def restrict_host(request_handler):
    @functools.wraps(request_handler)
    def _restrict_host(*args, **kws):
        noip_config = db.session.query(Option).filter_by(name="network", section="dyndns").first()
        if noip_config:
            noip_config = json.loads(noip_config.value)

        if noip_config and noip_config.get("restrict_host", False):
            allowed_hostname = noip_config.get("hostname", None)
            actual_hostname = request.environ["HTTP_HOST"].split(":")[0]
            if allowed_hostname and allowed_hostname != actual_hostname:
                logger.warn("Not allowed host (%s) != %s", allowed_hostname, actual_hostname)
                # don't use tuple as a response to avoid exception using multiple decorators
                response = jsonify({"error": "host not allowed"})
                response.status_code = 401
                return response

        return request_handler(*args, **kws)

    return _restrict_host


def registered(request_handler):
    @functools.wraps(request_handler)
    def _registered(*args, **kws):
        auth_header = request.headers.get("Authorization")
        logger.debug("Header: %s", auth_header)
        raw_token = auth_header.split(" ")[1] if auth_header else ""
        if raw_token:
            try:
                token = jwt.decode(raw_token, os.environ.get("SECRET"), algorithms="HS256")
                logger.debug("Token: %s", token)
                return request_handler(*args, **kws)
            except jose.exceptions.JWTError:
                logger.warn("Bad token (%s) from %s", raw_token, request.remote_addr)
                return jsonify({"error": "operation not permitted (wrong token)"}), 403
        else:
            logger.info("Request without authentication info from %s", request.remote_addr)
            return jsonify({"error": "operation not permitted (missing token)"}), 403

    return _registered


def generate_user_token(name, role, origin):
    token = {"name": name, "role": role, "origin": origin, "timestamp": int(dt.now(tz=UTC).timestamp())}

    return jwt.encode(token, os.environ.get("SECRET"), algorithm="HS256")


def authenticated(role=ROLE_ADMIN):
    def _authenticated(request_handler):
        @functools.wraps(request_handler)
        def check_access(*args, **kws):
            auth_header = request.headers.get("Authorization")
            logger.debug("Header: %s", auth_header)
            remote_address = request.environ.get("HTTP_X_REAL_IP", request.remote_addr)
            logger.debug("Input from '%s': '%s'", remote_address, request.json)

            raw_token = auth_header.split(" ")[1] if auth_header else ""
            if raw_token:
                try:
                    token = jwt.decode(raw_token, os.environ.get("SECRET"), algorithms="HS256")
                    logger.debug("Token: %s", token)
                    if int(token.get("timestamp", 0)) < int(dt.now(tz=UTC).timestamp()) - USER_TOKEN_EXPIRY:
                        return jsonify({"error": "token expired"}), 401

                    # HTTP_ORIGIN is not always sent
                    referer = urlparse(request.environ["HTTP_REFERER"])
                    origin = urlparse(token["origin"])

                    if origin.scheme != referer.scheme or origin.netloc != referer.netloc:
                        return jsonify({"error": f"invalid origin {origin} <> {referer}"}), 401

                    if (role == ROLE_USER and token["role"] not in (ROLE_USER, ROLE_ADMIN)) or (
                        role == ROLE_ADMIN and token["role"] not in (ROLE_ADMIN,)
                    ):
                        logger.info(
                            "Operation %s not permitted for user='%s/%s' from %s",
                            request,
                            token["name"],
                            token["role"],
                            token["origin"],
                            remote_address,
                        )
                        return jsonify({"error": "operation not permitted (role)"}), 403

                    response = request_handler(*args, **kws)
                    # generate new user token to extend the user session
                    response.headers["User-Token"] = generate_user_token(
                        token["name"], token["role"], f"{origin.scheme}://{origin.netloc}"
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
