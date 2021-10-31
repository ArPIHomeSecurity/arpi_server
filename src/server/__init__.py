import logging
from os import environ, path, getcwd

from flask import Flask, jsonify
from flask_migrate import Migrate


from server.blueprints.alert import alert_blueprint
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
app.config["WEBAPP_SOURCE"] = path.join(getcwd(), environ.get("SERVER_STATIC_FOLDER", ""))
app.logger.debug("Web application folder: %s", app.config["WEBAPP_SOURCE"])
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

# avoid reloading records from database after session commit
db.init_app(app)
migrate = Migrate(app, db)

app.register_blueprint(alert_blueprint)
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
