SOURCE_NETWORK = "network"
SOURCE_BATTERY = "battery"


class PowerAdapterBase:
    """
    Determine the source of the power (network or battery)
    """
    @property
    def source_type(self):
        """
        Get the source type of the power adapter.
        """
        raise NotImplementedError
