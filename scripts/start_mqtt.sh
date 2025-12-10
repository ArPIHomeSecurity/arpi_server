#!/bin/bash

CURRENT_PATH=$(dirname "${BASH_SOURCE[0]}")

docker volume create argus-mqtt
docker start argus-mqtt || docker run -d -it \
    --name argus-mqtt \
    -p 127.0.0.1:1883:1883 \
    -p 127.0.0.1:9001:9001 \
    -v ${CURRENT_PATH}/mosquitto/mosquitto.dev.conf:/mosquitto/config/mosquitto.conf:ro \
    -v arpi-mosquitto:/mosquitto/data/ \
    eclipse-mosquitto
