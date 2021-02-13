"""
Created on 2017. szept. 23.

@author: gkovacs
"""

import json
import logging
import os
import socketio


from flask import Flask
from urllib.parse import parse_qs, urlparse
from jose import jwt
import jose.exceptions

from models import Option, db
from monitoring.constants import LOG_SOCKETIO


noip_config = Option.query.filter_by(name='network', section='dyndns').first()
if noip_config:
    noip_config = json.loads(noip_config.value)

if noip_config and noip_config.get("restrict_host", False) and noip_config.get("hostname", None):
    allowed_origins = f"https://{noip_config['hostname']}"
else:
    allowed_origins = "*"

if len(allowed_origins) == 1:
    allowed_origins = allowed_origins[0]

sio = socketio.Server(
        async_mode="threading",
        cors_allowed_origins=allowed_origins
)
logger = logging.getLogger(LOG_SOCKETIO)
logging.getLogger("werkzeug").setLevel(logging.DEBUG)


def start_socketio():
    logger.info("Server CORS allowed on '%s'", allowed_origins)

    app = Flask(__name__)
    # wrap Flask application with socketio's middleware
    app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)
    app.run(
        threaded=True,
        host=os.environ["MONITOR_HOST"],
        port=int(os.environ["MONITOR_PORT"]),
    )


@sio.on("connect")
def connect(sid, environ):
    logger.debug('Client info "%s": %s', sid, environ)
    query_string = parse_qs(environ["QUERY_STRING"])
    remote_address = environ.get("HTTP_X_REAL_IP", environ.get("REMOTE_ADDR", ""))
    try:
        device_info = jwt.decode(
            query_string["token"][0], os.environ.get("SECRET"), algorithms="HS256"
        )
        logger.info("Connecting with device info: %s", device_info)

        # TODO: the client IP can change for mobile devices!?
        if device_info.get("ip", "") != remote_address:
            logger.info("Authentication failed from IP '%s'!= '%s'", device_info["ip"], remote_address)
            return False

        referer = urlparse(environ["HTTP_REFERER"])
        origin = urlparse(device_info["origin"])
        
        if origin.scheme != referer.scheme or origin.netloc != referer.netloc:
            logger.info("Authentication failed from origin '%s'!= '%s'", origin, referer)
            return False

        logger.info("New connection from '%s' =>'%s'", device_info["ip"], device_info["origin"])
        logger.debug("New connection from '%s': %s =>'%s'", sid, environ, device_info)
    except jose.exceptions.JWTError:
        logger.error("Authentication failed from '%s'! token='%s'", remote_address, query_string["token"][0])
        return False


@sio.on("disconnect")
def disconnect(sid):
    logging.getLogger("SocketIO").info('Disconnected "%s"', sid)


def send_alert_state(arm_state):
    send_message("alert_state_change", arm_state)


def send_arm_state(arm_state):
    send_message("arm_state_change", arm_state)


def send_sensors_state(sensors_state):
    send_message("sensors_state_change", sensors_state)


def send_syren_state(syren_state):
    send_message("syren_state_change", syren_state)


def send_system_state_change(system_state):
    send_message("system_state_change", system_state)


def send_message(message_type, message):
    logging.getLogger("SocketIO").debug(
        "Sending message: %s -> %s", message_type, message
    )
    sio.emit(message_type, message)
