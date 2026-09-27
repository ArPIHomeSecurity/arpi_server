"""Zigbee tab widget for the simulator."""

from datetime import datetime
from pathlib import Path
from random import randint

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Input, Label, Static

from monitor.adapters.mock.utils import (
    get_zigbee_devices,
    set_zigbee_capability,
    set_zigbee_devices,
)
from monitor.database import create_database_session
from utils.models import ZigbeeDevice


def random_ieee_address() -> str:
    """Generate a random IEEE 802.15.4 address for a new simulated device."""
    return ":".join(f"{randint(0, 255):02X}" for _ in range(8))


class ZigbeeDevices(Widget):
    """Widget for Zigbee device management."""

    can_focus = False
    DEFAULT_CSS = Path(__file__).with_name("zigbee.tcss").read_text()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # widget id => (ieee address, "endpoint/capability")
        self.zigbee_properties = {}
        # the property widgets are removed asynchronously, so their ids must stay unique
        self.zigbee_property_generation = 0

    def compose(self) -> ComposeResult:
        with Container(id="zigbee-pane"):
            with Horizontal(id="zigbee-action-bar", classes="action-bar"):
                yield Button("Update from database", id="zigbee-refresh", classes="refresh-button")
            with Horizontal(classes="zigbee-row"):
                with Horizontal():
                    yield Label("Device name", classes="zigbee-label")
                    yield Input(placeholder="Device name", id="zigbee-name")
                with Horizontal():
                    yield Label("IEEE address", classes="zigbee-label")
                    yield Input(
                        placeholder="IEEE address",
                        value=random_ieee_address(),
                        id="zigbee-ieee",
                    )
                with Horizontal():
                    yield Label("Model", classes="zigbee-label")
                    yield Input(placeholder="Model", value="Zigbee Sim Device", id="zigbee-model")
            with Horizontal(classes="zigbee-row"):
                with Horizontal():
                    yield Label("Endpoint", classes="zigbee-label")
                    yield Input(placeholder="Endpoint", value="1", id="zigbee-endpoint")
                with Horizontal():
                    yield Label("Capability", classes="zigbee-label")
                    yield Input(placeholder="Capability", value="contact", id="zigbee-capability")
                with Horizontal():
                    yield Label("Battery %", classes="zigbee-label")
                    yield Input(placeholder="Battery %", value="87", id="zigbee-battery")
                with Horizontal():
                    yield Label("Signal %", classes="zigbee-label")
                    yield Input(placeholder="Signal %", value="72", id="zigbee-signal")

            with Horizontal(id="zigbee-actions"):
                yield Button("Add Device", id="zigbee-add-device")

            yield Label("Devices", classes="zigbee-label")
            yield Vertical(id="zigbee-devices")

    def on_mount(self) -> None:
        """Populate the device list from the database when the tab mounts."""
        self.refresh_zigbee_devices(update_state=True)

    def load_zigbee_devices(self) -> dict:
        """
        Load the Zigbee devices registered by the monitor from the database.
        Returns a dict mapping IEEE addresses to device attributes.
        """
        with create_database_session() as session:
            devices = session.query(ZigbeeDevice).order_by(ZigbeeDevice.ieee_address).all()

            return {
                device.ieee_address: {
                    "name": device.name,
                    "manufacturer": device.manufacturer,
                    "model": device.model,
                    "available": device.availability == "online",
                    "battery_level": device.battery_level,
                    "signal_quality": device.signal_quality,
                    "last_seen": device.last_seen.isoformat() if device.last_seen else None,
                    "capabilities": (device.device_metadata or {}).get("capabilities", {}),
                }
                for device in devices
            }

    def refresh_zigbee_devices(self, update_state=False):
        """Rebuild the device list with a property checkbox row for every known device."""
        container = self.query_one("#zigbee-devices", Vertical)
        container.remove_children()

        # load the Zigbee devices from the database
        devices = self.load_zigbee_devices()

        # update the simulator state with the loaded devices if requested
        if update_state:
            set_zigbee_devices(devices)

        if not devices:
            container.mount(Static("No devices added yet.", classes="zigbee-no-device"))
            return

        self.zigbee_properties = {}
        self.zigbee_property_generation += 1
        generation = self.zigbee_property_generation
        for index, (ieee, device) in enumerate(sorted(devices.items())):
            name = device.get("name") or ieee
            registered = "registered" if device.get("registered") else "pairing"
            row = [
                Static(
                    f"{name} ({ieee}) | {registered}"
                    f" | battery={device.get('battery_level', 100)}%"
                    f" | signal={device.get('signal_quality', 100)}%",
                    classes="zigbee-device-label",
                )
            ]

            capabilities = device.get("capabilities") or {}
            properties = {
                key: value for key, value in capabilities.items() if isinstance(value, bool)
            }
            for property_index, (capability_key, value) in enumerate(sorted(properties.items())):
                widget_id = f"zigbee-property-{generation}-{index}-{property_index}"
                self.zigbee_properties[widget_id] = (ieee, capability_key)
                row.append(
                    Checkbox(capability_key, id=widget_id, value=value, classes="zigbee-property")
                )

            container.mount(Horizontal(*row, classes="zigbee-device-row"))

    def add_zigbee_device(self):
        """Register a new simulated device with a pending pairing request."""
        devices = get_zigbee_devices()
        devices.setdefault("devices", {})

        ieee_field = self.query_one("#zigbee-ieee", Input).value.strip()
        name_field = self.query_one("#zigbee-name", Input).value.strip()
        if not ieee_field:
            return

        endpoint = self.query_one("#zigbee-endpoint", Input).value.strip() or "1"
        capability = self.query_one("#zigbee-capability", Input).value.strip() or "contact"
        capability_key = f"{endpoint}/{capability}"
        model = self.query_one("#zigbee-model", Input).value.strip() or "Simulator Device"

        device = devices["devices"].setdefault(ieee_field, {})
        device["name"] = name_field or device.get("name", "Simulator Device")
        device["manufacturer"] = "Simulator"
        device["model"] = model
        device["available"] = True
        device["pairing"] = True
        device["battery_level"] = int(self.query_one("#zigbee-battery", Input).value or 100)
        device["signal_quality"] = int(self.query_one("#zigbee-signal", Input).value or 100)

        device.setdefault("capabilities", {})
        device["capabilities"].setdefault(capability_key, False)
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
        """Reload the Zigbee device list from the database."""
        self.refresh_zigbee_devices()

    @on(Checkbox.Changed, "#zigbee-devices Checkbox")
    def zigbee_property_changed(self, event: Checkbox.Changed) -> None:
        """Write the new value of a boolean device property to the simulator state."""
        entry = self.zigbee_properties.get(event.checkbox.id)
        if not entry:
            return

        ieee, capability_key = entry
        value = bool(event.value)
        capabilities = get_zigbee_devices().get("devices", {}).get(ieee, {}).get("capabilities", {})
        # the checkbox also reports the value set while building the widget
        if capabilities.get(capability_key) == value:
            return

        set_zigbee_capability(ieee, capability_key, value)
