
import logging
from time import sleep

from gpiozero import LED

from monitoring.adapters.keypads.base import KeypadBase
from monitoring.constants import LOG_ADKEYPAD
import wiegand_io as wr


class WiegandKeypad(KeypadBase):
    '''
    Decoding data from wiegand_io module
    Data:00000100           Bit count: 4    Pending:  4
    Data:0001000100000000   Bit count: 8    Pending:  8
    Data:0001000100000001   Bit count:12    Pending: 12
    '''
    def __init__(self, data0, data1, beeper):
        super(WiegandKeypad, self).__init__()
        self._data0 = data0
        self._data1 = data1
        self._reader = None
        self._card_number = None
        self._beeper = LED(beeper)
        self._beeper.on()
        self._logger = logging.getLogger(LOG_ADKEYPAD)

    def initialise(self):
        self._reader = wr.construct()
        wr.begin(self._reader, self._data0, self._data1)
        self._logger.info("Wiegand keypad initialized: %s", wr.isinitialized(self._reader))

        # ???
        wr.ReadData(self._reader)

    def set_error(self, state: bool):
        for _ in range(2):
            self._beeper.off()
            sleep(0.1)
            self._beeper.on()
            sleep(0.5)

    def set_ready(self, state: bool):
        pass

    def set_armed(self, state: bool):
        for _ in range(6 if state else 3):
            self._beeper.off()
            sleep(0.01)
            self._beeper.on()
            sleep(0.3)

    def communicate(self):
        pending = wr.GetPendingBitCount(self._reader)
        if pending == 0:
            return

        binary_data, bits = wr.ReadData(self._reader)
        self._logger.debug("Wiegand(Data:%s Bit count:%s Pending: %s)", binary_data, bits, pending)

        if bits in (26, 34):
            self._card_number = str(int(binary_data, 2))
            self._logger.debug("Using card: %s", self._card_number)
        else:
            self._keys += self.decode_keys(binary_data, bits)
            self._logger.debug("Pressed key: %s", self._keys)

    @staticmethod
    def decode_keys(binary, bits):
        words = []
        for idx in range(0, bits, 8):
            words.append(binary[idx:idx+8])

        keys = []
        for word in words:
            for idx in range(8-min(8, bits), 7, 4):
                if bits > 0:
                    keys.append(str(int(word[idx:idx+4], 2)))
                    bits -= 4

        return keys
