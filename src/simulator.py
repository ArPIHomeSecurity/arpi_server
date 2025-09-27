#!/usr/bin/env python

import logging
from contextlib import suppress
from copy import deepcopy
from enum import Enum
from os import environ

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.logging import TextualHandler
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Select, Static

from models import SensorContactTypes
from monitor.adapters.mock.utils import (
    DEFAULT_KEYPAD,
    get_channel_configs,
    get_output_states,
    set_input_states,
    set_keypad_state,
)
from monitor.output import OUTPUT_NAMES
from monitor.sensor.detector import wiring_config


class WiringStrategies(str, Enum):
    SINGLE_WITH_EOL = "single_with_eol"
    SINGLE_WITH_2EOL = "single_with_2eol"
    DUAL = "dual"
    CUT = "cut"
    SHORTAGE = "shortage"


# Wiring strategies
WIRING_STRATEGIES = [
    ("Single/EOL", WiringStrategies.SINGLE_WITH_EOL.value),
    ("Single/2 EOL", WiringStrategies.SINGLE_WITH_2EOL.value),
    ("Dual", WiringStrategies.DUAL.value),
    ("Cut", WiringStrategies.CUT.value),
    ("Shortage", WiringStrategies.SHORTAGE.value),
]

# Contact types
CONTACT_TYPES = [("NC", "nc"), ("NO", "no")]

# channel error states
CHANNEL_CUT = 1.0
CHANNEL_SHORTAGE = 0.0

POWER_LOW = 0
POWER_HIGH = 1

# <card number:pending bits>
CARD_1 = "550021576706:34"
CARD_2 = "550021576707:34"
CARD_3 = "550021576708:34"


class Channels(Widget):
    """Display and control the channels"""

    DEFAULT_CSS = """
    #channels {
        overflow: scroll;
    }

    .channel-column {
        width: 44;
        margin-right: 5;
    }

    .channel-row {
        height: 3;
        background: black 100%;
    }

    .channel-label {
        width: 6;
        height: 3;
        content-align: center middle;
        color: white;
    }

    .channel-label.default {
        background: green 90%;
        color: white;
    }

    .channel-label.active-low {
        background: red 50%;
        color: white;
    }

    .channel-label.active {
        background: red 80%;
        color: white;
    }

    .channel-label.shortage {
        background: yellow 100%;
        color: white;
    }

    .channel-label.cut {
        background: orange 100%;
        color: white;
    }

    .wiring-strategy-select {
        width: 20;
        margin: 0;
    }

    .contact-type-select {
        width: 12;
        margin: 0;
    }

    .sensor-button {
        min-width: 3;
        width: 3;
        height: 3;
    }

    .sensor-active {
        background: red 80%;
        color: white;
    }

    /* power button */
    #power {
        height: 3;
        width: 100%;
        background: green 90%;
        border: none;
    }

    #power.channel-active {
        background: red 80%;
    }
    """

    def __init__(self, default_states, channel_configs, **kwargs):
        super().__init__(**kwargs)
        self._default_states = default_states
        self._channel_configs = channel_configs

    def compose(self) -> ComposeResult:
        """Create channel rows with strategy select, contact type select, and sensor buttons in two columns"""
        num_channels = len(self._default_states) - 1
        col1 = range(1, num_channels // 2 + 1)
        col2 = range(num_channels // 2 + 1, num_channels + 1)
        with Horizontal(id="channels"):
            for col in [col1, col2]:
                with Vertical(classes="channel-column"):
                    for i in col:
                        ch_key = f"CH{i:02d}"
                        config = self._channel_configs.get(ch_key, {})
                        wiring_strategy = config.get("wiring_strategy", "cut")
                        contact_type = config.get("contact_type", "nc")
                        sensor_a_active = config.get("sensor_a_active", False)
                        sensor_b_active = config.get("sensor_b_active", False)

                        with Horizontal(classes="channel-row"):
                            channel_class = self.get_channel_class(
                                wiring_strategy, sensor_a_active, sensor_b_active
                            )

                            yield Static(
                                f"CH{i:02d} {self._default_states[i - 1]:.2f}V",
                                id=f"channel-label-{i}",
                                classes=f"channel-label {channel_class or wiring_strategy}",
                            )

                            # Wiring strategy select
                            yield Select(
                                [(value, label) for value, label in WIRING_STRATEGIES],
                                value=wiring_strategy,
                                id=f"wiring-strategy-{i}",
                                classes="wiring-strategy-select",
                                allow_blank=False,
                            )

                            # Contact type select (disabled for cut/shortage)
                            contact_disabled = wiring_strategy in ["cut", "shortage"]
                            yield Select(
                                [(value, label) for value, label in CONTACT_TYPES],
                                value=contact_type,
                                id=f"contact-type-{i}",
                                classes="contact-type-select",
                                disabled=contact_disabled,
                                allow_blank=False,
                            )

                            # Sensor activation buttons (only enabled for dual configurations)
                            yield Button(
                                "A",
                                id=f"sensor-{i}-a",
                                classes="sensor-button"
                                + (" sensor-active" if sensor_a_active else ""),
                                disabled=(
                                    wiring_strategy
                                    not in [
                                        WiringStrategies.DUAL.value,
                                        WiringStrategies.SINGLE_WITH_EOL.value,
                                        WiringStrategies.SINGLE_WITH_2EOL.value,
                                    ]
                                ),
                            )
                            yield Button(
                                "B",
                                id=f"sensor-{i}-b",
                                classes="sensor-button"
                                + (" sensor-active" if sensor_b_active else ""),
                                disabled=wiring_strategy != WiringStrategies.DUAL.value,
                            )

        yield Static("")
        yield Button("POWER", id="power", classes="power")

    @staticmethod
    def get_channel_class(wiring_strategy, sensor_a_active, sensor_b_active):
        """
        Determine the CSS class for the channel label based on wiring strategy and sensor states
        """
        channel_class = None
        if wiring_strategy in [WiringStrategies.CUT.value, WiringStrategies.SHORTAGE.value]:
            channel_class = wiring_strategy
        else:
            if sensor_a_active and sensor_b_active:
                channel_class = "active"
            elif sensor_a_active or sensor_b_active:
                channel_class = "active-low"
            else:
                channel_class = "default"
        return channel_class


class Outputs(Widget):
    """Display the output states"""

    DEFAULT_CSS = """
    #outputs {
        background: black 100%;
        overflow: scroll;
    }

    #outputs Checkbox {
        width: 10;
        height: 3;
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Create output checkboxes"""
        with Horizontal(id="outputs"):
            yield Checkbox("GO", id="output-GO", value=False)
            yield Checkbox("R1", id="output-R1", value=False)
            yield Checkbox("R0", id="output-R0", value=False)
            yield Checkbox("O4", id="output-O4", value=False)
            yield Checkbox("O3", id="output-O3", value=False)
            yield Checkbox("O2", id="output-O2", value=False)
            yield Checkbox("O1", id="output-O1", value=False)
            yield Checkbox("O0", id="output-O0", value=False)


class Keypad(Widget):
    """Widget for keypad controls"""

    can_focus = False

    DEFAULT_CSS = """
    #keypad {
        layout: grid;
        grid-size: 3 5;
        grid-gutter: 1 1;
        grid-rows: 3 3 3 3 3;
        grid-columns: 11 11 11;
        background: black 100%;
        overflow: scroll;
    }
    
    #keypad Button {
        background: blue 60%;
        color: white 100%;
        height: 3;
        border: none;
    }
    """

    def compose(self) -> ComposeResult:
        """Create keypad buttons"""
        with Container(id="keypad"):
            yield Button("1", id="button-1")
            yield Button("2", id="button-2")
            yield Button("3", id="button-3")
            yield Button("4", id="button-4")
            yield Button("5", id="button-5")
            yield Button("6", id="button-6")
            yield Button("7", id="button-7")
            yield Button("8", id="button-8")
            yield Button("9", id="button-9")
            yield Button("*", id="button-10")
            yield Button("0", id="button-0")
            yield Button("#", id="button-11")
            yield Button("Card 1", id="card-1")
            yield Button("Card 2", id="card-2")
            yield Button("Card 3", id="card-3")


class SimulatorApp(App):
    """Simulate status of sensors and power for argus"""

    DEFAULT_CSS = """
    Screen {
        overflow: auto;
    }

    #main-grid {
        layout: grid;
        grid-size: 2 2;
        grid-gutter: 2 2;
        grid-rows: 7fr 1fr;
        grid-columns: 2fr 38;
        width: 100%;
        height: 37;
    }

    #channels-pane {
    }

    #keypad-pane {
    }

    #outputs-pane {
        column-span: 2;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.keypad = deepcopy(DEFAULT_KEYPAD)
        self.channel_values = {}
        self.channel_configs = {}

    def initialize_channels(self, input_number: int) -> None:
        """
        Initialize channel states and values from saved data or defaults.
        """
        # Load channel configurations from buffer file
        saved_configs = get_channel_configs()

        # Initialize channel dictionaries
        self.channel_values = {f"CH{i:02d}": CHANNEL_CUT for i in range(1, input_number + 1)}
        self.channel_values["POWER"] = POWER_HIGH

        self.channel_configs = {
            f"CH{i:02d}": {
                "wiring_strategy": "cut",
                "contact_type": "nc",
                "sensor_a_active": False,
                "sensor_b_active": False,
            }
            for i in range(1, input_number + 1)
        }

        # Apply saved configurations and calculate values
        for ch_key, config in saved_configs.items():
            if ch_key in self.channel_configs:
                self.channel_configs[ch_key] = config
                # Calculate initial values based on configuration
                self.channel_values[ch_key] = self.calculate_channel_value(ch_key)

    def compose(self) -> ComposeResult:
        """Add our widgets in a grid layout."""
        with Container(id="main-grid"):
            yield Channels(
                id="channels-pane",
                default_states=list(self.channel_values.values()),
                channel_configs=self.channel_configs,
            )
            yield Keypad(id="keypad-pane")
            yield Outputs(id="outputs-pane")

    def read_output_states(self):
        outputs = get_output_states()

        for idx, name in OUTPUT_NAMES.items():
            with suppress(NoMatches):
                checkbox = self.query_one(f"#output-{name}")
                checkbox.value = outputs[idx]

    def save_input_states(self):
        set_input_states(
            list(self.channel_values.values()),
            [
                self.channel_configs[f"CH{i:02d}"]
                for i in range(1, int(environ.get("INPUT_NUMBER", 15)) + 1)
            ],
        )

    def save_keypad_states(self):
        set_keypad_state(self.keypad["pending_bits"], self.keypad["data"])
        # reset keypad state
        self.keypad = deepcopy(DEFAULT_KEYPAD)

    def on_mount(self) -> None:
        """Start background tasks when the app mounts"""
        self.set_interval(0.5, self.read_output_states)

    def calculate_channel_value(self, channel: str) -> float:
        """Calculate the channel value based on wiring strategy and sensor states"""
        config = self.channel_configs[channel]
        wiring_strategy = config["wiring_strategy"]
        contact_type = config["contact_type"]
        sensor_a_active = config["sensor_a_active"]
        sensor_b_active = config["sensor_b_active"]

        logging.debug(
            "Calculating value channel: %s, strategy: %s, contact: %s, A active: %s, B active: %s",
            channel,
            wiring_strategy,
            contact_type,
            sensor_a_active,
            sensor_b_active,
        )

        if wiring_strategy == WiringStrategies.CUT.value:
            return CHANNEL_CUT
        elif wiring_strategy == WiringStrategies.SHORTAGE.value:
            return CHANNEL_SHORTAGE

        # Convert contact type to SensorContactTypes enum
        contact_enum = SensorContactTypes.NC if contact_type == "nc" else SensorContactTypes.NO

        if wiring_strategy == WiringStrategies.SINGLE_WITH_EOL.value:
            strategy = wiring_config.select_strategy(contact_enum, dual=False, two_eol=False)
            return strategy.active if sensor_a_active else strategy.default
        elif wiring_strategy == WiringStrategies.SINGLE_WITH_2EOL.value:
            strategy = wiring_config.select_strategy(contact_enum, dual=False, two_eol=True)
            return strategy.active if sensor_a_active else strategy.default
        elif wiring_strategy == WiringStrategies.DUAL.value:
            strategy = wiring_config.select_strategy(contact_enum, dual=True, two_eol=False)
            if sensor_a_active and sensor_b_active:
                return strategy.both_active
            elif sensor_a_active:
                return strategy.channel_a_active
            elif sensor_b_active:
                return strategy.channel_b_active
            else:
                return strategy.default
        else:
            raise ValueError(f"Unknown wiring strategy: {wiring_strategy}")

    @on(Button.Pressed, "#channels-pane .sensor-button")
    def sensor_button_pressed(self, event: Button.Pressed) -> None:
        """Toggle sensor A/B state"""
        _, channel_num, sensor = event.button.id.split("-")
        channel_num = int(channel_num)
        channel_name = f"CH{channel_num:02d}"

        config = self.channel_configs[channel_name]
        # Toggle sensor state
        if sensor == "a":
            config["sensor_a_active"] = not config["sensor_a_active"]
        elif sensor == "b":
            config["sensor_b_active"] = not config["sensor_b_active"]

        # Update button appearance
        event.button.toggle_class("sensor-active")

        # Update channel value
        self.channel_values[channel_name] = self.calculate_channel_value(channel_name)

        # Update channel label
        self.update_channel_label(channel_num, channel_name, config)

        self.save_input_states()

    @on(Select.Changed, "#channels-pane .wiring-strategy-select")
    def wiring_strategy_changed(self, event: Select.Changed) -> None:
        """Handle wiring strategy selection changes"""
        select_id = event.select.id
        channel_num = int(select_id.split("-")[2])
        channel_name = f"CH{channel_num:02d}"
        wiring_strategy = event.value

        # Update configuration
        config = self.channel_configs[channel_name]
        config["wiring_strategy"] = wiring_strategy
        config["sensor_a_active"] = False  # Reset sensor states
        config["sensor_b_active"] = False

        # Update contact type select enable/disable
        contact_disabled = wiring_strategy in ["cut", "shortage"]
        contact_select = self.query_one(f"#contact-type-{channel_num}")
        contact_select.disabled = contact_disabled

        # Update sensor button enable/disable
        sensor_a_button = self.query_one(f"#sensor-{channel_num}-a")
        sensor_b_button = self.query_one(f"#sensor-{channel_num}-b")
        sensor_a_button.disabled = config["wiring_strategy"] in [
            WiringStrategies.CUT.value,
            WiringStrategies.SHORTAGE.value,
        ]
        sensor_b_button.disabled = wiring_strategy != WiringStrategies.DUAL.value

        # Reset sensor button appearance
        sensor_a_button.remove_class("sensor-active")
        sensor_b_button.remove_class("sensor-active")

        # Update channel value and label
        self.update_channel_label(channel_num, channel_name, config)

        self.save_input_states()

    @on(Select.Changed, "#channels-pane .contact-type-select")
    def contact_type_changed(self, event: Select.Changed) -> None:
        """Handle contact type selection changes"""
        select_id = event.select.id
        channel_num = int(select_id.split("-")[2])
        channel_name = f"CH{channel_num:02d}"

        # Update configuration
        config = self.channel_configs[channel_name]
        config["contact_type"] = event.value

        # Update channel value and label
        self.update_channel_label(channel_num, channel_name, config)

        self.save_input_states()

    def update_channel_label(self, channel_num, channel_name, config):
        self.channel_values[channel_name] = self.calculate_channel_value(channel_name)
        channel_label = self.query_one(f"#channel-label-{channel_num}")
        channel_label.update(f"CH{channel_num:02d} {self.channel_values[channel_name]:.2f}V")
        channel_label.set_classes(
            [
                "channel-label",
                Channels.get_channel_class(
                    config["wiring_strategy"], config["sensor_a_active"], config["sensor_b_active"]
                )
                or config["wiring_strategy"],
            ]
        )

    @on(Button.Pressed, "#power")
    def power_button_pressed(self, event: Button.Pressed) -> None:
        """
        Pressed the power button.
        """
        self.channel_values["POWER"] = (
            POWER_HIGH if self.channel_values["POWER"] == POWER_LOW else POWER_LOW
        )
        event.button.toggle_class("channel-active")
        self.save_input_states()

    @on(Button.Pressed, "#keypad Button")
    def keypad_button_pressed(self, event: Button.Pressed) -> None:
        """Pressed a button on the keypad."""
        label = str(event.button.label)

        # Card handling
        card_map = {
            "Card 1": CARD_1,
            "Card 2": CARD_2,
            "Card 3": CARD_3,
        }

        if label in card_map:
            card_data, pending_bits = card_map[label].split(":")
            self.keypad["data"].append(card_data)
            self.keypad["pending_bits"] = int(pending_bits)
        else:
            self.keypad["data"].append(label)
            self.keypad["pending_bits"] = len(self.keypad["data"]) * 8

        self.save_keypad_states()


logging.basicConfig(
    level="NOTSET",
    handlers=[TextualHandler()],
    format="%(asctime)s: %(message)s",
)
if __name__ == "__main__":
    app = SimulatorApp()
    # Initialize channel values and states from saved data
    app.initialize_channels(int(environ.get("INPUT_NUMBER", 15)))

    # Save initial states only after initialization
    app.save_input_states()
    app.save_keypad_states()
    app.run()
