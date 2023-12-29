
import logging
from re import compile
from time import sleep

from gpiozero import LED
from pywiegand import WiegandReader

from monitor.adapters.keypads.base import Function, KeypadBase
from constants import LOG_ADKEYPAD


# Function key combinations
ACTION_AWAY = "#1"
ACTION_STAY = "#2"

FUNCTION_REGEX = compile(r'([#]\d)')


class WiegandKeypad(KeypadBase):
    '''
    Decoding data from wiegand_io module
    Data:00000100           Bit count: 4    Pending:  4
    Data:0001000100000000   Bit count: 8    Pending:  8
    Data:0001000100000001   Bit count:12    Pending: 12
    '''
    def __init__(self, data0, data1, beeper):
        super(WiegandKeypad, self).__init__()
        self._logger = logging.getLogger(LOG_ADKEYPAD)
        self._reader = WiegandReader(data0, data1)
        self._logger.info("Wiegand keypad created: %s", self._reader.is_initialized())
        self._function_mode = False

        # initialize sound
        self._beeper = LED(beeper)
        self._beeper.on()

    def set_error(self, state: bool):
        self.beeps(3, 0.1, 0.1)

    def set_ready(self, state: bool):
        pass

    def beeps(self, count, beep, mute):
        for _ in range(count):
            self._beeper.off()
            sleep(mute)
            self._beeper.on()
            sleep(beep)

    def set_armed(self, state: bool):
        super().set_armed(state)
        self.beeps(2, 0.1, 0.1)

    def communicate(self):
        self.manage_delay()

        pending_bits = self._reader.get_pending_bit_count()
        if pending_bits == 0:
            return

        data = self._reader.read()
        self._logger.debug("Wiegand(Data:%s Bit count:%s)", data, pending_bits)

        if pending_bits in (26, 34):
            self._card = data
            self._logger.debug("Using card: %s", self._card)
        else:
            keys = data
            self._logger.info("Pressed keys: %s", keys)
            if self._function_mode:
                # previous key was a #
                # next key is the function
                keys = list(filter(lambda k: k != '#', keys))
                if keys:
                    self.identify_function(f"#{keys[0]}")
                    self._function_mode = False
            elif ['#'] == keys:
                # only a # pressed
                self._logger.debug("Waiting for next key to identify the function...")
                self._function_mode = True
            elif '#' in keys:
                # multiple keys pressed
                matches = FUNCTION_REGEX.search(''.join(keys))
                if matches:
                    # use only the first match
                    action = matches.group()
                    self.identify_function(action)
                    self._function_mode = False
                else:
                    # no function number found => switch to function mode
                    self._function_mode = True
            else:
                # normal key presses
                self._keys += keys

    def identify_function(self, action):
        self._logger.debug("Detected action: %s", action)
        if ACTION_AWAY == action:
            self._function = Function.AWAY
        elif ACTION_STAY == action:
            self._function = Function.STAY
        else:
            self._logger.warning("Unknown function: %s", action)

    @staticmethod
    def decode_keys(binary, bits):
        """
        Reading multiple keys presses from the keypad.
        """
        words = [binary[idx:idx+8] for idx in range(0, bits, 8)]

        keys = []
        for word in words:
            for idx in range(8-min(8, bits), 7, 4):
                if bits > 0:
                    key = int(word[idx:idx+4], 2)
                    # replace number with character
                    if key == 11:
                        key = '#'
                    elif key == 12:
                        key = '*'
                    keys.append(str(key))
                    bits -= 4

        return keys
