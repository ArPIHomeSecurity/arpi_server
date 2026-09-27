from typing import Protocol

SOURCE_NETWORK = "network"
SOURCE_BATTERY = "battery"


class PowerAdapterBase(Protocol):
    """
    Determine the source of the power (network or battery)
    """

    @property
    def source_type(self) -> str:
        """
        Get the source type of the power adapter.
        """
        raise NotImplementedError
