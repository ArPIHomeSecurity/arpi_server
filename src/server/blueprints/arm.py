from datetime import datetime, timedelta

from flask.blueprints import Blueprint
from flask import jsonify, request, current_app
from sqlalchemy import or_
from sqlalchemy.dialects import postgresql

from utils.constants import ROLE_USER, ARM_DISARM
from utils.models import Arm, Disarm
from server.database import db
from server.decorators import authenticated, restrict_host

arm_blueprint = Blueprint("arm", __name__)

@arm_blueprint.route("/api/arms", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_arms():
    # TODO: add on going sabotage event
    # on going sabotage event only has an alert without arm or disarm
    filters = []
    if request.args.get("has_alert") == "true":
        filters.append(Disarm.alert != None)
    if request.args.get("has_alert") == "false":
        filters.append(Disarm.alert == None)

    if request.args.get("user_id"):
        user_id = request.args.get("user_id")
        filters.append(or_(Disarm.user_id == user_id, Arm.user_id == user_id))
    if request.args.get("keypad_id"):
        # TODO: identify keypads
        filters.append(or_(Disarm.keypad_id != None, Arm.keypad_id != None))

    if request.args.get("arm_type"):
        arm_type = request.args.get("arm_type")
        if arm_type == ARM_DISARM:
            filters.append(Arm.id == None)
        else:
            filters.append(Arm.type == request.args.get("arm_type"))

    if request.args.get("start"):
        start = request.args.get("start")
        filters.append(
            or_(Arm.time >= datetime.strptime(start, "%Y-%m-%d"),
                Disarm.time >= datetime.strptime(start, "%Y-%m-%d"))
        )
    if request.args.get("end"):
        end = request.args.get("end")
        filters.append(
            or_(Arm.time <= datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1),
                Disarm.time <= datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1))
        )

    query_events = (
        db.session.query(Disarm)
        .with_entities(Arm, Disarm)
        .outerjoin(Arm, full=True)
        .filter(*filters)
        .order_by(Disarm.time.desc())
        .limit(request.args.get("limit", 10))
        .offset(request.args.get("offset", 0))
    )

    current_app.logger.info("Query: %s", 
                            str(query_events.statement.compile(
                            dialect=postgresql.dialect(),
                            compile_kwargs={"literal_binds": True})))

    results = []
    for i in query_events.all():
        # current_app.logger.info("DB events: %s", str(i))
        event = {}
        if i[0]:
            event["arm"] = i[0].serialized
            if i[0].alert:
                event["alert"] = i[0].alert.serialized
            
            sensors_by_timestamp = {}
            for sensor in i[0].sensors:
                if sensor.serialized["timestamp"] in sensors_by_timestamp:
                    sensors_by_timestamp[sensor.serialized["timestamp"]].append(sensor.serialized)
                else:
                    sensors_by_timestamp[sensor.serialized["timestamp"]] = [sensor.serialized]

            event["sensorChanges"] = []
            for timestamp, sensors in sensors_by_timestamp.items():
                event["sensorChanges"].append({
                    "timestamp": timestamp,
                    "sensors": sensors
                })

        if i[1]:
            event["disarm"] = i[1].serialized
            if i[1].alert:
                event["alert"] = i[1].alert.serialized

        results.append(event)

    return jsonify(results)


@arm_blueprint.route("/api/arms/count", methods=["GET"])
@authenticated(role=ROLE_USER)
@restrict_host
def get_arms_count():
    filters = []
    if request.args.get("has_alert") == "true":
        filters.append(Disarm.alert != None)
    if request.args.get("has_alert") == "false":
        filters.append(Disarm.alert == None)

    if request.args.get("user_id"):
        user_id = request.args.get("user_id")
        filters.append(or_(Disarm.user_id == user_id, Arm.user_id == user_id))
    if request.args.get("keypad_id"):
        # TODO: identify keypads
        filters.append(or_(Disarm.keypad_id != None, Arm.keypad_id != None))

    if request.args.get("arm_type"):
        arm_type = request.args.get("arm_type")
        if arm_type == ARM_DISARM:
            filters.append(Arm.id == None)
        else:
            filters.append(Arm.type == request.args.get("arm_type"))

    if request.args.get("start"):
        start = request.args.get("start")
        filters.append(
            or_(Arm.time >= datetime.strptime(start, "%Y-%m-%d"),
                Disarm.time >= datetime.strptime(start, "%Y-%m-%d"))
        )
    if request.args.get("end"):
        end = request.args.get("end")
        filters.append(
            or_(Arm.time <= datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1),
                Disarm.time <= datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1))
        )

    return jsonify(db.session.query(Disarm)
                   .outerjoin(Arm, full=True)
                   .filter(*filters).count()
    )
