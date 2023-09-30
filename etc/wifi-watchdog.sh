#!/bin/bash

## Wifi watchdog script
# schedule with cron
# */30 * * * * systemd-cat -t 'argus_wifi' bash -c 'sudo /home/argus/wifi-watchdog.sh'
##

SCRIPT_NAME="wifi-watchdog"

WIFI_STATUS_CMD="iwgetid"

WIFI_RESTART_CMD="sudo systemctl restart wpa_supplicant"

WIFI_STATUS=$(${WIFI_STATUS_CMD} | awk '{print $2}')

if [[ ${WIFI_STATUS} == "" ]]; then
    echo "No living wifi connection. Restarting wpa supplicant..."
    ${WIFI_RESTART_CMD}
else
    echo "Wifi connection is OK on $WIFI_STATUS"
fi
