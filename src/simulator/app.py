#!/usr/bin/env python3

import logging
from os import environ
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.logging import TextualHandler
from textual.types import CSSPathType
from textual.widgets import TabbedContent, TabPane

from simulator.channels import Channels
from simulator.gsm import GSM
from simulator.keypad import Keypad
from simulator.outputs import Outputs
from simulator.zigbee import ZigbeeDevices


class SimulatorApp(App):
    """Simulate status of sensors and power for argus"""

    CSS_PATH: ClassVar[CSSPathType | None] = [Path(__file__).with_name("app.tcss")]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_v3_board = environ.get("BOARD_VERSION") == "3"

    def compose(self) -> ComposeResult:
        """Add our widgets in a tabbed layout."""
        input_number = int(environ.get("INPUT_NUMBER", "15"))
        with TabbedContent(id="simulator-tabs"):
            with TabPane("Channels", id="channels-tab"):
                yield Channels(
                    id="channels-pane",
                    input_number=input_number,
                    is_v3_board=self.is_v3_board,
                )

            with TabPane("Keypad", id="keypad-tab"):
                yield Keypad(id="keypad-pane")

            with TabPane("GSM", id="gsm-tab"):
                yield GSM(id="gsm-pane")

            with TabPane("Zigbee", id="zigbee-tab"):
                yield ZigbeeDevices(id="zigbee-pane")

            with TabPane("Outputs", id="outputs-tab"):
                yield Outputs(id="outputs-pane")


logging.basicConfig(
    level="NOTSET",
    handlers=[TextualHandler()],
    format="%(asctime)s: %(message)s",
)


def main():
    """Main entry point for the simulator application."""
    app = SimulatorApp()
    app.run()


if __name__ == "__main__":
    main()
