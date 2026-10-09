from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import OnOff, PollControl, PowerConfiguration
from zigpy.zcl.clusters.measurement import OccupancySensing
from zigpy.zcl.clusters.security import IasZone, ZoneStatus


class ZigbeeValueDecoder(StrEnum):
    IAS_ZONE_STATUS = "ias_zone_status"
    BATTERY_PERCENTAGE = "battery_percentage"
    ZONE_TYPE = "zone_type"


@dataclass(frozen=True)
class ZigbeeSignalDefinition:
    field: str | None = None


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
    # the signals that this attribute can produce, or an empty tuple if none
    signals: tuple[ZigbeeSignalDefinition, ...] = ()
    # the commands that this attribute can produce, or an empty tuple if none 
    commands: tuple[Any, ...] = ()

    @property
    def attribute_id(self) -> int:
        return int(self.attribute.id)

    def signal_for(self, field: str) -> ZigbeeSignalDefinition:
        for signal in self.signals:
            if signal.field == field:
                return signal
        raise KeyError(f"No signal for field {field!r}")


@dataclass(frozen=True)
class ZigbeeDecodedValue:
    signals: tuple[tuple[ZigbeeSignalDefinition, object], ...] = ()
    device_state: tuple[str, object] | None = None


IAS_ZONE_STATUS_ATTRIBUTE = ZigbeeAttributeDefinition(
    cluster=IasZone,
    attribute=IasZone.AttributeDefs.zone_status,
    decoder=ZigbeeValueDecoder.IAS_ZONE_STATUS,
    reporting=(60, 600),
    signals=(
        ZigbeeSignalDefinition("alarm"),
        ZigbeeSignalDefinition("tamper"),
        ZigbeeSignalDefinition("trouble"),
    ),
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
            signals=(ZigbeeSignalDefinition(),),
        ),
    ),
    int(OnOff.cluster_id): (
        ZigbeeAttributeDefinition(
            cluster=OnOff,
            attribute=OnOff.AttributeDefs.on_off,
            reporting=(60, 600),
            signals=(ZigbeeSignalDefinition(),),
        ),
    ),
    int(PollControl.cluster_id): (
        ZigbeeAttributeDefinition(
            cluster=PollControl,
            attribute=PollControl.AttributeDefs.checkin_interval,
            reporting=(60, 600),
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
            return ZigbeeDecodedValue(
                signals=tuple((signal, value) for signal in definition.signals)
            )

        # decode ias zone status bitfield
        case ZigbeeValueDecoder.IAS_ZONE_STATUS:
            alarm, tamper, trouble = decode_zone_status(value)
            decoded_fields = {"alarm": alarm, "tamper": tamper, "trouble": trouble}
            return ZigbeeDecodedValue(
                signals=tuple(
                    (signal, decoded_fields[signal.field])
                    for signal in definition.signals
                    if signal.field in decoded_fields
                )
            )

        # decode battery percentage remaining
        case ZigbeeValueDecoder.BATTERY_PERCENTAGE:
            try:
                battery_level = min(100, int(value) // 2)
            except (TypeError, ValueError):
                return ZigbeeDecodedValue()
            return ZigbeeDecodedValue(device_state=("battery_level", battery_level))

        # decode zone type
        case ZigbeeValueDecoder.ZONE_TYPE:
            if value is None:
                return ZigbeeDecodedValue()
            return ZigbeeDecodedValue(device_state=("zone_type", int(value)))

        # fallback for unknown decoders
        case _:
            return ZigbeeDecodedValue()


def describe_zigbee_signals(cluster, endpoint_id: int) -> list[dict]:
    descriptors = []
    for definition in ZIGBEE_ATTRIBUTE_REGISTRY.get(int(cluster.cluster_id), ()):
        if not definition.signals:
            continue

        attribute = cluster.find_attribute(definition.attribute_id)
        descriptors.extend(
            _describe_attribute_signals(
                definition,
                endpoint_id,
                attribute,
                cluster.ep_attribute or type(cluster).__name__,
            )
        )
    return descriptors


def describe_zigbee_attribute(
    definition: ZigbeeAttributeDefinition, endpoint_id: int
) -> list[dict]:
    return _describe_attribute_signals(
        definition,
        endpoint_id,
        definition.attribute,
        definition.cluster.ep_attribute or definition.cluster.__name__,
    )


def _describe_attribute_signals(
    definition: ZigbeeAttributeDefinition,
    endpoint_id: int,
    attribute,
    cluster_name: str,
) -> list[dict]:
    descriptors = []
    if not definition.signals:
        return descriptors

    sources = []
    if definition.reporting is not None and attribute.access & foundation.ZCLAttributeAccess.Report:
        sources.append("attribute")
    sources.extend(f"command:{command.name}" for command in definition.commands)
    if not sources:
        return descriptors

    for signal in definition.signals:
        descriptor = {
            "endpoint": str(endpoint_id),
            "cluster": cluster_name,
            "clusterId": int(definition.cluster.cluster_id),
            "attribute": attribute.name,
            "attributeId": int(attribute.id),
            "valueType": getattr(attribute.type, "__name__", str(attribute.type)),
            "sources": sources.copy(),
        }
        if signal.field is not None:
            descriptor["field"] = signal.field
        descriptors.append(descriptor)
    return descriptors


def decode_zone_status(value) -> tuple[bool, bool, bool]:
    status = ZoneStatus(int(value))
    return (
        bool(status & (ZoneStatus.Alarm_1 | ZoneStatus.Alarm_2)),
        bool(status & ZoneStatus.Tamper),
        bool(status & ZoneStatus.Trouble),
    )
