from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from zigpy.zcl.clusters.security import IasZone, ZoneStatus, ZoneType

from monitor.adapters.zigbee import ZigbeeAdapter
from utils.zigbee import (
    IAS_TAMPER_CAPABILITY,
    IAS_ZONE_CAPABILITY,
    decode_zone_status,
    encode_capability,
    normalize_attribute_value,
)


@pytest.mark.parametrize(
    ("cluster_id", "attribute_name", "value", "expected"),
    [
        (0x0500, "zone_status", 0, False),
        (0x0500, "zone_status", 1, True),
        (0x0500, "zone_status", 2, True),
        (0x0500, "zone_status", 3, True),
        (0x0500, "zone_status", 4, False),
        (0x0500, "zone_status", 8, False),
        (0x0500, "zone_status", 0xFFFF, True),
        (0x0406, "occupancy", True, True),
        (0x0001, "zone_status", 4, 4),
        (0x0500, "zone_type", 4, 4),
    ],
)
def test_normalize_attribute_value(cluster_id, attribute_name, value, expected):
    assert normalize_attribute_value(cluster_id, attribute_name, value) is expected


@pytest.mark.parametrize(
    ("cluster_id", "attribute_id", "capability"),
    [
        (0x0500, 0x0002, "a:0500:0002"),
        (0x0406, 0x0000, "a:0406:0000"),
        (0x0000, 0x0000, "a:0000:0000"),
        (0xFFFF, 0xFFFF, "a:ffff:ffff"),
    ],
)
def test_encode_capability(cluster_id, attribute_id, capability):
    assert encode_capability(cluster_id, attribute_id) == capability


@pytest.mark.parametrize(
    ("cluster_id", "attribute_id"),
    [(-1, 0), (0, -1), (0x10000, 0), (0, 0x10000)],
)
def test_encode_out_of_range_ids(cluster_id, attribute_id):
    with pytest.raises(ValueError, match="between 0 and 65535"):
        encode_capability(cluster_id, attribute_id)


@pytest.mark.parametrize(
    ("status", "alarm", "tamper", "error"),
    [
        (0, False, False, None),
        (ZoneStatus.Alarm_1, True, False, None),
        (ZoneStatus.Alarm_2, True, False, None),
        (ZoneStatus.Tamper, False, True, None),
        (ZoneStatus.Trouble, False, False, "ias_zone_trouble"),
        (ZoneStatus.Battery, False, False, None),
        (ZoneStatus.Alarm_1 | ZoneStatus.Trouble, True, False, "ias_zone_trouble"),
        (ZoneStatus.Tamper | ZoneStatus.Trouble, False, True, "ias_zone_trouble"),
        (0xFFFF, True, True, "ias_zone_trouble"),
    ],
)
def test_decode_zone_status(status, alarm, tamper, error):
    assert decode_zone_status(status) == (alarm, tamper, error)


def test_tamper_capability():
    assert IAS_TAMPER_CAPABILITY == "a:0500:0002:tamper"
