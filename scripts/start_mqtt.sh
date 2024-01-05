#!/bin/bash

docker volume create argus-mqtt
docker start argus-mqtt || docker run -d -it \
    --name argus-mqtt \
    -p 127.0.0.1:1883:1883 \
    -p 127.0.0.1:9001:9001 \
    -v $(pwd)/etc/mosquitto/mosquitto.dev.conf:/mosquitto/config/mosquitto.conf:ro \
    -v arpi-mosquitto:/mosquitto/data/ \
    eclipse-mosquitto
