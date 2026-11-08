import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic
from typing import Any, NamedTuple

from zigpy.zcl.clusters.general import OnOff, PowerConfiguration
from zigpy.zcl.clusters.measurement import OccupancySensing
from zigpy.zcl.clusters.security import IasZone, ZoneStatus


class IasField(StrEnum):
    ALARM = "alarm"
    TAMPER = "tamper"
    TROUBLE = "trouble"


class ZigbeeSignal(NamedTuple):
    """A value an endpoint of a device can report; field selects a part of a bitfield attribute."""

    endpoint: str
    cluster_id: int
    attribute_id: int
    field: str | None = None

    @classmethod
    def create(cls, endpoint, cluster_id, attribute_id, field=None) -> "ZigbeeSignal":
        return cls(
            str(endpoint),
            int(cluster_id),
            int(attribute_id),
            None if field is None else str(field),
        )

    @classmethod
    def from_json(cls, data: Mapping) -> "ZigbeeSignal":
        return cls.create(data["endpoint"], data["clusterId"], data["attributeId"], data.get("field"))

    def to_json(self, zone_type: int | None = None) -> dict:
        definition = find_attribute_definition(self.cluster_id, self.attribute_id)
        data = {
            "endpoint": self.endpoint,
            "cluster": definition.cluster.ep_attribute,
            "clusterId": self.cluster_id,
            "attribute": definition.attribute.name,
            "attributeId": self.attribute_id,
        }
        if self.field is not None:
            data["field"] = self.field
        if zone_type is not None:
            data["zoneType"] = zone_type
        return data


@dataclass(frozen=True)
class ZigbeeReading:
    ieee_address: str
    signal: ZigbeeSignal
    value: object
    timestamp: str | None = None

    @property
    def key(self) -> tuple[str, ZigbeeSignal]:
        return (self.ieee_address, self.signal)


class ZigbeeHealthState(StrEnum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OVERDUE = "overdue"
    OFFLINE = "offline"
    COORDINATOR_UNAVAILABLE = "coordinator_unavailable"


@dataclass(frozen=True)
class ZigbeeDeviceHealth:
    status: ZigbeeHealthState
    deadline: float | None = None

    @property
    def state(self) -> ZigbeeHealthState:
        if (
            self.status == ZigbeeHealthState.ONLINE
            and self.deadline is not None
            and monotonic() >= self.deadline
        ):
            return ZigbeeHealthState.OVERDUE
        return self.status

    @property
    def available(self) -> bool:
        return self.state == ZigbeeHealthState.ONLINE

    @property
    def availability(self) -> str:
        state = self.state
        return (
            state
            if state in (ZigbeeHealthState.UNKNOWN, ZigbeeHealthState.ONLINE)
            else ZigbeeHealthState.OFFLINE
        ).value


@dataclass
class ZigbeeDevice:
    ieee_address: str
    network_address: int | None = None
    manufacturer: str | None = None
    model: str | None = None
    name: str | None = None
    available: bool = True
    last_seen: str | None = None
    battery_level: int | None = None
    signal_quality: int | None = None
    signals: list[ZigbeeSignal] = field(default_factory=list)
    # IAS zone type by endpoint
    zone_types: dict[str, int] = field(default_factory=dict)
    health: ZigbeeDeviceHealth | None = None

    def signals_json(self) -> list[dict]:
        return [
            signal.to_json(
                self.zone_types.get(signal.endpoint)
                if signal.cluster_id == int(IasZone.cluster_id)
                else None
            )
            for signal in self.signals
        ]


@dataclass(frozen=True)
class ZigbeeSnapshot:
    readings: tuple[ZigbeeReading, ...]
    health: Mapping[str, ZigbeeDeviceHealth]
    devices: tuple[ZigbeeDevice, ...] | None = None


class ZigbeeSupervision:
    def __init__(
        self,
        timeout_seconds: int = 1800,
        timeout_overrides: Mapping[str, int] | None = None,
    ):
        self._timeout_seconds = timeout_seconds
        self._timeout_overrides = dict(timeout_overrides or {})
        self._lock = threading.Lock()
        self._last_packets: dict[str, float | None] = {}
        self._offline: set[str] = set()
        self._removed: set[str] = set()

    def register(self, ieee_address: str):
        with self._lock:
            if ieee_address in self._removed:
                self._last_packets[ieee_address] = None
                self._removed.discard(ieee_address)
                self._offline.discard(ieee_address)
            self._last_packets.setdefault(ieee_address, None)

    def record_packet(self, ieee_address: str):
        with self._lock:
            if ieee_address in self._last_packets and ieee_address not in self._removed:
                self._last_packets[ieee_address] = monotonic()
                self._offline.discard(ieee_address)

    def mark_offline(self, ieee_address: str, removed: bool = False):
        with self._lock:
            self._last_packets[ieee_address] = None
            self._offline.add(ieee_address)
            if removed:
                self._removed.add(ieee_address)

    def snapshot(self, running: bool) -> dict[str, ZigbeeDeviceHealth]:
        with self._lock:
            health = {}
            for address, last_packet in self._last_packets.items():
                if not running:
                    health[address] = ZigbeeDeviceHealth(ZigbeeHealthState.COORDINATOR_UNAVAILABLE)
                elif address in self._offline:
                    health[address] = ZigbeeDeviceHealth(ZigbeeHealthState.OFFLINE)
                elif last_packet is None:
                    health[address] = ZigbeeDeviceHealth(ZigbeeHealthState.UNKNOWN)
                else:
                    timeout = self._timeout_overrides.get(address.lower(), self._timeout_seconds)
                    health[address] = ZigbeeDeviceHealth(ZigbeeHealthState.ONLINE, last_packet + timeout)
            return health


class ZigbeeValueDecoder(StrEnum):
    IAS_ZONE_STATUS = "ias_zone_status"
    OCCUPANCY = "occupancy"
    BATTERY_PERCENTAGE = "battery_percentage"
    ZONE_TYPE = "zone_type"


@dataclass(frozen=True)
class ZigbeeAttributeDefinition:
    """
    Defines the characteristics of a Zigbee attribute.
    """

    cluster: Any
    attribute: Any
    # the reporting interval in seconds as a tuple of (min, max) or None if not reportable
    reporting: tuple[int, int] | None = None
    # the decoder to use for this attribute, or None if no decoding is needed
    decoder: ZigbeeValueDecoder | None = None
    # the signal fields this attribute produces; None is the whole attribute value
    fields: tuple[str | None, ...] = ()
    # the commands that this attribute can produce, or an empty tuple if none
    commands: tuple[Any, ...] = ()

    @property
    def attribute_id(self) -> int:
        return int(self.attribute.id)

    def signal(self, endpoint, field: str | None = None) -> ZigbeeSignal:
        return ZigbeeSignal.create(endpoint, self.cluster.cluster_id, self.attribute_id, field)


@dataclass(frozen=True)
class ZigbeeDecodedValue:
    # (signal field, value) pairs
    values: tuple[tuple[str | None, object], ...] = ()
    zone_type: int | None = None
    battery_level: int | None = None


IAS_ZONE_STATUS_ATTRIBUTE = ZigbeeAttributeDefinition(
    cluster=IasZone,
    attribute=IasZone.AttributeDefs.zone_status,
    decoder=ZigbeeValueDecoder.IAS_ZONE_STATUS,
    # zone_status is read-only; changes arrive as status change notifications
    fields=(IasField.ALARM, IasField.TAMPER, IasField.TROUBLE),
    commands=(IasZone.ClientCommandDefs.status_change_notification,),
)

ZIGBEE_ATTRIBUTE_REGISTRY: dict[int, tuple[ZigbeeAttributeDefinition, ...]] = {
    int(IasZone.cluster_id): (
        IAS_ZONE_STATUS_ATTRIBUTE,
        ZigbeeAttributeDefinition(
            cluster=IasZone,
            attribute=IasZone.AttributeDefs.zone_type,
            decoder=ZigbeeValueDecoder.ZONE_TYPE,
        ),
    ),
    int(OccupancySensing.cluster_id): (
        ZigbeeAttributeDefinition(
            cluster=OccupancySensing,
            attribute=OccupancySensing.AttributeDefs.occupancy,
            reporting=(60, 600),
            decoder=ZigbeeValueDecoder.OCCUPANCY,
            fields=(None,),
        ),
    ),
    int(OnOff.cluster_id): (
        ZigbeeAttributeDefinition(
            cluster=OnOff,
            attribute=OnOff.AttributeDefs.on_off,
            reporting=(60, 600),
            fields=(None,),
        ),
    ),
    int(PowerConfiguration.cluster_id): (
        ZigbeeAttributeDefinition(
            cluster=PowerConfiguration,
            attribute=PowerConfiguration.AttributeDefs.battery_percentage_remaining,
            decoder=ZigbeeValueDecoder.BATTERY_PERCENTAGE,
            reporting=(3600, 21600),
        ),
    ),
}


def decode_zigbee_attribute(definition: ZigbeeAttributeDefinition, value) -> ZigbeeDecodedValue:
    match definition.decoder:
        case None:
            # No decoder specified, treat the raw value as the signal value
            return ZigbeeDecodedValue(values=tuple((f, value) for f in definition.fields))

        case ZigbeeValueDecoder.OCCUPANCY:
            occupied = bool(int(value) & 0x01)
            return ZigbeeDecodedValue(values=tuple((f, occupied) for f in definition.fields))

        # decode ias zone status bitfield
        case ZigbeeValueDecoder.IAS_ZONE_STATUS:
            alarm, tamper, trouble = decode_zone_status(value)
            return ZigbeeDecodedValue(
                values=(
                    (IasField.ALARM, alarm),
                    (IasField.TAMPER, tamper),
                    (IasField.TROUBLE, trouble),
                )
            )

        # decode battery percentage remaining
        case ZigbeeValueDecoder.BATTERY_PERCENTAGE:
            try:
                battery_level = min(100, int(value) // 2)
            except (TypeError, ValueError):
                return ZigbeeDecodedValue()
            return ZigbeeDecodedValue(battery_level=battery_level)

        # decode zone type
        case ZigbeeValueDecoder.ZONE_TYPE:
            if value is None:
                return ZigbeeDecodedValue()
            return ZigbeeDecodedValue(zone_type=int(value))

        # fallback for unknown decoders
        case _:
            return ZigbeeDecodedValue()


def find_attribute_definition(cluster_id, attribute_id) -> ZigbeeAttributeDefinition | None:
    return next(
        (
            definition
            for definition in ZIGBEE_ATTRIBUTE_REGISTRY.get(int(cluster_id), ())
            if definition.attribute_id == int(attribute_id)
        ),
        None,
    )


def zigbee_signals(cluster_id, endpoint) -> list[ZigbeeSignal]:
    """The signals a cluster on the given endpoint can report."""
    return [
        definition.signal(endpoint, field)
        for definition in ZIGBEE_ATTRIBUTE_REGISTRY.get(int(cluster_id), ())
        for field in definition.fields
    ]


def decode_zone_status(value) -> tuple[bool, bool, bool]:
    """
    Decode the zone status value into a tuple of booleans representing:
    (alarm, tamper, trouble)
    """
    status = ZoneStatus(int(value))
    return (
        bool(status & (ZoneStatus.Alarm_1 | ZoneStatus.Alarm_2)),
        bool(status & ZoneStatus.Tamper),
        bool(status & ZoneStatus.Trouble),
    )
