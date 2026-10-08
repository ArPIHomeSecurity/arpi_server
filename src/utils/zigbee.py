from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import OnOff, PollControl, PowerConfiguration
from zigpy.zcl.clusters.measurement import OccupancySensing
from zigpy.zcl.clusters.security import IasZone, ZoneStatus


def encode_capability(cluster_id: int, attribute_id: int) -> str:
    """Encode Zigbee attribute IDs as an a:cccc:aaaa capability."""
    if not (0 <= cluster_id <= 0xFFFF and 0 <= attribute_id <= 0xFFFF):
        raise ValueError("Cluster and attribute IDs must be between 0 and 65535")

    return f"a:{cluster_id:04x}:{attribute_id:04x}"


IAS_ZONE_CAPABILITY = encode_capability(
    IasZone.cluster_id, IasZone.AttributeDefs.zone_status.id
)
IAS_TAMPER_CAPABILITY = f"{IAS_ZONE_CAPABILITY}:tamper"


class ZigbeeValueDecoder(StrEnum):
    IAS_ZONE_STATUS = "ias_zone_status"
    BATTERY_PERCENTAGE = "battery_percentage"
    ZONE_TYPE = "zone_type"


@dataclass(frozen=True)
class ZigbeeSignalDefinition:
    capability: str
    field: str | None = None


@dataclass(frozen=True)
class ZigbeeAttributeDefinition:
    cluster: Any
    attribute: Any
    reporting: tuple[int, int] | None = None
    decoder: ZigbeeValueDecoder | None = None
    signals: tuple[ZigbeeSignalDefinition, ...] = ()
    commands: tuple[Any, ...] = ()

    @property
    def attribute_id(self) -> int:
        return int(self.attribute.id)


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
        ZigbeeSignalDefinition(IAS_ZONE_CAPABILITY, "alarm"),
        ZigbeeSignalDefinition(IAS_TAMPER_CAPABILITY, "tamper"),
    ),
    commands=(IasZone.ClientCommandDefs.status_change_notification,),
)

ZIGBEE_ATTRIBUTE_REGISTRY = {
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
            signals=(
                ZigbeeSignalDefinition(
                    encode_capability(
                        OccupancySensing.cluster_id,
                        OccupancySensing.AttributeDefs.occupancy.id,
                    )
                ),
            ),
        ),
    ),
    int(OnOff.cluster_id): (
        ZigbeeAttributeDefinition(
            cluster=OnOff,
            attribute=OnOff.AttributeDefs.on_off,
            reporting=(60, 600),
            signals=(
                ZigbeeSignalDefinition(
                    encode_capability(OnOff.cluster_id, OnOff.AttributeDefs.on_off.id)
                ),
            ),
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


def decode_zigbee_attribute(
    definition: ZigbeeAttributeDefinition, value
) -> ZigbeeDecodedValue:
    match definition.decoder:
        case None:
            return ZigbeeDecodedValue(
                signals=tuple((signal, value) for signal in definition.signals)
            )
        case ZigbeeValueDecoder.IAS_ZONE_STATUS:
            alarm, tamper = decode_zone_status(value)
            decoded_fields = {"alarm": alarm, "tamper": tamper}
            return ZigbeeDecodedValue(
                signals=tuple(
                    (signal, decoded_fields[signal.field])
                    for signal in definition.signals
                    if signal.field in decoded_fields
                )
            )
        case ZigbeeValueDecoder.BATTERY_PERCENTAGE:
            try:
                battery_level = min(100, int(value) // 2)
            except (TypeError, ValueError):
                return ZigbeeDecodedValue()
            return ZigbeeDecodedValue(device_state=("battery_level", battery_level))
        case ZigbeeValueDecoder.ZONE_TYPE:
            if value is None:
                return ZigbeeDecodedValue()
            return ZigbeeDecodedValue(device_state=("zone_type", int(value)))
        case _:
            return ZigbeeDecodedValue()


def describe_zigbee_signals(cluster, endpoint_id: int) -> dict[str, dict]:
    descriptors = {}
    for definition in ZIGBEE_ATTRIBUTE_REGISTRY.get(int(cluster.cluster_id), ()):
        if not definition.signals:
            continue

        attribute = cluster.find_attribute(definition.attribute_id)
        descriptors.update(
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
) -> dict[str, dict]:
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
) -> dict[str, dict]:
    descriptors = {}
    if not definition.signals:
        return descriptors

    sources = []
    if (
        definition.reporting is not None
        and attribute.access & foundation.ZCLAttributeAccess.Report
    ):
        sources.append("attribute")
    sources.extend(f"command:{command.name}" for command in definition.commands)
    if not sources:
        return descriptors

    for signal in definition.signals:
        descriptor = {
            "cluster": cluster_name,
            "clusterId": int(definition.cluster.cluster_id),
            "attribute": attribute.name,
            "attributeId": int(attribute.id),
            "valueType": getattr(attribute.type, "__name__", str(attribute.type)),
            "sources": sources.copy(),
        }
        if signal.field is not None:
            descriptor["field"] = signal.field
        descriptors[f"{endpoint_id}/{signal.capability}"] = descriptor
    return descriptors


def decode_zone_status(value) -> tuple[bool, bool]:
    status = ZoneStatus(int(value))
    return (
        bool(status & (ZoneStatus.Alarm_1 | ZoneStatus.Alarm_2)),
        bool(status & ZoneStatus.Tamper),
    )


