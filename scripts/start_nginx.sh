#!/bin/bash

# echo commands 
set -x

CURRENT_PATH=$(dirname "${BASH_SOURCE[0]}")

HOST_IP=$(hostname -I | awk '{print $1}')

docker rm -fv arpi-server
docker run -d --name arpi-server \
    -p 8000:8000 \
    -e HOST_IP=${HOST_IP} \
    -v ${CURRENT_PATH}/nginx/nginx.conf.template:/etc/nginx/templates/nginx.conf.template:ro \
    -v ${CURRENT_PATH}/nginx/arpi_dev_dhparams.pem:/etc/nginx/arpi_dev_dhparams.pem:ro \
    -v ${CURRENT_PATH}/nginx/arpi_app.crt:/etc/nginx/arpi_app.crt:ro \
    -v ${CURRENT_PATH}/nginx/arpi_app.key:/etc/nginx/arpi_app.key:ro \
    nginx
