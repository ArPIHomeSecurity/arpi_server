"""Channels tab widget for the simulator."""

import logging
from os import environ
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Select, Static

from monitor.adapters.mock.utils import (
    ChannelConfig,
    WiringStrategies,
    load_channel_configs,
    set_input_states,
)
from monitor.sensor.detector import wiring_config
from utils.models import SensorContactTypes

logger = logging.getLogger("simulator")

# Wiring strategies for control
WIRING_STRATEGIES = [
    ("Single/EOL", WiringStrategies.SINGLE_WITH_EOL.value),
    ("Single/2 EOL", WiringStrategies.SINGLE_WITH_2EOL.value),
    ("Dual", WiringStrategies.DUAL.value),
    ("Cut", WiringStrategies.CUT.value),
    ("Shortage", WiringStrategies.SHORTAGE.value),
]

# Contact types for control
CONTACT_TYPES = [
    ("NC", SensorContactTypes.NC.value),
    ("NO", SensorContactTypes.NO.value),
]

# channel error states
CHANNEL_CUT = wiring_config.open_circuit
CHANNEL_SHORTAGE = wiring_config.shortcut

POWER_LOW = 0
POWER_HIGH = 1


class Channels(Widget):
    """Display and control the channels"""

    DEFAULT_CSS = Path(__file__).with_name("channels.tcss").read_text()

    def __init__(self, input_number, is_v3_board=False, **kwargs):
        super().__init__(**kwargs)
        self._is_v3_board = is_v3_board
        self._is_advanced_mode = False
        self._show_voltage = False
        self._channel_values = {}
        self._channel_configs = {}
        self.initialize_channels(input_number)

    def initialize_channels(self, input_number: int) -> None:
        """
        Initialize channel states and load channel configuration from the database.
        """
        self._channel_values = {f"CH{i:02d}": CHANNEL_CUT for i in range(1, input_number + 1)}
        self._channel_values["POWER"] = POWER_HIGH

        self.load_configuration(input_number)

    def load_configuration(self, input_number: int) -> None:
        """
        Refresh channel configurations from the database and recalculate channel values.
        """
        self._channel_configs = load_channel_configs(input_number)

        for i in range(1, input_number + 1):
            channel_name = f"CH{i:02d}"
            self._channel_values[channel_name] = self.calculate_channel_value(channel_name)

        # turn on advanced mode if v3 features are present
        if self.has_v3_features() and self._is_v3_board:
            self._is_advanced_mode = True

    def has_v3_features(self):
        v3_features = [
            WiringStrategies.DUAL.value,
            WiringStrategies.SINGLE_WITH_2EOL.value,
        ]
        return any(
            self._channel_configs[ch].wiring_strategy in v3_features for ch in self._channel_configs
        )

    def on_mount(self) -> None:
        """Persist the initial channel state so mock adapters can read it."""
        self.save_input_states()

    def compose(self) -> ComposeResult:
        """Create the action bar plus channel rows with strategy select, contact type select, and sensor buttons in two columns"""
        with Horizontal(id="channels-action-bar", classes="action-bar"):
            yield Checkbox(
                "Advanced Mode",
                id="mode-toggle",
                value=self._is_advanced_mode,
                disabled=not self._is_v3_board or self.has_v3_features(),
            )
            yield Checkbox("Show Voltage", id="voltage-toggle", value=self._show_voltage)
            yield Button("Update from database", id="channels-refresh", classes="refresh-button")

        default_states = list(self._channel_values.values())
        num_channels = len(default_states) - 1
        col1 = range(1, num_channels // 2 + 1)
        col2 = range(num_channels // 2 + 1, num_channels + 1)
        with Vertical(id="channels-container"):
            with Horizontal(id="channels"):
                for col in [col1, col2]:
                    with Vertical(classes="channel-column"):
                        for i in col:
                            ch_key = f"CH{i:02d}"
                            config = self._channel_configs.get(ch_key)
                            if config is None:
                                config = ChannelConfig(
                                    wiring_strategy=WiringStrategies.CUT.value,
                                    contact_type=SensorContactTypes.NC,
                                )

                            wiring_strategy = config.wiring_strategy
                            contact_type = config.contact_type.value
                            sensor_a_active = config.sensor_a_active
                            sensor_b_active = config.sensor_b_active

                            with Horizontal(classes="channel-row"):
                                channel_class = self.get_channel_class(
                                    wiring_strategy, sensor_a_active, sensor_b_active
                                )

                                value_str = self._format_channel_value(default_states[i - 1])
                                yield Static(
                                    f"CH{i:02d} {value_str}",
                                    id=f"channel-label-{i}",
                                    classes=f"channel-label {channel_class or wiring_strategy}",
                                )

                                # Wiring strategy select (advanced mode only)
                                if self._is_advanced_mode:
                                    yield Select(
                                        [(value, label) for value, label in WIRING_STRATEGIES],
                                        value=wiring_strategy,
                                        id=f"wiring-strategy-{i}",
                                        classes="wiring-strategy-select",
                                        allow_blank=False,
                                    )

                                    # Contact type select (disabled for cut/shortage)
                                    contact_disabled = wiring_strategy in ["cut", "shortage"]
                                    yield Select(
                                        [(value, label) for value, label in CONTACT_TYPES],
                                        value=contact_type,
                                        id=f"contact-type-{i}",
                                        classes="contact-type-select",
                                        disabled=contact_disabled,
                                        allow_blank=False,
                                    )

                                # Sensor activation buttons (only enabled for dual configurations)
                                yield Button(
                                    "A",
                                    id=f"sensor-{i}-a",
                                    classes="sensor-button"
                                    + (" sensor-active" if sensor_a_active else ""),
                                    disabled=(
                                        wiring_strategy
                                        not in [
                                            WiringStrategies.DUAL.value,
                                            WiringStrategies.SINGLE_WITH_EOL.value,
                                            WiringStrategies.SINGLE_WITH_2EOL.value,
                                        ]
                                    ),
                                )
                                if self._is_advanced_mode:
                                    yield Button(
                                        "B",
                                        id=f"sensor-{i}-b",
                                        classes="sensor-button"
                                        + (" sensor-active" if sensor_b_active else ""),
                                        disabled=wiring_strategy != WiringStrategies.DUAL.value,
                                    )

            yield Button("POWER", id="power", classes="power")

    def _format_channel_value(self, value):
        """
        Format channel value as voltage or raw value
        """
        if self._show_voltage:
            voltage = value * 5.0
            return f"{voltage:.2f}V"
        else:
            return f"{value:.2f}"

    def save_input_states(self):
        set_input_states(list(self._channel_values.values()))

    def calculate_channel_value(self, channel: str) -> float:
        """
        Calculate the channel value based on wiring strategy and sensor states
        """
        config = self._channel_configs[channel]
        wiring_strategy = config.wiring_strategy
        contact_type = config.contact_type
        sensor_a_active = config.sensor_a_active
        sensor_b_active = config.sensor_b_active

        logger.debug(
            "Calculating value channel: %s, strategy: %s, contact: %s, A active: %s, B active: %s",
            channel,
            wiring_strategy,
            contact_type,
            sensor_a_active,
            sensor_b_active,
        )

        if wiring_strategy == WiringStrategies.CUT.value:
            return CHANNEL_CUT
        elif wiring_strategy == WiringStrategies.SHORTAGE.value:
            return CHANNEL_SHORTAGE

        if wiring_strategy == WiringStrategies.SINGLE_WITH_EOL.value:
            strategy = wiring_config.select_strategy(contact_type, dual=False, two_eol=False)
            return strategy.active if sensor_a_active else strategy.default
        elif wiring_strategy == WiringStrategies.SINGLE_WITH_2EOL.value:
            strategy = wiring_config.select_strategy(contact_type, dual=False, two_eol=True)
            return strategy.active if sensor_a_active else strategy.default
        elif wiring_strategy == WiringStrategies.DUAL.value:
            strategy = wiring_config.select_strategy(contact_type, dual=True, two_eol=False)
            if sensor_a_active and sensor_b_active:
                return strategy.both_active
            elif sensor_a_active:
                return strategy.channel_a_active
            elif sensor_b_active:
                return strategy.channel_b_active
            else:
                return strategy.default
        else:
            raise ValueError(f"Unknown wiring strategy: {wiring_strategy}")

    @on(Button.Pressed, "#channels-pane .sensor-button")
    def sensor_button_pressed(self, event: Button.Pressed) -> None:
        """Toggle sensor A/B state"""
        _, channel_num, sensor = event.button.id.split("-")
        channel_num = int(channel_num)
        channel_name = f"CH{channel_num:02d}"

        config = self._channel_configs[channel_name]
        # Toggle sensor state
        if sensor == "a":
            config.sensor_a_active = not config.sensor_a_active
        elif sensor == "b":
            config.sensor_b_active = not config.sensor_b_active

        # Update button appearance
        event.button.toggle_class("sensor-active")

        # Update channel value
        self._channel_values[channel_name] = self.calculate_channel_value(channel_name)

        # Update channel label
        self.update_channel_label(channel_num, channel_name, config)

        self.save_input_states()

    @on(Select.Changed, "#channels-pane .wiring-strategy-select")
    def wiring_strategy_changed(self, event: Select.Changed) -> None:
        """Handle wiring strategy selection changes"""
        if not self._is_advanced_mode:
            return

        select_id = event.select.id
        channel_num = int(select_id.split("-")[2])
        channel_name = f"CH{channel_num:02d}"
        wiring_strategy = event.value

        # Update configuration
        config = self._channel_configs[channel_name]
        config.wiring_strategy = wiring_strategy
        config.sensor_a_active = False  # Reset sensor states
        config.sensor_b_active = False

        # Update contact type select enable/disable
        contact_disabled = wiring_strategy in ["cut", "shortage"]
        contact_select = self.query_one(f"#contact-type-{channel_num}")
        contact_select.disabled = contact_disabled

        # Update sensor button enable/disable
        sensor_a_button = self.query_one(f"#sensor-{channel_num}-a")
        sensor_b_button = self.query_one(f"#sensor-{channel_num}-b")
        sensor_a_button.disabled = config.wiring_strategy in [
            WiringStrategies.CUT.value,
            WiringStrategies.SHORTAGE.value,
        ]
        sensor_b_button.disabled = wiring_strategy != WiringStrategies.DUAL.value

        # Reset sensor button appearance
        sensor_a_button.remove_class("sensor-active")
        sensor_b_button.remove_class("sensor-active")

        # Update channel value and label
        self.update_channel_label(channel_num, channel_name, config)

        # update mode
        checkbox = self.query_one("#mode-toggle")
        checkbox.disabled = self.has_v3_features()

        self.save_input_states()

    @on(Select.Changed, "#channels-pane .contact-type-select")
    def contact_type_changed(self, event: Select.Changed) -> None:
        """Handle contact type selection changes"""
        if not self._is_advanced_mode:
            return

        select_id = event.select.id
        channel_num = int(select_id.split("-")[2])
        channel_name = f"CH{channel_num:02d}"

        # Update configuration
        config = self._channel_configs[channel_name]
        # Convert string value back to enum
        config.contact_type = (
            SensorContactTypes.NC if event.value == "NC" else SensorContactTypes.NO
        )

        # Update channel value and label
        self.update_channel_label(channel_num, channel_name, config)

        self.save_input_states()

    def update_channel_label(self, channel_num, channel_name, config):
        self._channel_values[channel_name] = self.calculate_channel_value(channel_name)
        channel_label = self.query_one(f"#channel-label-{channel_num}")
        value_str = self._format_channel_value(self._channel_values[channel_name])
        channel_label.update(f"CH{channel_num:02d} {value_str}")
        channel_label.set_classes(
            [
                "channel-label",
                Channels.get_channel_class(
                    config.wiring_strategy, config.sensor_a_active, config.sensor_b_active
                )
                or config.wiring_strategy,
            ]
        )

    @on(Checkbox.Changed, "#mode-toggle")
    async def mode_toggle_changed(self, event: Checkbox.Changed) -> None:
        """Toggle between basic and advanced mode"""
        self._is_advanced_mode = event.value
        await self.recompose()

    @on(Checkbox.Changed, "#voltage-toggle")
    async def voltage_toggle_changed(self, event: Checkbox.Changed) -> None:
        """Toggle between raw values and voltage display"""
        self._show_voltage = event.value
        await self.recompose()

    @on(Button.Pressed, "#channels-refresh")
    async def channels_refresh_pressed(self, _event: Button.Pressed) -> None:
        """Reload channel settings from the database."""
        input_number = int(environ.get("INPUT_NUMBER", 15))
        self.load_configuration(input_number)
        self.save_input_states()
        await self.recompose()

    @on(Button.Pressed, "#power")
    def power_button_pressed(self, event: Button.Pressed) -> None:
        """
        Pressed the power button.
        """
        self._channel_values["POWER"] = (
            POWER_HIGH if self._channel_values["POWER"] == POWER_LOW else POWER_LOW
        )
        event.button.toggle_class("channel-active")
        self.save_input_states()

    @staticmethod
    def get_channel_class(wiring_strategy, sensor_a_active, sensor_b_active):
        """
        Determine the CSS class for the channel label based on wiring strategy and sensor states
        """
        channel_class = None
        if wiring_strategy in [WiringStrategies.CUT.value, WiringStrategies.SHORTAGE.value]:
            channel_class = wiring_strategy
        else:
            if sensor_a_active and sensor_b_active:
                channel_class = "active"
            elif sensor_a_active or sensor_b_active:
                channel_class = "active-low"
            else:
                channel_class = "default"
        return channel_class
