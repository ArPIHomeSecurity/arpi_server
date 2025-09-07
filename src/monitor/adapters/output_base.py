
class OutputAdapterBase:
    """
    Base class for output adapters.
    """

    def control_channel(self, channel: int, state: bool):
        """
        Control the state of a specific output channel.
        """
        raise NotImplementedError

    @property
    def states(self):
        """
        Get the current states of all output channels.
        """
        raise NotImplementedError
