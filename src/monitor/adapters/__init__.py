"""
Definition of the GPIO pins used by the monitor
for communication with the ArPI board.
"""

# Power pin
POWER_PIN = 8 # BOARD PIN 24


# Output channel pins - SPI communication (V2)
LATCH_PIN_V2 = 27 # BOARD PIN 13
ENABLE_PIN_V2 = 22 # BOARD PIN 15
CLOCK_PIN_V2 = 11 # BOARD PIN 23
DATA_IN_PIN_V2 = 10 # BOARD PIN 19
DATA_OUT_PIN_V2 = 9 # BOARD PIN 21

# Output channel pins - SPI communication (V3)
LATCH_PIN_V3 = 16 # BOARD PIN 36
ENABLE_PIN_V3 = 26 # BOARD PIN 37
CLOCK_PIN_V3 = 21 # BOARD PIN 40
DATA_IN_PIN_V3 = 19 # BOARD PIN 35
DATA_OUT_PIN_V3 = 20 # BOARD PIN 38


# Wiegand pins
KEYBUS_PIN0 = 18 # BOARD PIN 12
KEYBUS_PIN1 = 17 # BOARD PIN 11
KEYBUS_PIN2 = 4 # BOARD PIN 7
