#!/bin/bash

# echo commands 
set -x

# get script directory
SCRIPT_DIR=$(dirname "${BASH_SOURCE[0]}")/nginx

# check if self signed certificate exists
if [ ! -f "${SCRIPT_DIR}/arpi_dev.key" ] || [ ! -f "${SCRIPT_DIR}/arpi_dev.crt" ]; then
    printf "\n\n## Create self signed certificate\n"
    openssl req -new -newkey rsa:4096 -nodes -x509 \
        -subj "/C=HU/ST=Fejér/L=Baracska/O=ArPI/CN=arpi.local" \
        -days 730 \
        -keyout "${SCRIPT_DIR}/arpi_dev.key" \
        -out "${SCRIPT_DIR}/arpi_dev.crt" \
        -addext "subjectAltName=DNS:arpi.local,DNS:*.arpi.local"
fi

# check dhparams file
if [ ! -f "${SCRIPT_DIR}/arpi_dhparams.pem" ]; then
    printf "\n\n## Create dhparams file\n"
    openssl dhparam -out "${SCRIPT_DIR}/arpi_dhparams.pem" 1024
fi

CURRENT_PATH=$(dirname "${BASH_SOURCE[0]}")

HOST_IP=$(hostname -I | awk '{print $1}')

docker rm -fv arpi-server
docker run -d --name arpi-server \
    -p 8000:8000 \
    -e HOST_IP=${HOST_IP} \
    -v ${CURRENT_PATH}/nginx/nginx.conf.template:/etc/nginx/templates/nginx.conf.template:ro \
    -v ${CURRENT_PATH}/nginx/arpi_dhparams.pem:/etc/nginx/arpi_dhparams.pem:ro \
    -v ${CURRENT_PATH}/nginx/arpi_dev.crt:/etc/nginx/arpi_dev.crt:ro \
    -v ${CURRENT_PATH}/nginx/arpi_dev.key:/etc/nginx/arpi_dev.key:ro \
    nginx
