"""
Tests for the static mosquitto access control list installed by the MQTT installer.

The two external accounts are separated by capability: argus_reader may only observe the
system, argus_control may additionally send the arm/disarm commands. The control account
must not read the command topics, because their payload carries the plain access code of
a user. The reader keeps its historical full read access for backward compatibility.
"""

from pathlib import Path

import pytest

ACL_FILE = Path(__file__).parents[2] / "src/installer/installers/etc/mosquitto/acl.conf"

COMMAND_TOPIC = "arpi/alarm_control_panel/+/state/set"
STATE_TOPIC = "arpi/alarm_control_panel/house/state"

READER = "argus_reader"
CONTROL = "argus_control"
SERVICE = "argus"

WRITE_ACCESS = ("write", "readwrite")
READ_ACCESS = ("read", "readwrite")


def topic_matches(topic_filter: str, topic: str) -> bool:
    """
    Match a topic against an MQTT topic filter, level exact except for + and #.
    """
    filter_levels = topic_filter.split("/")
    topic_levels = topic.split("/")

    for index, level in enumerate(filter_levels):
        if level == "#":
            return index <= len(topic_levels)
        if index >= len(topic_levels):
            return False
        if level not in ("+", topic_levels[index]):
            return False

    return len(filter_levels) == len(topic_levels)


def parse_acl(path: Path) -> dict[str, list[tuple[str, str]]]:
    """
    Parse a mosquitto ACL file into {username: [(access, topic filter), ...]}.
    """
    rules: dict[str, list[tuple[str, str]]] = {}
    user = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        # only whole lines are comments, "#" is also the multi level topic wildcard
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("user "):
            user = line[len("user ") :].strip()
            rules[user] = []
        elif line.startswith("topic "):
            assert user is not None, f"topic rule outside of a user block: {raw_line}"
            parts = line[len("topic ") :].split()
            # without an access type mosquitto defaults to readwrite
            if len(parts) == 1:
                rules[user].append(("readwrite", parts[0]))
            else:
                rules[user].append((parts[0], parts[1]))

    return rules


@pytest.fixture(name="acl", scope="module")
def acl_fixture():
    return parse_acl(ACL_FILE)


def test_all_accounts_are_defined(acl):
    assert set(acl) == {READER, CONTROL, SERVICE}


def test_reader_has_no_write_access(acl):
    write_rules = [topic for access, topic in acl[READER] if access in WRITE_ACCESS]
    assert not write_rules


def test_reader_reads_the_state(acl):
    read_rules = [topic for access, topic in acl[READER] if access in READ_ACCESS]
    assert any(topic_matches(topic, STATE_TOPIC) for topic in read_rules)


def test_control_may_send_commands(acl):
    assert ("write", COMMAND_TOPIC) in acl[CONTROL]


def test_reader_keeps_full_read_access(acl):
    """
    Existing external clients rely on the reader account being able to subscribe to
    everything, so its historical full read access must not be restricted.
    """
    assert ("read", "#") in acl[READER]


def test_control_reads_the_published_topics(acl):
    control_reads = [topic for access, topic in acl[CONTROL] if access in READ_ACCESS]
    for topic in (
        "arpi/binary_sensor/1/state",
        "arpi/alarm_control_panel/house/config",
        STATE_TOPIC,
    ):
        assert any(topic_matches(rule, topic) for rule in control_reads), topic


def test_command_topics_are_not_readable_by_control(acl):
    """
    The command payload carries the plain access code of a user, subscribing to the
    command topics would allow harvesting the codes of every user. The reader account
    is exempt for backward compatibility, see the ACL file.
    """
    command_topic = COMMAND_TOPIC.replace("+", "house")
    readable = [
        topic
        for access, topic in acl[CONTROL]
        if access in READ_ACCESS and topic_matches(topic, command_topic)
    ]
    assert not readable


def test_service_account_keeps_full_access(acl):
    assert ("readwrite", "#") in acl[SERVICE]
