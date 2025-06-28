import logging
import os
from constants import LOG_ADSENSOR
from .sensor_base import BaseSensorAdapter

# check if running with simulator

USE_SIMULATOR = os.environ.get("USE_SIMULATOR", "false").lower() == "true"
if not USE_SIMULATOR:
    from gpiozero import MCP3008, OutputDevice
else:
    from monitor.adapters.mock.mcp3008 import MockMCP3008 as MCP3008

    class OutputDevice:
        def __init__(self, pin, active_high=True, initial_value=False):
            self.pin = pin
            self.active_high = active_high
            self.value = initial_value
            logging.getLogger(LOG_ADSENSOR).trace("OutputDevice created for pin %s", pin)

        def on(self):
            logging.getLogger(LOG_ADSENSOR).trace("OutputDevice pin %s ON", self.pin)
            self.value = True

        def off(self):
            logging.getLogger(LOG_ADSENSOR).trace("OutputDevice pin %s OFF", self.pin)
            self.value = False


class SensorAdapterV3(BaseSensorAdapter):
    """
    SPI/AD converter-based sensor adapter (board version 3)
    """

    def __init__(self):
        self._logger = logging.getLogger(LOG_ADSENSOR)
        self._output_device_class = OutputDevice
        # Channel mapping: channel index -> (AD chip, AD channel)
        self._channel_map = [
            (1, 0),  # CH1
            (1, 1),  # CH2
            (1, 2),  # CH3
            (1, 3),  # CH4
            (1, 4),  # CH5
            (1, 5),  # CH6
            (1, 6),  # CH7
            (1, 7),  # CH8
            (2, 0),  # CH9
            (2, 1),  # CH10
            (2, 2),  # CH11
            (2, 3),  # CH12
            (2, 4),  # CH13
            (2, 5),  # CH14
            (2, 6),  # CH15
        ]

    def get_value(self, channel):
        if not (0 <= channel < len(self._channel_map)):
            self._logger.error("Invalid channel number: %s", channel)
            return 0
        
        ad_chip, ad_channel = self._channel_map[channel]
        LATCH_GPIO = {1: 8, 2: 7}  # AD1: GPIO8 (CE0), AD2: GPIO7 (CE1)
        latch_pin = LATCH_GPIO[ad_chip]
        reader = MCP3008(clock_pin=11, mosi_pin=10, miso_pin=9, cs_pin=latch_pin, channel=ad_channel)
        value = reader.value
        self._logger.trace("ADC Value[CH%02d]: %s", channel + 1, value)
        return value

    def get_values(self):
        return [self.get_value(i) for i in range(len(self._channel_map))]

    def close(self):
        pass

    @property
    def channel_count(self):
        return len(self._channel_map)
