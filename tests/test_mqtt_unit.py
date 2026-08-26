from monitor.communication.mqtt import (
    join_topic,
    parse_command_topic,
    parse_switch_command_topic,
)


def test_join_topic():
    assert (
        join_topic("arpi/", "/alarm_control_panel/", "/state/set")
        == "arpi/alarm_control_panel/state/set"
    )
    assert join_topic("arpi", "binary_sensor", "config") == "arpi/binary_sensor/config"
    assert join_topic("arpi", None, "", "switch") == "arpi/switch"


def test_parse_command_topic():
    assert parse_command_topic("arpi/alarm_control_panel/system/state/set") == ("system", None)
    assert parse_command_topic("arpi/alarm_control_panel/house_1/state/set") == ("house", "1")
    assert parse_command_topic("arpi/alarm_control_panel/living_room_2_22/state/set") == (
        "living_room_2",
        "22",
    )
    assert parse_command_topic("arpi/alarm_control_panel/invalid") == (None, None)
    assert parse_command_topic("other/topic/state/set") == (None, None)


def test_parse_switch_command_topic():
    assert parse_switch_command_topic("arpi/switch/siren_1/state/set") == ("siren", 1)
    assert parse_switch_command_topic("arpi/switch/relay_output_5/state/set") == ("relay_output", 5)
    assert parse_switch_command_topic("arpi/switch/siren/state/set") == (None, None)
    assert parse_switch_command_topic("arpi/switch/siren_abc/state/set") == (None, None)
