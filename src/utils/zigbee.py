from zigpy.zcl.clusters.security import IasZone, ZoneStatus


def normalize_attribute_value(cluster_id, attribute_name: str, value) -> object:
    if (
        int(cluster_id) == IasZone.cluster_id
        and attribute_name == IasZone.AttributeDefs.zone_status.name
    ):
        return bool(int(value) & (ZoneStatus.Alarm_1 | ZoneStatus.Alarm_2))

    return value


def encode_capability(cluster_id: int, attribute_id: int) -> str:
    """Encode Zigbee attribute IDs as an a:cccc:aaaa capability."""
    if not (0 <= cluster_id <= 0xFFFF and 0 <= attribute_id <= 0xFFFF):
        raise ValueError("Cluster and attribute IDs must be between 0 and 65535")

    return f"a:{cluster_id:04x}:{attribute_id:04x}"
