import logging

from gpiozero import DigitalInputDevice

from constants import LOG_ADPOWER
from monitor.adapters import V2BoardPin
from monitor.adapters.power_base import SOURCE_BATTERY, SOURCE_NETWORK


class PowerAdapter:
    """
    Determine the source of the power (network or battery)
    """

    def __init__(self):
        """
        Constructor
        """
        self._sense = None
        self._logger = logging.getLogger(LOG_ADPOWER)

        self._logger.debug("Power sense creating...")
        # the sense is on the last channel
        self._sense = DigitalInputDevice(V2BoardPin.POWER_PIN)

    def __del__(self):
        self._cleanup()

    @property
    def source_type(self):
        """
        Get the source type of the power adapter.
        """
        if self._sense.value == 0:
            return SOURCE_NETWORK

        return SOURCE_BATTERY

    def _cleanup(self):
        """
        Close the power adapter.
        """
        if self._sense is not None:
            self._sense.close()
            self._sense = None
