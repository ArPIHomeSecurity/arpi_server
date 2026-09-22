"""Outputs tab widget for the simulator."""

from contextlib import suppress
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Checkbox

from monitor.adapters.mock.utils import get_output_states
from monitor.output import OUTPUT_NAMES


class Outputs(Widget):
    """Display the output states"""

    DEFAULT_CSS = Path(__file__).with_name("outputs.tcss").read_text()

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

    def on_mount(self) -> None:
        """Poll the mock output state file while the tab is mounted."""
        self.set_interval(0.5, self.read_output_states)

    def read_output_states(self):
        outputs = get_output_states()

        for idx, name in OUTPUT_NAMES.items():
            with suppress(NoMatches):
                checkbox = self.query_one(f"#output-{name}")
                checkbox.value = outputs[idx]
