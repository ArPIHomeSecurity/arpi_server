
import logging

from gpiozero import MCP3008

from constants import LOG_ADPOWER
from monitor.adapters import V3BoardPin
from monitor.adapters.power_base import SOURCE_BATTERY, SOURCE_NETWORK


class PowerAdapter:
    """
    Determine the source of the power (network or battery) using MCP3008 AD2 pin 0 (CE1, channel 0)
    """

    def __init__(self):
        self._logger = logging.getLogger(LOG_ADPOWER)
        self._logger.debug("Power sense (MCP3008 AD2 ch0) creating...")

        try:
            self._sense = MCP3008(
                clock_pin=V3BoardPin.SENSOR_CLOCK_PIN,
                mosi_pin=V3BoardPin.SENSOR_MOSI_PIN,
                miso_pin=V3BoardPin.SENSOR_MISO_PIN,
                select_pin=V3BoardPin.SENSOR_LATCH_PIN_AD2,
                channel=0
            )
        except (OSError, ValueError, RuntimeError) as e:
            self._logger.error("Failed to init MCP3008 for power sense: %s", e)
            self._sense = None

    def __del__(self):
        self._cleanup()

    @property
    def source_type(self):
        """
        Get the source type of the power adapter.
        Uses a threshold to determine if the value indicates network or battery.
        """
        if self._sense is None:
            self._logger.error("Power sense not initialized!")
            return SOURCE_BATTERY

        try:
            value = self._sense.value
        except Exception as e:
            self._logger.error("Error reading MCP3008 for power sense: %s", e)
            return SOURCE_BATTERY

        # Threshold: <0.5 = network, >=0.5 = battery (adjust as needed)
        if value < 0.5:
            return SOURCE_NETWORK
        return SOURCE_BATTERY

    def _cleanup(self):
        """
        Close the power adapter.
        """
        if self._sense is not None:
            self._sense.close()
            self._sense = None
