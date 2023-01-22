# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:08:24
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:08:26

# See fields of monitoring.notifications.notification.Notification


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
