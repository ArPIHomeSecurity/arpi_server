
import logging

from constants import LOG_ADSENSOR
from monitor.adapters.mock.utils import get_input_state
from monitor.adapters.power_base import SOURCE_BATTERY, SOURCE_NETWORK, PowerAdapterBase

logger = logging.getLogger(LOG_ADSENSOR)


class PowerAdapter(PowerAdapterBase):
    """
    Mock output adapter for simulator mode.
    """

    def is_initialized(self) -> bool:
        return True

    @property
    def source_type(self):
        """
        Get the source type of the power adapter.
        """
        return SOURCE_NETWORK if get_input_state("POWER") else SOURCE_BATTERY
