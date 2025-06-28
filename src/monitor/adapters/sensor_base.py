class BaseSensorAdapter:
    """
    Base class for sensor adapters.
    """
    def get_value(self, channel):
        raise NotImplementedError

    def get_values(self):
        raise NotImplementedError

    def close(self):
        pass

    @property
    def channel_count(self):
        raise NotImplementedError
