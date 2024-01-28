#!/usr/bin/env python

import json
import threading

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button

CHANNEL_LOW = 0
CHANNEL_HIGH = 1

POWER_LOW = 0
POWER_HIGH = 1


class SimulatorApp(App):
    """Simulate status of sensors and power for argus"""

    CSS = """
    Screen {
        overflow: auto;
    }

    #simulator {
        layout: grid;
        grid-size: 4;
        grid-gutter: 1 2;
        grid-columns: 1fr;
        grid-rows: 1fr 1fr 1fr 1fr 1fr 1fr;
        margin: 1 2;
        min-height: 25;
        min-width: 26;
        height: 100%;
    }

    Button {
        width: 100%;
        height: 100%;
    }

    .button {
        background: green 60%;
        color: white 100%;
    }

    .button-pressed {
        background: red 50%;
        color: black 100%;
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
        "POWER": POWER_LOW
    }

    def save_output(self):
        lock = threading.Lock()
        with lock:
            with open('simulator_input.json', 'w', encoding='utf-8') as outfile:
                json.dump(self.outputs, outfile)

    def compose(self) -> ComposeResult:
        """Add our buttons."""
        with Container(id="simulator"):
            yield Button("CH01", id="channel-1", classes="button")
            yield Button("CH02", id="channel-2", classes="button")
            yield Button("CH03", id="channel-3", classes="button")
            yield Button("CH04", id="channel-4", classes="button")
            yield Button("CH05", id="channel-5", classes="button")
            yield Button("CH06", id="channel-6", classes="button")
            yield Button("CH07", id="channel-7", classes="button")
            yield Button("CH08", id="channel-8", classes="button")
            yield Button("CH09", id="channel-9", classes="button")
            yield Button("CH10", id="channel-10", classes="button")
            yield Button("CH11", id="channel-11", classes="button")
            yield Button("CH12", id="channel-12", classes="button")
            yield Button("CH13", id="channel-13", classes="button")
            yield Button("CH14", id="channel-14", classes="button")
            yield Button("CH15", id="channel-15", classes="button")

            yield Button("POWER", id="channel-0", classes="button")

    @on(Button.Pressed, ".button, .button-pressed")
    def button_pressed(self, event: Button.Pressed) -> None:
        """Pressed a button."""
        assert event.button.id is not None

        button_type, _, _ = event.button.id.partition("-")

        if button_type == "channel":
            if self.outputs[str(event.button.label)] == CHANNEL_LOW:
                self.outputs[str(event.button.label)] = CHANNEL_HIGH
                event.button.classes = "button-pressed"
            else:
                self.outputs[str(event.button.label)] = CHANNEL_LOW
                event.button.classes = "button"
        elif button_type == "power":
            if self.outputs[str(event.button.label)] == POWER_LOW:
                self.outputs[str(event.button.label)] = POWER_HIGH
                event.button.classes = "button-pressed"
            else:
                self.outputs[str(event.button.label)] = POWER_LOW
                event.button.classes = "button"

        self.save_output()


if __name__ == "__main__":
    app = SimulatorApp()
    app.save_output()
    app.run()
