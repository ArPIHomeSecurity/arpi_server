import functools
import logging
import os
import re
from datetime import datetime as dt
from os.path import isfile, join

import jose.exceptions
from dateutil.tz import UTC, tzlocal
from flask import Flask, jsonify, request, send_from_directory
from flask.helpers import make_response
from flask_sqlalchemy import SQLAlchemy
from jose import jwt

from monitoring.constants import ROLE_ADMIN, ROLE_USER, USER_TOKEN_EXPIRY
from server.ipc import IPCClient
from server.version import __version__
from tools.clock import Clock

argus_application_folder = os.path.join(
    os.getcwd(), os.environ.get("SERVER_STATIC_FOLDER", "")
)

# app = Flask(__name__, static_folder=argus_application_folder, static_url_path='/')
app = Flask(__name__)
# app.logger.debug("App folder: %s", argus_application_folder)

POSTGRES = {
    "user": os.environ.get("DB_USER", None),
    "pw": os.environ.get("DB_PASSWORD", None),
    "db": os.environ.get("DB_SCHEMA", None),
    "host": os.environ.get("DB_HOST", None),
    "port": os.environ.get("DB_PORT", None),
}
app.config["SQLALCHEMY_DATABASE_URI"] = (
    "postgresql://%(user)s:%(pw)s@%(host)s:%(port)s/%(db)s" % POSTGRES
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.use_reloader = False

# avoid reloading records from database after session commit
db = SQLAlchemy(app, session_options={"expire_on_commit": False})

from models import *


@app.route("/")
def root():
    app.logger.debug("ROOT: return index.html")
    return send_from_directory(argus_application_folder, "index.html")


def registered():
    def _registered(request_handler):
        @functools.wraps(request_handler)
        def check_access(*args, **kws):
            auth_header = request.headers.get("Authorization")
            # app.logger.info("Header: %s", auth_header)
            remote_address = (
                request.remote_addr
                if request.remote_addr != "b''"
                else request.headers.get("X-Real-Ip")
            )
            # app.logger.debug("Input from '%s': '%s'", remote_address, request.json)

            raw_token = auth_header.split(" ")[1] if auth_header else ""
            if raw_token:
                # app.logger.info("Token: %s", token)
                try:
                    token = jwt.decode(raw_token, os.environ.get("SECRET"), algorithms="HS256")
                    return request_handler(*args, **kws)
                except jose.exceptions.JWTError:
                    app.logger.info("Bad token (%s) from %s", raw_token, request.remote_addr)
                    return jsonify({"error": "operation not permitted (wrong token)"}), 403
            else:
                app.logger.info("Request without authentication info from %s", request.remote_addr)
                return jsonify({"error": "operation not permitted (missing token)"}), 403

        return check_access

    return _registered


def generate_user_token(name, role):
    token = {
        "name": name,
        "role": role,
        "timestamp": int(dt.now(tz=UTC).timestamp())
    }

    return jwt.encode(token, os.environ.get("SECRET"), algorithm="HS256")


def authenticated(role=ROLE_ADMIN):
    def _authenticated(request_handler):
        @functools.wraps(request_handler)
        def check_access(*args, **kws):
            auth_header = request.headers.get("Authorization")
            # app.logger.info("Header: %s", auth_header)
            remote_address = (
                request.remote_addr
                if request.remote_addr != "b''"
                else request.headers.get("X-Real-Ip")
            )
            # app.logger.debug("Input from '%s': '%s'", remote_address, request.json)

            raw_token = auth_header.split(" ")[1] if auth_header else ""
            if raw_token:
                # app.logger.info("Token: %s", token)
                try:
                    token = jwt.decode(raw_token, os.environ.get("SECRET"), algorithms="HS256")
                    if int(token["timestamp"]) < int(dt.now(tz=UTC).timestamp()) - USER_TOKEN_EXPIRY:
                        return jsonify({"error": "token expired"}), 401

                    if (role == ROLE_USER and token["role"] not in (ROLE_USER, ROLE_ADMIN)) or \
                       (role == ROLE_ADMIN and token["role"] not in (ROLE_ADMIN,)):
                        app.logger.info(
                            "Operation %s not permitted for user='%s/%s' from %s",
                            request,
                            token["name"],
                            token["role"],
                            remote_address
                        )
                        return jsonify({"error": "operation not permitted (role)"}), 403

                    response = request_handler(*args, **kws)
                    # generate new user token to extend the user session
                    response.headers["User-Token"] = generate_user_token(token["name"], token["role"])
                    return response
                except jose.exceptions.JWTError:
                    app.logger.info("Bad token (%s) from %s", raw_token, request.remote_addr)
                    return jsonify({"error": "operation not permitted (wrong token)"}), 403
            else:
                app.logger.info("Request without authentication info from %s", request.remote_addr)
                return jsonify({"error": "operation not permitted (missing token)"}), 403

        return check_access

    return _authenticated


@app.errorhandler(AssertionError)
def handle_validation_errors(error):
    return jsonify({'error': str(error)}), 400


@app.route("/api/authenticate", methods=["POST"])
def authenticate():
    # app.logger.debug("Authenticating...")
    remote_address = (
        request.remote_addr
        if request.remote_addr != "b''"
        else request.headers.get("X-Real-Ip")
    )
    try:
        device_token = jwt.decode(request.json["device_token"], os.environ.get("SECRET"), algorithms="HS256")
    except jose.exceptions.JWTError:
        app.logger.info("Bad device token (%s) from %s", request.json["device_token"], request.remote_addr)
        return jsonify({"error": "invalid device token"}), 400
    except KeyError:
        app.logger.info("Missing device token from %s", request.remote_addr)
        return jsonify({"error": "missing device token"}), 400

    if device_token["ip"] != remote_address:
        app.logger.warn("User access from not the registered IP: %s != %s", device_token["ip"], remote_address)

    user = User.query.get(device_token["user_id"])
    if user and user.access_code == hash_code(request.json["access_code"]):
        return jsonify({
            "user_token": generate_user_token(user.name, user.role),
        })
    elif not user:
        return jsonify({"error": "invalid user id"}), 400

    return jsonify(False)


@app.route("/api/register_device", methods=["POST"])
def register_device():
    app.logger.debug("Authenticating...")
    # check user credentials and return fake jwt token if valid
    remote_address = (
        request.remote_addr
        if request.remote_addr != "b''"
        else request.headers.get("X-Real-Ip")
    )
    app.logger.debug("Input from '%s': '%s'", remote_address, request.json)
    if request.json["registration_code"]:
        user = User.query.filter_by(registration_code=hash_code(request.json["registration_code"].upper())).first()

        if user:
            if user.registration_expiry and dt.now(tzlocal()) > user.registration_expiry:
                return make_response(jsonify({
                    "error": "Failed to register device",
                    "reason": "Expired registration code"}),
                    400
                )

            user.registration_code = None
            db.session.commit()
            token = {
                "ip": remote_address,
                "user_id": user.id
            }
            return jsonify({
                "device_token": jwt.encode(token, os.environ.get("SECRET"), algorithm="HS256")
            })
        else:
            return make_response(jsonify({
                "error": "Failed to register device",
                "reason": "User not found"}),
                400
            )

    return make_response(jsonify({
        "error": "Failed to register device",
        "reason": "Missing registration code"}),
        400
    )


@app.route("/api/alerts", methods=["GET"])
@authenticated(role=ROLE_USER)
def get_alerts():
    # app.logger.debug("Request: %s", request.args.get('alerting'))
    return jsonify([i.serialize for i in Alert.query.order_by(Alert.start_time.desc())])


@app.route("/api/alert", methods=["GET"])
@registered()
def get_alert():
    alert = (
        Alert.query.filter_by(end_time=None).order_by(Alert.start_time.desc()).first()
    )
    if alert:
        return jsonify(alert.serialize)
    else:
        return jsonify(None)


@app.route("/api/users", methods=["GET", "POST"])
@authenticated()
def users():
    if request.method == "GET":
        return jsonify([i.serialize for i in User.query.order_by(User.role).all()])
    elif request.method == "POST":
        data = request.json
        user = User(name=data["name"], role=data["role"], access_code=data["accessCode"])
        db.session.add(user)
        db.session.commit()

    return jsonify(None)

@app.route("/api/user/<int:user_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
def user(user_id):
    if request.method == "GET":
        user = User.query.get(user_id)
        if user:
            return jsonify(user.serialize)

        return make_response(jsonify({"error": "User not found"}), 404)
    elif request.method == "PUT":
        user = User.query.get(user_id)
        if user:
            if user.update(request.json):
                db.session.commit()
                return jsonify(None)
            else:
                return make_response('', 204)

        return make_response(jsonify({"error": "User not found"}), 404)
    elif request.method == "DELETE":
        user = User.query.get(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()
            return jsonify(None)
        else:
            return make_response(jsonify({"error": "User not found"}), 404)

    return make_response(jsonify({"error": "Unknown action"}), 400)

@app.route("/api/user/<int:user_id>/registration_code", methods=["GET", "DELETE"])
@authenticated()
def registration_code(user_id):
    app.logger.debug("Authenticating...")
    # check user credentials and return fake jwt token if valid
    remote_address = (
        request.remote_addr
        if request.remote_addr != "b''"
        else request.headers.get("X-Real-Ip")
    )
    app.logger.debug("Input from '%s': '%s'", remote_address, request.json)

    if request.method == "GET":
        user = User.query.get(user_id)
        if user:
            if user.registration_code:
                return make_response(jsonify({"error": "Already has registration code"}), 400)

            expiry = int(request.args.get('expiry')) if request.args.get('expiry') else None
            code = user.add_registration_code(expiry=expiry)
            db.session.commit()
            return jsonify({"code": code})

        return make_response(jsonify({"error": "User not found"}), 404)
    elif request.method == "DELETE":
        user = User.query.get(user_id)
        if user:
            user.registration_code = None
            user.registration_expiry = None
            db.session.commit()
            return jsonify(None)
        else:
            return make_response(jsonify({"error": "User not found"}), 404)

    return make_response(jsonify({"error": "Unknown action"}), 400)


@app.route("/api/sensors/", methods=["GET"])
@authenticated(role=ROLE_USER)
def view_sensors():
    # app.logger.debug("Request: %s", request.args.get('alerting'))
    if not request.args.get("alerting"):
        return jsonify(
            [
                i.serialize
                for i in Sensor.query.filter_by(deleted=False).order_by(
                    Sensor.channel.asc()
                )
            ]
        )
    return jsonify([i.serialize for i in Sensor.query.filter_by(alert=True).all()])


@app.route("/api/sensors/", methods=["POST"])
@authenticated()
def create_sensor():
    data = request.json
    zone = Zone.query.get(request.json["zoneId"])
    sensor_type = SensorType.query.get(data["typeId"])
    sensor = Sensor(
        channel=data["channel"],
        zone=zone,
        sensor_type=sensor_type,
        description=data["description"],
    )
    db.session.add(sensor)
    db.session.commit()

    return process_ipc_response(IPCClient().update_configuration())


@app.route("/api/sensors/reset-references", methods=["PUT"])
@authenticated()
def sensors_reset_references():
    if request.method == "PUT":
        for sensor in Sensor.query.all():
            sensor.reference_value = None

        db.session.commit()

        return process_ipc_response(IPCClient().update_configuration())

    return make_response(jsonify({"error": "Unknown action"}), 400)


@app.route("/api/sensor/<int:sensor_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
def sensor(sensor_id):
    if request.method == "GET":
        sensor = Sensor.query.filter_by(id=sensor_id, deleted=False).first()
        if sensor:
            return jsonify(sensor.serialize)
        return jsonify({"error": "Sensor not found"}), (404)
    elif request.method == "DELETE":
        sensor = Sensor.query.get(sensor_id)
        sensor.deleted = True
        db.session.commit()
        return process_ipc_response(IPCClient().update_configuration())
    elif request.method == "PUT":
        sensor = Sensor.query.get(sensor_id)
        if sensor:
            if sensor.update(request.json):
                db.session.commit()
                return process_ipc_response(IPCClient().update_configuration())
            else:
                return make_response('', 204)

        return jsonify({"error": "Sensor not found"}), (404)

    return make_response(jsonify({"error": "Unknown action"}), 400)


@app.route("/api/sensortypes")
@authenticated(role=ROLE_USER)
def sensor_types():
    # app.logger.debug("Request: %s", request.args.get('alerting'))
    return jsonify([i.serialize for i in SensorType.query.all()])


@app.route("/api/sensor/alert", methods=["GET"])
@registered()
def get_sensor_alert():
    if request.args.get("sensorId"):
        return jsonify(
            Sensor.query.filter_by(id=request.args.get("sensorId"), alert=True).first()
            is not None
        )
    else:
        return jsonify(Sensor.query.filter_by(alert=True).first() is not None)


@app.route("/api/zones/", methods=["GET"])
@authenticated(role=ROLE_USER)
def get_zones():
    return jsonify([i.serialize for i in Zone.query.filter_by(deleted=False).all()])


@app.route("/api/zones/", methods=["POST"])
@authenticated()
def create_zone():
    zone = Zone()
    zone.update(request.json)
    if not zone.description:
        zone.description = zone.name
    db.session.add(zone)
    db.session.commit()
    IPCClient().update_configuration()
    return jsonify(zone.serialize)


@app.route("/api/zone/<int:zone_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
def zone(zone_id):
    if request.method == "GET":
        zone = Zone.query.get(zone_id)
        if zone:
            return jsonify(zone.serialize)

        return make_response(jsonify({"error": "Zone not found"}), 404)
    elif request.method == "DELETE":
        zone = Zone.query.get(zone_id)
        if zone:
            zone.deleted = True
            db.session.commit()
            return process_ipc_response(IPCClient().update_configuration())

        return make_response(jsonify({"error": "Zone not found"}), 404)
    elif request.method == "PUT":
        zone = Zone.query.get(zone_id)
        if zone:
            if zone.update(request.json):
                db.session.commit()
                return process_ipc_response(IPCClient().update_configuration())
            else:
                return make_response('', 204)
        else:
            return make_response(jsonify({"error": "Zone not found"}), 404)

    return make_response(jsonify({"error": "Unknown action"}), 400)


@app.route("/api/monitoring/arm", methods=["GET"])
@registered()
def get_arm():
    return process_ipc_response(IPCClient().get_arm())


@app.route("/api/monitoring/arm", methods=["PUT"])
@authenticated(role=ROLE_USER)
def put_arm():
    return process_ipc_response(IPCClient().arm(request.args.get("type")))


@app.route("/api/monitoring/disarm", methods=["PUT"])
@authenticated(role=ROLE_USER)
def disarm():
    return process_ipc_response(IPCClient().disarm())


@app.route("/api/monitoring/state", methods=["GET"])
@registered()
def get_state():
    return process_ipc_response(IPCClient().get_state())


@app.route("/api/config/<string:option>/<string:section>", methods=["GET", "PUT"])
@authenticated()
def option(option, section):
    if request.method == "GET":
        db_option = Option.query.filter_by(name=option, section=section).first()
        if db_option:
            return jsonify(db_option.serialize) if db_option else jsonify(None)

        return make_response(jsonify({"error": "Option not found"}), 404)
    elif request.method == "PUT":
        db_option = Option.query.filter_by(name=option, section=section).first()
        if not db_option:
            # create the new option
            db_option = Option(name=option, section=section, value="")
            db.session.add(db_option)

        # do update
        changed = db_option.update_value(request.json)
        db.session.commit()

        if option == "notifications":
            if changed:
                return process_ipc_response(IPCClient().update_configuration())
        elif db_option.name == "network" and db_option.section == "dyndns":
            if os.environ.get("ARGUS_DEVELOPMENT", "0") == "0":
                return process_ipc_response(IPCClient().update_dyndns())

        return make_response('', 204)

    return make_response(jsonify({"error": "Unknown action"}), 400)


@app.route("/api/version", methods=["GET"])
def version():
    return __version__


@app.route("/api/clock", methods=["GET"])
@authenticated()
def get_clock():
    clock = Clock()
    result = {
        "system": dt.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hw": clock.gettime_hw(),
        "timezone": clock.get_timezone(),
    }

    network = clock.gettime_ntp()
    if network:
        result["network"] = network
    else:
        result["network"] = None

    return jsonify(result)


@app.route("/api/clock", methods=["PUT"])
def set_clock():
    return process_ipc_response(IPCClient().set_clock(request.json))


# disabled (time-sync service and hwclock cron job is running)
# @app.route("/api/clock/sync", methods=["PUT"])
# def sync_clock():
#     ipc_client = IPCClient()
#     ipc_client.sync_clock()

#     return jsonify(True)

@app.route("/api/keypads/", methods=["GET"])
@authenticated(role=ROLE_USER)
def get_keypads():
    #return jsonify([i.serialize for i in Keypad.query.filter_by(deleted=False).all()])
    return jsonify([i.serialize for i in Keypad.query.all()])


@app.route("/api/keypad/<int:keypad_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
def keypad(keypad_id):
    '''
    Limited to handle only one keypad!
    '''
    if request.method == "GET":
        keypad = Keypad.query.first()
        if keypad:
            return jsonify(keypad.serialize)
        
        return make_response(jsonify({"error": "Option not found"}), 404 )
    elif request.method == "DELETE":
        keypad = Keypad.query.get(keypad_id)
        if keypad:
            keypad.deleted = True
            db.session.commit()
            return process_ipc_response(IPCClient().update_keypad())

        return make_response(jsonify({"error": "Option not found"}), 404)
    elif request.method == "PUT":
        keypad = Keypad.query.get(keypad_id)
        if not keypad:
            # create the new keypad
            keypad = Keypad(keypad_type=KeypadType.query.get(request.json["typeId"]))

        if keypad.update(request.json):
            db.session.commit()
            return process_ipc_response(IPCClient().update_keypad())
        else:
            return make_response('', 204)

    return make_response(jsonify({"error": "Unknown action"}), 400)


@app.route("/api/keypadtypes", methods=["GET"])
@authenticated()
def keypadtypes():
    # app.logger.debug("Request: %s", request.args.get('alerting'))
    return jsonify([i.serialize for i in KeypadType.query.all()])


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    # app.logger.debug("Working in: %s", os.environ.get('SERVER_STATIC_FOLDER', ''))
    # app.logger.debug("FALLBACK for path: %s", path)

    # check compression
    compress = os.environ["COMPRESS"].lower() == "true"
    if compress and (path.endswith(".js") or path.endswith(".css")):
        # app.logger.debug("Use compression")
        path += ".gz"
    else:
        compress = False

    # detect language from url path (en|hu)
    languages = os.environ["LANGUAGES"].split(" ")
    result = re.search("(" + "|".join(languages) + ")", path)
    language = result.group(0) if result else ""

    # app.logger.debug("Language: %s from %s", language if language else "No language in URL", languages)
    if language == "en":
        path = path.replace("en/", "")

    # app.logger.debug("FALLBACK for path processed: %s", path)

    # return with file if exists
    # app.logger.debug("Checking for %s", path)
    if isfile(join(argus_application_folder, path)):
        # app.logger.debug("Path exists without language: %s", path)
        response = send_from_directory(argus_application_folder, path)
        if compress:
            response.headers["Content-Encoding"] = "gzip"
        return response
    elif language and isfile(join(argus_application_folder, language, "index.html")):
        # app.logger.debug("Path exists with language: %s",join(language, 'index.html'))
        return send_from_directory(
            join(argus_application_folder, language), "index.html"
        )

    # or return with the index file
    # app.logger.debug("INDEX without language: %s", join(language, 'index.html'))
    return send_from_directory(argus_application_folder, "index.html")


def process_ipc_response(response):
    if response:
        if response['result']:
            return jsonify(response.get('value'))
        else:
            return make_response(jsonify({'message': response['message']}), 500)
    else:
        return make_response(jsonify({'message': 'No response from monitoring service'}), 503)


if __name__ != "__main__":
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
