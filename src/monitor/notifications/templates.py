"""
Templates for email and SMS messages
"""

ALERT_STARTED_SMS = "Alert({id}) started at {time}!"
ALERT_STARTED_EMAIL = """
Hi,

You have an alert({id}) since {time}.
The alert started on sensor(s): {sensors}!

ArPI Home Security

"""

ALERT_STOPPED_SMS = "Alert({id}) stopped at {time}!"
ALERT_STOPPED_EMAIL = """
Hi,

The alert({id}) stopped at {time}!

ArPI Home Security

"""


POWER_OUTAGE_STARTED_SMS = "Power outage started at {time}!"
POWER_OUTAGE_STARTED_EMAIL = """
Hi,

You have a power outage since {time}.

ArPI Home Security

"""

POWER_OUTAGE_STOPPED_SMS = "Power outage stopped at {time}!"
POWER_OUTAGE_STOPPED_EMAIL = """
Hi,

The power outage stopped at {time}!

ArPI Home Security

"""