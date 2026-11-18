#!/usr/bin/env bash
# Create the owner role and the database of the local run, as step 3 of backend/README.md does
# (docs/design/local-run.md). The entrypoint of the PostgreSQL image runs this file once, on the
# first start of the volume, as the superuser. The owner password comes from the environment of
# the container through \getenv, so it never appears on a command line.
set -euo pipefail

psql --no-psqlrc --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<'SQL'
\getenv owner_password LOCAL_DB_OWNER_PASSWORD
CREATE ROLE supportiq_owner LOGIN CREATEDB CREATEROLE PASSWORD :'owner_password';
CREATE DATABASE supportiq OWNER supportiq_owner;
SQL
