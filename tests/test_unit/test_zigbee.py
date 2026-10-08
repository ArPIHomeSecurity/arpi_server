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
)


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
    ("status", "alarm", "tamper"),
    [
        (0, False, False),
        (ZoneStatus.Alarm_1, True, False),
        (ZoneStatus.Alarm_2, True, False),
        (ZoneStatus.Tamper, False, True),
        (ZoneStatus.Trouble, False, False),
        (ZoneStatus.Battery, False, False),
        (ZoneStatus.Alarm_1 | ZoneStatus.Trouble, True, False),
        (ZoneStatus.Tamper | ZoneStatus.Trouble, False, True),
        (0xFFFF, True, True),
    ],
)
def test_decode_zone_status(status, alarm, tamper):
    assert decode_zone_status(status) == (alarm, tamper)


def test_tamper_capability():
    assert IAS_TAMPER_CAPABILITY == "a:0500:0002:tamper"
