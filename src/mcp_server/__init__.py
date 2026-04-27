from importlib.resources import files

from fastmcp import FastMCP

from mcp_server.auth import JWTVerifier
from mcp_server.namespaces.area import area_mcp
from mcp_server.namespaces.arm import arm_mcp
from mcp_server.namespaces.card import card_mcp
from mcp_server.namespaces.clock import clock_mcp
from mcp_server.namespaces.generic import generic_mcp
from mcp_server.namespaces.monitoring import monitoring_mcp
from mcp_server.namespaces.option import (
    alert_sensitivity_option_mcp,
    dyndns_option_mcp,
    gsm_option_mcp,
    location_option_mcp,
    mqtt_option_mcp,
    smtp_option_mcp,
    ssh_option_mcp,
    subscriptions_option_mcp,
    syren_option_mcp,
)
from mcp_server.namespaces.keypad import keypad_mcp
from mcp_server.namespaces.output import output_mcp
from mcp_server.namespaces.prompts import prompts_mcp
from mcp_server.namespaces.sensor import sensor_mcp
from mcp_server.namespaces.user import user_mcp
from mcp_server.namespaces.zone import zone_mcp
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
    main_mcp.mount(arm_mcp, namespace="arm")
    main_mcp.mount(card_mcp, namespace="card")
    main_mcp.mount(clock_mcp, namespace="clock")
    main_mcp.mount(generic_mcp, namespace="generic")
    main_mcp.mount(keypad_mcp, namespace="keypad")
    main_mcp.mount(monitoring_mcp, namespace="monitoring")
    main_mcp.mount(output_mcp, namespace="output")
    main_mcp.mount(prompts_mcp, namespace="prompts")
    main_mcp.mount(sensor_mcp, namespace="sensor")
    main_mcp.mount(user_mcp, namespace="user")
    main_mcp.mount(zone_mcp, namespace="zone")

    main_mcp.mount(syren_option_mcp, namespace="option_syren")
    main_mcp.mount(alert_sensitivity_option_mcp, namespace="option_alert_sensitivity")
    main_mcp.mount(gsm_option_mcp, namespace="option_gsm")
    main_mcp.mount(mqtt_option_mcp, namespace="option_mqtt")
    main_mcp.mount(smtp_option_mcp, namespace="option_smtp")
    main_mcp.mount(subscriptions_option_mcp, namespace="option_subscriptions")
    main_mcp.mount(ssh_option_mcp, namespace="option_ssh")
    main_mcp.mount(dyndns_option_mcp, namespace="option_dyndns")
    main_mcp.mount(location_option_mcp, namespace="option_location")


def generate_system_prompt():
    """
    Generate the system prompt for the main MCP.

    Add dynamic data from the database and source code.
    """
    system_prompt = (
        files("mcp_server").joinpath("prompts/general_system.txt").read_text(encoding="utf-8")
    )

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
app = main_mcp.http_app()

if __name__ == "__main__":
    main_mcp.run()
