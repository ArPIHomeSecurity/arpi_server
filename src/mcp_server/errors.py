from fastmcp.exceptions import ToolError


class ToolChangesNotAllowed(ToolError):
    """
    Raised when a configuration change is not allowed at the moment.
    """

    def __init__(self):
        super().__init__("Configuration changes are not allowed at the moment.")


class ToolObjectNotFound(ToolError):
    """
    Raised when an object is not found.
    """

    def __init__(self, object_name: str):
        super().__init__(f"{object_name} not found.")
