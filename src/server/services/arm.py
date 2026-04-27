"""
Arm service module to handle arm/disarm event queries.
"""

from datetime import datetime, timedelta

from sqlalchemy import or_

from server.services.base import BaseService
from utils.constants import ARM_DISARM
from utils.models import Arm, Disarm


class ArmService(BaseService):
    """
    Service for querying arm and disarm events.
    """

    def get_arms(
        self,
        has_alert: bool = None,
        user_id: int = None,
        keypad_id: int = None,
        arm_type: str = None,
        start: str = None,
        end: str = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict]:
        """
        Get arm/disarm events with optional filters.

        Returns a list of event dicts, each containing arm, disarm,
        alert and sensorChanges keys as applicable.
        """
        filters = self._build_filters(has_alert, user_id, keypad_id, arm_type, start, end)

        query = (
            self._db_session.query(Disarm)
            .with_entities(Arm, Disarm)
            .outerjoin(Arm, full=True)
            .filter(*filters)
            .order_by(Disarm.time.desc())
            .limit(limit)
            .offset(offset)
        )

        results = []
        for arm, disarm in query.all():
            event = {}
            if arm:
                event["arm"] = arm.serialized
                if arm.alert:
                    event["alert"] = arm.alert.serialized

                sensors_by_timestamp = {}
                for sensor in arm.sensors:
                    ts = sensor.serialized["timestamp"]
                    if ts in sensors_by_timestamp:
                        sensors_by_timestamp[ts].append(sensor.serialized)
                    else:
                        sensors_by_timestamp[ts] = [sensor.serialized]

                event["sensorChanges"] = [
                    {"timestamp": ts, "sensors": sensors}
                    for ts, sensors in sensors_by_timestamp.items()
                ]

            if disarm:
                event["disarm"] = disarm.serialized
                if disarm.alert:
                    event["alert"] = disarm.alert.serialized

            results.append(event)

        return results

    def get_arms_count(
        self,
        has_alert: bool = None,
        user_id: int = None,
        keypad_id: int = None,
        arm_type: str = None,
        start: str = None,
        end: str = None,
    ) -> int:
        """
        Get the count of arm/disarm events matching the given filters.
        """
        filters = self._build_filters(has_alert, user_id, keypad_id, arm_type, start, end)

        return self._db_session.query(Disarm).outerjoin(Arm, full=True).filter(*filters).count()

    def _build_filters(
        self,
        has_alert: bool,
        user_id: int,
        keypad_id: int,
        arm_type: str,
        start: str,
        end: str,
    ) -> list:
        """
        Build the SQLAlchemy filter list from the given parameters.
        """
        filters = []

        if has_alert is True:
            filters.append(Disarm.alert is not None)
        elif has_alert is False:
            filters.append(Disarm.alert is None)

        if user_id is not None:
            filters.append(or_(Disarm.user_id == user_id, Arm.user_id == user_id))

        if keypad_id is not None:
            # TODO: identify keypads
            filters.append(or_(Disarm.keypad_id is not None, Arm.keypad_id is not None))

        if arm_type is not None:
            if arm_type == ARM_DISARM:
                filters.append(Arm.id is None)
            else:
                filters.append(Arm.type == arm_type)

        if start is not None:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            filters.append(or_(Arm.time >= start_dt, Disarm.time >= start_dt))

        if end is not None:
            end_dt = datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)
            filters.append(or_(Arm.time <= end_dt, Disarm.time <= end_dt))

        return filters
