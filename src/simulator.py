#!/usr/bin/env python

from contextlib import suppress
from copy import deepcopy
from time import sleep

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.css.query import NoMatches
from textual.widgets import Button, Checkbox, Static
from textual.worker import get_current_worker

from monitor.adapters.mock.utils import (
    DEFAULT_KEYPAD,
    get_output_states,
    set_input_states,
    set_keypad_state,
)
from monitor.output import OUTPUT_NAMES


CHANNEL_SHORTAGE = 0
CHANNEL_LOW = 0.2
CHANNEL_NORMAL = 0.5
CHANNEL_HIGH = 0.8
CHANNEL_BROKEN = 1.0

POWER_LOW = 0
POWER_HIGH = 1

# <card number:pending bits>
CARD_1 = "550021576706:34"
CARD_2 = "550021576707:34"
CARD_3 = "550021576708:34"


class SimulatorApp(App):
    """Simulate status of sensors and power for argus"""

    CSS = """
    Screen {
        overflow: auto;
    }

    #simulator {
        layout: grid;
        grid-size: 2;
        grid-columns: 2fr 1fr;
        grid-rows: 1fr 5;
        min-height: 26;
        height: 100%;
    }

    #channels {
        layout: grid;
        grid-size: 4;
        grid-gutter: 1 2;
        grid-columns: 1fr;
        grid-rows: 1fr 1fr 1fr 1fr 1fr 1fr;
        margin: 1 2;
        min-height: 24;
        height: 100%;
    }

    #keypad {
        layout: grid;
        grid-size: 3 5;
        grid-gutter: 1 2;
        grid-columns: 1fr 1fr 1fr;
        grid-rows: 1fr 1fr 1fr 1fr;
        margin: 1 2;
        min-height: 3;
        min-width: 10;

        Button {
            background: blue 60%;
            color: white 100%;
        }
    }

    #outputs {
        column-span: 2;
        layout: grid;
        grid-size: 8;
        margin: 0 2;
        height: 3;
    }

    Button {
        min-height: 3;
        height: 100%;
        width: 100%;
        background: green 60%;
        color: white 100%;
    }

    .button-pressed {
        background: red 50%;
        color: black 100%;
    }

    /* power button */
    #input-16 {
        column-span: 8;
    }

    #spacer-0 {
        column-span: 2;
    }

    Checkbox {
        width: 100%;
        height: 3;
    }
    """

    inputs = {
        "CH01": CHANNEL_LOW,
        "CH02": CHANNEL_LOW,
        "CH03": CHANNEL_LOW,
        "CH04": CHANNEL_LOW,
        "CH05": CHANNEL_LOW,
        "CH06": CHANNEL_LOW,
        "CH07": CHANNEL_LOW,
        "CH08": CHANNEL_LOW,
        "CH09": CHANNEL_LOW,
        "CH10": CHANNEL_LOW,
        "CH11": CHANNEL_LOW,
        "CH12": CHANNEL_LOW,
        "CH13": CHANNEL_LOW,
        "CH14": CHANNEL_LOW,
        "CH15": CHANNEL_LOW,
        "POWER": POWER_LOW,
    }

    keypad = deepcopy(DEFAULT_KEYPAD)

    def read_output_states(self):
        outputs = get_output_states()

        for idx, name in OUTPUT_NAMES.items():
            with suppress(NoMatches):
                checkbox = self.query_one(f"#output-{name}")
                checkbox.value = outputs[idx]

    @work(exclusive=True, thread=True)
    async def watch_output_states(self):
        worker = get_current_worker()
        while not worker.is_cancelled:
            self.read_output_states()
            sleep(0.5)

    def save_input_states(self):
        set_input_states(list(self.inputs.values()))

    def save_keypad_states(self):
        set_keypad_state(self.keypad["pending_bits"], self.keypad["data"])
        # reset keypad state
        self.keypad = deepcopy(DEFAULT_KEYPAD)

    def compose(self) -> ComposeResult:
        """Add our buttons."""
        with Container(id="simulator"):
            with Container(id="channels"):
                yield Button("CH01", id="input-1")
                yield Button("CH02", id="input-2")
                yield Button("CH03", id="input-3")
                yield Button("CH04", id="input-4")
                yield Button("CH05", id="input-5")
                yield Button("CH06", id="input-6")
                yield Button("CH07", id="input-7")
                yield Button("CH08", id="input-8")
                yield Button("CH09", id="input-9")
                yield Button("CH10", id="input-10")
                yield Button("CH11", id="input-11")
                yield Button("CH12", id="input-12")
                yield Button("CH13", id="input-13")
                yield Button("CH14", id="input-14")
                yield Button("CH15", id="input-15")
                yield Static("", id="spacer-0")

                yield Button("POWER", id="input-16")

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

            with Container(id="outputs"):
                yield Checkbox("GO", id="output-GO", value=False)
                yield Checkbox("R1", id="output-R1", value=False)
                yield Checkbox("R0", id="output-R0", value=False)
                yield Checkbox("O4", id="output-O4", value=False)
                yield Checkbox("O3", id="output-O3", value=False)
                yield Checkbox("O2", id="output-O2", value=False)
                yield Checkbox("O1", id="output-O1", value=False)
                yield Checkbox("O0", id="output-O0", value=False)

        self.watch_output_states()

    @on(Button.Pressed, "#channels Button")
    def channel_button_pressed(self, event: Button.Pressed) -> None:
        """
        Pressed a button on the channels.
        """
        if self.inputs[str(event.button.label)] == CHANNEL_LOW:
            self.inputs[str(event.button.label)] = CHANNEL_HIGH
            event.button.classes = "button-pressed"
        else:
            self.inputs[str(event.button.label)] = CHANNEL_LOW
            event.button.classes = "button"

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


if __name__ == "__main__":
    app = SimulatorApp()
    app.save_input_states()
    app.save_keypad_states()
    app.run()
