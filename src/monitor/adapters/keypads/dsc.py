import logging
from datetime import datetime
from time import sleep, time

import RPi.GPIO as GPIO

from monitor.adapters.keypads.base import KeypadBase
from constants import LOG_ADKEYPAD

# Magic numbers
NULL = 0x00
PLACEHOLDER = 0xAA
COMMAND_0x81 = 0b10000001
COMMAND_0x01 = 0b00000001
UNKNOWN_DATA = 0b10010001  # 0x91
PARTITION_DISABLED = 0b11000111  # 0xC7
UNKNOWN_COMMAND = 0xFE
VOID = 0xFF


class Lights:
    BACKLIGHT = 0b10000000  # 0x80
    FIRE = 0b01000000  # 0x40
    PROGRAM = 0b00100000  # 0x20
    ERROR = 0b00010000  # 0x10
    BYPASS = 0b00001000  # 0x08
    MEMORY = 0b00000100  # 0x04
    ARMED = 0b00000010  # 0x02
    READY = 0b00000001  # 0x01

    def __init__(self):
        self.backlight = True
        self.fire = False
        self.program = False
        self.error = False
        self.bypass = False
        self.memory = False
        self.armed = False
        self.ready = True

    def get_lights(self):
        status = 0
        if self.backlight:
            status |= Lights.BACKLIGHT
        if self.fire:
            status |= Lights.FIRE
        if self.program:
            status |= Lights.PROGRAM
        if self.error:
            status |= Lights.ERROR
        if self.bypass:
            status |= Lights.BYPASS
        if self.memory:
            status |= Lights.MEMORY
        if self.armed:
            status |= Lights.ARMED
        if self.ready:
            status |= Lights.READY
        return status


class Buttons:
    codes = {
        0x00: "0",
        0x05: "1",
        0x0A: "2",
        0x0F: "3",
        0x11: "4",
        0x16: "5",
        0x1B: "6",
        0x1C: "7",
        0x22: "8",
        0x27: "9",
        0x28: "*",
        0x2D: "#",
        0xAF: "Stay",
        0xB1: "Away",
    }

    @staticmethod
    def get_button(value):
        try:
            return Buttons.codes[value]
        except KeyError:
            return f"{value} = ?"


class Line:
    BYTE_GAP = 0  # 0.001

    def __init__(self, clock, data):
        self._clock = clock
        self._data = data
        GPIO.setmode(GPIO.BCM)
        GPIO.setup([self._clock, self._data], GPIO.OUT)
        self.conversation = []

    def receive_bit(self):
        GPIO.output(self._clock, 0)
        GPIO.output(self._data, 1)
        sleep(0.000200)
        bit = GPIO.input(self._data)
        sleep(0.000200)
        GPIO.output(self._data, 1)
        GPIO.output(self._clock, 1)
        sleep(0.000450)

        self.conversation.append({"sent_b": 0, "received_b": bit})
        return bit

    def send_receive_byte(self, byte):
        response = "0b"
        GPIO.output(self._data, 1)
        for bit in "{0:08b}".format(byte):
            GPIO.output(self._clock, 0)
            sleep(0.000200)

            response += str(GPIO.input(self._data))
            GPIO.output(self._data, int(bit))
            sleep(0.000020)
            GPIO.output(self._clock, 1)
            sleep(0.000020)
            GPIO.output(self._data, 1)
            sleep(0.000350)

        self.conversation.append({"sent": byte, "received": int(response, 2)})
        return response

    def send_and_receive(self, messages):
        self.send_receive_byte(messages.pop(0))
        sleep(Line.BYTE_GAP)
        self.receive_bit()
        sleep(Line.BYTE_GAP)

        while messages:
            self.send_receive_byte(messages.pop(0))
            sleep(Line.BYTE_GAP)


class DSCKeypad(KeypadBase):
    # DSC COMMANDS
    KEYBUS_QUERY = 0x4C
    PARTITION_STATUS = 0x05
    ZONE_STATUS = 0x27
    ZONE_LIGHTS = 0x0A
    DATETIME_STATUS = 0xA5
    BEEP = 0x64

    def __init__(self, clock_pin, data_pin):
        super(DSCKeypad, self).__init__()
        self._logger = logging.getLogger(LOG_ADKEYPAD)
        self._lights = Lights()
        self._line = Line(clock=clock_pin, data=data_pin)
        self._start_time = None

    def initialise(self):
        # initialize connection
        self._start_time = time()
        self.send_command(self.send_partition_status)
        self.send_command(self.send_zone_status)
        self.send_command(self.send_zone_lights)
        self.send_command(self.send_datetime)

    def set_armed(self, state):
        self._lights.armed = state
        self.send_command(self.send_beep, 4)

    def set_error(self, state):
        self._lights.error = state

    def set_ready(self, state):
        self._lights.ready = state

    def communicate(self):
        self._logger.trace("Start communication DSC...")
        # send partition status info in every roud
        self.send_command(self.send_partition_status)

        # send additional info in every 4th minute
        if time() - self._start_time > 240:
            self.send_command(self.send_zone_status)
            self.send_command(self.send_zone_lights)
            self.send_command(self.send_datetime)
            self._start_time = time()

    def send_command_with_retry(self, method, param=None):
        """
        Not use, can be later deleted
        """
        BIT_PERIOD = 0.0015
        start_time = time()
        sent_bytes = self.send_command(method, param)
        safe_communication_time = BIT_PERIOD * 8 * sent_bytes + 0.008
        period = time() - start_time
        self._logger.debug("Period: %.3f > %.3f", period, safe_communication_time)

        while period > safe_communication_time:
            # clear pressed button
            self._keys = []
            self._logger.debug("RETRY: %.3f > %.3f", period, safe_communication_time)
            start_time = time()
            sent_bytes = self.send_command(method, param)
            period = time() - start_time

    def send_command(self, method, param=None):
        if param:
            method(param)
        else:
            method()

        make_keybus_query = False
        try:
            make_keybus_query = self._line.conversation[4]["received"] == UNKNOWN_COMMAND
        except IndexError:
            pass

        if self._line.conversation[2]["received"] != VOID:
            self._keys.append(Buttons.get_button(self._line.conversation[2]["received"]))

        sent_bytes = len(self._line.conversation) - 1  # remove 9. bit
        self.print_communication()

        if make_keybus_query:
            self.send_keybus_query()
            sent_bytes += len(self._line.conversation) - 1  # remove 9. bit
            self.print_communication()

        return sent_bytes

    def send_beep(self, count):
        self._logger.debug("BEEP 0x%0X x %s", self.BEEP, count)

        param = 0x04
        if count == 2:
            param = 0x04
        elif count == 3:
            param == 0x06
        elif count == 4:
            param == 0x08
        elif count == 6:
            param == 0x0C

        self._line.send_and_receive(self.add_CRC([self.BEEP, param]))

    def send_keybus_query(self):
        self._logger.info("KEYBUS QUERY 0x%0X" % self.KEYBUS_QUERY)
        self._line.send_and_receive(
            [
                self.KEYBUS_QUERY,
                PLACEHOLDER,
                PLACEHOLDER,
                PLACEHOLDER,
                PLACEHOLDER,
                PLACEHOLDER,
                PLACEHOLDER,
                PLACEHOLDER,
                PLACEHOLDER,
                PLACEHOLDER,
                PLACEHOLDER,
                PLACEHOLDER,
            ]
        )

    def send_partition_status(self):
        self._logger.debug("PARTITION STATUS 0x%0X" % self.PARTITION_STATUS)
        led_status = self._lights.get_lights()
        self._line.send_and_receive([self.PARTITION_STATUS, led_status, 0x01, UNKNOWN_DATA, PARTITION_DISABLED])

    def send_zone_status(self):
        self._logger.debug("ZONE STATUS 0x%0X" % self.ZONE_STATUS)
        led_status = self._lights.get_lights()
        self._line.send_and_receive(self.add_CRC([self.ZONE_STATUS, led_status, 0x01, UNKNOWN_DATA, 0xC7, 0x02]))

    def send_datetime(self):
        timestamp = datetime.now()
        self._logger.debug("DATETIME 0x%0X => %s" % (self.DATETIME_STATUS, timestamp.isoformat()))

        b1 = int((timestamp.year - 2000) / 10) << 4
        b1 |= 0x0F & ((timestamp.year - 2000) % 10)
        b2 = 0x3C & (timestamp.month << 2)
        b2 |= (timestamp.day & 0b00011000) >> 3
        b3 = (timestamp.day & 0b00000111) << 5
        b3 |= timestamp.hour & 0x1F
        b4 = timestamp.minute << 2
        self._line.send_and_receive(self.add_CRC([self.DATETIME_STATUS, b1, b2, b3, b4, NULL, NULL]))

    def send_zone_lights(self):
        self._logger.debug("ZONE LIGHTS 0x%0X" % self.ZONE_LIGHTS)
        led_status = self._lights.get_lights()
        self._line.send_and_receive(self.add_CRC([self.ZONE_LIGHTS, led_status, 0x01, 0x65, NULL, NULL, NULL, NULL]))

    def add_CRC(self, messages):
        total = 0
        for message in messages:
            total += message

        messages.append(total % 256)
        return messages

    def print_communication(self):
        sent = ""
        received = ""
        for message in self._line.conversation:
            if "sent_b" in message and "received_b" in message:
                sent += " {0:01b}".format(message["sent_b"])
                received += " {0:01b}".format(message["received_b"])
            elif "sent" in message and "received" in message:
                sent += " {0:08b}".format(message["sent"])
                received += " {0:08b}".format(message["received"])

        # self._logger.debug("Sent:     {}".format(sent))
        # self._logger.debug("Received: {}".format(received))
        try:
            if self._line.conversation[4]["received"] == 0xFE:
                self._logger.warning("!!! Unknown command !!!")
        except (KeyError, IndexError):
            pass

        self._line.conversation = []
