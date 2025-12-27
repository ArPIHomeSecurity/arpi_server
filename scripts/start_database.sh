#!/bin/bash

docker volume create argus-database
docker start argus-database || docker run -d -it \
    --name argus-database \
    -p 127.0.0.1:5432:5432 \
    -v /var/run/postgresql:/var/run/postgresql \
    -v argus-database:/var/lib/postgresql/data \
    -e POSTGRES_USER=argus \
    -e POSTGRES_PASSWORD=argus1 \
    -e POSTGRES_DB=argus \
    postgres:15
