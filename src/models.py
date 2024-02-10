import enum
import hashlib
import json
import locale
import os
import uuid
from copy import deepcopy
from datetime import date, timedelta, datetime as dt
from re import search
from dateutil.tz.tz import tzlocal
from typing import List

from sqlalchemy import MetaData, Column, Integer, String, Float, Boolean, DateTime, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql.schema import ForeignKey
from sqlalchemy.orm import relationship, backref, Mapped, mapped_column
from sqlalchemy.orm.mapper import validates
from stringcase import camelcase, snakecase

from constants import (
    ALERT_AWAY,
    ALERT_SABOTAGE,
    ALERT_STAY,
    ARM_AWAY,
    ARM_STAY,
    ARM_DISARM,
    ARM_MIXED,
)
from tools.dictionary import merge_dicts, replace_keys


def hash_code(access_code):
    return hashlib.sha256(
        (f"{access_code}:{os.environ.get('SALT')}").encode("utf-8")
    ).hexdigest()


def convert2camel(data):
    """Convert the attribute names of the dictonary to camel case for compatibility with angular"""
    return {camelcase(key): value for key, value in data.items()}


class ArmStates(str, enum.Enum):
    AWAY = ARM_AWAY
    STAY = ARM_STAY
    MIXED = ARM_MIXED
    DISARM = ARM_DISARM

    @staticmethod
    def merge(as1, as2):
        if as1 == as2:
            return as1
        elif as1 != ArmStates.DISARM and as2 != ArmStates.DISARM:
            return ArmStates.MIXED
        elif as1 == ArmStates.DISARM or as2 == ArmStates.DISARM:
            if as1 == ArmStates.DISARM:
                return as2
            elif as2 == ArmStates.DISARM:
                return as1
        else:
            return ArmStates.DISARM


metadata = MetaData()
Base = declarative_base(metadata=metadata)


class BaseModel(Base):
    """Base data model for all objects"""

    __abstract__ = True

    def __init__(self, *args):
        super().__init__(*args)

    def __repr__(self):
        """Define a base way to print models"""
        return f"{self.__class__.__name__}({dict(self.__dict__.items())})"

    def json(self):
        """
        Define a base way to jsonify models, dealing with datetime objects
        """
        return {
            column: value.strftime("%Y-%m-%d") if isinstance(value, date) else value
            for column, value in self.__dict__.items()
        }

    def update_record(self, attributes, data):
        """Update the given attributes of the record (dict) based on a dictionary"""
        record_changed = False
        for key, value in data.items():
            snake_key = snakecase(key)
            if snake_key in attributes and value != getattr(self, snake_key, value):
                setattr(self, snake_key, value)
                record_changed = True
        return record_changed

    def serialize_attributes(self, attributes):
        """Create JSON object with given attributes"""
        serialized = {}
        for attribute in attributes:
            value = getattr(self, attribute, None)
            if isinstance(value, dt):
                value = value.replace(microsecond=0, tzinfo=None).isoformat(sep=" ")
            serialized[attribute] = value

        return serialized


class SensorType(BaseModel):
    """Model for sensor type table"""

    __tablename__ = "sensor_type"

    NAME_LENGTH = 16

    id = Column(Integer, primary_key=True)
    name = Column(String(NAME_LENGTH))
    description = Column(String)

    def __init__(self, id, name, description):
        self.id = id
        self.name = name
        self.description = description

    @property
    def serialized(self):
        return convert2camel(self.serialize_attributes(("id", "name", "description")))

    @validates("name")
    def validates_name(self, key, name):
        assert (
            0 <= len(name) <= SensorType.NAME_LENGTH
        ), f"Incorrect name field length ({len(name)})"
        return name


class Sensor(BaseModel):
    """
    Model for the sensor table

    The disconnected channel value is "-1".
    """

    __tablename__ = "sensor"

    id = Column(Integer, primary_key=True)
    channel = Column(Integer, nullable=True)
    reference_value = Column(Float, nullable=True)
    alert = Column(Boolean, default=False)
    enabled = Column(Boolean, default=True)
    deleted = Column(Boolean, default=False)
    description = Column(String, nullable=False)

    zone_id = Column(Integer, ForeignKey("zone.id"), nullable=False)
    zone = relationship("Zone", back_populates="sensors")

    area_id = Column(Integer, ForeignKey("area.id"), nullable=False)
    area = relationship("Area", back_populates="sensors")

    type_id = Column(Integer, ForeignKey("sensor_type.id"), nullable=False)
    type = relationship("SensorType", backref=backref("sensor_type", lazy="dynamic"))
    alerts = relationship("AlertSensor", back_populates="sensor")

    ui_order = Column(Integer, nullable=True)
    ui_hidden = Column(Boolean, nullable=False, default=False)

    def __init__(
        self, channel, sensor_type, area, zone=None, description=None, enabled=True
    ):
        self.channel = channel
        self.zone = zone
        self.area = area
        self.type = sensor_type
        self.description = description
        self.enabled = enabled
        self.deleted = False

    def update(self, data):
        # reset reference value if channel changed
        if data["channel"] != self.channel:
            self.reference_value = None

        return self.update_record(
            (
                "channel",
                "enabled",
                "description",
                "zone_id",
                "area_id",
                "type_id",
                "ui_hidden",
            ),
            data,
        )

    @property
    def serialized(self):
        return convert2camel(
            self.serialize_attributes(
                (
                    "id",
                    "channel",
                    "alert",
                    "description",
                    "zone_id",
                    "area_id",
                    "type_id",
                    "enabled",
                    "ui_order",
                    "ui_hidden",
                )
            )
        )

    @validates("name")
    def validates_name(self, key, name):
        assert (
            0 <= len(name) <= SensorType.NAME_LENGTH
        ), f"Incorrect name field length ({len(name)})"
        return name

    @validates("channel")
    def validates_channel(self, key, channel):
        assert (
            -1 <= channel <= int(os.environ["INPUT_NUMBER"])
        ), f"Incorrect channel (0..{os.environ['INPUT_NUMBER']})"
        return channel


class Alert(BaseModel):
    """Model for alert table"""

    __tablename__ = "alert"

    id = Column(Integer, primary_key=True)
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    silent = Column(Boolean, nullable=True, default=False)

    sensors = relationship("AlertSensor", back_populates="alert")
    arm: Mapped["Arm"] = relationship(back_populates="alert")
    disarm: Mapped["Disarm"] = relationship(back_populates="alert")

    def __init__(self, arm, start_time, sensors, silent=None, end_time=None):
        self.arm = arm
        self.start_time = start_time
        self.end_time = end_time
        self.sensors = sensors
        self.silent = silent

    @staticmethod
    def get_alert_type(arm_type):
        if arm_type == ARM_AWAY:
            return ALERT_AWAY
        elif arm_type == ARM_STAY:
            return ALERT_STAY
        elif arm_type == ARM_DISARM:
            return ALERT_SABOTAGE

    @property
    def serialized(self):
        locale.setlocale(locale.LC_ALL)
        return convert2camel(
            {
                "id": self.id,
                "alert_type": (
                    Alert.get_alert_type(self.arm.type) if self.arm else ALERT_SABOTAGE
                ),
                "start_time": self.start_time.replace(
                    microsecond=0, tzinfo=None
                ).isoformat(sep=" "),
                "end_time": (
                    self.end_time.replace(microsecond=0, tzinfo=None).isoformat(sep=" ")
                    if self.end_time
                    else None
                ),
                "silent": self.silent,
                "sensors": [alert_sensor.serialized for alert_sensor in self.sensors],
            }
        )


class AlertSensor(BaseModel):
    """
    Storing the state of the sensors when the alert started.
    """

    __tablename__ = "alert_sensor"
    alert_id = Column(Integer, ForeignKey("alert.id"), primary_key=True)
    sensor_id = Column(Integer, ForeignKey("sensor.id"), primary_key=True)
    channel = Column(Integer)
    type_id = Column(Integer, ForeignKey("sensor_type.id"), nullable=False)
    description = Column(String)
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    delay = Column(Integer)

    sensor = relationship("Sensor", back_populates="alerts")
    alert = relationship("Alert", back_populates="sensors")

    def __init__(self, channel, type_id, description, start_time, delay):
        self.channel = channel
        self.type_id = type_id
        self.description = description
        self.start_time = start_time
        self.delay = delay

    @property
    def serialized(self):
        return convert2camel(
            self.serialize_attributes(
                (
                    "sensor_id",
                    "channel",
                    "type_id",
                    "description",
                    "start_time",
                    "end_time",
                    "delay",
                )
            )
        )


class Arm(BaseModel):
    """
    Storing arm events.
    """

    __tablename__ = "arm"
    id = Column(Integer, primary_key=True)
    type = Column(Enum(ArmStates), nullable=False)
    time = Column(DateTime(timezone=True), nullable=False)
    keypad_id = Column(Integer, ForeignKey("keypad.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=True)

    alert_id = Column(Integer, ForeignKey("alert.id"), nullable=True)
    alert: Mapped["Alert"] = relationship(back_populates="arm")
    sensors: Mapped[List["ArmSensor"]] = relationship(back_populates="arm")

    disarm: Mapped["Disarm"] = relationship(back_populates="arm")

    def __init__(self, arm_type, time, user_id=None, keypad_id=None):
        self.type = arm_type
        self.time = time
        self.keypad_id = keypad_id
        self.user_id = user_id

    @property
    def serialized(self):
        response = self.serialize_attributes(("type", "time", "keypad_id", "user_id"))
        return convert2camel(response)


class Disarm(BaseModel):
    """
    Storing disarm events.
    """

    __tablename__ = "disarm"
    id = Column(Integer, primary_key=True)
    time = Column(DateTime(timezone=True))
    keypad_id = Column(Integer, ForeignKey("keypad.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=True)

    alert_id = Column(Integer, ForeignKey("alert.id"), nullable=True)
    alert: Mapped[Alert] = relationship(back_populates="disarm")

    arm_id: Mapped[int] = mapped_column(ForeignKey("arm.id"), nullable=True)
    arm: Mapped[Arm] = relationship(back_populates="disarm")

    def __init__(self, arm_id, time, user_id=None, keypad_id=None):
        self.arm_id = arm_id
        self.time = time
        self.keypad_id = keypad_id
        self.user_id = user_id

    @property
    def serialized(self):
        response = self.serialize_attributes(("time", "keypad_id", "user_id"))
        return convert2camel(response)


class ArmSensor(BaseModel):
    """
    Storing the state of the sensors when an arm is changed.
    """

    __tablename__ = "arm_sensor"
    id = Column(Integer, primary_key=True)
    arm_id = Column(Integer, ForeignKey("arm.id"))
    sensor_id = Column(Integer, ForeignKey("sensor.id"))
    channel = Column(Integer, nullable=False)
    type_id = Column(Integer, ForeignKey("sensor_type.id"), nullable=False)
    description = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True))
    delay = Column(Integer, nullable=True)
    enabled = Column(Boolean, nullable=False)

    sensor = relationship("Sensor")
    arm = relationship("Arm", back_populates="sensors")

    def __init__(
        self,
        arm_id,
        sensor_id,
        channel,
        type_id,
        description,
        timestamp,
        delay,
        enabled,
    ):
        self.arm_id = arm_id
        self.sensor_id = sensor_id
        self.channel = channel
        self.type_id = type_id
        self.description = description
        self.timestamp = timestamp
        self.delay = delay
        self.enabled = enabled

    @classmethod
    def from_sensor(cls, arm: Arm, sensor: Sensor, timestamp: DateTime, delay: Integer):
        return ArmSensor(
            arm_id=arm.id,
            sensor_id=sensor.id,
            channel=sensor.channel,
            type_id=sensor.type_id,
            description=sensor.description,
            timestamp=timestamp,
            delay=delay,
            enabled=sensor.enabled,
        )

    @property
    def serialized(self):
        return convert2camel(
            self.serialize_attributes(
                (
                    "sensor_id",
                    "channel",
                    "type_id",
                    "description",
                    "timestamp",
                    "delay",
                    "enabled",
                )
            )
        )


class Zone(BaseModel):
    """Model for zone table"""

    __tablename__ = "zone"

    NAME_LENGTH = 32

    id = Column(Integer, primary_key=True)
    name = Column(String(NAME_LENGTH), nullable=False)
    description = Column(String, nullable=False)
    disarmed_delay = Column(Integer, default=None, nullable=True)
    away_alert_delay = Column(Integer, default=None, nullable=True)
    stay_alert_delay = Column(Integer, default=None, nullable=True)
    away_arm_delay = Column(Integer, default=None, nullable=True)
    stay_arm_delay = Column(Integer, default=None, nullable=True)
    deleted = Column(Boolean, default=False)

    ui_order = Column(Integer, nullable=True)

    sensors = relationship("Sensor", back_populates="zone")

    def __init__(
        self,
        name="zone",
        disarmed_delay=None,
        away_alert_delay=0,
        stay_alert_delay=0,
        away_arm_delay=0,
        stay_arm_delay=0,
        description="Default zone",
    ):
        self.name = name
        self.description = description
        self.disarmed_delay = disarmed_delay
        self.away_alert_delay = away_alert_delay
        self.stay_alert_delay = stay_alert_delay
        self.away_arm_delay = away_arm_delay
        self.stay_arm_delay = stay_arm_delay

    def update(self, data):
        return self.update_record(
            (
                "name",
                "description",
                "disarmed_delay",
                "away_alert_delay",
                "stay_alert_delay",
                "away_arm_delay",
                "stay_arm_delay",
            ),
            data,
        )

    @property
    def serialized(self):
        return convert2camel(
            self.serialize_attributes(
                (
                    "id",
                    "name",
                    "description",
                    "disarmed_delay",
                    "away_alert_delay",
                    "stay_alert_delay",
                    "away_arm_delay",
                    "stay_arm_delay",
                    "ui_order",
                )
            )
        )

    @validates(
        "disarmed_delay",
        "away_alert_delay",
        "stay_alert_delay",
        "away_arm_delay",
        "stay_arm_delay",
    )
    def validates_away_alert_delay(self, key, delay):
        assert delay and delay >= 0 or not delay, "Delay is positive integer (>= 0)"
        return delay

    @validates("name")
    def validates_name(self, key, name):
        assert (
            0 <= len(name) <= Zone.NAME_LENGTH
        ), f"Incorrect name field length ({len(name)})"
        return name


class Area(BaseModel):
    """Model for area table"""

    __tablename__ = "area"

    NAME_LENGTH = 32

    id = Column(Integer, primary_key=True)
    name = Column(String(NAME_LENGTH), nullable=False)
    arm_state = Column(Enum(ArmStates), nullable=False)
    deleted = Column(Boolean, default=False)

    ui_order = Column(Integer, nullable=True)

    output = relationship("Output", back_populates="area")
    sensors = relationship("Sensor", back_populates="area")

    def __init__(self, name="area"):
        self.name = name
        self.arm_state = ArmStates.DISARM

    @property
    def serialized(self):
        return convert2camel(
            self.serialize_attributes(("id", "name", "arm_state", "ui_order"))
        )

    def update(self, data):
        return self.update_record(("name", "arm_state"), data)


class User(BaseModel):
    """Model for role table"""

    __tablename__ = "user"

    NAME_LENGTH = 32
    EMAIL_LENGTH = 255
    REGISTRATION_CODE_LENGTH = 64

    id = Column(Integer, primary_key=True)
    name = Column(String(NAME_LENGTH), nullable=False)
    email = Column(String(EMAIL_LENGTH), nullable=True)
    role = Column(String(12), nullable=False)
    registration_code = Column(
        String(REGISTRATION_CODE_LENGTH), unique=True, nullable=True
    )
    registration_expiry = Column(DateTime(timezone=True))
    card_registration_expiry = Column(DateTime(timezone=True))
    access_code = Column(String(64), unique=False, nullable=False)
    fourkey_code = Column(String(64), nullable=False)
    cards = relationship("Card")
    comment = Column(String, nullable=True)

    def __init__(self, name, role, access_code, fourkey_code=None):
        self.id = int(str(uuid.uuid1(1000).int)[:8])
        self.name = name
        self.email = ""
        self.role = role
        self.access_code = hash_code(access_code)
        self.fourkey_code = fourkey_code or hash_code(access_code[:4])

    def update(self, data):
        # !!! incoming data has camelCase key/field name format
        fields = ("name", "email", "role", "comment")
        access_code = data.get("accessCode", "")
        if access_code:
            assert (
                len(access_code) >= 4 and len(access_code) <= 12
            ), "Access code length (>=4, <=12)"
            assert access_code.isdigit(), "Access code only number"
            data["accessCode"] = hash_code(access_code)
            if not data.get("fourkeyCode", None):
                data["fourkeyCode"] = hash_code(access_code[:4])
            else:
                assert len(data["fourkeyCode"]) == 4, "Fourkey code length (=4)"
                assert data["fourkeyCode"].isdigit(), "Fourkey code only number"
                data["fourkeyCode"] = hash_code(data["fourkeyCode"])
            fields += (
                "access_code",
                "fourkey_code",
            )

        return self.update_record(fields, data)

    def set_card_registration(self):
        self.update_record(
            ("card_registration_expiry"),
            {"card_registration_expiry": dt.now() + timedelta(seconds=60)},
        )

    def add_registration_code(self, registration_code=None, expiry=None):
        if not registration_code:
            registration_code = str(uuid.uuid4()).upper().split("-")[-1]

        registration_expiry = None
        if expiry is None:
            registration_expiry = None
        else:
            registration_expiry = dt.now(tzlocal()) + timedelta(seconds=expiry)

        if self.update_record(
            ("registration_code", "registration_expiry"),
            {
                "registration_code": hash_code(registration_code),
                "registration_expiry": registration_expiry,
            },
        ):
            return registration_code

    @property
    def serialized(self):
        return convert2camel(
            {
                "id": self.id,
                "name": self.name,
                "email": self.email,
                "has_registration_code": bool(self.registration_code),
                "has_card": bool(self.cards),
                "registration_expiry": (
                    self.registration_expiry.strftime("%Y-%m-%dT%H:%M:%S")
                    if self.registration_expiry
                    else None
                ),
                "role": self.role,
                "comment": self.comment,
            }
        )

    @validates("name")
    def validates_name(self, key, name):
        assert (
            0 < len(name) <= User.NAME_LENGTH
        ), f"Incorrect user name field length ({len(name)})"
        return name

    @validates("email")
    def validates_email(self, key, email):
        assert (
            0 <= len(email) <= User.EMAIL_LENGTH
        ), f"Incorrect email field length ({len(email)})"
        if len(email):
            email_format = r"^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w{2,3}$"
            assert search(email_format, email), "Invalid email format"
        return email


class Card(BaseModel):

    __tablename__ = "card"

    id = Column(Integer, primary_key=True)
    code = Column(String(64), nullable=False)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    enabled = Column(Boolean, default=True)
    description = Column(String, nullable=True)

    def __init__(self, card, owner_id, description=None):
        self.id = int(str(uuid.uuid1(1000).int)[:8])
        self.code = hash_code(card)
        self.user_id = owner_id
        self.description = description or self.generate_card_description()
        self.enabled = True

    @staticmethod
    def generate_card_description():
        """Example: 2021-10-30_08:15_284"""
        return f"{dt.now().isoformat().replace('T', '_')[:16]}_{str(uuid.uuid1(1000).int)[:3]}"

    def update(self, data):
        fields = ("enabled", "description")
        return self.update_record(fields, data)

    @property
    def serialized(self):
        return convert2camel(
            {
                "id": self.id,
                "user_id": self.user_id,
                "description": self.description,
                "enabled": self.enabled,
            }
        )


class Option(BaseModel):
    """Model for option table"""

    __tablename__ = "option"

    OPTION_LENGTH = 32

    id = Column(Integer, primary_key=True)
    name = Column(String(OPTION_LENGTH), nullable=False)
    section = Column(String(OPTION_LENGTH), nullable=False)
    value = Column(String)

    def __init__(self, name, section, value):
        self.name = name
        self.section = section
        self.value = value

    def update_value(self, value):
        """Update the value field (merging dictionaries). Return true if value changed"""
        if not self.value:
            self.value = json.dumps(value)
            return True
        else:
            tmp_value = json.loads(self.value)
            merge_dicts(tmp_value, value)
            tmp_value = json.dumps(tmp_value)
            changed = self.value != tmp_value
            self.value = tmp_value
            return changed

    @property
    def serialized(self):
        filtered_value = deepcopy(json.loads(self.value))
        replace_keys(
            filtered_value, {"smtp_password": "******", "replace_empty": False}
        )
        replace_keys(filtered_value, {"password": "******", "replace_empty": False})
        return convert2camel(
            {"name": self.name, "section": self.section, "value": filtered_value}
        )

    @validates("name", "section")
    def validates_name(self, key, value):
        assert (
            0 < len(value) <= Option.OPTION_LENGTH
        ), f"Incorrect name field length ({len(value)})"
        if key == "name":
            assert value in (
                "notifications",
                "network",
                "syren",
            ), f"Unknown option ({value})"
        elif key == "section":
            assert value in (
                "smtp",
                "gsm",
                "subscriptions",
                "dyndns",
                "access",
            ), f"Unknown section ({value})"
        return value


class Keypad(BaseModel):
    """Model for keypad table"""

    __tablename__ = "keypad"

    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, default=True)

    type_id = Column(Integer, ForeignKey("keypad_type.id"), nullable=False)
    type = relationship("KeypadType", backref=backref("keypad_type", lazy="dynamic"))

    def __init__(self, keypad_type, enabled=True):
        self.type = keypad_type
        self.enabled = enabled

    def update(self, data):
        return self.update_record(("enabled", "type_id"), data)

    @property
    def serialized(self):
        return convert2camel(self.serialize_attributes(("id", "type_id", "enabled")))


class KeypadType(BaseModel):
    """Model for keypad type table"""

    __tablename__ = "keypad_type"

    id = Column(Integer, primary_key=True)
    name = Column(String(32))
    description = Column(String)

    def __init__(self, id, name, description):
        self.id = id
        self.name = name
        self.description = description

    @property
    def serialized(self):
        return convert2camel(self.serialize_attributes(("id", "name", "description")))


class OutputTriggerType(str, enum.Enum):
    """
    Output trigger type
    """

    AREA = "area"
    SYSTEM = "system"
    BUTTON = "button"


class Output(BaseModel):
    """Model for output table"""

    __tablename__ = "output"

    id = Column(Integer, primary_key=True)
    name = Column(String(16), nullable=True)
    description = Column(String, nullable=True)
    channel = Column(Integer, default=None, nullable=True)
    state = Column(Boolean, default=False, nullable=False)
    trigger_type = Column(
        Enum(
            OutputTriggerType.AREA.value,
            OutputTriggerType.SYSTEM.value,
            OutputTriggerType.BUTTON.value,
            name="output_trigger_type",
        ),
        nullable=False,
    )
    area_id = Column(Integer, ForeignKey("area.id"), nullable=True)
    delay = Column(Integer, default=0)
    duration = Column(Integer, default=0, nullable=False)
    default_state = Column(Boolean, default=False)
    ui_order = Column(Integer, nullable=True)
    enabled = Column(Boolean, default=True)

    area = relationship("Area", back_populates="output")

    def __init__(
        self,
        name,
        description,
        channel,
        trigger_type,
        area_id,
        delay,
        duration,
        default_state,
        enabled,
    ):
        self.name = name
        self.description = description
        self.channel = channel
        self.trigger_type = trigger_type
        self.area_id = area_id
        self.delay = delay
        self.duration = duration
        self.default_state = default_state
        self.enabled = enabled

    def update(self, data):
        return self.update_record(
            (
                "name",
                "description",
                "channel",
                "state",
                "trigger_type",
                "area_id",
                "delay",
                "duration",
                "default_state",
                "enabled",
                "ui_order",
            ),
            data,
        )

    @property
    def serialized(self):
        return convert2camel(
            self.serialize_attributes(
                (
                    "id",
                    "name",
                    "description",
                    "channel",
                    "state",
                    "trigger_type",
                    "area_id",
                    "delay",
                    "duration",
                    "default_state",
                    "enabled",
                    "ui_order",
                )
            )
        )

    @validates("channel")
    def validates_channel(self, key, channel):
        if channel is not None:
            assert (
                0 <= channel <= int(os.environ["OUTPUT_NUMBER"])
            ), f"Incorrect channel (0..{os.environ['OUTPUT_NUMBER']})"
        return channel

    @validates("duration")
    def validates_duration(self, key, duration):
        assert duration >= -1, "Duration must be >= -1"
        return duration
