import os

from fastmcp import FastMCP

from server.version import __version__


user_mcp = FastMCP("ArPI - user service")


@user_mcp.tool(
    name="get_version",
)
def get_version():
    """
    Tool to retrieve the version of the backend software.
    """
    return __version__


@user_mcp.tool(
    name="get_board_version",
)
def get_board_version():
    """
    Tool to retrieve the board version from the environment.
    """
    return os.environ["BOARD_VERSION"]
