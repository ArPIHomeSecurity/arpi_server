from datetime import datetime as dt

from server.ipc import IPCClient
from tools.clock import Clock


class ClockService:
    """
    Service for clock-related operations.
    """

    def get_clock_info(self) -> dict:
        """
        Retrieve current clock information including timezone, system time,
        hardware clock, NTP time, and system/service uptimes.
        """
        clock = Clock()
        return {
            "timezone": clock.get_timezone(),
            "system": dt.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
            "hw": clock.get_time_hw(),
            "network": clock.get_time_ntp(),
            "uptime": clock.get_uptime(),
            "uptime_server": clock.get_service_uptime("argus_server.service"),
            "uptime_monitor": clock.get_service_uptime("argus_monitor.service"),
            "uptime_nginx": clock.get_service_uptime("nginx.service"),
        }

    def set_clock(self, settings: dict):
        """
        Set the system clock timezone and/or datetime via IPC.
        """
        return IPCClient().set_clock(settings)
