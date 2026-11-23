from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ZigbeeEntity:
    """
    Represents a Zigbee entity such as a device or sensor within the Zigbee network,
    encapsulating the state of a specific cluster and attribute.
    """

    entity_id: str
    unique_id: str
    platform: str
    name: str
    device_class: str | None = None
    value: object = None
    available: bool | None = None
    cluster: str | None = None
    attribute: str | None = None
    attributes: Mapping = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Mapping) -> "ZigbeeEntity":
        return cls(
            entity_id=data["entityId"],
            unique_id=data["uniqueId"],
            platform=data["platform"],
            name=data.get("name") or data["entityId"],
            device_class=data.get("deviceClass"),
            value=data.get("value"),
            available=data.get("available"),
            cluster=data.get("cluster"),
            attribute=data.get("attribute"),
            attributes=data.get("attributes") or {},
        )

    def to_json(self) -> dict:
        return {
            "entityId": self.entity_id,
            "uniqueId": self.unique_id,
            "platform": self.platform,
            "name": self.name,
            "cluster": self.cluster,
            "attribute": self.attribute,
            "deviceClass": self.device_class,
            "value": self.value,
            "available": self.available,
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True)
class ZigbeeEntityReading:
    ieee_address: str
    entity_id: str
    value: object
    device_class: str | None = None
    attributes: Mapping = field(default_factory=dict)
    available: bool | None = None
    timestamp: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.ieee_address, self.entity_id)


@dataclass
class ZigbeeDevice:
    ieee_address: str
    network_address: int | None = None
    manufacturer: str | None = None
    model: str | None = None
    name: str | None = None
    last_seen: str | None = None
    battery_level: int | None = None
    signal_quality: int | None = None
    entities: list[ZigbeeEntity] = field(default_factory=list)

    def entities_json(self) -> list[dict]:
        return [entity.to_json() for entity in self.entities]


@dataclass(frozen=True)
class ZigbeeSnapshot:
    readings: tuple[ZigbeeEntityReading, ...]
    devices: tuple[ZigbeeDevice, ...] | None = None
