import pytest
from zigpy.zcl.clusters.security import ZoneStatus

from utils.zigbee import IAS_ZONE_STATUS_ATTRIBUTE, decode_zone_status


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


def test_ias_signals_are_distinguished_by_field():
    assert IAS_ZONE_STATUS_ATTRIBUTE.signal_for("alarm").field == "alarm"
    assert IAS_ZONE_STATUS_ATTRIBUTE.signal_for("tamper").field == "tamper"
