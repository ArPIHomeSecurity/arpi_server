import logging

from crontab import CronTab

from utils.constants import LOG_IPC


dyndns_job = (
    "systemd-cat -t 'argus_dyndns' "
    "bash -c 'cd /home/argus/server/;"
    " PYTHONPATH=/home/argus/server/src /usr/bin/python3"
    " /home/argus/server/bin/dyndns.py'"
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
