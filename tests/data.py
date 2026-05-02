from dataclasses import asdict
import json
import logging

from bin.data import SENSOR_TYPES
from monitor.config.models import MQTTConfigInternalPublish
from monitor.database import get_database_session
from utils.constants import ROLE_ADMIN, ROLE_USER
from utils.models import (
    Area,
    ChannelTypes,
    Option,
    Sensor,
    SensorContactTypes,
    SensorEOLCount,
    User,
    Zone,
)

logger = logging.getLogger(__name__)


def create_test_with_v2():
    """
    This configuration is used for testing with V2 board.
    """
    session = get_database_session()
    admin_user = User(id=1, name="Administrator", role=ROLE_ADMIN, access_code="1234")
    admin_user.add_registration_code("ABCD1234")
    session.add_all(
        [admin_user, User(id=2, name="Chuck Norris", role=ROLE_USER, access_code="1111")]
    )
    logger.info(" - Created users")

    z1 = Zone(name="No delay", description="Alert with no delay")
    z2 = Zone(
        name="Tamper",
        disarmed_delay=0,
        away_alert_delay=0,
        stay_alert_delay=0,
        description="Sabotage alert",
    )
    z3 = Zone(
        name="Away/stay delayed",
        away_alert_delay=3,
        stay_alert_delay=3,
        description="Alert delayed when armed AWAY or STAY",
    )
    z4 = Zone(
        name="Stay delayed",
        stay_alert_delay=3,
        description="Alert delayed when armed STAY",
    )
    z5 = Zone(
        name="Stay",
        stay_alert_delay=None,
        description="No alert when armed STAY",
    )
    session.add_all([z1, z2, z3, z4, z5])
    logger.info(" - Created zones")

    session.add_all(SENSOR_TYPES)
    logger.info(" - Created sensor types")

    area = Area(name="House")
    session.add(area)
    logger.info(" - Created area")

    s1 = Sensor(
        channel=0,
        channel_type=ChannelTypes.NORMAL,
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        sensor_type=SENSOR_TYPES[0],
        area=area,
        zone=z3,
        name="Test room",
        description="Test room movement sensor",
        silent_alert=True,
    )
    s2 = Sensor(
        channel=1,
        channel_type=ChannelTypes.NORMAL,
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        sensor_type=SENSOR_TYPES[2],
        area=area,
        zone=z3,
        name="Test room 0",
        description="Test room 0 door sensor",
    )
    s3 = Sensor(
        channel=2,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=SENSOR_TYPES[1],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=z2,
        name="Tamper",
        description="Sabotage wire",
    )
    session.add_all([s1, s2, s3])
    logger.info(" - Created sensors")

    session.add(
        Option(
            name=MQTTConfigInternalPublish.OPTION_NAME,
            section=MQTTConfigInternalPublish.SECTION_NAME,
            value=json.dumps(asdict(
                MQTTConfigInternalPublish(
                    hostname="localhost",
                    port=1883,
                    username="argus_reader",
                    password="",
                    tls_enabled=False,
                    tls_insecure=True,
                )
            )),
        )
    )

    session.commit()
