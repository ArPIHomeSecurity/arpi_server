"""GSM tab widget for the simulator."""

from datetime import datetime
from pathlib import Path
from random import randint

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widget import Widget
from textual.widgets import Button, Input

from monitor.adapters.mock.utils import append_sms_message
from monitor.config.models import GSMConfig
from monitor.database import create_database_session


class GSM(Widget):
    """Widget for GSM controls"""

    can_focus = False
    DEFAULT_CSS = Path(__file__).with_name("gsm.tcss").read_text()

    def compose(self) -> ComposeResult:
        with Container(id="gsm"):
            with Horizontal(id="gsm-action-bar", classes="action-bar"):
                yield Button("Update from database", id="gsm-refresh", classes="refresh-button")
            yield Input(
                placeholder="Source number",
                id="gsm-source-number",
            )
            yield Input(
                value=f"Test message {randint(1000, 9999)}",
                placeholder="Message",
                id="gsm-message",
            )
            yield Button("Add SMS", id="gsm-add")

    @on(Button.Pressed, "#gsm-refresh")
    def gsm_refresh_pressed(self, _event: Button.Pressed) -> None:
        """Reload the configured GSM source number from the database."""
        with create_database_session() as session:
            config = GSMConfig.load_config(session=session) or GSMConfig()
        self.query_one("#gsm-source-number", Input).value = config.phone_number_1 or ""

    @on(Button.Pressed, "#gsm-add")
    def gsm_add_pressed(self, _event: Button.Pressed) -> None:
        """Add an incoming SMS to the mock GSM message queue."""
        source_number = self.query_one("#gsm-source-number", Input).value
        message = self.query_one("#gsm-message", Input).value
        append_sms_message(source_number, message, datetime.now().astimezone())
