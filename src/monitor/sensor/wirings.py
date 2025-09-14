"""
Sensor wiring strategies and their voltage level calculations.

NC = Normally Closed
NO = Normally Open
EOL = End Of Line resistor
"""

import logging

from functools import cached_property

from constants import LOG_ADSENSOR


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

    class SingleSensorWithEOL:
        """Single sensor configurations with one EOL resistor."""

        def __init__(self, config):
            self._config = config

        @cached_property
        def nc(self):
            """
            Access NC wiring configuration.
            """
            return self.NC(self._config)

        @cached_property
        def no(self):
            """
            Access NO wiring configuration.
            """
            return self.NO(self._config)

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
                return self._config.r_a / (self._config.r_a + self._config.r_pull_up)

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
                return self._config.r_a / (self._config.r_a + self._config.r_pull_up)

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

        @cached_property
        def nc(self):
            """
            Access NC wiring configuration.
            """
            return self.NC(self._config)

        @cached_property
        def no(self):
            """
            Access NO wiring configuration.
            """
            return self.NO(self._config)

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
                return self._config.r_a / (self._config.r_a + self._config.r_pull_up)

            @cached_property
            def active(self) -> float:
                """
                Voltage level when the sensor is triggered.
                """
                return (self._config.r_a + self._config.r_b) / (
                    self._config.r_a + self._config.r_b + self._config.r_pull_up
                )

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
                return (self._config.r_a + self._config.r_b) / (
                    self._config.r_a + self._config.r_b + self._config.r_pull_up
                )

            @cached_property
            def active(self) -> float:
                """
                Voltage level when the sensor is triggered.
                """
                return self._config.r_a / (self._config.r_a + self._config.r_pull_up)

    class DualSensor:
        """Dual sensor configurations on a single input with two EOL resistors."""

        def __init__(self, config):
            self._config = config

        @cached_property
        def nc(self):
            """
            Access NC wiring configuration.
            """
            return self.NC(self._config)

        @cached_property
        def no(self):
            """
            Access NO wiring configuration.
            """
            return self.NO(self._config)

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
                r_ab = 1 / (1 / self._config.r_a + 1 / self._config.r_b)
                return r_ab / (r_ab + self._config.r_pull_up)

            @cached_property
            def channel_a_active(self) -> float:
                """
                Voltage level when only sensor A is triggered.
                """
                return self._config.r_b / (self._config.r_b + self._config.r_pull_up)

            @cached_property
            def channel_b_active(self) -> float:
                """
                Voltage level when only sensor B is triggered.
                """
                return self._config.r_a / (self._config.r_a + self._config.r_pull_up)

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
                return (self._config.r_a + self._config.r_b) / (
                    self._config.r_a + self._config.r_b + self._config.r_pull_up
                )

            @cached_property
            def channel_a_active(self) -> float:
                """
                Voltage level when only sensor A is triggered.
                """
                return self._config.r_b / (self._config.r_b + self._config.r_pull_up)

            @cached_property
            def channel_b_active(self) -> float:
                """
                Voltage level when only sensor B is triggered.
                """
                return self._config.r_a / (self._config.r_a + self._config.r_pull_up)

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
        logger.debug("  Default Level: %.3f", self.single_with_eol.nc.default)
        logger.debug("  Active Level: %.3f", self.single_with_eol.nc.active)
        logger.debug("NO with EOL:")
        logger.debug("  Default Level: %.3f", self.single_with_eol.no.default)
        logger.debug("  Active Level: %.3f", self.single_with_eol.no.active)
        logger.debug("NC with 2 EOL:")
        logger.debug("  Default Level: %.3f", self.single_sensor_2_eol.nc.default)
        logger.debug("  Active Level: %.3f", self.single_sensor_2_eol.nc.active)
        logger.debug("NO with 2 EOL:")
        logger.debug("  Default Level: %.3f", self.single_sensor_2_eol.no.default)
        logger.debug("  Active Level: %.3f", self.single_sensor_2_eol.no.active)
        logger.debug("2 NC with EOL:")
        logger.debug("  Default Level (Both Closed): %.3f", self.dual.nc.default)
        logger.debug("  Channel A Active Level (A Open): %.3f", self.dual.nc.channel_a_active)
        logger.debug("  Channel B Active Level (B Open): %.3f", self.dual.nc.channel_b_active)
        logger.debug("  Both Active Level (Both Open): %.3f", self.dual.nc.both_active)
        logger.debug("2 NO with EOL:")
        logger.debug("  Default Level (Both Open): %.3f", self.dual.no.default)
        logger.debug("  Channel A Active Level (A Closed): %.3f", self.dual.no.channel_a_active)
        logger.debug("  Channel B Active Level (B Closed): %.3f", self.dual.no.channel_b_active)
        logger.debug("  Both Active Level (Both Closed): %.3f", self.dual.no.both_active)
