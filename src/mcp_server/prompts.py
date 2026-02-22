from fastmcp import FastMCP
from fastmcp.prompts import Message


from utils.models import ChannelTypes, SensorContactTypes, SensorEOLCount


prompts_mcp = FastMCP("ArPI - prompts service")


@prompts_mcp.prompt(name="greet_user", description="Greet a user by their name")
def greet_user(name: str) -> str:
    """
    Greet a user by their name.
    Args:
        name: The name of the user to greet.
    Returns:
        A greeting message.
    """
    return f"Greet me as {name}."


@prompts_mcp.tool(
    name="greeting", description="Generate a greeting message for a user given their name."
)
def generate_greeting(name: str) -> str:
    """
    Generate a greeting message for a user given their name.
    Args:
        name: The name of the user to greet.
    Returns:
        A greeting message.
    """
    return f"Hello, {name}! Welcome to the ArPI home security system."


@prompts_mcp.prompt(name="add_sensor", description="Add a new sensor with given parameters.")
def add_sensor(
    name: str,
    description: str = "",
    enabled: bool = True,
    silent_alert: bool = False,
    monitor_period: int = None,
    monitor_threshold=None,
    channel_type: ChannelTypes = ChannelTypes.BASIC,
    sensor_contact_type: SensorContactTypes = SensorContactTypes.NO,
    sensor_eol_count: SensorEOLCount = SensorEOLCount.SINGLE,
):
    """
    Add a new sensor with given parameters.
    Args:
        name: The name of the sensor.
        description: Optional description of the sensor.
        enabled: Whether the sensor is enabled.
        silent_alert: Whether the sensor has silent alerts.
        monitor_period: Monitoring period for the sensor.
        monitor_threshold: Monitoring threshold for the sensor.
        channel_type: The channel type of the sensor.
        sensor_contact_type: The contact type of the sensor.
        sensor_eol_count: The end-of-line count for the sensor.
    Returns:
        A confirmation message with sensor details.
    """
    return f"""We want to add a new sensor, but first we need to gather the details
        for the area, zone, and sensor type based on the provided names.
        Find the corresponding values for 'channel', 'area', 'zone', and 'sensor_type' 
        and then create the sensor with the following details:

        Sensor '{name}' as '{description}' added to channel, enabled={enabled}, 
        with the following settings:
        
        Monitoring settings:
            monitor_period={monitor_period}, monitor_threshold={monitor_threshold},
            silent_alert={silent_alert},

        Sensor specifications:
            channel_type={channel_type}, 
            sensor_contact_type={sensor_contact_type}, 
            sensor_eol_count={sensor_eol_count}."""


@prompts_mcp.prompt(
    name="first_setup_sensors",
    description="Deploy the ArPI home security system sensors to the specified environment.",
)
def first_setup_sensors() -> list[Message]:
    """
    This prompt helps the user to deploy a fresh installation of the ArPI home security system
    with sensors to the specified environment.

    Returns:
        A confirmation message indicating successful deployment.
    """
    system_prompt = ""
    with open("src/mcp_server/prompts/setup_wizard_sensors_system.txt", "r", encoding="utf-8") as f:
        system_prompt = f.read()

    return [
        Message(role="assistant", content=system_prompt),
        Message(
            role="user",
            content=(
                "Configure a fresh installation of the ArPI home security system "
                "with sensors to the specified environment."
            )
        ),
    ]

@prompts_mcp.prompt(
    name="add_output",
    description="Add a new output with given parameters.",
)
def add_output(
    name: str,
    channel: str,
    area: str,
    description: str = "",
    trigger_type: str = "button",
    delay: int = 0,
    duration: int = 0,
    default_state: bool = False,
    enabled: bool = True,
):
    """
    Add a new output with given parameters.
    Args:
        channel: The channel number of the output.
        area: The area name where the output is located.
        name: The name of the output.
        description: Optional description of the output.
        trigger_type: The trigger type of the output.
        delay: Delay before activation.
        duration: Duration of activation.
        default_state: Default state of the output.
        enabled: Whether the output is enabled.
    Returns:
        A confirmation message with output details.
    """
    return f"""We want to add a new output, but first we need to gather the details
        for the area based on the provided name.
        Find the corresponding ID for area={area} 
        and then create the output with the following details: 
        Output '{name}' as '{description}' added to channel {channel}, enabled={enabled}, 
        with the following settings:
        
        Trigger settings:
            trigger_type={trigger_type}, 
            delay={delay}, 
            duration={duration}, 
            default_state={default_state}."""
