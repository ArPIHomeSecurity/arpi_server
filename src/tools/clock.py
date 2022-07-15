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

    def gettime_ntp(self, addr="0.pool.ntp.org"):
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

    def gettime_hw(self):
        try:
            result = re.search("RTC time: [a-zA-Z]{0,4} ([0-9\\-: ]*)", check_output("timedatectl").decode("utf-8"))
            if result:
                return result.group(1)
        except CalledProcessError:
            pass

    def get_timezone(self):
        full_path = os.readlink("/etc/localtime")
        return full_path.replace("/usr/share/zoneinfo/", "")

    def sync_clock(self):
        network = self.gettime_ntp()

        if network is not None:
            self._logger.info("Network time: {} => writing to hw clock".format(network))
            run(["date", "--set={}".format(network)])
            run(["/sbin/hwclock", "-w", "--verbose"])
        else:
            hw = self.gettime_hw()
            if hw:
                self._logger.info("HW clock time: {} => wrinting to system clock".format(hw))
                run(["date", "--set={}".format(hw)])

    def set_clock(self, settings):
        try:
            if "timezone" in settings and os.path.isfile("/usr/share/zoneinfo/" + settings["timezone"]):
                os.remove("/etc/localtime")
                os.symlink("/usr/share/zoneinfo/" + settings["timezone"], "/etc/localtime")
            if "datetime" in settings and settings["datetime"]:
                run(["date", "--set={}".format(settings["datetime"])])
        except PermissionError:
            self._logger.error("Permission denied when changing date/time and zone")
            return False

        return True


if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)-15s %(message)s", level=logging.INFO)

    Clock(logging.getLogger("argus_clock")).sync_clock()
