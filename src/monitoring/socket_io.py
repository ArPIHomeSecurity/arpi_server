"""
Created on 2017. szept. 23.

@author: gkovacs
"""

import logging
import os
import socketio


from flask import Flask
from urllib.parse import parse_qs
from jose import jwt
import jose.exceptions

from monitoring.constants import LOG_SOCKETIO


sio = socketio.Server(
        async_mode="threading",
        cors_allowed_origins=os.environ['APPLICATION_URIS'].split(',')
)
logger = logging.getLogger(LOG_SOCKETIO)
logging.getLogger("werkzeug").setLevel(logging.DEBUG)


def start_socketio():
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
    logger.info("Server CORS allowed: %s", os.environ['APPLICATION_URIS'].split(','))
    logger.debug("Client: %s", sid)
    # logger.debug('Client info "%s": %s', sid, environ)
    qs = parse_qs(environ["QUERY_STRING"])
    remote_address = environ["REMOTE_ADDR"]
    try:
        device_info = jwt.decode(
            qs["token"][0], os.environ.get("SECRET"), algorithms="HS256"
        )
        # unfortunately we can't get back the correct remote address
        #         if 'ip' in device_info and device_info['ip'] != remote_address:
        #             logger.info("Authentication failed from '%s'! device info='%s'", remote_address, device_info)
        #             return False
        logger.info("New connection from '%s'", device_info["ip"])
    except jose.exceptions.JWTError:
        logger.error(
            "Authentication failed from '%s'! token='%s'",
            remote_address,
            qs["token"][0],
        )
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
