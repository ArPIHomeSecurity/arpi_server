from fastmcp import FastMCP

from mcp_server.area import area_mcp
from mcp_server.auth import JWTVerifier
from mcp_server.card import card_mcp
from mcp_server.monitoring import monitoring_mcp
from mcp_server.output import output_mcp
from mcp_server.option.syren import syren_option_mcp
from mcp_server.option.alert_sensitivity import alert_sensitivity_option_mcp
from mcp_server.option.dyndns import dyndns_option_mcp
from mcp_server.option.gsm import gsm_option_mcp
from mcp_server.option.ssh import ssh_option_mcp
from mcp_server.prompts import prompts_mcp
from mcp_server.sensor import sensor_mcp
from mcp_server.user import user_mcp
from mcp_server.zone import zone_mcp

from monitor.database import get_database_session
from utils.models import (
    ChannelTypes,
    SensorContactTypes,
    SensorEOLCount,
    SensorType,
)


PROMPT_DYNAMIC_DATA = """
#################################################
Dynamic Data Types:
- SensorContactTypes: {SensorContactTypes}
- SensorType: {SensorType}
- SensorEOLCount: {SensorEOLCount}
- ChannelTypes: {ChannelTypes}
"""


def mount_servers():
    """
    Setup and import all MCP servers.
    """
    main_mcp.mount(area_mcp, namespace="area")
    main_mcp.mount(card_mcp, namespace="card")
    main_mcp.mount(monitoring_mcp, namespace="monitoring")
    main_mcp.mount(output_mcp, namespace="output")
    main_mcp.mount(prompts_mcp, namespace="prompts")
    main_mcp.mount(sensor_mcp, namespace="sensor")
    main_mcp.mount(user_mcp, namespace="user")
    main_mcp.mount(zone_mcp, namespace="zone")

    main_mcp.mount(syren_option_mcp, namespace="option_syren")
    main_mcp.mount(alert_sensitivity_option_mcp, namespace="option_alert_sensitivity")
    main_mcp.mount(gsm_option_mcp, namespace="option_gsm")
    main_mcp.mount(ssh_option_mcp, namespace="option_ssh")
    main_mcp.mount(dyndns_option_mcp, namespace="option_dyndns")


def generate_system_prompt():
    """
    Generate the system prompt for the main MCP.

    Add dynamic data from the database and source code.
    """
    system_prompt = ""
    with open("src/mcp_server/prompts/general_system.txt", "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # get sensor types from the database
    db_session = get_database_session()
    sensor_types = db_session.query(SensorType).all()

    # we add data types to the main MCP for global usage
    system_prompt += PROMPT_DYNAMIC_DATA.format(
        SensorContactTypes=SensorContactTypes.__members__,
        SensorType=[f"ID:{st.id} Name:{st.name}" for st in sensor_types],
        SensorEOLCount=SensorEOLCount.__members__,
        ChannelTypes=ChannelTypes.__members__,
    )
    return system_prompt


main_mcp = FastMCP(
    "ArPI home security system",
    instructions=generate_system_prompt(),
    auth=JWTVerifier(),
)
mount_servers()

if __name__ == "__main__":
    main_mcp.run()
