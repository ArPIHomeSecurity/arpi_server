"""
Definition of the GPIO pins used by the monitor
for communication with the ArPI board.
"""

# Input channel pins
CH01_PIN = 19
CH02_PIN = 20
CH03_PIN = 26
CH04_PIN = 21
CH05_PIN = 12
CH06_PIN = 6
CH07_PIN = 13
CH08_PIN = 16
CH09_PIN = 7
CH10_PIN = 1
CH11_PIN = 0
CH12_PIN = 5
CH13_PIN = 23
CH14_PIN = 24
CH15_PIN = 25

CHANNEL_GPIO_PINS = [
    CH01_PIN,
    CH02_PIN,
    CH03_PIN,
    CH04_PIN,
    CH05_PIN,
    CH06_PIN,
    CH07_PIN,
    CH08_PIN,
    CH09_PIN,
    CH10_PIN,
    CH11_PIN,
    CH12_PIN,
    CH13_PIN,
    CH14_PIN,
    CH15_PIN,
]

# Power pin
POWER_PIN = 8

# Output channel pins - SPI communication
LATCH_PIN = 27
ENABLE_PIN = 22
CLOCK_PIN = 11
DATA_IN_PIN = 10
DATA_OUT_PIN = 9

# Wiegand pins
KEYBUS_PIN0 = 18
KEYBUS_PIN1 = 17
KEYBUS_PIN2 = 4
