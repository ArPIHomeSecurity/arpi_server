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
from zigpy.zcl.clusters.security import IasZone, ZoneStatus, ZoneType

from monitor.adapters.mock.utils import (
    get_zigbee_devices,
    set_zigbee_devices,
    set_zigbee_signal,
    set_zigbee_trouble,
)
from monitor.database import create_database_session
from utils.models import ZigbeeDevice
from utils.zigbee import (
    IasField,
    IAS_ZONE_STATUS_ATTRIBUTE,
    ZigbeeSignal,
    zigbee_signals,
)

DEFAULT_ZIGBEE_ENDPOINT = "1"


def _registered_signals(cluster):
    return [
        signal.to_json() for signal in zigbee_signals(cluster.cluster_id, DEFAULT_ZIGBEE_ENDPOINT)
    ]


OPEN_DETECTOR_SIGNALS = _registered_signals(IasZone) + _registered_signals(OnOff)
MOTION_SENSOR_SIGNALS = _registered_signals(IasZone)
OCCUPANCY_SENSOR_SIGNALS = _registered_signals(OccupancySensing)


class ZigbeeDeviceType(str, Enum):
    OPEN_DETECTOR = "Open detector"
    MOTION_SENSOR = "Motion sensor"
    OCCUPANCY_SENSOR = "Occupancy sensor"


ZIGBEE_SIGNALS = {
    ZigbeeDeviceType.OPEN_DETECTOR: OPEN_DETECTOR_SIGNALS,
    ZigbeeDeviceType.MOTION_SENSOR: MOTION_SENSOR_SIGNALS,
    ZigbeeDeviceType.OCCUPANCY_SENSOR: OCCUPANCY_SENSOR_SIGNALS,
}

ZIGBEE_TYPE_OPTIONS = [
    ("Open detector", ZigbeeDeviceType.OPEN_DETECTOR),
    ("Motion sensor", ZigbeeDeviceType.MOTION_SENSOR),
    ("Occupancy sensor", ZigbeeDeviceType.OCCUPANCY_SENSOR),
]


def random_ieee_address() -> str:
    """Generate a random IEEE 802.15.4 address for a new simulated device."""
    return ":".join(f"{randint(0, 255):02X}" for _ in range(8))


def _ias_endpoints(signals) -> set[str]:
    """Endpoints with an IAS zone alarm signal."""
    return {
        signal["endpoint"]
        for signal in signals
        if ZigbeeSignal.from_json(signal)
        == IAS_ZONE_STATUS_ATTRIBUTE.signal(signal["endpoint"], IasField.ALARM)
    }


def _find_signal_value(signal_values, descriptor):
    signal = ZigbeeSignal.from_json(descriptor)
    for record in signal_values:
        if ZigbeeSignal.from_json(record) == signal:
            return record.get("value")
    return False


def _signal_value_record(descriptor, value):
    return {**descriptor, "value": value}


class ZigbeeDevices(Widget):
    """Widget for Zigbee device management."""

    can_focus = False
    DEFAULT_CSS = Path(__file__).with_name("zigbee.tcss").read_text()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # widget id => (IEEE address, structured signal descriptor)
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
                    "available": device.availability == "online",
                    "battery_level": device.battery_level,
                    "signal_quality": device.signal_quality,
                    "last_seen": device.last_seen.isoformat() if device.last_seen else None,
                    "registered": True,
                    "signals": (device.device_metadata or {}).get("signals", []),
                }
                for device in devices
            }

    @staticmethod
    def _signal_label(signal) -> str:
        cluster = signal.get("cluster")
        attribute = signal.get("field") or signal.get("attribute")
        cluster_label = str(cluster or "").replace("_", " ").title()
        if cluster == IasZone.ep_attribute:
            cluster_label = IasZone.name
        attribute_label = str(attribute or signal.get("attributeId")).replace("_", " ").title()
        label = f"{cluster_label}: {attribute_label}" if cluster_label else attribute_label
        return f"{label} (endpoint {signal['endpoint']})"

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

                current_signals = simulator_device.get("signal_values", [])
                statuses = simulator_device.get("ias_zone_status", {})
                signals = list(device.get("signals") or [])
                known = {ZigbeeSignal.from_json(signal) for signal in signals}
                for endpoint in _ias_endpoints(signals):
                    trouble = IAS_ZONE_STATUS_ATTRIBUTE.signal(endpoint, IasField.TROUBLE)
                    if trouble not in known:
                        signals.append(trouble.to_json())
                simulator_device["signal_values"] = [
                    _signal_value_record(
                        signal,
                        bool(int(statuses[signal["endpoint"]]) & ZoneStatus.Trouble)
                        if signal.get("field") == IasField.TROUBLE and signal["endpoint"] in statuses
                        else _find_signal_value(current_signals, signal),
                    )
                    for signal in signals
                ]
                simulator_device["signal_metadata"] = signals
                for attribute in (
                    "name",
                    "manufacturer",
                    "model",
                    "available",
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

            signals = device.get("signals") or []
            signal_values = simulator_devices.get(ieee, {}).get("signal_values", [])
            for property_index, signal in enumerate(signals):
                if signal.get("field") == IasField.TROUBLE:
                    continue
                widget_id = f"zigbee-property-{generation}-{index}-{property_index}"
                self.zigbee_properties[widget_id] = (ieee, signal)
                row.append(
                    Checkbox(
                        self._signal_label(signal),
                        id=widget_id,
                        value=bool(_find_signal_value(signal_values, signal)),
                        classes="zigbee-property",
                    )
                )

            for endpoint in sorted(_ias_endpoints(signals)):
                widget_id = f"zigbee-trouble-{generation}-{index}-{endpoint}"
                self.zigbee_trouble_properties[widget_id] = (ieee, endpoint)
                status = simulator_devices.get(ieee, {}).get("ias_zone_status", {}).get(endpoint, 0)
                row.append(
                    Checkbox(
                        f"IAS Zone: Trouble (endpoint {endpoint})",
                        id=widget_id,
                        value=bool(int(status) & ZoneStatus.Trouble),
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
        signals = ZIGBEE_SIGNALS.get(selected_device_type, [])

        device = devices["devices"].setdefault(ieee_field, {})
        device["name"] = device.get("name", "Simulator Device")
        device["manufacturer"] = "Simulator"
        device["model"] = "Simulator Device"
        device["available"] = True
        device["pairing"] = True
        device["battery_level"] = 1
        device["signal_quality"] = 100

        ias_zone_type = None
        if selected_device_type == ZigbeeDeviceType.OPEN_DETECTOR:
            ias_zone_type = int(ZoneType.Contact_Switch)
        elif selected_device_type == ZigbeeDeviceType.MOTION_SENSOR:
            ias_zone_type = int(ZoneType.Motion_Sensor)
        device["signal_values"] = [_signal_value_record(signal, False) for signal in signals]
        device["signal_metadata"] = [
            {**signal, "zoneType": ias_zone_type}
            if signal["clusterId"] == int(IasZone.cluster_id) and ias_zone_type is not None
            else signal
            for signal in signals
        ]
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
            ieee, endpoint = trouble_entry
            device = get_zigbee_devices().get("devices", {}).get(ieee, {})
            status = device.get("ias_zone_status", {}).get(endpoint, 0)
            if bool(int(status) & ZoneStatus.Trouble) != bool(event.value):
                set_zigbee_trouble(ieee, endpoint, event.value)
            return
        entry = self.zigbee_properties.get(event.checkbox.id)
        if not entry:
            return

        ieee, signal = entry
        value = bool(event.value)
        device = get_zigbee_devices().get("devices", {}).get(ieee, {})
        # the checkbox also reports the value set while building the widget
        if _find_signal_value(device.get("signal_values", []), signal) == value:
            return

        set_zigbee_signal(
            ieee,
            signal["endpoint"],
            signal["clusterId"],
            signal["attributeId"],
            signal.get("field"),
            value,
        )
