#!/usr/bin/env python

from contextlib import suppress
from copy import deepcopy
import logging
from os import environ

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.css.query import NoMatches
from textual.logging import TextualHandler
from textual.widgets import Button, Checkbox, Static, RadioButton, RadioSet
from textual.widget import Widget

from monitor.sensor.detector import wiring_config
from monitor.adapters.mock.utils import (
    DEFAULT_KEYPAD,
    get_output_states,
    set_input_states,
    get_channel_types,
    set_keypad_state,
)
from monitor.output import OUTPUT_NAMES


# channel error states
CHANNEL_CUT = 1.0
CHANNEL_SHORTAGE = 0.0

# channel A and B active level
CHANNEL_A_B = wiring_config.dual.nc.both_active

# channel B active level
CHANNEL_B = wiring_config.dual.nc.channel_b_active
CHANNEL_A_DEFAULT = wiring_config.dual.nc.default

# channel A active level
CHANNEL_A = wiring_config.dual.nc.channel_a_active
CHANNEL_B_DEFAULT = wiring_config.dual.nc.default

# channel AB default when both A and B are not active
CHANNEL_AB_DEFAULT = wiring_config.dual.nc.default

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
        width: 56;
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

    .channel-label.a, .channel-label.b, .channel-label.ab {
        background: green 90%;
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

    .channel-label.low {
        background: red 40%;
        color: white;
    }

    .channel-label.middle {
        background: red 60%;
        color: white;
    }

    .channel-label.high {
        background: red 90%;
        color: white;
    }

    .channel-button {
        min-width: 3;
        width: 3;
        height: 3;
    }

    .channel-active {
        background: red 80%;
        color: white;
    }

    RadioSet {
        layout: horizontal;
        width: 100%;
        height: 3;
    }

    RadioButton.default {
        width: 6;
    }

    RadioButton.cut {
        width: 8;
    }

    RadioButton.shortage {
        width: 12;
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

    def __init__(self, default_states, channel_states, **kwargs):
        super().__init__(**kwargs)
        self._default_states = default_states
        self._channel_states = channel_states

    def compose(self) -> ComposeResult:
        """Create channel rows with radio buttons and A/B buttons in two columns"""
        num_channels = len(self._default_states) - 1
        col1 = range(1, num_channels // 2 + 1)
        col2 = range(num_channels // 2 + 1, num_channels + 1)
        with Horizontal(id="channels"):
            for col in [col1, col2]:
                with Vertical(classes="channel-column"):
                    for i in col:
                        ch_key = f"CH{i:02d}"
                        channel_type = self._channel_states.get(ch_key, "cut")
                        
                        with Horizontal(classes="channel-row"):
                            yield Static(
                                f"CH{i:02d} {self._default_states[i - 1]:.2f}V",
                                id=f"channel-label-{i}",
                                classes=f"channel-label {channel_type}",
                            )
                            with RadioSet(classes="channel-radio", id=f"channel-radio-{i}"):
                                yield RadioButton("A", id=f"channel-radio-{i}-a", classes="default", value=(channel_type == "a"))
                                yield RadioButton("B", id=f"channel-radio-{i}-b", classes="default", value=(channel_type == "b"))
                                yield RadioButton("AB", id=f"channel-radio-{i}-ab", classes="default", value=(channel_type == "ab"))
                                yield RadioButton(
                                    "Cut", value=(channel_type == "cut"), id=f"channel-radio-{i}-cut", classes="cut"
                                )
                                yield RadioButton(
                                    "Shortage", id=f"channel-radio-{i}-shortage", classes="shortage", value=(channel_type == "shortage")
                                )

                            # Set A/B button disabled states based on channel type
                            disabled_states = ["cut", "shortage"]
                            yield Button("A", id=f"channel-{i}-a", classes="channel-button", 
                                       disabled=(channel_type in disabled_states or channel_type == "b"))
                            yield Button("B", id=f"channel-{i}-b", classes="channel-button", 
                                       disabled=(channel_type in disabled_states or channel_type == "a"))

        yield Static("")
        yield Button("POWER", id="power", classes="power")


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
        height: 35;
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
        self.channel_states = {}
        self.channel_a_active = {}
        self.channel_b_active = {}

    def initialize_channels(self, input_number: int) -> None:
        """Initialize channel states and values from saved data or defaults"""
        # Load channel types from buffer file
        saved_types = get_channel_types()

        # Initialize channel dictionaries
        self.channel_values = {
            f"CH{i:02d}": CHANNEL_CUT for i in range(1, input_number + 1)
        }
        self.channel_values["POWER"] = POWER_HIGH

        self.channel_states = {
            f"CH{i:02d}": "cut" for i in range(1, input_number + 1)
        }

        self.channel_a_active = {
            f"CH{i:02d}": False for i in range(1, input_number + 1)
        }
        self.channel_b_active = {
            f"CH{i:02d}": False for i in range(1, input_number + 1)
        }

        # Apply saved types and calculate values
        for ch_key, channel_type in saved_types.items():
            if ch_key in self.channel_states:
                self.channel_states[ch_key] = channel_type
                # Reset A/B buttons to inactive state
                self.channel_a_active[ch_key] = False
                self.channel_b_active[ch_key] = False
                # Calculate initial values based on types
                self.channel_values[ch_key] = self.calculate_channel_value(ch_key)

    def compose(self) -> ComposeResult:
        """Add our widgets in a grid layout."""
        with Container(id="main-grid"):
            yield Channels(id="channels-pane", 
                         default_states=list(self.channel_values.values()),
                         channel_states=self.channel_states)
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
            [self.channel_states[f"CH{i:02d}"] for i in range(1, int(environ.get("INPUT_NUMBER", 15)) + 1)]
        )

    def save_keypad_states(self):
        set_keypad_state(self.keypad["pending_bits"], self.keypad["data"])
        # reset keypad state
        self.keypad = deepcopy(DEFAULT_KEYPAD)

    def on_mount(self) -> None:
        """Start background tasks when the app mounts"""
        self.set_interval(0.5, self.read_output_states)

    def calculate_channel_value(self, channel: str) -> float:
        """Calculate the channel value based on state and A/B buttons"""
        state = self.channel_states[channel]

        logging.debug(
            "Calculating value channel: %s, state: %s, A active: %s, B active: %s",
            channel,
            state,
            self.channel_a_active[channel],
            self.channel_b_active[channel],
        )
        if state == "cut":
            return CHANNEL_CUT
        elif state == "shortage":
            return CHANNEL_SHORTAGE
        elif state == "a":
            return CHANNEL_A if self.channel_a_active[channel] else CHANNEL_A_DEFAULT
        elif state == "b":
            return CHANNEL_B if self.channel_b_active[channel] else CHANNEL_B_DEFAULT
        elif state == "ab":
            if self.channel_a_active[channel] and self.channel_b_active[channel]:
                return CHANNEL_A_B
            if self.channel_a_active[channel]:
                return CHANNEL_A
            if self.channel_b_active[channel]:
                return CHANNEL_B
            return CHANNEL_AB_DEFAULT
        else:
            raise ValueError(f"Unknown channel state: {state}")

    @on(Button.Pressed, "#channels-pane .channel-button")
    def channel_button_pressed(self, event: Button.Pressed) -> None:
        """Toggle channel A/B state"""
        _, channel_num, state = event.button.id.split("-")
        channel_num = int(channel_num)
        channel_name = f"CH{channel_num:02d}"

        # Only allow toggle if in default state
        if self.channel_states[channel_name] in ["a", "b", "ab"]:
            # remove channel label class
            channel_label = self.query_one(f"#channel-label-{channel_num}")
            channel_label.set_classes("channel-label")
            event.button.toggle_class("channel-active")

            # update channel A/B active states
            if state == "a":
                self.channel_a_active[channel_name] = not self.channel_a_active[channel_name]
            if state == "b":
                self.channel_b_active[channel_name] = not self.channel_b_active[channel_name]

            # update channel value
            self.channel_values[channel_name] = self.calculate_channel_value(channel_name)

            # update channel label
            channel_label.update(f"CH{channel_num:02d} {self.channel_values[channel_name]:.2f}V")
            if self.channel_a_active[channel_name] and self.channel_b_active[channel_name]:
                channel_label.add_class("high")
            elif self.channel_b_active[channel_name]:
                channel_label.add_class("middle")
            elif self.channel_a_active[channel_name]:
                channel_label.add_class("low")
            else:
                channel_label.add_class(state)

            self.save_input_states()

    @on(RadioSet.Changed, "#channels-pane .channel-radio")
    def radio_changed(self, event: RadioSet.Changed) -> None:
        """Handle radio button state changes"""
        radio_id = event.radio_set.id
        channel_num = int(radio_id.split("-")[2])
        channel = f"CH{channel_num:02d}"

        # remove class based on previous state
        channel_label = self.query_one(f"#channel-label-{channel_num}")
        channel_label.set_classes("channel-label")
        logging.debug(
            "Channel state: %s, classes: %s", self.channel_states[channel], channel_label.classes
        )

        # determine new state based on selected radio button
        state = event.pressed.id.split("-")[-1]
        self.channel_states[channel] = state
        logging.debug(
            "Radio changed: %s, new state: %s", event.pressed.id, self.channel_states[channel]
        )

        # update channel value
        self.channel_values[channel] = self.calculate_channel_value(channel)

        # update A,B buttons disabled states
        disabled_states = ["cut", "shortage"]
        self.query_one(f"#channel-{channel_num}-a").disabled = (
            self.channel_states[channel] in disabled_states or state == "b"
        )
        self.query_one(f"#channel-{channel_num}-b").disabled = (
            self.channel_states[channel] in disabled_states or state == "a"
        )

        # update channel label
        channel_label.update(f"CH{channel_num:02d} {self.channel_values[channel]:.2f}V")
        if self.channel_a_active[channel] and self.channel_b_active[channel] and state == "ab":
            channel_label.add_class("high")
        elif self.channel_b_active[channel] and "b" in state:
            channel_label.add_class("middle")
        elif self.channel_a_active[channel] and "a" in state:
            channel_label.add_class("low")
        else:
            channel_label.add_class(state)

        self.save_input_states()

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
