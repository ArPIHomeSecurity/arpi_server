from monitor.adapters.mock.zigbee import ZigbeeAdapter
from simulator.zigbee import ZigbeeDeviceType, _entities_for_device
from utils.zigbee import ZigbeeEntity, ZigbeeEntityReading


IEEE_ADDRESS = "11:22:33:44:55:66:77:88"
ENTITY_ID = f"binary_sensor/{IEEE_ADDRESS}-1-1280"


def test_mock_adapter_builds_reading_from_entity_state():
    adapter = ZigbeeAdapter()
    entity = {
        "entityId": ENTITY_ID,
        "uniqueId": f"{IEEE_ADDRESS}-1-1280",
        "platform": "binary_sensor",
        "name": "Contact",
        "cluster": "IAS Zone",
        "attribute": "zone_status",
        "deviceClass": "opening",
        "value": True,
        "attributes": {"trouble": False},
    }

    adapter._refresh_cache(
        {
            IEEE_ADDRESS: {
                "entities": [entity],
            }
        }
    )

    assert adapter._cache[(IEEE_ADDRESS, ENTITY_ID)] == ZigbeeEntityReading(
        ieee_address=IEEE_ADDRESS,
        entity_id=ENTITY_ID,
        value=True,
        device_class="opening",
        attributes={"trouble": False},
        available=True,
        timestamp=None,
    )


def test_mock_adapter_builds_device_metadata_from_entities():
    entity = {
        "entityId": ENTITY_ID,
        "uniqueId": f"{IEEE_ADDRESS}-1-1280",
        "platform": "binary_sensor",
        "name": "Contact",
        "cluster": "IAS Zone",
        "attribute": "zone_status",
        "deviceClass": "opening",
    }

    device = ZigbeeAdapter._build_device(IEEE_ADDRESS, {"entities": [entity]})

    assert device.entities == [
        ZigbeeEntity(
            entity_id=ENTITY_ID,
            unique_id=f"{IEEE_ADDRESS}-1-1280",
            platform="binary_sensor",
            name="Contact",
            device_class="opening",
            value=None,
            available=True,
            cluster="IAS Zone",
            attribute="zone_status",
        )
    ]


def test_entity_state_round_trips_through_json():
    entity = ZigbeeEntity(
        entity_id=ENTITY_ID,
        unique_id=f"{IEEE_ADDRESS}-1-1280",
        platform="binary_sensor",
        name="Contact",
        device_class="opening",
        value=True,
        attributes={"trouble": True},
    )

    assert ZigbeeEntity.from_json(entity.to_json()) == entity


def test_simulator_device_types_define_entity_metadata():
    cases = (
        (ZigbeeDeviceType.OPEN_DETECTOR, ("IAS Zone", "On/Off")),
        (ZigbeeDeviceType.MOTION_SENSOR, ("IAS Zone",)),
        (ZigbeeDeviceType.OCCUPANCY_SENSOR, ("Occupancy Sensing",)),
    )

    for device_type, expected_clusters in cases:
        entities = _entities_for_device(IEEE_ADDRESS, device_type)

        assert all(entity["platform"] == "binary_sensor" for entity in entities)
        assert tuple(entity["cluster"] for entity in entities) == expected_clusters
