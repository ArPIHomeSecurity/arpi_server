
class SensorAdapterBase:
    """
    Base class for sensor adapters.
    """
    def get_value(self, channel):
        """
        Get the value from the specified channel.
        """
        raise NotImplementedError

    def get_values(self):
        """
        Get the values from all channels.
        """
        raise NotImplementedError

    @property
    def channel_count(self):
        """
        Get the number of channels supported by the adapter.
        """
        raise NotImplementedError
