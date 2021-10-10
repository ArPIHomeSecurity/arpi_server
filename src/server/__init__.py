# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:05:40
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:05:42
import logging
import os
import re
from datetime import datetime as dt
from os.path import isfile, join

import jose.exceptions
from dateutil.tz import tzlocal
from flask import Flask, jsonify, request, send_from_directory
from flask.helpers import make_response
from flask_migrate import Migrate
from jose import jwt

from models import Alert, Keypad, KeypadType, Option, Sensor, SensorType, User, Zone, hash_code
from monitoring.constants import ROLE_USER
from server.blueprints.power import power
from server.database import db
from server.decorators import authenticated, generate_user_token, registered, restrict_host
from server.ipc import IPCClient
from server.tools import process_ipc_response
from server.version import __version__
from tools.clock import Clock

argus_application_folder = os.path.join(os.getcwd(), os.environ.get("SERVER_STATIC_FOLDER", ""))

app = Flask(__name__)
app.register_blueprint(power)

if __name__ != "server":
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

app.logger.debug("App folder: %s", argus_application_folder)

POSTGRES = {
    "user": os.environ.get("DB_USER", None),
    "pw": os.environ.get("DB_PASSWORD", None),
    "db": os.environ.get("DB_SCHEMA", None),
    "host": os.environ.get("DB_HOST", None),
    "port": os.environ.get("DB_PORT", None),
}
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://%(user)s:%(pw)s@%(host)s:%(port)s/%(db)s" % POSTGRES
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.use_reloader = False

# avoid reloading records from database after session commit
db.init_app(app)
migrate = Migrate(app, db)


@app.route("/")
def root():
    app.logger.debug("ROOT: return index.html")
    return send_from_directory(argus_application_folder, "index.html")


@app.errorhandler(AssertionError)
def handle_validation_errors(error):
    return jsonify({"error": str(error)}), 400


@app.route("/api/authenticate", methods=["POST"])
@restrict_host
def authenticate():
    app.logger.debug("Authenticating...")
    try:
        device_token = jwt.decode(request.json["device_token"], os.environ.get("SECRET"), algorithms="HS256")
    except jose.exceptions.JWTError:
        app.logger.info("Bad device token (%s) from %s", request.json["device_token"], request.remote_addr)
        return jsonify({"error": "invalid device token"}), 400
    except KeyError:
        app.logger.info("Missing device token from %s", request.remote_addr)
        return jsonify({"error": "missing device token"}), 400

    # TODO: the client IP can change for mobile devices!?
    remote_address = request.environ.get("HTTP_X_REAL_IP", request.remote_addr)
    if device_token["ip"] != remote_address:
        app.logger.warn("User access from not the registered IP: %s != %s", device_token["ip"], remote_address)

    if device_token["origin"] != request.environ["HTTP_ORIGIN"]:
        app.logger.warn(
            "User access from not the registered origin: %s != %s", device_token["ip"], request.environ["HTTP_ORIGIN"]
        )
        return jsonify({"error": "invalid origin"}), 400

    user = db.session.query(User).get(device_token["user_id"])
    if user and user.access_code == hash_code(request.json["access_code"]):
        return jsonify(
            {
                "user_token": generate_user_token(user.name, user.role, request.environ["HTTP_ORIGIN"]),
            }
        )
    elif not user:
        return jsonify({"error": "invalid user id"}), 400

    return jsonify(False)


@app.route("/api/register_device", methods=["POST"])
@restrict_host
def register_device():
    app.logger.debug("Authenticating...")

    remote_address = request.environ.get("HTTP_X_REAL_IP", request.remote_addr)
    app.logger.debug("Input from '%s' on '%s': '%s'", remote_address, request.environ["HTTP_ORIGIN"], request.json)
    if request.json["registration_code"]:
        user = (
            db.session.query(User)
            .filter_by(registration_code=hash_code(request.json["registration_code"].upper()))
            .first()
        )

        if user:
            if user.registration_expiry and dt.now(tzlocal()) > user.registration_expiry:
                return make_response(
                    jsonify({"error": "Failed to register device", "reason": "Expired registration code"}), 400
                )

            user.registration_code = None
            db.session.commit()
            token = {"ip": remote_address, "origin": request.environ["HTTP_ORIGIN"], "user_id": user.id}
            return jsonify({"device_token": jwt.encode(token, os.environ.get("SECRET"), algorithm="HS256")})
        else:
            return make_response(jsonify({"error": "Failed to register device", "reason": "User not found"}), 400)

    return make_response(jsonify({"error": "Failed to register device", "reason": "Missing registration code"}), 400)


@app.route("/api/alerts", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_alerts():
    return jsonify([i.serialize for i in db.session.query(Alert).order_by(Alert.start_time.desc())])


@app.route("/api/alert", methods=["GET"])
@registered
@restrict_host
def get_alert():
    alert = db.session.query(Alert).filter_by(end_time=None).order_by(Alert.start_time.desc()).first()
    if alert:
        return jsonify(alert.serialize)
    else:
        return jsonify(None)


@app.route("/api/users", methods=["GET", "POST"])
@authenticated()
@restrict_host
def users():
    if request.method == "GET":
        return jsonify([i.serialize for i in db.session.query(User).order_by(User.role).all()])
    elif request.method == "POST":
        data = request.json
        user = User(name=data["name"], role=data["role"], access_code=data["accessCode"])
        db.session.add(user)
        db.session.commit()

    return jsonify(None)


@app.route("/api/user/<int:user_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def user(user_id):
    if request.method == "GET":
        user = db.session.query(User).get(user_id)
        if user:
            return jsonify(user.serialize)

        return make_response(jsonify({"error": "User not found"}), 404)
    elif request.method == "PUT":
        user = db.session.query(User).get(user_id)
        if user:
            if user.update(request.json):
                db.session.commit()
                return jsonify(None)
            else:
                return make_response("", 204)

        return make_response(jsonify({"error": "User not found"}), 404)
    elif request.method == "DELETE":
        user = db.session.query(User).get(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()
            return jsonify(None)
        else:
            return make_response(jsonify({"error": "User not found"}), 404)

    return make_response(jsonify({"error": "Unknown action"}), 400)


@app.route("/api/user/<int:user_id>/registration_code", methods=["GET", "DELETE"])
@authenticated()
@restrict_host
def registration_code(user_id):
    app.logger.debug("Authenticating...")
    # check user credentials and return fake jwt token if valid
    remote_address = request.environ.get("HTTP_X_REAL_IP", request.remote_addr)
    app.logger.debug(
        "Input from '%s' on '%s': '%s'", remote_address, request.environ.get("HTTP_ORIGIN", ""), request.json
    )

    if request.method == "GET":
        user = db.session.query(User).get(user_id)
        if user:
            if user.registration_code:
                return make_response(jsonify({"error": "Already has registration code"}), 400)

            expiry = int(request.args.get("expiry")) if request.args.get("expiry") else None
            code = user.add_registration_code(expiry=expiry)
            db.session.commit()
            return jsonify({"code": code})

        return make_response(jsonify({"error": "User not found"}), 404)
    elif request.method == "DELETE":
        user = db.session.query(User).get(user_id)
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
@restrict_host
def view_sensors():
    app.logger.debug("Request->alerting: %s", request.args.get("alerting"))
    if not request.args.get("alerting"):
        return jsonify(
            [i.serialize for i in db.session.query(Sensor).filter_by(deleted=False).order_by(Sensor.channel.asc())]
        )
    return jsonify([i.serialize for i in db.session.query(Sensor).filter_by(alert=True).all()])


@app.route("/api/sensors/", methods=["POST"])
@authenticated()
@restrict_host
def create_sensor():
    data = request.json
    zone = db.session.query(Zone).get(request.json["zoneId"])
    sensor_type = db.session.query(SensorType).get(data["typeId"])
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
@restrict_host
def sensors_reset_references():
    if request.method == "PUT":
        for sensor in db.session.query(Sensor).all():
            sensor.reference_value = None

        db.session.commit()

        return process_ipc_response(IPCClient().update_configuration())

    return make_response(jsonify({"error": "Unknown action"}), 400)


@app.route("/api/sensor/<int:sensor_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def sensor(sensor_id):
    if request.method == "GET":
        sensor = db.session.query(Sensor).filter_by(id=sensor_id, deleted=False).first()
        if sensor:
            return jsonify(sensor.serialize)
        return jsonify({"error": "Sensor not found"}), (404)
    elif request.method == "DELETE":
        sensor = db.session.query(Sensor).get(sensor_id)
        sensor.deleted = True
        db.session.commit()
        return process_ipc_response(IPCClient().update_configuration())
    elif request.method == "PUT":
        sensor = db.session.query(Sensor).get(sensor_id)
        if sensor:
            if sensor.update(request.json):
                db.session.commit()
                return process_ipc_response(IPCClient().update_configuration())
            else:
                return make_response("", 204)

        return jsonify({"error": "Sensor not found"}), (404)

    return make_response(jsonify({"error": "Unknown action"}), 400)


@app.route("/api/sensortypes")
@authenticated(role=ROLE_USER)
@restrict_host
def sensor_types():
    return jsonify([i.serialize for i in db.session.query(SensorType).all()])


@app.route("/api/sensor/alert", methods=["GET"])
@registered
@restrict_host
def get_sensor_alert():
    if request.args.get("sensorId"):
        return jsonify(
            db.session.query(Sensor).filter_by(id=request.args.get("sensorId"), alert=True).first() is not None
        )
    else:
        return jsonify(db.session.query(Sensor).filter_by(alert=True).first() is not None)


@app.route("/api/zones/", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_zones():
    return jsonify([i.serialize for i in db.session.query(Zone).filter_by(deleted=False).all()])


@app.route("/api/zones/", methods=["POST"])
@authenticated()
@restrict_host
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
@restrict_host
def zone(zone_id):
    if request.method == "GET":
        zone = db.session.query(Zone).get(zone_id)
        if zone:
            return jsonify(zone.serialize)

        return make_response(jsonify({"error": "Zone not found"}), 404)
    elif request.method == "DELETE":
        zone = db.session.query(Zone).get(zone_id)
        if zone:
            zone.deleted = True
            db.session.commit()
            return process_ipc_response(IPCClient().update_configuration())

        return make_response(jsonify({"error": "Zone not found"}), 404)
    elif request.method == "PUT":
        zone = db.session.query(Zone).get(zone_id)
        if zone:
            if zone.update(request.json):
                db.session.commit()
                return process_ipc_response(IPCClient().update_configuration())
            else:
                return make_response("", 204)
        else:
            return make_response(jsonify({"error": "Zone not found"}), 404)

    return make_response(jsonify({"error": "Unknown action"}), 400)


@app.route("/api/monitoring/arm", methods=["GET"])
@registered
@restrict_host
def get_arm():
    return process_ipc_response(IPCClient().get_arm())


@app.route("/api/monitoring/arm", methods=["PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def put_arm():
    return process_ipc_response(IPCClient().arm(request.args.get("type")))


@app.route("/api/monitoring/disarm", methods=["PUT"])
@authenticated(role=ROLE_USER)
@restrict_host
def disarm():
    return process_ipc_response(IPCClient().disarm())


@app.route("/api/monitoring/state", methods=["GET"])
@registered
@restrict_host
def get_state():
    return process_ipc_response(IPCClient().get_state())


@app.route("/api/config/<string:option>/<string:section>", methods=["GET", "PUT"])
@authenticated()
@restrict_host
def option(option, section):
    if request.method == "GET":
        db_option = db.session.query(Option).filter_by(name=option, section=section).first()
        if db_option:
            return jsonify(db_option.serialize) if db_option else jsonify(None)

        return make_response(jsonify({}), 200)
    elif request.method == "PUT":
        db_option = db.session.query(Option).filter_by(name=option, section=section).first()
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
        elif db_option.name == "network" and db_option.section == "access":
            if os.environ.get("ARGUS_DEVELOPMENT", "0") == "0":
                return process_ipc_response(IPCClient().update_ssh())

        return make_response("", 204)

    return make_response(jsonify({"error": "Unknown action"}), 400)


@app.route("/api/version", methods=["GET"])
@restrict_host
def version():
    return __version__


@app.route("/api/clock", methods=["GET"])
@authenticated()
@restrict_host
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
@restrict_host
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
@restrict_host
def get_keypads():
    # return jsonify([i.serialize for i in db.session.query(Keypad).filter_by(deleted=False).all()])
    return jsonify([i.serialize for i in db.session.query(Keypad).all()])


@app.route("/api/keypad/<int:keypad_id>", methods=["GET", "PUT", "DELETE"])
@authenticated()
@restrict_host
def keypad(keypad_id):
    """
    Limited to handle only one keypad!
    """
    if request.method == "GET":
        keypad = db.session.query(Keypad).first()
        if keypad:
            return jsonify(keypad.serialize)

        return make_response(jsonify({"error": "Option not found"}), 404)
    elif request.method == "DELETE":
        keypad = db.session.query(Keypad).get(keypad_id)
        if keypad:
            keypad.deleted = True
            db.session.commit()
            return process_ipc_response(IPCClient().update_keypad())

        return make_response(jsonify({"error": "Option not found"}), 404)
    elif request.method == "PUT":
        keypad = db.session.query(Keypad).get(keypad_id)
        if not keypad:
            # create the new keypad
            keypad = Keypad(keypad_type=db.session.query(KeypadType).get(request.json["typeId"]))

        if keypad.update(request.json):
            db.session.commit()
            return process_ipc_response(IPCClient().update_keypad())
        else:
            return make_response("", 204)

    return make_response(jsonify({"error": "Unknown action"}), 400)


@app.route("/api/keypadtypes", methods=["GET"])
@authenticated()
@restrict_host
def keypadtypes():
    return jsonify([i.serialize for i in db.session.query(KeypadType).all()])


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
@restrict_host
def catch_all(path):
    app.logger.debug("Working in: %s", os.environ.get("SERVER_STATIC_FOLDER", ""))
    app.logger.debug("FALLBACK for path: %s", path)

    # check compression
    compress = os.environ["COMPRESS"].lower() == "true"
    if compress and (path.endswith(".js") or path.endswith(".css")):
        app.logger.debug("Use compression")
        path += ".gz"
    else:
        compress = False

    # detect language from url path (en|hu)
    languages = os.environ["LANGUAGES"].split(" ")
    result = re.search("(" + "|".join(languages) + ")", path)
    language = result.group(0) if result else ""

    app.logger.debug("Language: %s from %s", language if language else "No language in URL", languages)
    if language == "en":
        path = path.replace("en/", "")

    app.logger.debug("FALLBACK for path processed: %s", path)

    # return with file if exists
    app.logger.debug("Checking for %s", path)
    if isfile(join(argus_application_folder, path)):
        app.logger.debug("Path exists without language: %s", path)
        response = send_from_directory(argus_application_folder, path)
        if compress:
            response.headers["Content-Encoding"] = "gzip"
        return response
    elif language and isfile(join(argus_application_folder, language, "index.html")):
        app.logger.debug("Path exists with language: %s", join(language, "index.html"))
        return send_from_directory(join(argus_application_folder, language), "index.html")

    # or return with the index file
    app.logger.debug("INDEX without language: %s", join(language, "index.html"))
    return send_from_directory(argus_application_folder, "index.html")
