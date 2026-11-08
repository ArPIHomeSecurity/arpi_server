import pytest
from zigpy.zcl.clusters.security import IasZone, ZoneStatus

from utils.zigbee import (
    IAS_ZONE_STATUS_ATTRIBUTE,
    IasField,
    ZigbeeSignal,
    decode_zigbee_attribute,
    decode_zone_status,
    zigbee_signals,
)


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
    signals = zigbee_signals(IasZone.cluster_id, 1)
    assert [signal.field for signal in signals] == ["alarm", "tamper", "trouble"]
    assert ZigbeeSignal.from_json(signals[0].to_json()) == signals[0]


def test_ias_zone_status_decodes_all_fields():
    decoded = decode_zigbee_attribute(IAS_ZONE_STATUS_ATTRIBUTE, ZoneStatus.Alarm_1)
    assert decoded.values == (
        (IasField.ALARM, True),
        (IasField.TAMPER, False),
        (IasField.TROUBLE, False),
    )
