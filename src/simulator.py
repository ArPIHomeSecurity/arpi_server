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

from monitor.adapters.mock.utils import (
    DEFAULT_KEYPAD,
    get_output_states,
    set_input_states,
    set_keypad_state,
)
from monitor.output import OUTPUT_NAMES


# Channel states
CHANNEL_CUT = 1.0
CHANNEL_DEFAULT_HIGH = 0.9
CHANNEL_A = 0.7
CHANNEL_B = 0.4
CHANNEL_A_B = 0.2
CHANNEL_SHORTAGE = 0.0

CHANNEL_STATE_TO_CLASS = {
    CHANNEL_CUT: "cut",
    CHANNEL_DEFAULT_HIGH: "default",
    CHANNEL_A: "high",
    CHANNEL_B: "middle",
    CHANNEL_A_B: "low",
    CHANNEL_SHORTAGE: "shortage",
}

POWER_LOW = 0
POWER_HIGH = 1

# <card number:pending bits>
CARD_1 = "550021576706:34"
CARD_2 = "550021576707:34"
CARD_3 = "550021576708:34"


class Channels(Widget):
    """Display and control the channels"""

    DEFAULT_CSS = """
    .channel-row {
        width: 100%;
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

    .channel-label.shortage {
        background: yellow 100%;
        color: white;
    }

    .channel-label.cut {
        background: red 100%;
        color: white;
    }

    .channel-label.high {
        background: red 40%;
        color: white;
    }

    .channel-label.middle {
        background: red 60%;
        color: white;
    }

    .channel-label.low {
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
        width: 12;
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

    def compose(self) -> ComposeResult:
        """Create channel rows with radio buttons and A/B buttons"""
        with Vertical():
            for i in range(1, int(environ.get("INPUT_NUMBER", 15)) + 1):
                with Horizontal(classes="channel-row"):
                    yield Static(
                        f"CH{i:02d}", id=f"channel-label-{i}", classes="channel-label default"
                    )
                    with RadioSet(classes="channel-radio", id=f"channel-radio-{i}"):
                        yield RadioButton(
                            "Default",
                            value=True,
                            id=f"channel-radio-{i}-default",
                            classes="default",
                        )
                        yield RadioButton("Cut", id=f"channel-radio-{i}-cut", classes="cut")
                        yield RadioButton(
                            "Shortage", id=f"channel-radio-{i}-shortage", classes="shortage"
                        )

                    yield Button("A", classes="channel-button", id=f"channel-{i}-a")
                    yield Button("B", classes="channel-button", id=f"channel-{i}-b")

            yield Static("")
            yield Button("POWER", id="power", classes="power")


class Outputs(Widget):
    """Display the output states"""

    DEFAULT_CSS = """
    #outputs {
        background: black 100%;
    }

    #outputs Checkbox {
        width: 100%;
        height: 3;
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Create output checkboxes"""
        with Vertical(id="outputs"):
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

    #channels-pane {
        min-width: 48;
        width: 30%;
    }

    #outputs-pane {
        min-width: 10;
        width: 15%;
    }

    #keypad-pane {
        min-width: 21;
        width: 60%;
    }
    """

    channel_values = {
        "CH01": CHANNEL_DEFAULT_HIGH,
        "CH02": CHANNEL_DEFAULT_HIGH,
        "CH03": CHANNEL_DEFAULT_HIGH,
        "CH04": CHANNEL_DEFAULT_HIGH,
        "CH05": CHANNEL_DEFAULT_HIGH,
        "CH06": CHANNEL_DEFAULT_HIGH,
        "CH07": CHANNEL_DEFAULT_HIGH,
        "CH08": CHANNEL_DEFAULT_HIGH,
        "CH09": CHANNEL_DEFAULT_HIGH,
        "CH10": CHANNEL_DEFAULT_HIGH,
        "CH11": CHANNEL_DEFAULT_HIGH,
        "CH12": CHANNEL_DEFAULT_HIGH,
        "CH13": CHANNEL_DEFAULT_HIGH,
        "CH14": CHANNEL_DEFAULT_HIGH,
        "CH15": CHANNEL_DEFAULT_HIGH,
        "POWER": POWER_HIGH,
    }

    # Track channel states: "default", "cut", "shortage"
    channel_states = {
        f"CH{i:02d}": "default" for i in range(1, int(environ.get("INPUT_NUMBER", 15)) + 1)
    }

    # Track A/B button states for normal channels
    channel_a_active = {
        f"CH{i:02d}": False for i in range(1, int(environ.get("INPUT_NUMBER", 15)) + 1)
    }
    channel_b_active = {
        f"CH{i:02d}": False for i in range(1, int(environ.get("INPUT_NUMBER", 15)) + 1)
    }

    keypad = deepcopy(DEFAULT_KEYPAD)

    def compose(self) -> ComposeResult:
        """Add our widgets."""
        with Horizontal():
            yield Channels(id="channels-pane")
            yield Outputs(id="outputs-pane")
            yield Keypad(id="keypad-pane")

    def calculate_channel_value(self, channel):
        """Calculate the channel value based on state and A/B buttons"""
        state = self.channel_states[channel]

        if state == "cut":
            return CHANNEL_CUT
        elif state == "shortage":
            return CHANNEL_SHORTAGE
        else:  # in default state combination of A/B buttons
            a_active = self.channel_a_active[channel]
            b_active = self.channel_b_active[channel]

            if a_active and b_active:
                return CHANNEL_A_B
            elif a_active:
                return CHANNEL_A
            elif b_active:
                return CHANNEL_B
            else:
                return CHANNEL_DEFAULT_HIGH

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

    @on(Button.Pressed, "#channels-pane .channel-button")
    def channel_button_pressed(self, event: Button.Pressed) -> None:
        """Toggle channel A/B state"""
        _, channel_num, channel_type = event.button.id.split("-")
        channel_num = int(channel_num)
        channel_name = f"CH{channel_num:02d}"

        # Only allow toggle if in default state
        if self.channel_states[channel_name] == "default":
            # remove channel label class
            channel_label = self.query_one(f"#channel-label-{channel_num}")
            channel_label.remove_class(CHANNEL_STATE_TO_CLASS[self.channel_values[channel_name]])
            event.button.toggle_class("channel-active")

            if channel_type == "a":
                self.channel_a_active[channel_name] = not self.channel_a_active[channel_name]
            if channel_type == "b":
                self.channel_b_active[channel_name] = not self.channel_b_active[channel_name]

            self.channel_values[channel_name] = self.calculate_channel_value(channel_name)
            channel_label.add_class(CHANNEL_STATE_TO_CLASS[self.channel_values[channel_name]])
            self.save_input_states()

    @on(RadioSet.Changed, "#channels-pane .channel-radio")
    def radio_changed(self, event: RadioSet.Changed) -> None:
        """Handle radio button state changes"""
        radio_id = event.radio_set.id
        channel_num = int(radio_id.split("-")[2])
        channel = f"CH{channel_num:02d}"

        channel_label = self.query_one(f"#channel-label-{channel_num}")
        channel_label.remove_class(CHANNEL_STATE_TO_CLASS[self.channel_values[channel]])

        # Determine new state based on selected radio button
        if event.pressed.id.endswith("-default"):
            self.channel_states[channel] = "default"
        elif event.pressed.id.endswith("-cut"):
            channel_label.add_class("cut")
            self.channel_states[channel] = "cut"
        elif event.pressed.id.endswith("-shortage"):
            self.channel_states[channel] = "shortage"

        # Update channel value and button states
        self.channel_values[channel] = self.calculate_channel_value(channel)
        self.query_one(f"#channel-{channel_num}-a").disabled = (
            self.channel_states[channel] != "default"
        )
        self.query_one(f"#channel-{channel_num}-b").disabled = (
            self.channel_states[channel] != "default"
        )
        channel_label.add_class(CHANNEL_STATE_TO_CLASS[self.channel_values[channel]])
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
        """
        Pressed a button on the keypad.
        """
        if str(event.button.label) == "Card 1":
            self.keypad["data"].append(CARD_1.split(":")[0])
            self.keypad["pending_bits"] = int(CARD_1.split(":")[1])
        elif str(event.button.label) == "Card 2":
            self.keypad["data"].append(CARD_2.split(":")[0])
            self.keypad["pending_bits"] = int(CARD_2.split(":")[1])
        elif str(event.button.label) == "Card 3":
            self.keypad["data"].append(CARD_3.split(":")[0])
            self.keypad["pending_bits"] = int(CARD_3.split(":")[1])
        else:
            self.keypad["data"].append(str(event.button.label))
            self.keypad["pending_bits"] = len(self.keypad["data"]) * 8

        self.save_keypad_states()


logging.basicConfig(
    level="NOTSET",
    handlers=[TextualHandler()],
)
if __name__ == "__main__":
    app = SimulatorApp()
    app.save_input_states()
    app.save_keypad_states()
    app.run()
