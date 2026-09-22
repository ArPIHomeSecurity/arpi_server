"""Keypad tab widget for the simulator."""

from copy import deepcopy
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Container
from textual.widget import Widget
from textual.widgets import Button

from monitor.adapters.mock.utils import DEFAULT_KEYPAD, set_keypad_state

# <card number:pending bits>
CARD_1 = "550021576706:34"
CARD_2 = "550021576707:34"
CARD_3 = "550021576708:34"


class Keypad(Widget):
    """Widget for keypad controls"""

    can_focus = False
    DEFAULT_CSS = Path(__file__).with_name("keypad.tcss").read_text()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._keypad = deepcopy(DEFAULT_KEYPAD)

    def on_mount(self) -> None:
        """Persist the initial keypad state so mock adapters can read it."""
        self.save_keypad_states()

    def save_keypad_states(self):
        set_keypad_state(self._keypad["pending_bits"], self._keypad["data"])
        # reset keypad state
        self._keypad = deepcopy(DEFAULT_KEYPAD)

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
            self._keypad["data"].append(card_data)
            self._keypad["pending_bits"] = int(pending_bits)
        else:
            self._keypad["data"].append(label)
            self._keypad["pending_bits"] = len(self._keypad["data"]) * 8

        self.save_keypad_states()

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
