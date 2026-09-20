#!/bin/bash
# Reads DATABASE_URL from the root .env (SQLAlchemy postgresql:// form),
# derives the JDBC form cs-service needs, and launches the jar against it.
# Not committed as a permanent script - just a local convenience so the
# credential never has to be typed into a shell command by hand.
set -euo pipefail
cd "$(dirname "$0")"

ROOT_ENV="../.env"
DB_URL=$(grep -m1 '^DATABASE_URL=' "$ROOT_ENV" | cut -d'=' -f2-)

# postgresql://user:pass@host:port/dbname  ->  jdbc:postgresql://host:port/dbname?...
USERPASS_HOST=${DB_URL#postgresql://}
USERPASS=${USERPASS_HOST%%@*}
HOSTPORTDB=${USERPASS_HOST#*@}
DB_USER=${USERPASS%%:*}
DB_PASS=${USERPASS#*:}
HOSTPORT=${HOSTPORTDB%%/*}
DB_NAME=${HOSTPORTDB#*/}

export SPRING_DATASOURCE_URL="jdbc:postgresql://${HOSTPORT}/${DB_NAME}?prepareThreshold=0&sslmode=require"
export SPRING_DATASOURCE_USERNAME="$DB_USER"
export SPRING_DATASOURCE_PASSWORD="$DB_PASS"

echo "Starting cs-service against ${SPRING_DATASOURCE_URL} as ${SPRING_DATASOURCE_USERNAME}"
exec java -jar target/cs-service-1.0.0.jar
