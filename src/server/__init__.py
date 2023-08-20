import logging
from os import environ

from flask import Flask, jsonify
from flask_migrate import Migrate


from server.blueprints.alert import alert_blueprint
from server.blueprints.area import area_blueprint
from server.blueprints.arm import arm_blueprint
from server.blueprints.card import card_blueprint
from server.blueprints.clock import clock_blueprint
from server.blueprints.config import config_blueprint
from server.blueprints.generic import generic_blueprint
from server.blueprints.keypad import keypad_blueprint
from server.blueprints.monitor import monitor_blueprint
from server.blueprints.power import power_blueprint
from server.blueprints.sensor import sensor_blueprint
from server.blueprints.user import user_blueprint
from server.blueprints.zone import zone_blueprint
from server.database import db


app = Flask(__name__)

# enable CORS if necessary (in development)
if environ.get("FLASK_CORS", 'False').lower() in ('true', '1'):
    from flask_cors import CORS
    CORS(app, expose_headers=["User-Token"])

app.logger.debug("App name: %s", __name__)

if __name__ != "server":
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://%(user)s:%(pw)s@%(host)s:%(port)s/%(db)s" % {
    "user": environ.get("DB_USER", None),
    "pw": environ.get("DB_PASSWORD", None),
    "db": environ.get("DB_SCHEMA", None),
    "host": environ.get("DB_HOST", None),
    "port": environ.get("DB_PORT", None),
}

app.logger.debug("App config: %s", app.config)

# avoid reloading records from database after session commit
db.init_app(app)
migrate = Migrate(app, db)

app.register_blueprint(alert_blueprint)
app.register_blueprint(arm_blueprint)
app.register_blueprint(area_blueprint)
app.register_blueprint(card_blueprint)
app.register_blueprint(clock_blueprint)
app.register_blueprint(config_blueprint)
app.register_blueprint(generic_blueprint)
app.register_blueprint(keypad_blueprint)
app.register_blueprint(monitor_blueprint)
app.register_blueprint(power_blueprint)
app.register_blueprint(sensor_blueprint)
app.register_blueprint(user_blueprint)
app.register_blueprint(zone_blueprint)


@app.errorhandler(AssertionError)
def handle_validation_errors(error):
    return jsonify({"error": str(error)}), 400


@app.errorhandler(404)
def invalid_route(e):
    return "Invalid route", 404


@app.errorhandler(Exception)
def all_exception_handler(error):
    app.logger.exception(error)
    return (str(error), 500) if app.debug else ('Error: internal error', 500)
