"""
Area service module to handle area-related operations.
"""

from server.ipc import IPCClient
from server.services.base import (
    BaseService,
    ConfigChangesNotAllowed,
    ObjectNotChanged,
    ObjectNotFound,
)
from utils.models import Area


class ZigbeeService(BaseService):
    """
    Service for Area management operations.
    """
