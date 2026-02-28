from dataclasses import asdict
import json

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from monitor.database import get_database_session
from server.ipc import IPCClient
from server.services.area import AreaService
from server.services.option import (
    AlertSensitivityService,
    DyndnsService,
    GSMService,
    MQTTService,
    SMTPService,
    SSHService,
    SubscriptionsService,
    SyrenService,
)
from server.services.output import OutputService
from server.services.sensor import SensorService
from server.services.zone import ZoneService
from server.tools import evaluate_ipc_response
from utils.constants import ARM_DISARM
from utils.queries import get_arm_state

monitoring_mcp = FastMCP("ArPI - monitoring service")


session = get_database_session()


@monitoring_mcp.resource(
    uri="objects://list",
    name="all_objects",
    mime_type="application/json",
    description="Resource to retrieve all objects in the system",
)
def get_all_objects() -> str:
    """
    Retrieve all objects in the system.
    """
    db_session = get_database_session()
    areas = [area.serialized for area in AreaService(db_session).get_areas()]
    zones = [zone.serialized for zone in ZoneService(db_session).get_zones()]
    sensors = [sensor.serialized for sensor in SensorService(db_session).get_sensors()]
    outputs = [output.serialized for output in OutputService(db_session).get_outputs()]
    return json.dumps({
        "areas": areas,
        "zones": zones,
        "sensors": sensors,
        "outputs": outputs,
    })


@monitoring_mcp.resource(
    uri="options://list",
    name="all_options",
    mime_type="application/json",
    description="Resource to retrieve all options in the system",
)
def get_all_options() -> str:
    """
    Retrieve all options in the system.
    """
    db_session = get_database_session()
    alert_sensitivity = AlertSensitivityService(db_session).get_alert_sensitivity_config()
    dyndns_config = DyndnsService(db_session).get_dyndns_config()
    gsm_config = GSMService(db_session).get_gsm_config()
    mqtt_external_publish = MQTTService(db_session).get_external_publish_config()
    mqtt_internal_read = MQTTService(db_session).get_internal_read_config()
    smtp_config = SMTPService(db_session).get_smtp_config()
    ssh_config = SSHService(db_session).get_ssh_config()
    subscriptions = SubscriptionsService(db_session).get_subscriptions_config()
    syren_config = SyrenService(db_session).get_syren_config()
    return json.dumps({
        "alert_sensitivity": asdict(alert_sensitivity),
        "dyndns": asdict(dyndns_config),
        "gsm": asdict(gsm_config),
        "mqtt_external_publish": asdict(mqtt_external_publish),
        "mqtt_internal_read": asdict(mqtt_internal_read),
        "smtp": asdict(smtp_config),
        "ssh": asdict(ssh_config),
        "subscriptions": asdict(subscriptions),
        "syren": asdict(syren_config),
    })


@monitoring_mcp.tool(
    name="update_configuration",
)
def update_configuration_tool():
    """
    Tool to trigger configuration update.
    """
    arm_state = get_arm_state(session=session)
    if arm_state != ARM_DISARM:
        raise ToolError("Cannot update configuration while system is armed.")

    response = IPCClient().update_configuration()
    if response is not None:
        _, success = evaluate_ipc_response(response)
        return "Success" if success else "Failed"

    return "Success"


@monitoring_mcp.tool(
    name="get_arm_state",
)
def get_arm_state_tool():
    """
    Tool to retrieve the current arm state.
    """
    return get_arm_state(session=session)
