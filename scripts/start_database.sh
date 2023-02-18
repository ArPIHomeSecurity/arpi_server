#!/bin/bash

docker volume create argus-database
docker start argus-database || docker run -d -it \
    --name argus-database \
    -p 127.0.0.1:5432:5432 \
    -v argus-database:/var/lib/postgresql/data \
    -e POSTGRES_USER=$DB_USER \
    -e POSTGRES_PASSWORD=$DB_PASSWORD \
    -e POSTGRES_DB=$DB_SCHEMA \
    postgres:13
