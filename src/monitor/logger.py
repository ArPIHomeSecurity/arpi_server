from logging import Logger

from utils.constants import TRACE


class ArgusLogger(Logger):
    """
    Custom logger class for Argus.

    TODO: add logging to the database
    """

    def trace(self, message, *args, **kwargs):
        """
        Log 'message % args' with severity 'TRACE'.

        Use for logging sensitive information.
        """
        self.log(TRACE, message, *args, **kwargs)
