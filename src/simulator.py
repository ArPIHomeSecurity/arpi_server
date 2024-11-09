#!/usr/bin/env python

from contextlib import suppress
from copy import deepcopy
import fcntl
import json
from time import sleep

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.css.query import NoMatches
from textual.widgets import Button, Checkbox, Static
from textual.worker import get_current_worker


CHANNEL_LOW = 0
CHANNEL_HIGH = 1

POWER_LOW = 0
POWER_HIGH = 1

# <card number:pending bits>
CARD_1 = "550021576706:34"
CARD_2 = "550021576707:34"
CARD_3 = "550021576708:34"


EMPTY_DATA = {
    "pending_bits": 0,
    "data": []
}


class SimulatorApp(App):
    """Simulate status of sensors and power for argus"""

    CSS = """
    Screen {
        overflow: auto;
    }

    #simulator {
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr 1fr;
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
    #channel-16 {
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

    outputs = {
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

    keypad = deepcopy(EMPTY_DATA)

    def read_output_states(self):
        with open("simulator_output.json", "r", encoding="utf-8") as outputs_file:
            try:
                outputs = json.load(outputs_file)
            except FileNotFoundError:
                return
            except json.JSONDecodeError:
                self.log.error("Error decoding simulator_output.json")
                return

            for key in outputs:
                with suppress(NoMatches):
                    checkbox = self.query_one(f"#id-{key}")
                    if outputs[key] == 0:
                        checkbox.value = False
                    elif outputs[key] == 1:
                        checkbox.value = True
                    else:
                        raise ValueError(f"Invalid value for {key}: {outputs[key]}")

    @work(exclusive=True, thread=True)
    async def watch_output_states(self):
        worker = get_current_worker()
        while not worker.is_cancelled:
            self.read_output_states()
            sleep(0.5)

    def save_input_states(self):
        with open("simulator_input.json", "w", encoding="utf-8") as inputs_file:
            fcntl.flock(inputs_file, fcntl.LOCK_EX)
            json.dump(self.outputs, inputs_file)
            fcntl.flock(inputs_file, fcntl.LOCK_UN)

    def save_keypad_states(self):
        with open("simulator_keypad.json", "r+", encoding="utf-8") as keypad_file:
            fcntl.flock(keypad_file, fcntl.LOCK_EX)
            try:
                tmp = json.load(keypad_file)
            except json.JSONDecodeError:
                tmp = deepcopy(EMPTY_DATA)
            tmp["pending_bits"] += self.keypad["pending_bits"]
            tmp["data"].extend(self.keypad["data"])
            self.keypad = deepcopy(EMPTY_DATA)
            keypad_file.seek(0)
            keypad_file.truncate()
            json.dump(tmp, keypad_file)
            fcntl.flock(keypad_file, fcntl.LOCK_UN)

    def compose(self) -> ComposeResult:
        """Add our buttons."""
        with Container(id="simulator"):
            with Container(id="channels"):
                yield Button("CH01", id="channel-1")
                yield Button("CH02", id="channel-2")
                yield Button("CH03", id="channel-3")
                yield Button("CH04", id="channel-4")
                yield Button("CH05", id="channel-5")
                yield Button("CH06", id="channel-6")
                yield Button("CH07", id="channel-7")
                yield Button("CH08", id="channel-8")
                yield Button("CH09", id="channel-9")
                yield Button("CH10", id="channel-10")
                yield Button("CH11", id="channel-11")
                yield Button("CH12", id="channel-12")
                yield Button("CH13", id="channel-13")
                yield Button("CH14", id="channel-14")
                yield Button("CH15", id="channel-15")
                yield Static("", id="spacer-0")

                yield Button("POWER", id="channel-16")

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
                yield Checkbox("GO", id="id-GO", value=False)
                yield Checkbox("R1", id="id-R1", value=False)
                yield Checkbox("R0", id="id-R0", value=False)
                yield Checkbox("O4", id="id-O4", value=False)
                yield Checkbox("O3", id="id-O3", value=False)
                yield Checkbox("O2", id="id-O2", value=False)
                yield Checkbox("O1", id="id-O1", value=False)
                yield Checkbox("O0", id="id-O0", value=False)

        self.watch_output_states()

    @on(Button.Pressed, "#channels Button")
    def channel_button_pressed(self, event: Button.Pressed) -> None:
        """
        Pressed a button on the channels.
        """
        if self.outputs[str(event.button.label)] == CHANNEL_LOW:
            self.outputs[str(event.button.label)] = CHANNEL_HIGH
            event.button.classes = "button-pressed"
        else:
            self.outputs[str(event.button.label)] = CHANNEL_LOW
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
            self.keypad["pending_bits"] = len(self.keypad["data"])*8

        self.save_keypad_states()


if __name__ == "__main__":
    app = SimulatorApp()
    app.save_input_states()
    app.run()
