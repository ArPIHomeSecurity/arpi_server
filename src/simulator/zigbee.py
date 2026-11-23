"""Zigbee tab widget for the simulator."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from random import randint

from sqlalchemy import select
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Input, Label, Select, Static
from zigpy.zcl.clusters.general import OnOff
from zigpy.zcl.clusters.measurement import OccupancySensing
from zigpy.zcl.clusters.security import IasZone

from monitor.adapters.mock.utils import (
    get_zigbee_devices,
    set_zigbee_devices,
    set_zigbee_entity_attribute,
    set_zigbee_entity_value,
)
from monitor.database import create_database_session
from utils.models import ZigbeeDevice

DEFAULT_ZIGBEE_ENDPOINT = "1"


class ZigbeeDeviceType(str, Enum):
    OPEN_DETECTOR = "Open detector"
    MOTION_SENSOR = "Motion sensor"
    OCCUPANCY_SENSOR = "Occupancy sensor"


ZIGBEE_TYPE_OPTIONS = [
    ("Open detector", ZigbeeDeviceType.OPEN_DETECTOR),
    ("Motion sensor", ZigbeeDeviceType.MOTION_SENSOR),
    ("Occupancy sensor", ZigbeeDeviceType.OCCUPANCY_SENSOR),
]


def _binary_sensor_entity(ieee_address, cluster, attribute, device_class, name):
    unique_id = f"{ieee_address.lower()}-{DEFAULT_ZIGBEE_ENDPOINT}-{int(cluster.cluster_id)}"
    return {
        "entityId": f"binary_sensor/{unique_id}",
        "uniqueId": unique_id,
        "platform": "binary_sensor",
        "name": name,
        "cluster": cluster.name,
        "attribute": attribute.name,
        "deviceClass": device_class,
        "value": False,
        "available": True,
        "attributes": {},
    }


def _entities_for_device(ieee_address, device_type):
    if device_type == ZigbeeDeviceType.OPEN_DETECTOR:
        return [
            _binary_sensor_entity(
                ieee_address,
                IasZone,
                IasZone.AttributeDefs.zone_status,
                "opening",
                "Contact",
            ),
            _binary_sensor_entity(
                ieee_address,
                OnOff,
                OnOff.AttributeDefs.on_off,
                "opening",
                "On/Off",
            ),
        ]
    if device_type == ZigbeeDeviceType.MOTION_SENSOR:
        return [
            _binary_sensor_entity(
                ieee_address,
                IasZone,
                IasZone.AttributeDefs.zone_status,
                "motion",
                "Motion",
            )
        ]
    if device_type == ZigbeeDeviceType.OCCUPANCY_SENSOR:
        return [
            _binary_sensor_entity(
                ieee_address,
                OccupancySensing,
                OccupancySensing.AttributeDefs.occupancy,
                "occupancy",
                "Occupancy",
            )
        ]
    return []


def random_ieee_address() -> str:
    """Generate a random IEEE 802.15.4 address for a new simulated device."""
    return ":".join(f"{randint(0, 255):02X}" for _ in range(8))


def _ias_entities(entities):
    """Return IAS Zone entities that can report trouble."""
    return {
        entity["entityId"]: entity
        for entity in entities
        if entity.get("cluster") == IasZone.name
        and entity.get("attribute") == IasZone.AttributeDefs.zone_status.name
    }


def _entity_label(entity):
    cluster = entity.get("cluster")
    attribute = entity.get("attribute")
    label = " / ".join(
        str(value).replace("_", " ").title() for value in (cluster, attribute) if value
    )
    return label or entity.get("name") or entity["entityId"]


class ZigbeeDevices(Widget):
    """Widget for Zigbee device management."""

    can_focus = False
    DEFAULT_CSS = Path(__file__).with_name("zigbee.tcss").read_text()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # widget id => (IEEE address, entity ID)
        self.zigbee_properties = {}
        self.zigbee_trouble_properties = {}
        # the property widgets are removed asynchronously, so their ids must stay unique
        self.zigbee_property_generation = 0

    def compose(self) -> ComposeResult:
        with Container(id="zigbee-pane"):
            with Horizontal(id="zigbee-action-bar", classes="action-bar"):
                yield Button("Update from database", id="zigbee-refresh", classes="refresh-button")
            with Horizontal(classes="zigbee-row"):
                with Horizontal():
                    yield Label("IEEE address", classes="zigbee-label")
                    yield Input(
                        placeholder="IEEE address",
                        value=random_ieee_address(),
                        id="zigbee-ieee",
                    )
                with Horizontal():
                    yield Label("Type", classes="zigbee-label")
                    yield Select(
                        ZIGBEE_TYPE_OPTIONS,
                        value=ZigbeeDeviceType.OPEN_DETECTOR,
                        id="zigbee-type",
                        allow_blank=False,
                    )

            with Horizontal(id="zigbee-actions"):
                yield Button("Add Device", id="zigbee-add-device")

            yield Label("Devices", classes="zigbee-label")
            yield Vertical(id="zigbee-devices")

    def on_mount(self) -> None:
        """Populate the device list from the database when the tab mounts."""
        self.refresh_zigbee_devices(update_state=True)

    def load_zigbee_devices_from_database(self) -> dict:
        """
        Load the Zigbee devices registered by the monitor from the database.
        Returns a dict mapping IEEE addresses to device attributes.
        """
        with create_database_session() as session:
            devices = session.scalars(
                select(ZigbeeDevice)
                .where(ZigbeeDevice.deleted == False)
                .order_by(ZigbeeDevice.ieee_address)
            ).all()

            return {
                device.ieee_address: {
                    "name": device.name,
                    "manufacturer": device.manufacturer,
                    "model": device.model,
                    "battery_level": device.battery_level,
                    "signal_quality": device.signal_quality,
                    "last_seen": device.last_seen.isoformat() if device.last_seen else None,
                    "registered": True,
                    "entities": (device.device_metadata or {}).get("entities", []),
                }
                for device in devices
            }

    def refresh_zigbee_devices(self, update_state=False):
        """Rebuild the device list with a property checkbox row for every known device."""
        container = self.query_one("#zigbee-devices", Vertical)
        container.remove_children()

        # load the Zigbee devices from the database
        devices = self.load_zigbee_devices_from_database()
        simulator_state = {"devices": {}} if update_state else get_zigbee_devices()
        if not isinstance(simulator_state, dict):
            simulator_state = {}

        if "devices" not in simulator_state:
            simulator_devices = simulator_state
            simulator_state = {"devices": simulator_devices}
        else:
            simulator_devices = simulator_state.get("devices")
            if not isinstance(simulator_devices, dict):
                simulator_devices = {}
                simulator_state["devices"] = simulator_devices

        # update the simulator state with the loaded devices if requested
        if update_state:
            for ieee, device in devices.items():
                simulator_device = simulator_devices.get(ieee)
                if not isinstance(simulator_device, dict):
                    simulator_device = {}
                    simulator_devices[ieee] = simulator_device

                entities = list(device.get("entities") or [])
                current_entities = {
                    entity.get("entityId"): entity
                    for entity in simulator_device.get("entities", [])
                    if isinstance(entity, dict) and entity.get("entityId")
                }
                for entity in entities:
                    current = current_entities.get(entity["entityId"], {})
                    entity["value"] = current.get("value", entity.get("value", False))
                    entity["attributes"] = current.get("attributes", entity.get("attributes", {}))
                simulator_device["entities"] = entities
                for attribute in (
                    "name",
                    "manufacturer",
                    "model",
                    "last_seen",
                    "battery_level",
                    "signal_quality",
                ):
                    if device.get(attribute) is not None:
                        simulator_device[attribute] = device[attribute]

            set_zigbee_devices(simulator_state)

        if not devices:
            container.mount(Static("No devices added yet.", classes="zigbee-no-device"))
            return

        self.zigbee_properties = {}
        self.zigbee_trouble_properties = {}
        self.zigbee_property_generation += 1
        generation = self.zigbee_property_generation
        for index, (ieee, device) in enumerate(sorted(devices.items())):
            name = device.get("name") or ieee
            registered = "registered" if device.get("registered") else "pairing"
            row = [
                Static(
                    f"{name} ({ieee}) | {registered}"
                    f" | battery={device.get('battery_level', 1)}%"
                    f" | signal={device.get('signal_quality', 100)}%",
                    classes="zigbee-device-label",
                )
            ]

            entities = [
                entity
                for entity in device.get("entities", [])
                if entity.get("platform") == "binary_sensor"
            ]
            simulator_device = simulator_devices.get(ieee, {})
            entities_by_id = {
                entity.get("entityId"): entity
                for entity in simulator_device.get("entities", [])
                if isinstance(entity, dict)
            }
            for property_index, entity in enumerate(entities):
                widget_id = f"zigbee-property-{generation}-{index}-{property_index}"
                entity_id = entity["entityId"]
                simulator_entity = entities_by_id.get(entity_id, entity)
                self.zigbee_properties[widget_id] = (ieee, entity_id)
                row.append(
                    Checkbox(
                        _entity_label(entity),
                        id=widget_id,
                        value=bool(simulator_entity.get("value", False)),
                        classes="zigbee-property",
                    )
                )

            for entity_id, entity in _ias_entities(entities).items():
                widget_id = (
                    f"zigbee-trouble-{generation}-{index}-{len(self.zigbee_trouble_properties)}"
                )
                self.zigbee_trouble_properties[widget_id] = (ieee, entity_id)
                simulator_entity = entities_by_id.get(entity_id, entity)
                trouble = simulator_entity.get("attributes", {}).get("trouble", False)
                row.append(
                    Checkbox(
                        "IAS Zone / Trouble",
                        id=widget_id,
                        value=bool(trouble),
                        classes="zigbee-property",
                    )
                )

            container.mount(Vertical(*row, classes="zigbee-device-row"))

    def add_zigbee_device(self):
        """Register a new simulated device with a pending pairing request."""
        devices = get_zigbee_devices()
        devices.setdefault("devices", {})

        ieee_field = self.query_one("#zigbee-ieee", Input).value.strip()
        if not ieee_field:
            return

        selected_device_type = self.query_one("#zigbee-type", Select).value
        entities = _entities_for_device(ieee_field, selected_device_type)

        device = devices["devices"].setdefault(ieee_field, {})
        device["name"] = device.get("name", "Simulator Device")
        device["manufacturer"] = "Simulator"
        device["model"] = "Simulator Device"
        device["pairing"] = True
        device["battery_level"] = 1
        device["signal_quality"] = 100

        device["entities"] = entities
        device["last_seen"] = datetime.now().astimezone().isoformat()

        set_zigbee_devices(devices)
        self.query_one("#zigbee-ieee", Input).value = random_ieee_address()
        self.refresh_zigbee_devices()

    @on(Button.Pressed, "#zigbee-add-device")
    def zigbee_add_device_pressed(self, _event: Button.Pressed) -> None:
        """Create a new simulated Zigbee device."""
        self.add_zigbee_device()

    @on(Button.Pressed, "#zigbee-refresh")
    def zigbee_refresh_pressed(self, _event: Button.Pressed) -> None:
        """Reload the Zigbee device list and simulator state from the database."""
        self.refresh_zigbee_devices(update_state=True)

    @on(Checkbox.Changed, "#zigbee-devices Checkbox")
    def zigbee_property_changed(self, event: Checkbox.Changed) -> None:
        """Write the new value of a boolean device property to the simulator state."""
        trouble_entry = self.zigbee_trouble_properties.get(event.checkbox.id)
        if trouble_entry:
            ieee, entity_id = trouble_entry
            device = get_zigbee_devices().get("devices", {}).get(ieee, {})
            entity = next(
                (item for item in device.get("entities", []) if item.get("entityId") == entity_id),
                {},
            )
            attributes = entity.get("attributes", {})
            if bool(attributes.get("trouble", False)) != bool(event.value):
                set_zigbee_entity_attribute(ieee, entity_id, "trouble", event.value)
            return
        entry = self.zigbee_properties.get(event.checkbox.id)
        if not entry:
            return

        ieee, entity_id = entry
        value = bool(event.value)
        device = get_zigbee_devices().get("devices", {}).get(ieee, {})
        # the checkbox also reports the value set while building the widget
        entity = next(
            (item for item in device.get("entities", []) if item.get("entityId") == entity_id),
            {},
        )
        if bool(entity.get("value", False)) == value:
            return

        set_zigbee_entity_value(ieee, entity_id, value)
