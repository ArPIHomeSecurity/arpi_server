# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:04:25
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:04:27
import logging
import os
import os.path
import re
from datetime import datetime as dt
from subprocess import CalledProcessError, check_output, run

from constants import LOG_CLOCK


TIME1970 = 2208988800


class Clock:
    def __init__(self, logger=None):
        self._logger = logger or logging.getLogger(LOG_CLOCK)

    def get_time_ntp(self, addr="0.pool.ntp.org"):
        # http://code.activestate.com/recipes/117211-simple-very-sntp-client/
        import socket
        import struct

        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            data = ("\x1b" + 47 * "\0").encode("utf-8")
            client.sendto(data, (addr, 123))
            data, _ = client.recvfrom(1024)
            if data:
                t = struct.unpack("!12I", data)[10]
                t -= TIME1970
                return dt.fromtimestamp(t).isoformat(sep=" ")
        except socket.gaierror:
            pass

    def get_time_hw(self):
        try:
            result = re.search("RTC time: [a-zA-Z]{0,4} ([0-9\\-: ]*)", check_output("timedatectl").decode("utf-8"))
            if result:
                return result.group(1)
        except CalledProcessError:
            pass

    def get_timezone(self):
        full_path = os.readlink("/etc/localtime")
        return full_path.replace("/usr/share/zoneinfo/", "")

    def get_uptime(self):
        """
        Get the uptime of the system in seconds
        """
        try:
            return int(float(check_output("cat /proc/uptime", shell=True).decode("utf-8").split(" ")[0]))
        except CalledProcessError:
            return None
        
    def get_service_uptime(self, service):
        """
        Get the uptime of a systemd service in seconds
        """
        try:
            uptime = check_output(f"systemctl show -p ActiveEnterTimestamp {service}", shell=True).decode("utf-8")
            # remove the "ActiveEnterTimestamp=" part
            uptime = uptime.split("=")[1]
            # remove timezone and day
            uptime = uptime.split(" ")[1:3]
            # parse the uptime to float from iso datetime string
            uptime = dt.fromisoformat(" ".join(uptime)).timestamp()
            # get elapsed time in seconds
            uptime = dt.now().timestamp() - uptime
            return int(float(uptime))
        except Exception:  # pylint: disable=broad-except
            return None

    def sync_clock(self):
        network = self.get_time_ntp()

        if network is not None:
            self._logger.info("Network time: {} => writing to hw clock".format(network))
            run(["date", "--set={}".format(network)])
            run(["/sbin/hwclock", "-w", "--verbose"])
        else:
            hw = self.get_time_hw()
            if hw:
                self._logger.info("HW clock time: {} => wrinting to system clock".format(hw))
                run(["date", "--set={}".format(hw)])

    def set_clock(self, settings):
        try:
            if "timezone" in settings and os.path.isfile("/usr/share/zoneinfo/" + settings["timezone"]):
                os.remove("/etc/localtime")
                os.symlink("/usr/share/zoneinfo/" + settings["timezone"], "/etc/localtime")
                with open("/etc/timezone", "w", encoding='utf-8') as timezone_file:
                    timezone_file.write(settings["timezone"] + "\n")
            if "datetime" in settings and settings["datetime"]:
                run(["date", "--set={}".format(settings["datetime"])])
        except PermissionError:
            self._logger.error("Permission denied when changing date/time and zone")
            return False

        return True


if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)-15s %(message)s", level=logging.INFO)

    Clock(logging.getLogger("argus_clock")).sync_clock()
