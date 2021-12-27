# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:05:23
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:05:26
import logging

from crontab import CronTab

from monitoring.constants import LOG_IPC


dyndns_job = (
    "systemd-cat -t 'argus_dyndns' "
    "bash -c 'cd /home/argus/server/; "
    "/usr/local/bin/pipenv run python /home/argus/server/src/tools/dyndns.py'"
)

certbot_job = (
    "systemd-cat -t 'argus_certbot' "
    "bash -c 'cd /home/argus/server/; "
    "/usr/local/bin/pipenv run python /home/argus/server/src/tools/certbot.py'"
)


def enable_dyndns_job(enable=True):
    try:
        argus_cron = CronTab(user="argus")
    except OSError as error:
        logging.getLogger(LOG_IPC).error("Can't access crontab! %s", error)
        return

    jobs = list(argus_cron.find_command("argus_dyndns"))
    job = jobs[0] if jobs else None
    if job is None:
        job = argus_cron.new(
            command=dyndns_job,
            comment="Update the IP address at the dynamic DNS provider",
        )

    job.hours.every(1)
    job.enable(enable)
    argus_cron.write()


def enable_certbot_job(enable=True):
    try:
        root_cron = CronTab(user="root")
    except OSError as error:
        logging.getLogger(LOG_IPC).error("Can't access crontab! %s", error)
        return

    jobs = list(root_cron.find_command("argus_certbot"))
    job = jobs[0] if jobs else None
    if job is None:
        job = root_cron.new(
            command=certbot_job,
            comment="Generate or update certificate with certbot",
        )

    job.day.every(1)
    job.enable(enable)
    root_cron.write()
