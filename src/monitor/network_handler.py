"""
Periodically checks the network/wifi connectivity.
"""

import contextlib
import logging
import socket
import subprocess
from datetime import datetime
from enum import Enum
from queue import Empty, Queue
from threading import Thread
from time import time

from monitor.actions import MonitorStopCommand
from monitor.broadcast import Broadcaster
from monitor.notifications.notifier import Notifier
from utils.constants import LOG_NETWORK, THREAD_NETWORK

logger = logging.getLogger(LOG_NETWORK)

CHECK_INTERVAL = 60  # sec, how often the connectivity is checked
POLL_TIMEOUT = 1  # sec, queue poll timeout to stay responsive to stop commands
SOCKET_TIMEOUT = 3  # sec
# well-known public DNS resolvers, tried in order until one is reachable
DNS_RESOLVERS = ["1.1.1.1", "8.8.8.8", "9.9.9.9"]
DNS_PORT = 53


class ConnectivityStatus(Enum):
    """Result of a connectivity check, distinguishing where the connection breaks."""

    OK = "ok"
    NO_LOCAL_NETWORK = "no_local_network"  # gateway/wifi unreachable
    NO_INTERNET = "no_internet"  # gateway reachable, but no public resolver responds


class NetworkHandler(Thread):
    """
    Class for periodically checking the network/wifi connectivity.
    """

    def __init__(self, broadcaster: Broadcaster):
        super().__init__(name=THREAD_NETWORK)
        self._actions = Queue()
        self._broadcaster = broadcaster
        self._broadcaster.register_queue(id(self), self._actions)
        self._last_status = ConnectivityStatus.OK

    def run(self):
        try:
            self.communicate()
        except Exception:
            logger.exception("Network handler crashed!")

        logger.info("Network handler stopped")

    def communicate(self):
        last_check = 0
        while True:
            with contextlib.suppress(Empty):
                message = self._actions.get(timeout=POLL_TIMEOUT)
                match message:
                    case MonitorStopCommand():
                        break

            if time() - last_check >= CHECK_INTERVAL:
                last_check = time()
                self.check_connectivity()

    def check_connectivity(self) -> ConnectivityStatus:
        """
        Check whether the local network (wifi) and the internet are reachable,
        notifying on each state transition.
        """
        status = self._probe_connectivity()
        self._notify_on_transition(status)
        self._last_status = status
        return status

    def _probe_connectivity(self) -> ConnectivityStatus:
        gateway = self._get_default_gateway()
        if not gateway or not self._can_connect(gateway, DNS_PORT):
            logger.warning("No local network connectivity detected (wifi connection may be lost)")
            return ConnectivityStatus.NO_LOCAL_NETWORK

        if not any(self._can_connect(host, DNS_PORT) for host in DNS_RESOLVERS):
            logger.warning("Local network OK, but no internet connectivity detected")
            return ConnectivityStatus.NO_INTERNET

        logger.debug("Network connectivity OK (gateway %s)", gateway)
        return ConnectivityStatus.OK

    def _notify_on_transition(self, status: ConnectivityStatus):
        previous = self._last_status
        if status == previous:
            return

        now = datetime.now()
        if previous == ConnectivityStatus.NO_LOCAL_NETWORK and status != previous:
            Notifier.notify_local_network_issue_stopped(now)
        if previous == ConnectivityStatus.NO_INTERNET and status != previous:
            Notifier.notify_internet_issue_stopped(now)

        if status == ConnectivityStatus.NO_LOCAL_NETWORK:
            Notifier.notify_local_network_issue_started(now)
        elif status == ConnectivityStatus.NO_INTERNET:
            Notifier.notify_internet_issue_started(now)

    @staticmethod
    def _get_default_gateway() -> str | None:
        try:
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True,
                text=True,
                timeout=SOCKET_TIMEOUT,
                check=True,
            )
            return result.stdout.split("via ")[1].split(" ")[0]
        except (IndexError, subprocess.SubprocessError):
            logger.error("Failed to determine the default gateway")
            return None

    @staticmethod
    def _can_connect(host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT):
                return True
        except OSError:
            return False
