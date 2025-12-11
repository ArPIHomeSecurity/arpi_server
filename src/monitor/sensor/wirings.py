"""
Sensor wiring strategies and their voltage level calculations.

Dual sensors == Zone doubling == two sensors on one input/channel.

NC = Normally Closed
NO = Normally Open
EOL = End Of Line resistor

R pull up = Pull-up resistor of the input
R pull down = Pull-down resistor of the input
Ra = EOL resistor for channel A
Rb = EOL resistor for channel B
"""

import logging

from functools import cached_property
from typing import Protocol

from utils.constants import LOG_ADSENSOR
from utils.models import SensorContactTypes


class VoltageCalculator:
    """Utility class for electrical calculations in sensor wiring configurations."""

    @staticmethod
    def voltage_divider(r_lower: float, r_upper: float) -> float:
        """
        Calculates the voltage at the first resistor (r_lower) in a voltage divider.

        Args:
            r_lower: Lower resistor value (connected to ground/reference)
            r_upper: Upper resistor value (connected to VCC)

        Returns:
            Voltage ratio (0.0 to 1.0)
        """
        return r_lower / (r_lower + r_upper)

    @staticmethod
    def parallel_resistance(*resistors: float) -> float:
        """
        Calculate equivalent resistance of resistors in parallel.

        Args:
            *resistors: Variable number of resistor values

        Returns:
            Equivalent parallel resistance
        """
        if not resistors:
            raise ValueError("At least one resistor value is required")
        return 1.0 / sum(1.0 / r for r in resistors)

    @staticmethod
    def series_resistance(*resistors: float) -> float:
        """
        Calculate equivalent resistance of resistors in series.

        Args:
            *resistors: Variable number of resistor values

        Returns:
            Equivalent series resistance
        """
        return sum(resistors)


class SingleSensorLevels(Protocol):
    """
    Interface for sensor level configurations.
    """

    @property
    def default(self) -> float:
        """
        Voltage level when the sensor is not triggered.
        """

    @property
    def active(self) -> float:
        """
        Voltage level when the sensor is triggered.
        """


class DualSensorLevels(Protocol):
    """
    Interface for dual sensor level configurations.
    """

    @property
    def default(self) -> float:
        """
        Voltage level when both sensors are not triggered.
        """

    @property
    def channel_a_active(self) -> float:
        """
        Voltage level when only sensor A is triggered.
        """

    @property
    def channel_b_active(self) -> float:
        """
        Voltage level when only sensor B is triggered.
        """

    @property
    def both_active(self) -> float:
        """
        Voltage level when both sensors are triggered.
        """


class PullUpConfig:
    """
    Calculation of levels for sensor wiring strategies with a pull-up resistor R_PULL_UP only.
    Properties are organized into logical groups using nested classes.
    """

    def __init__(self, r_pull_up: int, r_a: int, r_b: int):
        self.r_pull_up = r_pull_up
        self.r_a = r_a
        self.r_b = r_b

        # Initialize nested groups
        self.single_with_eol = self.SingleSensorWithEOL(self)
        self.single_sensor_2_eol = self.SingleSensorWith2EOL(self)
        self.dual = self.DualSensor(self)

    def select_strategy(
        self, sensor_contact_type: SensorContactTypes, dual: bool = False, two_eol: bool = False
    ) -> SingleSensorLevels | DualSensorLevels:
        """
        Select wiring strategy based on sensor contact type and configuration.
        """
        if dual and two_eol:
            raise ValueError("Dual sensors cannot have two EOL resistors.")

        if dual:
            return self.dual.select_contact_type(sensor_contact_type)
        elif two_eol:
            return self.single_sensor_2_eol.select_contact_type(sensor_contact_type)
        else:
            return self.single_with_eol.select_contact_type(sensor_contact_type)

    @property
    def shortcut(self) -> float:
        """
        Voltage level when the channel is shorted.
        """
        return 0.0

    @property
    def open_circuit(self) -> float:
        """
        Voltage level when the channel is open.
        """
        return 1.0

    class SingleSensorWithEOL:
        """Single sensor configurations with one EOL resistor."""

        def __init__(self, config):
            self._config = config
            self._nc = self.NC(config)
            self._no = self.NO(config)

        def select_contact_type(self, sensor_contact_type: SensorContactTypes):
            """
            Select NC or NO wiring configuration.
            """
            if sensor_contact_type == SensorContactTypes.NC:
                return self._nc
            elif sensor_contact_type == SensorContactTypes.NO:
                return self._no
            else:
                raise ValueError(f"Unsupported SensorContactType: {sensor_contact_type}")

        class NC:
            """
            Normally Closed single sensor with one EOL resistor.
            """

            def __init__(self, config):
                self._config = config

            @cached_property
            def default(self) -> float:
                """
                Voltage level when the sensor is not triggered.
                """
                return VoltageCalculator.voltage_divider(self._config.r_a, self._config.r_pull_up)

            @cached_property
            def active(self) -> float:
                """
                Voltage level when the sensor is triggered.
                """
                return 1.0

        class NO:
            """Normally Open single sensor."""

            def __init__(self, config):
                self._config = config

            @cached_property
            def default(self) -> float:
                """
                Voltage level when the sensor is not triggered.
                """
                return VoltageCalculator.voltage_divider(self._config.r_a, self._config.r_pull_up)

            @cached_property
            def active(self) -> float:
                """
                Voltage level when the sensor is triggered.
                """
                return 0.0

    class SingleSensorWith2EOL:
        """Single sensor configurations with two EOL resistors."""

        def __init__(self, config):
            self._config = config
            self._nc = self.NC(config)
            self._no = self.NO(config)

        def select_contact_type(self, sensor_contact_type: SensorContactTypes):
            """
            Select NC or NO wiring configuration.
            """
            if sensor_contact_type == SensorContactTypes.NC:
                return self._nc
            elif sensor_contact_type == SensorContactTypes.NO:
                return self._no
            else:
                raise ValueError(f"Unsupported SensorContactType: {sensor_contact_type}")

        class NC:
            """
            Normally Closed with two EOL resistors.
            """

            def __init__(self, config):
                self._config = config

            @cached_property
            def default(self) -> float:
                """
                Voltage level when the sensor is not triggered.
                """
                return VoltageCalculator.voltage_divider(self._config.r_a, self._config.r_pull_up)

            @cached_property
            def active(self) -> float:
                """
                Voltage level when the sensor is triggered.
                """
                r_series = VoltageCalculator.series_resistance(self._config.r_a, self._config.r_b)
                return VoltageCalculator.voltage_divider(r_series, self._config.r_pull_up)

        class NO:
            """
            Normally Open with two EOL resistors.
            """

            def __init__(self, config):
                self._config = config

            @cached_property
            def default(self) -> float:
                """
                Voltage level when the sensor is not triggered.
                """
                r_series = VoltageCalculator.series_resistance(self._config.r_a, self._config.r_b)
                return VoltageCalculator.voltage_divider(r_series, self._config.r_pull_up)

            @cached_property
            def active(self) -> float:
                """
                Voltage level when the sensor is triggered.
                """
                return VoltageCalculator.voltage_divider(self._config.r_a, self._config.r_pull_up)

    class DualSensor:
        """Dual sensor configurations on a single input with two EOL resistors."""

        def __init__(self, config):
            self._config = config
            self._nc = self.NC(config)
            self._no = self.NO(config)

        def select_contact_type(self, sensor_contact_type: SensorContactTypes):
            """
            Select NC or NO wiring configuration.
            """
            if sensor_contact_type == SensorContactTypes.NC:
                return self._nc
            elif sensor_contact_type == SensorContactTypes.NO:
                return self._no
            else:
                raise ValueError(f"Unsupported SensorContactType: {sensor_contact_type}")

        class NC:
            """
            Dual Normally Closed sensors with two EOL resistors.
            """

            def __init__(self, config):
                self._config = config

            @cached_property
            def default(self) -> float:
                """
                Voltage level when both sensors are not triggered.
                """
                r_ab = VoltageCalculator.parallel_resistance(self._config.r_a, self._config.r_b)
                return VoltageCalculator.voltage_divider(r_ab, self._config.r_pull_up)

            @cached_property
            def channel_a_active(self) -> float:
                """
                Voltage level when only sensor A is triggered.
                """
                return VoltageCalculator.voltage_divider(self._config.r_b, self._config.r_pull_up)

            @cached_property
            def channel_b_active(self) -> float:
                """
                Voltage level when only sensor B is triggered.
                """
                return VoltageCalculator.voltage_divider(self._config.r_a, self._config.r_pull_up)

            @cached_property
            def both_active(self) -> float:
                """
                Voltage level when both sensors are triggered.
                """
                return 1.0

        class NO:
            """
            Dual Normally Open sensors with two EOL resistors.
            """

            def __init__(self, config):
                self._config = config

            @cached_property
            def default(self) -> float:
                """
                Voltage level when both sensors are not triggered.
                """
                r_series = VoltageCalculator.series_resistance(self._config.r_a, self._config.r_b)
                return VoltageCalculator.voltage_divider(r_series, self._config.r_pull_up)

            @cached_property
            def channel_a_active(self) -> float:
                """
                Voltage level when only sensor A is triggered.
                """
                return VoltageCalculator.voltage_divider(self._config.r_b, self._config.r_pull_up)

            @cached_property
            def channel_b_active(self) -> float:
                """
                Voltage level when only sensor B is triggered.
                """
                return VoltageCalculator.voltage_divider(self._config.r_a, self._config.r_pull_up)

            @cached_property
            def both_active(self) -> float:
                """
                Voltage level when both sensors are triggered.
                """
                return 0.0

    def debug_values(self):
        """
        Log all calculated voltage levels.
        """
        logger = logging.getLogger(LOG_ADSENSOR)
        logger.debug("Pull-Up Resistor: R_PULL_UP = %d ohm", self.r_pull_up)
        logger.debug("EOL Resistor A: R_A = %d ohm", self.r_a)
        logger.debug("EOL Resistor B: R_B = %d ohm", self.r_b)
        logger.debug("NC with EOL:")
        logger.debug(
            "  Default Level: %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=False, two_eol=False).default,
        )
        logger.debug(
            "  Active Level: %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=False, two_eol=False).active,
        )
        logger.debug("NO with EOL:")
        logger.debug(
            "  Default Level: %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=False, two_eol=False).default,
        )
        logger.debug(
            "  Active Level: %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=False, two_eol=False).active,
        )
        logger.debug("Error Conditions:")
        logger.debug("  Shortcut Level: %.3f", self.shortcut)
        logger.debug("  Open Circuit Level: %.3f", self.open_circuit)
        logger.debug("NC with 2 EOL:")
        logger.debug(
            "  Default Level: %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=False, two_eol=True).default,
        )
        logger.debug(
            "  Active Level: %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=False, two_eol=True).active,
        )
        logger.debug("NO with 2 EOL:")
        logger.debug(
            "  Default Level: %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=False, two_eol=True).default,
        )
        logger.debug(
            "  Active Level: %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=False, two_eol=True).active,
        )
        logger.debug("2 NC with EOL:")
        logger.debug(
            "  Default Level (Both Closed): %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=True, two_eol=False).default,
        )
        logger.debug(
            "  Channel A Active Level (A Open): %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=True, two_eol=False).channel_a_active,
        )
        logger.debug(
            "  Channel B Active Level (B Open): %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=True, two_eol=False).channel_b_active,
        )
        logger.debug(
            "  Both Active Level (Both Open): %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=True, two_eol=False).both_active,
        )
        logger.debug("2 NO with EOL:")
        logger.debug(
            "  Default Level (Both Open): %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=True, two_eol=False).default,
        )
        logger.debug(
            "  Channel A Active Level (A Closed): %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=True, two_eol=False).channel_a_active,
        )
        logger.debug(
            "  Channel B Active Level (B Closed): %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=True, two_eol=False).channel_b_active,
        )
        logger.debug(
            "  Both Active Level (Both Closed): %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=True, two_eol=False).both_active,
        )


class PullUpDownConfig:
    """
    Calculation of levels for sensor wiring strategies with both pull-up and pull-down resistors.
    """

    def __init__(self, r_pull_up: int, r_pull_down: int, r_a: int, r_b: int):
        self.r_pull_up = r_pull_up
        self.r_pull_down = r_pull_down
        self.r_a = r_a
        self.r_b = r_b

        self.single_with_eol = self.SingleSensorWithEOL(self)
        self.single_sensor_2_eol = self.SingleSensorWith2EOL(self)
        self.dual = self.DualSensor(self)

    def select_strategy(
        self, sensor_contact_type: SensorContactTypes, dual: bool = False, two_eol: bool = False
    ) -> SingleSensorLevels | DualSensorLevels:
        """
        Select wiring strategy based on sensor contact type and configuration.
        """
        if dual and two_eol:
            raise ValueError("Dual sensors cannot have two EOL resistors.")

        if dual:
            return self.dual.select_contact_type(sensor_contact_type)
        elif two_eol:
            return self.single_sensor_2_eol.select_contact_type(sensor_contact_type)
        else:
            return self.single_with_eol.select_contact_type(sensor_contact_type)

    @property
    def shortcut(self) -> float:
        """
        Voltage level when the channel is shorted.
        """
        return 0.0

    @property
    def open_circuit(self) -> float:
        """
        Voltage level when the channel is open.
        """
        return VoltageCalculator.voltage_divider(self.r_pull_down, self.r_pull_up)

    class SingleSensorWithEOL:
        """
        Single sensor configurations with one EOL resistor.
        """

        def __init__(self, config):
            self._config = config
            self._nc = self.NC(config)
            self._no = self.NO(config)

        def select_contact_type(self, sensor_contact_type: SensorContactTypes):
            """
            Select NC or NO wiring configuration.
            """
            if sensor_contact_type == SensorContactTypes.NC:
                return self._nc
            elif sensor_contact_type == SensorContactTypes.NO:
                return self._no
            else:
                raise ValueError(f"Unsupported SensorContactType: {sensor_contact_type}")

        class NC:
            """
            Normally Closed single sensor with one EOL resistor.
            """

            def __init__(self, config):
                self._config = config

            @cached_property
            def default(self) -> float:
                """
                Voltage level when the sensor is not triggered.
                """
                r_total = VoltageCalculator.parallel_resistance(
                    self._config.r_a, self._config.r_pull_down
                )
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

            @cached_property
            def active(self) -> float:
                """
                Voltage level when the sensor is triggered.
                """
                r_total = self._config.r_pull_down
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

        class NO:
            """
            Normally Open single sensor with one EOL resistor.
            """

            def __init__(self, config):
                self._config = config

            @cached_property
            def default(self) -> float:
                """
                Voltage level when the sensor is not triggered.
                """
                r_total = VoltageCalculator.parallel_resistance(
                    self._config.r_a, self._config.r_pull_down
                )
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

            @cached_property
            def active(self) -> float:
                """
                Voltage level when the sensor is triggered.
                """
                return 0.0

    class SingleSensorWith2EOL:
        """
        Single sensor configurations with two EOL resistors.
        """

        def __init__(self, config):
            self._config = config
            self._nc = self.NC(config)
            self._no = self.NO(config)

        def select_contact_type(self, sensor_contact_type: SensorContactTypes):
            """
            Select NC or NO wiring configuration.
            """
            if sensor_contact_type == SensorContactTypes.NC:
                return self._nc
            elif sensor_contact_type == SensorContactTypes.NO:
                return self._no
            else:
                raise ValueError(f"Unsupported SensorContactType: {sensor_contact_type}")

        class NC:
            """
            Normally Closed with two EOL resistors.
            """

            def __init__(self, config):
                self._config = config

            @cached_property
            def default(self) -> float:
                """
                Voltage level when the sensor is not triggered.
                """
                r_total = VoltageCalculator.parallel_resistance(
                    self._config.r_a, self._config.r_pull_down
                )
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

            @cached_property
            def active(self) -> float:
                """
                Voltage level when the sensor is triggered.
                """
                r_total = VoltageCalculator.parallel_resistance(
                    self._config.r_a, self._config.r_b, self._config.r_pull_down
                )
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

        class NO:
            """
            Normally Open with two EOL resistors.
            """

            def __init__(self, config):
                self._config = config

            @cached_property
            def default(self) -> float:
                """
                Voltage level when the sensor is not triggered.
                """
                r_total = VoltageCalculator.parallel_resistance(
                    self._config.r_a, self._config.r_b, self._config.r_pull_down
                )
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

            @cached_property
            def active(self) -> float:
                """
                Voltage level when the sensor is triggered.
                """
                r_total = VoltageCalculator.parallel_resistance(
                    self._config.r_b, self._config.r_pull_down
                )
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

    class DualSensor:
        """
        Dual sensor configurations on a single input with two EOL resistors.
        """

        def __init__(self, config):
            self._config = config
            self._nc = self.NC(config)
            self._no = self.NO(config)

        def select_contact_type(self, sensor_contact_type: SensorContactTypes):
            """
            Select NC or NO wiring configuration.
            """
            if sensor_contact_type == SensorContactTypes.NC:
                return self._nc
            elif sensor_contact_type == SensorContactTypes.NO:
                return self._no
            else:
                raise ValueError(f"Unsupported SensorContactType: {sensor_contact_type}")

        class NO:
            """
            Dual Normally Open sensors with two EOL resistors.
            """

            def __init__(self, config):
                self._config = config

            @cached_property
            def default(self) -> float:
                """
                Voltage level when both sensors are not triggered.
                """
                r_ab = VoltageCalculator.series_resistance(self._config.r_a, self._config.r_b)
                r_total = VoltageCalculator.parallel_resistance(r_ab, self._config.r_pull_down)
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

            @cached_property
            def channel_a_active(self) -> float:
                """
                Voltage level when only sensor A is triggered.
                """
                r_total = VoltageCalculator.parallel_resistance(
                    self._config.r_b, self._config.r_pull_down
                )
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

            @cached_property
            def channel_b_active(self) -> float:
                """
                Voltage level when only sensor B is triggered.
                """
                r_total = VoltageCalculator.parallel_resistance(
                    self._config.r_a, self._config.r_pull_down
                )
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

            @cached_property
            def both_active(self) -> float:
                """
                Voltage level when both sensors are triggered.
                """
                r_total = 0.0
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

        class NC:
            """
            Dual Normally Closed sensors with two EOL resistors.
            """

            def __init__(self, config):
                self._config = config

            @cached_property
            def default(self) -> float:
                """
                Voltage level when both sensors are not triggered.
                """
                r_ab = VoltageCalculator.parallel_resistance(self._config.r_a, self._config.r_b)
                r_total = VoltageCalculator.parallel_resistance(r_ab, self._config.r_pull_down)
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

            @cached_property
            def channel_a_active(self) -> float:
                """
                Voltage level when only sensor A is triggered.
                """
                r_total = VoltageCalculator.parallel_resistance(
                    self._config.r_b, self._config.r_pull_down
                )
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

            @cached_property
            def channel_b_active(self) -> float:
                """
                Voltage level when only sensor B is triggered.
                """
                r_total = VoltageCalculator.parallel_resistance(
                    self._config.r_a, self._config.r_pull_down
                )
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

            @cached_property
            def both_active(self) -> float:
                """
                Voltage level when both sensors are triggered.
                """
                r_total = self._config.r_pull_down
                return VoltageCalculator.voltage_divider(r_total, self._config.r_pull_up)

    def debug_values(self):
        """
        Log all calculated voltage levels.
        """
        logger = logging.getLogger(LOG_ADSENSOR)
        logger.debug("Pull-Up Resistor: R_PULL_UP = %d ohm", self.r_pull_up)
        logger.debug("Pull-Down Resistor: R_PULL_DOWN = %d ohm", self.r_pull_down)
        logger.debug("EOL Resistor A: R_A = %d ohm", self.r_a)
        logger.debug("EOL Resistor B: R_B = %d ohm", self.r_b)
        logger.debug("NC with EOL:")
        logger.debug(
            "  Default Level: %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=False, two_eol=False).default,
        )
        logger.debug(
            "  Active Level: %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=False, two_eol=False).active,
        )
        logger.debug("NO with EOL:")
        logger.debug(
            "  Default Level: %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=False, two_eol=False).default,
        )
        logger.debug(
            "  Active Level: %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=False, two_eol=False).active,
        )
        logger.debug("Error Conditions:")
        logger.debug("  Shortcut Level: %.3f", self.shortcut)
        logger.debug("  Open Circuit Level: %.3f", self.open_circuit)
        logger.debug("NC with 2 EOL:")
        logger.debug(
            "  Default Level: %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=False, two_eol=True).default,
        )
        logger.debug(
            "  Active Level: %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=False, two_eol=True).active,
        )
        logger.debug("NO with 2 EOL:")
        logger.debug(
            "  Default Level: %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=False, two_eol=True).default,
        )
        logger.debug(
            "  Active Level: %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=False, two_eol=True).active,
        )
        logger.debug("2 NC with EOL:")
        logger.debug(
            "  Default Level (Both Closed): %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=True, two_eol=False).default,
        )
        logger.debug(
            "  Channel A Active Level (A Open): %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=True, two_eol=False).channel_a_active,
        )
        logger.debug(
            "  Channel B Active Level (B Open): %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=True, two_eol=False).channel_b_active,
        )
        logger.debug(
            "  Both Active Level (Both Open): %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=True, two_eol=False).both_active,
        )
        logger.debug("2 NO with EOL:")
        logger.debug(
            "  Default Level (Both Open): %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=True, two_eol=False).default,
        )
        logger.debug(
            "  Channel A Active Level (A Closed): %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=True, two_eol=False).channel_a_active,
        )
        logger.debug(
            "  Channel B Active Level (B Closed): %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=True, two_eol=False).channel_b_active,
        )
        logger.debug(
            "  Both Active Level (Both Open): %.3f",
            self.select_strategy(SensorContactTypes.NC, dual=True, two_eol=False).both_active,
        )
        logger.debug("2 NO with EOL:")
        logger.debug(
            "  Default Level (Both Open): %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=True, two_eol=False).default,
        )
        logger.debug(
            "  Channel A Active Level (A Closed): %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=True, two_eol=False).channel_a_active,
        )
        logger.debug(
            "  Channel B Active Level (B Closed): %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=True, two_eol=False).channel_b_active,
        )
        logger.debug(
            "  Both Active Level (Both Closed): %.3f",
            self.select_strategy(SensorContactTypes.NO, dual=True, two_eol=False).both_active,
        )
