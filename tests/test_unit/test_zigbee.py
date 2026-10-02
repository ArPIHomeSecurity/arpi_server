import pytest

from utils.zigbee import (
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