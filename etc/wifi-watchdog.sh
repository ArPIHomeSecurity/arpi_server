#!/bin/bash

## Wifi watchdog script
# schedule with cron
# */10 * * * * systemd-cat -t 'argus_wifi' bash -c 'sudo /home/argus/wifi-watchdog.sh'
##

SCRIPT_NAME="wifi-watchdog"

WIFI_STATUS_CMD="iwgetid"

WIFI_RESTART_CMD="sudo systemctl restart networking wpa_supplicant"

WIFI_RESTART_MAX_ATTEMPTS=5
WIFI_RESTART_ATTEMPT=0

WIFI_STATUS=$(${WIFI_STATUS_CMD} | awk '{print $2}')

if [[ ${WIFI_STATUS} == "" ]]; then
    WIFI_STATE_FILE="/tmp/wifi-watchdog.state"
    if [[ -f ${WIFI_STATE_FILE} ]]; then
        WIFI_RESTART_ATTEMPT=$(cat ${WIFI_STATE_FILE})
    fi

    if [[ ${WIFI_RESTART_ATTEMPT} -lt ${WIFI_RESTART_MAX_ATTEMPTS} ]]; then
        echo "No living wifi connection. Restarting wpa supplicant..."
        WIFI_RESTART_ATTEMPT=$((WIFI_RESTART_ATTEMPT+1))
        echo ${WIFI_RESTART_ATTEMPT} > ${WIFI_STATE_FILE}
        ${WIFI_RESTART_CMD}
    else
        echo "Wifi restart failed. Restarting host..."
        sudo reboot
    fi
else
    echo "Wifi connection is OK on $WIFI_STATUS"
    if [[ -f ${WIFI_STATE_FILE} ]]; then
        rm ${WIFI_STATE_FILE}
    fi
fi
