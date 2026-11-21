#!/usr/bin/env bash
# The checks of the smoke test of the local run (docs/design/local-run.md, Testing and
# evaluation). Each check runs once, without a retry.
#
#   running  after `local-run.sh start`: one readiness check of backend on its port, one through
#            the proxy of frontend, one load of the entry module of the app, and one sign-in of
#            customer-1 through that proxy at each allowed origin, localhost and 127.0.0.1,
#            which proves the seed and both origins
#   kept     after a later start: the checks of running, and the setup of that start found the
#            demo data already there (seed.skipped), so the data was kept
#   stopped  after `local-run.sh stop`: no container of the project remains, and every port is
#            free
#
# The password is read from .local-run/secrets.env and reaches curl on standard input, never on
# a command line or in the output.
#
# Usage: deploy/local/tests/smoke-check.sh running | kept | stopped
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
readonly ROOT_DIR
readonly SHARED_ENV_FILE="$ROOT_DIR/deploy/local/local-run.env"
readonly SECRETS_FILE="$ROOT_DIR/.local-run/secrets.env"
readonly PROJECT=supportiq-local
readonly REQUEST_TIMEOUT_S=10
readonly SESSION_CREATED=201

fail() {
  echo "smoke-check.sh: $1" >&2
  exit 1
}

setting() {
  sed -n "s/^$1=//p" "$2" | tail -n 1
}

frontend_port=$(setting LOCAL_FRONTEND_PORT "$SHARED_ENV_FILE")
backend_port=$(setting LOCAL_BACKEND_PORT "$SHARED_ENV_FILE")
readonly frontend_port backend_port

check_ready() {
  curl --fail --silent --show-error --max-time "$REQUEST_TIMEOUT_S" --output /dev/null \
    "http://127.0.0.1:$backend_port/health/ready" || fail "backend is not ready on its port"
  echo "backend is ready on 127.0.0.1:$backend_port"
  curl --fail --silent --show-error --max-time "$REQUEST_TIMEOUT_S" --output /dev/null \
    "http://127.0.0.1:$frontend_port/health/ready" || fail "backend is not ready through frontend"
  echo "backend is ready through the proxy of frontend on 127.0.0.1:$frontend_port"
  curl --fail --silent --show-error --max-time "$REQUEST_TIMEOUT_S" --output /dev/null \
    "http://127.0.0.1:$frontend_port/src/app/main.tsx" || fail "the dev server cannot transform the app"
  echo "the dev server transforms the entry module of the app"
}

# Sign in as customer-1 at one origin of the page, through the proxy of frontend.
sign_in_at() {
  local origin=$1 status
  status=$(printf '{"login_name":"customer-1","password":"%s"}' \
    "$(setting SEED_PASSWORD_CUSTOMER "$SECRETS_FILE")" \
    | curl --silent --show-error --max-time "$REQUEST_TIMEOUT_S" --output /dev/null \
      --write-out '%{http_code}' --header 'Content-Type: application/json' \
      --header "Origin: $origin" --data-binary @- "$origin/v1/sessions") \
    || fail "the sign-in request at $origin failed"
  [ "$status" = "$SESSION_CREATED" ] || fail "the sign-in of customer-1 at $origin answered $status"
  echo "customer-1 signed in at $origin"
}

check_running() {
  check_ready
  sign_in_at "http://localhost:$frontend_port"
  sign_in_at "http://127.0.0.1:$frontend_port"
}

check_kept() {
  check_running
  # `stop` removes the containers, so the log of backend-setup holds only this start.
  docker compose --project-name "$PROJECT" logs --no-log-prefix backend-setup \
    | grep -q '"event":"seed.skipped"' \
    || fail "the setup of this start did not find the demo data of the first start"
  echo "the demo data of the first start was kept"
}

check_stopped() {
  local name port
  [ -z "$(docker compose --project-name "$PROJECT" ps --all --quiet)" ] \
    || fail "a container of the project $PROJECT remains"
  for name in LOCAL_FRONTEND_PORT LOCAL_BACKEND_PORT LOCAL_AI_SERVICE_PORT LOCAL_GRAFANA_PORT \
    LOCAL_DB_PORT; do
    port=$(setting "$name" "$SHARED_ENV_FILE")
    if [ "$name" = LOCAL_DB_PORT ]; then port=${LOCAL_DB_PORT:-$port}; fi
    if (: < "/dev/tcp/127.0.0.1/$port") 2> /dev/null; then fail "port $port is still taken"; fi
  done
  echo "no container of the local run remains, and its ports are free"
}

case "${1:-}" in
  running) check_running ;;
  kept) check_kept ;;
  stopped) check_stopped ;;
  *) fail "usage: deploy/local/tests/smoke-check.sh running | kept | stopped" ;;
esac
