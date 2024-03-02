#!/usr/bin/env python

from contextlib import suppress
import json
import threading
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


class SimulatorApp(App):
    """Simulate status of sensors and power for argus"""

    CSS = """
    Screen {
        overflow: auto;
    }

    #simulator {
        layout: grid;
        grid-size: 8;
        grid-gutter: 1 2;
        grid-columns: 1fr;
        grid-rows: 1fr 1fr 1fr 1fr 1fr 1fr;
        margin: 1 2;
        min-height: 15;
        min-width: 10;
        height: 100%;
    }

    Button {
        width: 100%;
        height: 100%;
        background: green 60%;
        color: white 100%;
        column-span: 2;
    }

    .button-pressed {
        background: red 50%;
        color: black 100%;
    }

    #channel-16 {
        column-span: 8;
    }

    #spacer-0 {
        column-span: 2;
    }

    Checkbox {
        width: 100%;
        max-height: 5;
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

    def read_output_states(self):
        lock = threading.Lock()
        with lock:
            with suppress(FileNotFoundError):
                with open(
                    "simulator_output.json", "r", encoding="utf-8"
                ) as outputs_file:
                    try:
                        outputs = json.load(outputs_file)
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
                                self.log.error(
                                    f"Invalid value for {key}: {outputs[key]}"
                                )

    @work(exclusive=True, thread=True)
    async def watch_output_states(self):
        worker = get_current_worker()
        while not worker.is_cancelled:
            self.read_output_states()
            sleep(0.5)

    def save_input_states(self):
        lock = threading.Lock()
        with lock:
            with open("simulator_input.json", "w", encoding="utf-8") as outfile:
                json.dump(self.outputs, outfile)

    def compose(self) -> ComposeResult:
        """Add our buttons."""
        with Container(id="simulator"):
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

            yield Checkbox("GO", id="id-GO", value=False, disabled=True)
            yield Checkbox("R1", id="id-R1", value=False, disabled=True)
            yield Checkbox("R0", id="id-R0", value=False, disabled=True)
            yield Checkbox("O4", id="id-O4", value=False, disabled=True)
            yield Checkbox("O3", id="id-O3", value=False, disabled=True)
            yield Checkbox("O2", id="id-O2", value=False, disabled=True)
            yield Checkbox("O1", id="id-O1", value=False, disabled=True)
            yield Checkbox("O0", id="id-O0", value=False, disabled=True)

        self.watch_output_states()

    @on(Button.Pressed, "Button, .button-pressed")
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

        self.save_input_states()


if __name__ == "__main__":
    app = SimulatorApp()
    app.save_input_states()
    app.run()
