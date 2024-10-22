BCM = "bcm"
OUT="out"

def setmode(mode):
    pass


def setup(inputs, mode):
    pass


def input(pin):
    return 0


def output(pin, value):
    pass


class LED:

    def __init__(self, pin):
        self.pin = pin
        self.state = False

    def on(self):
        pass

    def off(self):
        pass

    def close(self):
        pass
