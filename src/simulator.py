#!/usr/bin/env python3
"""
A Textual app to create a fully working calculator, modelled after MacOS Calculator.
"""

import json
import threading

from rich.align import Align
from rich.console import Console, ConsoleOptions, RenderResult, RenderableType
from rich.padding import Padding
from rich.text import Text

from textual.app import App
from textual.reactive import Reactive
from textual.views import GridView
from textual.widget import Widget
from textual.widgets import Button, ButtonPressed

try:
    from pyfiglet import Figlet
except ImportError:
    print("Please install pyfiglet to run this example")
    raise


class FigletText:
    """A renderable to generate figlet text that adapts to fit the container."""

    def __init__(self, text: str) -> None:
        self.text = text

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Build a Rich renderable to render the Figlet text."""
        size = min(options.max_width / 3, options.max_height / 3)
        if size < 4:
            yield Text(self.text, style="bold")
        else:
            if size < 7:
                font_name = "mini"
            elif size < 8:
                font_name = "small"
            elif size < 10:
                font_name = "standard"
            else:
                font_name = "big"
            font = Figlet(font=font_name, width=options.max_width)
            yield Text(font.renderText(self.text).rstrip("\n"), style="bold")


class Numbers(Widget):
    """The digital display of the calculator."""

    value = Reactive("0")

    def render(self) -> RenderableType:
        """Build a Rich renderable to render the calculator display."""
        return Padding(
            Align.right(FigletText(self.value), vertical="middle"),
            (0, 1),
            style="white on rgb(51,51,51)",
        )


class Calculator(GridView):
    """A working calculator app."""
    CHANNEL_LOW = 0.247828446754
    CHANNEL_HIGH = 0.727374223523
    channels = {
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
        "CH15": CHANNEL_LOW
    }

    POWER_LOW = 0.00014782522
    POWER_HIGH = 0.93736749953
    power = {
        "POWER": POWER_HIGH
    }

    DARK = "white on rgb(51,51,51)"
    LIGHT = "black on rgb(165,165,165)"
    YELLOW = "white on rgb(255,159,7)"

    display = Reactive("0")

    def watch_display(self, value: str) -> None:
        """Called when self.display is modified."""
        # self.numbers is a widget that displays the calculator result
        # Setting the attribute value changes the display
        # This allows us to write self.display = "100" to update the display
        self.channel_button.value = value

    def on_mount(self) -> None:
        """Event when widget is first mounted (added to a parent view)."""

        # The calculator display
        self.channel_button = Numbers()
        self.channel_button.style_border = "bold"

        def make_button(text: str, style: str) -> Button:
            """Create a button with the given Figlet label."""
            return Button(FigletText(text), style=style, name=text)

        # Make all the buttons
        self.buttons = {
            name: make_button(f"CH{int(name):02d}", self.DARK)
            for name in "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15".split(",")
        }

        self.power_button = Button(FigletText("POWER"), style=self.DARK, name="POWER")

        # Set basic grid settings
        self.grid.set_gap(2, 1)
        self.grid.set_gutter(1)
        self.grid.set_align("center", "center")

        # Create rows / columns / areas
        self.grid.add_column("col", max_size=30, repeat=5)
        self.grid.add_row("numbers", max_size=15, repeat=3)
        self.grid.add_row("power", max_size=15, repeat=1)
        self.grid.add_areas(
            numbers="col1-start|col3-end,numbers",
            power="col1-start|col2-end, power",
        )

        # Place out widgets in to the layout
        self.grid.place(*self.buttons.values(), numbers=self.channel_button, power=self.power_button)

    def handle_button_pressed(self, message: ButtonPressed) -> None:
        """A message sent by the button widget"""

        assert isinstance(message.sender, Button)
        button_name = message.sender.name
        self.log(f"Button pressed: {button_name}")

        if button_name.startswith("CH"):
            index = button_name.replace("CH0", "").replace("CH", "")

            self.log(f"Button style: {self.buttons[index].button_style}")

            if self.channels[button_name] == Calculator.CHANNEL_LOW:
                self.channels[button_name] = Calculator.CHANNEL_HIGH
                self.buttons[index].button_style = self.LIGHT
            else:
                self.channels[button_name] = Calculator.CHANNEL_LOW
                self.buttons[index].button_style = self.DARK

            self.buttons[index].refresh()

            lock = threading.Lock()
            with lock:
                with open("channels.json", "w") as channels_file:
                    json.dump(self.channels, channels_file)
        elif button_name == "POWER":
            if self.power["POWER"] == Calculator.POWER_LOW:
                self.power["POWER"] = Calculator.POWER_HIGH
                self.power_button.button_style = self.DARK
            else:
                self.power["POWER"] = Calculator.POWER_LOW
                self.power_button.button_style = self.LIGHT

            self.power_button.refresh()

            lock = threading.Lock()
            with lock:
                with open("power.json", "w") as power_file:
                    json.dump(self.power, power_file)


class CalculatorApp(App):
    """The Calculator Application"""

    async def on_mount(self) -> None:
        """Mount the calculator widget."""
        await self.view.dock(Calculator())


CalculatorApp.run(title="Calculator Test", log="textual.log")
