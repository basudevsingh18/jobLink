#!/usr/bin/env bash
# Quick psql shell into the Postgres container
CONTAINER="${1:-jl_postgres}"
docker exec -it "$CONTAINER" psql -U ${2:-joblink} -d ${3:-joblink}
