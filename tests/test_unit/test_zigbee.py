import pytest
from zigpy.zcl.clusters.security import ZoneStatus

from utils.zigbee import IAS_ZONE_STATUS_ATTRIBUTE, decode_zone_status


@pytest.mark.parametrize(
    ("status", "alarm", "tamper", "trouble"),
    [
        (0, False, False, False),
        (ZoneStatus.Alarm_1, True, False, False),
        (ZoneStatus.Alarm_2, True, False, False),
        (ZoneStatus.Tamper, False, True, False),
        (ZoneStatus.Trouble, False, False, True),
        (ZoneStatus.Battery, False, False, False),
        (ZoneStatus.Alarm_1 | ZoneStatus.Trouble, True, False, True),
        (ZoneStatus.Tamper | ZoneStatus.Trouble, False, True, True),
        (0xFFFF, True, True, True),
    ],
)
def test_decode_zone_status(status, alarm, tamper, trouble):
    assert decode_zone_status(status) == (alarm, tamper, trouble)


def test_ias_signals_are_distinguished_by_field():
    assert IAS_ZONE_STATUS_ATTRIBUTE.signal_for("alarm").field == "alarm"
    assert IAS_ZONE_STATUS_ATTRIBUTE.signal_for("tamper").field == "tamper"
