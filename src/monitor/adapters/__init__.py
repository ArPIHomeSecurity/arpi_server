"""
Definition of the GPIO pins used by the monitor
for communication with the ArPI board.
"""


class V2BoardPin:
    """
    GPIO pin definitions for the V2 board.
    """

    # Sensor input channel pins (V2)
    CH01_PIN = 19  # BOARD PIN 35
    CH02_PIN = 20  # BOARD PIN 38
    CH03_PIN = 26  # BOARD PIN 37
    CH04_PIN = 21  # BOARD PIN 40
    CH05_PIN = 12  # BOARD PIN 32
    CH06_PIN = 6  # BOARD PIN 31
    CH07_PIN = 13  # BOARD PIN 33
    CH08_PIN = 16  # BOARD PIN 36
    CH09_PIN = 7  # BOARD PIN 26
    CH10_PIN = 1  # BOARD PIN 28
    CH11_PIN = 0  # BOARD PIN 23
    CH12_PIN = 5  # BOARD PIN 29
    CH13_PIN = 23  # BOARD PIN 16
    CH14_PIN = 24  # BOARD PIN 18
    CH15_PIN = 25  # BOARD PIN 22

    # Power pin
    POWER_PIN = 8  # BOARD PIN 24

    # Wiegand pins
    KEYBUS_PIN0 = 18  # BOARD PIN 12
    KEYBUS_PIN1 = 17  # BOARD PIN 11
    KEYBUS_PIN2 = 4  # BOARD PIN 7

    # Output channel pins - SPI communication (V2)
    LATCH_PIN = 27  # BOARD PIN 13
    ENABLE_PIN = 22  # BOARD PIN 15
    CLOCK_PIN = 11  # BOARD PIN 23
    DATA_IN_PIN = 10  # BOARD PIN 19
    DATA_OUT_PIN = 9  # BOARD PIN 21


class V3BoardPin:
    """
    GPIO pin definitions for the V3 board.
    """

    # Sensor input channel pins V3
    SENSOR_MOSI_PIN = 10  # BOARD PIN 19
    SENSOR_MISO_PIN = 9  # BOARD PIN 21
    SENSOR_CLOCK_PIN = 11  # BOARD PIN 23
    SENSOR_LATCH_PIN_AD1 = 8  # BOARD PIN 24 for AD1 (CE0)
    SENSOR_LATCH_PIN_AD2 = 7  # BOARD PIN 26 for AD2 (CE1)

    # Output channel pins - SPI communication (V3)
    OUTPUT_LATCH_PIN = 16  # BOARD PIN 36
    OUTPUT_ENABLE_PIN = 26  # BOARD PIN 37
    OUTPUT_CLOCK_PIN = 21  # BOARD PIN 40
    OUTPUT_DATA_IN_PIN = 19  # BOARD PIN 35
    OUTPUT_DATA_OUT_PIN = 20  # BOARD PIN 38

    # Wiegand pins
    KEYBUS_PIN0 = 12  # BOARD PIN 32
    KEYBUS_PIN1 = 6  # BOARD PIN 31
    KEYBUS_PIN2 = 13  # BOARD PIN 33
