#!/usr/bin/env python3

import logging
from contextlib import suppress
from copy import deepcopy
from datetime import datetime
from os import environ
from random import randint

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.logging import TextualHandler
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Input, Select, Static

from monitor.adapters.mock.utils import (
    DEFAULT_KEYPAD,
    ChannelConfig,
    WiringStrategies,
    append_sms_message,
    get_output_states,
    load_channel_configs,
    set_input_states,
    set_keypad_state,
)
from monitor.config.models import GSMConfig
from monitor.database import create_database_session
from monitor.output import OUTPUT_NAMES

# use the wiring configuration of the application
from monitor.sensor.detector import wiring_config
from utils.models import SensorContactTypes

# Wiring strategies for control
WIRING_STRATEGIES = [
    ("Single/EOL", WiringStrategies.SINGLE_WITH_EOL.value),
    ("Single/2 EOL", WiringStrategies.SINGLE_WITH_2EOL.value),
    ("Dual", WiringStrategies.DUAL.value),
    ("Cut", WiringStrategies.CUT.value),
    ("Shortage", WiringStrategies.SHORTAGE.value),
]

# Contact types for control
CONTACT_TYPES = [
    ("NC", SensorContactTypes.NC.value),
    ("NO", SensorContactTypes.NO.value),
]

# channel error states
CHANNEL_CUT = wiring_config.open_circuit
CHANNEL_SHORTAGE = wiring_config.shortcut

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
        width: 45;
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
        width: 10;
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

    def __init__(
        self, default_states, channel_configs, is_advanced_mode=False, show_voltage=False, **kwargs
    ):
        super().__init__(**kwargs)
        self._default_states = default_states
        self._channel_configs = channel_configs
        self._is_advanced_mode = is_advanced_mode
        self._show_voltage = show_voltage

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
                        config = self._channel_configs.get(ch_key)
                        if config is None:
                            config = ChannelConfig(
                                wiring_strategy=WiringStrategies.CUT.value,
                                contact_type=SensorContactTypes.NC,
                            )
                        wiring_strategy = config.wiring_strategy
                        contact_type = config.contact_type.value
                        sensor_a_active = config.sensor_a_active
                        sensor_b_active = config.sensor_b_active

                        with Horizontal(classes="channel-row"):
                            channel_class = self.get_channel_class(
                                wiring_strategy, sensor_a_active, sensor_b_active
                            )

                            value_str = self._format_channel_value(self._default_states[i - 1])
                            yield Static(
                                f"CH{i:02d} {value_str}",
                                id=f"channel-label-{i}",
                                classes=f"channel-label {channel_class or wiring_strategy}",
                            )

                            # Wiring strategy select (advanced mode only)
                            if self._is_advanced_mode:
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
                            if self._is_advanced_mode:
                                yield Button(
                                    "B",
                                    id=f"sensor-{i}-b",
                                    classes="sensor-button"
                                    + (" sensor-active" if sensor_b_active else ""),
                                    disabled=wiring_strategy != WiringStrategies.DUAL.value,
                                )

        yield Static("")
        yield Button("POWER", id="power", classes="power")

    def _format_channel_value(self, value):
        """
        Format channel value as voltage or raw value
        """
        if self._show_voltage:
            voltage = value * 5.0
            return f"{voltage:.2f}V"
        else:
            return f"{value:.2f}"

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


class GSM(Widget):
    """Widget for GSM controls"""

    can_focus = False

    DEFAULT_CSS = """
    GSM {
        width: 100%;
        background: black 100%;
    }

    #gsm {
        layout: vertical;
        grid-gutter: 1 1;
        width: 100%;
        height: auto;
        background: black 100%;
        overflow: auto;
    }

    #gsm Input {
        height: 3;
        width: 100%;
        margin: 0 0 1 0;
    }

    #gsm Button {
        background: green 60%;
        color: white 100%;
        height: 3;
        width: 100%;
        border: none;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="gsm"):
            yield Input(
                placeholder="Source number",
                id="gsm-source-number",
            )
            yield Input(
                value=f"Test message {randint(1000, 9999)}",
                placeholder="Message",
                id="gsm-message",
            )
            yield Button("Add SMS", id="gsm-add")


class SimulatorApp(App):
    """Simulate status of sensors and power for argus"""

    DEFAULT_CSS = """
    Screen {
        overflow: auto;
    }

    #main-grid {
        layout: grid;
        grid-size: 2;
        grid-rows: 3 31 4;
        grid-columns: 92 38;
        overflow: auto;
    }

    #top-bar {
        column-span: 2;
    }
    
    #left-pane {
    }

    #right-pane {
    }

    #keypad-pane {
        height: 20;
    }

    #gsm-pane {
        height: 12;
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
        self.is_advanced_mode = False
        self.show_voltage = False
        self.is_v3_board = environ.get("BOARD_VERSION") == "3"

    def load_configuration(self, input_number: int) -> None:
        """
        Refresh channel configurations from the database and recalculate channel values.
        """
        self.channel_configs = load_channel_configs(input_number)

        for i in range(1, input_number + 1):
            channel_name = f"CH{i:02d}"
            self.channel_values[channel_name] = self.calculate_channel_value(channel_name)

        # turn on advanced mode if v3 features are present
        new_advanced_mode = self.has_v3_features() and self.is_v3_board
        if new_advanced_mode:
            self.is_advanced_mode = new_advanced_mode

    def initialize_channels(self, input_number: int) -> None:
        """
        Initialize channel states and load channel configuration from the database.
        """
        self.channel_values = {f"CH{i:02d}": CHANNEL_CUT for i in range(1, input_number + 1)}
        self.channel_values["POWER"] = POWER_HIGH

        self.load_configuration(input_number)

    def has_v3_features(self):
        v3_features = [
            WiringStrategies.DUAL.value,
            WiringStrategies.SINGLE_WITH_2EOL.value,
        ]
        return any(
            self.channel_configs[ch].wiring_strategy in v3_features for ch in self.channel_configs
        )

    def compose(self) -> ComposeResult:
        """Add our widgets in a grid layout."""
        with Container(id="main-grid"):
            with Horizontal(id="top-bar"):
                yield Checkbox(
                    "Advanced Mode",
                    id="mode-toggle",
                    value=self.is_advanced_mode,
                    disabled=not self.is_v3_board or self.has_v3_features(),
                )
                yield Checkbox(
                    "Show Voltage",
                    id="voltage-toggle",
                    value=self.show_voltage,
                )
                yield Button(
                    "Update from database",
                    id="refresh-channels",
                    classes="refresh-button",
                )

            with Vertical(id="left-pane"):
                yield Channels(
                    id="channels-pane",
                    default_states=list(self.channel_values.values()),
                    channel_configs=self.channel_configs,
                    is_advanced_mode=self.is_advanced_mode,
                    show_voltage=self.show_voltage,
                )

            with Vertical(id="right-pane"):
                yield Keypad(id="keypad-pane")
                yield GSM(id="gsm-pane")

            yield Outputs(id="outputs-pane")

    def read_output_states(self):
        outputs = get_output_states()

        for idx, name in OUTPUT_NAMES.items():
            with suppress(NoMatches):
                checkbox = self.query_one(f"#output-{name}")
                checkbox.value = outputs[idx]

    def save_input_states(self):
        set_input_states(list(self.channel_values.values()))

    def save_keypad_states(self):
        set_keypad_state(self.keypad["pending_bits"], self.keypad["data"])
        # reset keypad state
        self.keypad = deepcopy(DEFAULT_KEYPAD)

    def on_mount(self) -> None:
        """Start background tasks when the app mounts"""
        self.set_interval(0.5, self.read_output_states)

    def calculate_channel_value(self, channel: str) -> float:
        """
        Calculate the channel value based on wiring strategy and sensor states
        """
        config = self.channel_configs[channel]
        wiring_strategy = config.wiring_strategy
        contact_type = config.contact_type
        sensor_a_active = config.sensor_a_active
        sensor_b_active = config.sensor_b_active

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

        if wiring_strategy == WiringStrategies.SINGLE_WITH_EOL.value:
            strategy = wiring_config.select_strategy(contact_type, dual=False, two_eol=False)
            return strategy.active if sensor_a_active else strategy.default
        elif wiring_strategy == WiringStrategies.SINGLE_WITH_2EOL.value:
            strategy = wiring_config.select_strategy(contact_type, dual=False, two_eol=True)
            return strategy.active if sensor_a_active else strategy.default
        elif wiring_strategy == WiringStrategies.DUAL.value:
            strategy = wiring_config.select_strategy(contact_type, dual=True, two_eol=False)
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
            config.sensor_a_active = not config.sensor_a_active
        elif sensor == "b":
            config.sensor_b_active = not config.sensor_b_active

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
        if not self.is_advanced_mode:
            return

        select_id = event.select.id
        channel_num = int(select_id.split("-")[2])
        channel_name = f"CH{channel_num:02d}"
        wiring_strategy = event.value

        # Update configuration
        config = self.channel_configs[channel_name]
        config.wiring_strategy = wiring_strategy
        config.sensor_a_active = False  # Reset sensor states
        config.sensor_b_active = False

        # Update contact type select enable/disable
        contact_disabled = wiring_strategy in ["cut", "shortage"]
        contact_select = self.query_one(f"#contact-type-{channel_num}")
        contact_select.disabled = contact_disabled

        # Update sensor button enable/disable
        sensor_a_button = self.query_one(f"#sensor-{channel_num}-a")
        sensor_b_button = self.query_one(f"#sensor-{channel_num}-b")
        sensor_a_button.disabled = config.wiring_strategy in [
            WiringStrategies.CUT.value,
            WiringStrategies.SHORTAGE.value,
        ]
        sensor_b_button.disabled = wiring_strategy != WiringStrategies.DUAL.value

        # Reset sensor button appearance
        sensor_a_button.remove_class("sensor-active")
        sensor_b_button.remove_class("sensor-active")

        # Update channel value and label
        self.update_channel_label(channel_num, channel_name, config)

        # update mode
        checkbox = self.query_one("#mode-toggle")
        checkbox.disabled = self.has_v3_features()

        self.save_input_states()

    @on(Select.Changed, "#channels-pane .contact-type-select")
    def contact_type_changed(self, event: Select.Changed) -> None:
        """Handle contact type selection changes"""
        if not self.is_advanced_mode:
            return

        select_id = event.select.id
        channel_num = int(select_id.split("-")[2])
        channel_name = f"CH{channel_num:02d}"

        # Update configuration
        config = self.channel_configs[channel_name]
        # Convert string value back to enum
        config.contact_type = (
            SensorContactTypes.NC if event.value == "NC" else SensorContactTypes.NO
        )

        # Update channel value and label
        self.update_channel_label(channel_num, channel_name, config)

        self.save_input_states()

    def update_channel_label(self, channel_num, channel_name, config):
        self.channel_values[channel_name] = self.calculate_channel_value(channel_name)
        channel_label = self.query_one(f"#channel-label-{channel_num}")
        value_str = self._format_channel_value(self.channel_values[channel_name])
        channel_label.update(f"CH{channel_num:02d} {value_str}")
        channel_label.set_classes(
            [
                "channel-label",
                Channels.get_channel_class(
                    config.wiring_strategy, config.sensor_a_active, config.sensor_b_active
                )
                or config.wiring_strategy,
            ]
        )

    def _format_channel_value(self, value):
        """
        Format channel value as voltage or raw value
        """
        if self.show_voltage:
            voltage = value * 5.0
            return f"{voltage:.2f}V"
        else:
            return f"{value:.2f}"

    @on(Checkbox.Changed, "#mode-toggle")
    async def mode_toggle_changed(self, event: Checkbox.Changed) -> None:
        """Toggle between basic and advanced mode"""
        self.is_advanced_mode = event.value
        await self.recompose()

    @on(Checkbox.Changed, "#voltage-toggle")
    async def voltage_toggle_changed(self, event: Checkbox.Changed) -> None:
        """Toggle between raw values and voltage display"""
        self.show_voltage = event.value
        await self.recompose()

    @on(Button.Pressed, "#refresh-channels")
    async def refresh_channels_pressed(self, _event: Button.Pressed) -> None:
        """Reload channel settings and the GSM source number from the database."""
        input_number = int(environ.get("INPUT_NUMBER", 15))
        self.load_configuration(input_number)
        self.save_input_states()

        with create_database_session() as session:
            config = GSMConfig.load_config(session=session) or GSMConfig()
        self.query_one("#gsm-source-number", Input).value = config.phone_number_1 or ""

        await self.recompose()

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

    @on(Button.Pressed, "#gsm-add")
    def gsm_add_pressed(self, _event: Button.Pressed) -> None:
        """Add an incoming SMS to the mock GSM message queue."""
        source_number = self.query_one("#gsm-source-number", Input).value
        message = self.query_one("#gsm-message", Input).value
        append_sms_message(source_number, message, datetime.now().astimezone())


logging.basicConfig(
    level="NOTSET",
    handlers=[TextualHandler()],
    format="%(asctime)s: %(message)s",
)


def main():
    """Main entry point for the simulator application."""
    app = SimulatorApp()
    # Initialize channel values and states from saved data
    app.initialize_channels(int(environ.get("INPUT_NUMBER", 15)))

    # Save initial states only after initialization
    app.save_input_states()
    app.save_keypad_states()
    app.run()


if __name__ == "__main__":
    main()
