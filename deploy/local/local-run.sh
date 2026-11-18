#!/usr/bin/env bash
# The one command of the local run of the whole system (docs/design/local-run.md, the guide
# docs/guides/local-run.md):
#
#   deploy/local/local-run.sh start [--with-ai <release folder>] [--observability] [--yes]
#   deploy/local/local-run.sh stop
#   deploy/local/local-run.sh status
#   deploy/local/local-run.sh logs [part]
#
# `start` runs the Compose project of compose.yaml. It checks every requirement first. When this
# start downloads or creates something, or moves PostgreSQL to another host port, it prints its
# plan and asks one question, which --yes answers; otherwise it starts without a question. It
# never installs system software, never runs as root, and never runs sudo: a missing tool stops
# it with the command to run. It writes only in .local-run/, which git ignores, and in the Docker
# objects of the project supportiq-local; `stop` deletes no data. Its messages go to standard
# error and never hold a secret. It runs with the bash 3.2 of macOS.
# Exit status: 0 done, 1 stopped, 2 wrong usage, 130 interrupted.
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
readonly ROOT_DIR
readonly SCRIPT_NAME=deploy/local/local-run.sh
readonly COMPOSE_YAML="$ROOT_DIR/deploy/local/compose.yaml"
readonly SHARED_ENV_FILE="$ROOT_DIR/deploy/local/local-run.env"
readonly STATE_DIR="$ROOT_DIR/.local-run"
readonly SECRETS_FILE="$STATE_DIR/secrets.env"
readonly DB_PORT_FILE="$STATE_DIR/db-port"
readonly LOCK_DIR="$STATE_DIR/start.lock"
readonly PROJECT=supportiq-local
readonly DATABASE_VOLUME="${PROJECT}_postgres-data"
readonly BACKEND_IMAGE=supportiq-local-backend
readonly FRONTEND_IMAGE=supportiq-local-frontend
readonly AI_SERVICE_IMAGE=supportiq-local-ai-service
readonly POSTGRES_IMAGE=postgres:17.11@sha256:748a18a54d3842d43bc156f0840d78029b8d349e0feca98c12b9c4ce3404a6b3
readonly OTEL_LGTM_IMAGE=grafana/otel-lgtm:0.41.0@sha256:2e3290657f2f2a256c7a9175f097424a3ac5b54840741ace433e108e109348b6
readonly PARTS="postgres backend-setup backend frontend ai-service otel-lgtm"
# How long `docker compose up --wait` waits until every part is healthy, in seconds. No value is
# measured yet; the first measured runs in CI set it (docs/design/local-run.md, Flow, step 8).
readonly COMPOSE_WAIT_TIMEOUT_S=600
# How long an interrupted docker command may take to end after TERM, in seconds, before KILL.
readonly CHILD_STOP_DEADLINE_S=30
# Each generated secret: 32 random bytes, written as 64 hexadecimal characters.
readonly SECRET_BYTES=32
# compose.yaml uses depends_on.required, which needs Compose 2.20.2, and
# healthcheck.start_interval, which needs Docker Engine 25, whose API is 1.44.
readonly MINIMUM_COMPOSE_VERSION=2.20.2
readonly MINIMUM_DOCKER_API_VERSION=1.44
readonly HIGHEST_PORT=65535
readonly EXIT_INTERRUPTED=130
readonly SECRET_NAMES="LOCAL_DB_SUPERUSER_PASSWORD LOCAL_DB_OWNER_PASSWORD LOCAL_DB_APP_PASSWORD \
LOCAL_SERVICE_TOKEN SEED_PASSWORD_CUSTOMER SEED_PASSWORD_STAFF SEED_PASSWORD_MANAGER \
SEED_PASSWORD_ADMIN"
readonly GRAFANA_PASSWORD_NAME=LOCAL_GRAFANA_ADMIN_PASSWORD
# The names that this script sets for Compose. A value of the environment would win over
# secrets.env and local-run.env when Compose interpolates, so the script clears them first.
# LOCAL_DB_PORT, LOCAL_GRAFANA_ADMIN_PASSWORD, GEMINI_API_KEY, and the two prices stay: the
# guide documents them as settings of the user.
readonly OWNED_NAMES="$SECRET_NAMES LOCAL_ALLOWED_ORIGINS LOCAL_BACKEND_BUILD_VERSION \
LOCAL_GEMINI_MODEL LOCAL_TRACE_EXPORTER LOCAL_RELEASE_FOLDER LOCAL_RUN_UID LOCAL_RUN_GID \
COMPOSE_PROFILES COMPOSE_FILE COMPOSE_PROJECT_NAME COMPOSE_ENV_FILES"
# ai-service requires these at startup, and its code does not change (docs/design/local-run.md,
# Two modes), so --with-ai takes them from the user's environment only.
readonly AI_SETTING_NAMES="GEMINI_API_KEY LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS \
LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS"
readonly RELEASE_MANIFEST=release-manifest.json
# The events of backend-setup that `start` reports: the app role, the migrations, the demo data.
readonly SETUP_EVENTS='database_role.applied|database.migrated|seed.loaded|seed.skipped'

say() {
  printf '%s\n' "$*" >&2
}

fail() {
  say "$SCRIPT_NAME: $1"
  exit 1
}

usage() {
  say "usage: $SCRIPT_NAME start [--with-ai <release folder>] [--observability] [--yes]
       $SCRIPT_NAME stop
       $SCRIPT_NAME status
       $SCRIPT_NAME logs [part]
  --with-ai        also run ai-service with a published release folder; needs GEMINI_API_KEY
                   and both LLM_*_PRICE_MICRO_USD_PER_MILLION_TOKENS in the environment
  --observability  also run the local Grafana stack
  --yes            answer the question of start with yes
  part             one of: $PARTS"
  exit 2
}

refuse_root() {
  if [ "$(id -u)" -eq 0 ]; then
    fail "do not run it as root or with sudo: run it as your normal user; nothing changed"
  fi
}

clear_owned_names() {
  # shellcheck disable=SC2086 # one name for each word
  unset $OWNED_NAMES
  # An empty password counts as not set; Compose would otherwise pass the empty value on.
  if [ -z "${LOCAL_GRAFANA_ADMIN_PASSWORD:-}" ]; then unset LOCAL_GRAFANA_ADMIN_PASSWORD; fi
}

# Whether a dotted version, such as 2.29.1, is at least another one. A suffix such as
# -desktop.1 is ignored; a value that is not a version is never enough.
version_is_at_least() {
  local IFS=. index have want
  local -a found minimum
  read -r -a found <<< "${1%%[-+]*}"
  read -r -a minimum <<< "$2"
  for index in 0 1 2; do
    have=${found[$index]:-0}
    want=${minimum[$index]:-0}
    case "$have" in '' | *[!0-9]*) return 1 ;; esac
    if [ "$have" -gt "$want" ]; then return 0; fi
    if [ "$have" -lt "$want" ]; then return 1; fi
  done
  return 0
}

# The value of one NAME=value line of an env file, or nothing. The file is read, never run.
env_value() {
  sed -n "s/^$1=//p" "$2" | tail -n 1
}

shared_setting() {
  local value
  value=$(env_value "$1" "$SHARED_ENV_FILE")
  [ -n "$value" ] || fail "deploy/local/local-run.env lacks $1"
  printf '%s' "$value"
}

platform() {
  case "$(uname -s)" in
    Darwin) echo macos ;;
    Linux)
      if grep -qi microsoft /proc/version 2> /dev/null; then echo wsl; else echo linux; fi
      ;;
    *) echo other ;;
  esac
}

docker_install_hint() {
  case "$(platform)" in
    macos) echo "install Docker Desktop with: brew install --cask docker, then open Docker once" ;;
    wsl) echo "install Docker Desktop on Windows and turn on its WSL integration for this distribution (Settings, Resources, WSL integration)" ;;
    linux) echo "install Docker Engine 25 or later with Compose $MINIMUM_COMPOSE_VERSION or later and BuildKit, as https://docs.docker.com/engine/install/ shows (the docker.io of a distribution can be older), then: sudo usermod -aG docker \"\$USER\", and sign in again" ;;
    *) echo "install Docker Engine 25 or later with Compose $MINIMUM_COMPOSE_VERSION or later and BuildKit: https://docs.docker.com/get-started/get-docker/" ;;
  esac
}

is_port_number() {
  case "$1" in
    '' | *[!0-9]* | 0*) return 1 ;;
  esac
  [ "$1" -le "$HIGHEST_PORT" ]
}

# Whether something answers on 127.0.0.1 at this port. bash opens the connection itself.
port_is_taken() {
  (: < "/dev/tcp/127.0.0.1/$1") 2> /dev/null
}

secret_is_generated() {
  [ -f "$SECRETS_FILE" ] && [ -n "$(env_value "$1" "$SECRETS_FILE")" ]
}

generate_secret() {
  od -An -tx1 -N"$SECRET_BYTES" /dev/urandom | tr -d ' \n'
}

docker_is_ready() {
  command -v docker > /dev/null 2>&1 && docker info > /dev/null 2>&1
}

image_is_present() {
  docker image inspect "$1" > /dev/null 2>&1
}

project_has_containers() {
  docker_is_ready && [ -n "$(docker compose --project-name "$PROJECT" ps --all --quiet 2> /dev/null)" ]
}

running_services() {
  docker compose --project-name "$PROJECT" ps --services --status running 2> /dev/null || true
}

# The progress is plain text: with the progress of a terminal, Compose 5.0.0 in a process group
# of its own did not end within 60 s of an INT or a TERM, and with plain text it ends within 1 s.
compose() {
  docker compose --progress plain --project-name "$PROJECT" --file "$COMPOSE_YAML" \
    --env-file "$SHARED_ENV_FILE" --env-file "$SECRETS_FILE" "$@"
}

# ----- start -----

is_with_ai=false
is_observability=false
is_confirmed=false
release_folder=""
frontend_port=""
backend_port=""
ai_service_port=""
grafana_port=""
db_port=""
db_port_source=""
recorded_db_port=""
is_database_new=false
gaps=""
plan=""
is_question_due=false
parts_before_start=""
is_compose_started=false
child_pid=""

add_gap() {
  gaps="${gaps}  - $1"$'\n'
}

# An action of the plan. An action that downloads or creates something makes the question due.
add_plan() {
  plan="${plan}  - $1"$'\n'
}

add_plan_with_question() {
  add_plan "$1"
  is_question_due=true
}

parse_start_options() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --with-ai)
        [ "$#" -ge 2 ] || usage
        is_with_ai=true
        release_folder=$2
        shift 2
        ;;
      --observability) is_observability=true; shift ;;
      --yes) is_confirmed=true; shift ;;
      *) usage ;;
    esac
  done
}

# The ports of local-run.env, and LOCAL_DB_PORT of the environment for PostgreSQL. They are
# exported, so Compose uses exactly the values that this start checked.
load_ports() {
  frontend_port=$(shared_setting LOCAL_FRONTEND_PORT)
  backend_port=$(shared_setting LOCAL_BACKEND_PORT)
  ai_service_port=$(shared_setting LOCAL_AI_SERVICE_PORT)
  grafana_port=$(shared_setting LOCAL_GRAFANA_PORT)
  if [ -n "${LOCAL_DB_PORT:-}" ]; then
    db_port=$LOCAL_DB_PORT
    db_port_source="from LOCAL_DB_PORT"
  else
    db_port=$(shared_setting LOCAL_DB_PORT)
    db_port_source="the default; set LOCAL_DB_PORT to change it"
  fi
  export LOCAL_FRONTEND_PORT="$frontend_port" LOCAL_BACKEND_PORT="$backend_port" \
    LOCAL_AI_SERVICE_PORT="$ai_service_port" LOCAL_GRAFANA_PORT="$grafana_port" \
    LOCAL_DB_PORT="$db_port"
  if [ -f "$DB_PORT_FILE" ]; then recorded_db_port=$(cat "$DB_PORT_FILE"); fi
}

# Every part of the requested mode runs: start is done. Parts of another mode stop the start.
stop_when_already_running() {
  local expected="postgres backend frontend" name has_ai=false has_observability=false
  local is_complete=true
  docker_is_ready || return 0
  parts_before_start=$(running_services)
  [ -n "$parts_before_start" ] || return 0
  if printf '%s\n' "$parts_before_start" | grep -qx ai-service; then has_ai=true; fi
  if printf '%s\n' "$parts_before_start" | grep -qx otel-lgtm; then has_observability=true; fi
  if [ "$has_ai" != "$is_with_ai" ] || [ "$has_observability" != "$is_observability" ]; then
    fail "the local run already runs in another mode; run $SCRIPT_NAME stop first; nothing changed"
  fi
  if [ "$is_with_ai" = true ]; then expected="$expected ai-service"; fi
  if [ "$is_observability" = true ]; then expected="$expected otel-lgtm"; fi
  for name in $expected; do
    if ! printf '%s\n' "$parts_before_start" | grep -qx "$name"; then is_complete=false; fi
  done
  if [ "$is_complete" = true ]; then
    if [ -n "$recorded_db_port" ] && [ "$recorded_db_port" != "$db_port" ]; then
      fail "the local run already runs with PostgreSQL on 127.0.0.1:$recorded_db_port; run $SCRIPT_NAME stop first to move it to $db_port; nothing changed"
    fi
    say "The local run already runs: http://localhost:$frontend_port. It runs the code of its last start; to run the changes of your working tree, run $SCRIPT_NAME stop, then start."
    exit 0
  fi
}

check_docker() {
  local compose_version api_version
  if ! command -v docker > /dev/null 2>&1; then
    add_gap "Docker is missing: $(docker_install_hint)"
    return 0
  fi
  if ! docker info > /dev/null 2>&1; then
    add_gap "Docker does not run: start Docker Desktop, or run: colima start"
    return 0
  fi
  compose_version=$(docker compose version --short 2> /dev/null || true)
  compose_version=${compose_version#v}
  if ! version_is_at_least "$compose_version" "$MINIMUM_COMPOSE_VERSION"; then
    add_gap "Docker Compose $MINIMUM_COMPOSE_VERSION or later is needed (docker compose, not docker-compose), and this one is ${compose_version:-missing}: $(docker_install_hint)"
  fi
  api_version=$(docker version --format '{{.Server.APIVersion}}' 2> /dev/null || true)
  if ! version_is_at_least "$api_version" "$MINIMUM_DOCKER_API_VERSION"; then
    add_gap "Docker Engine 25 or later is needed, with the API $MINIMUM_DOCKER_API_VERSION or later, and this one has the API ${api_version:-unknown}: $(docker_install_hint)"
  fi
  if ! docker buildx version > /dev/null 2>&1; then
    add_gap "BuildKit (docker buildx) is missing: $(docker_install_hint)"
  fi
}

check_port() {
  local name=$1 port=$2 part=$3
  if printf '%s\n' "$parts_before_start" | grep -qx "$part"; then
    # This part of the project already runs and holds its own port.
    return 0
  fi
  if port_is_taken "$port"; then
    if [ "$name" = LOCAL_DB_PORT ]; then
      add_gap "port $port on 127.0.0.1 is taken, so PostgreSQL cannot use it; set LOCAL_DB_PORT to a free port"
    else
      add_gap "port $port on 127.0.0.1 is taken ($name)"
    fi
  fi
}

check_ports() {
  if ! is_port_number "$db_port"; then
    add_gap "LOCAL_DB_PORT must be a port number from 1 to $HIGHEST_PORT"
    return 0
  fi
  check_port LOCAL_FRONTEND_PORT "$frontend_port" frontend
  check_port LOCAL_BACKEND_PORT "$backend_port" backend
  check_port LOCAL_DB_PORT "$db_port" postgres
  if [ "$is_with_ai" = true ]; then
    check_port LOCAL_AI_SERVICE_PORT "$ai_service_port" ai-service
  fi
  if [ "$is_observability" = true ]; then
    check_port LOCAL_GRAFANA_PORT "$grafana_port" otel-lgtm
  fi
}

check_ai_mode() {
  local name
  [ "$is_with_ai" = true ] || return 0
  if [ ! -d "$release_folder" ] || [ ! -r "$release_folder" ]; then
    add_gap "the release folder $release_folder is not a readable folder"
  elif [ ! -f "$release_folder/$RELEASE_MANIFEST" ] || [ ! -r "$release_folder/$RELEASE_MANIFEST" ]; then
    add_gap "the release folder $release_folder holds no readable $RELEASE_MANIFEST"
  fi
  for name in $AI_SETTING_NAMES; do
    if [ -z "${!name:-}" ]; then
      add_gap "--with-ai needs $name in the environment; without it, start without --with-ai"
    fi
  done
}

check_secrets_file() {
  local name
  if [ ! -f "$SECRETS_FILE" ]; then
    # New passwords would not open the database of the volume, so the setup would fail later
    # with an error that does not name the cause.
    if docker volume inspect "$DATABASE_VOLUME" > /dev/null 2>&1; then
      add_gap ".local-run/secrets.env is missing, but the volume $DATABASE_VOLUME still holds the database of an earlier start, which only the passwords of that file open; remove both, as the section Remove the local data of the guide shows"
    fi
    return 0
  fi
  for name in $SECRET_NAMES; do
    if ! secret_is_generated "$name"; then
      add_gap ".local-run/secrets.env lacks $name; it is never rewritten: add the line, or remove the local data as the guide shows"
    fi
  done
}

needs_grafana_password() {
  [ "$is_observability" = true ] && [ -z "${LOCAL_GRAFANA_ADMIN_PASSWORD:-}" ] \
    && ! secret_is_generated "$GRAFANA_PASSWORD_NAME"
}

build_plan() {
  local parts="postgres, backend-setup, backend, frontend" image
  local images="$BACKEND_IMAGE $FRONTEND_IMAGE"
  if [ ! -f "$SECRETS_FILE" ]; then
    add_plan_with_question "create .local-run/ and .local-run/secrets.env with random local passwords, mode 0600"
  fi
  if needs_grafana_password; then
    add_plan_with_question "add $GRAFANA_PASSWORD_NAME, generated, to .local-run/secrets.env"
  fi
  if [ "$is_with_ai" = true ]; then
    images="$images $AI_SERVICE_IMAGE"
    parts="$parts, ai-service"
  fi
  for image in $images; do
    if image_is_present "$image"; then
      add_plan "rebuild the image $image from this working tree, with the cache; when a file that its dependencies are installed from changed, it downloads every package again"
    else
      add_plan_with_question "build the image $image from this working tree, which downloads its dependencies"
    fi
  done
  if ! image_is_present "$POSTGRES_IMAGE"; then add_plan_with_question "download postgres:17.11"; fi
  if [ "$is_observability" = true ]; then
    parts="$parts, otel-lgtm"
    if ! image_is_present "$OTEL_LGTM_IMAGE"; then
      add_plan_with_question "download grafana/otel-lgtm:0.41.0"
    fi
  fi
  if ! docker volume inspect "$DATABASE_VOLUME" > /dev/null 2>&1; then
    is_database_new=true
    add_plan_with_question "create the Docker volume $DATABASE_VOLUME with the database supportiq, its owner role, and the demo data, and record its port in .local-run/db-port"
  fi
  if [ "$is_database_new" = false ] && [ -n "$recorded_db_port" ] && [ "$recorded_db_port" != "$db_port" ]; then
    add_plan_with_question "move PostgreSQL from 127.0.0.1:$recorded_db_port to 127.0.0.1:$db_port: every tool connected to the old port, such as psql or a test run, must change to the new one"
  fi
  add_plan "PostgreSQL on 127.0.0.1:$db_port, $db_port_source"
  add_plan "run the pending migrations"
  add_plan "start $parts, with their ports on 127.0.0.1"
}

ask_when_due() {
  local answer=""
  if [ "$is_question_due" = false ]; then
    say "Starting the local run: PostgreSQL on 127.0.0.1:$db_port, the pending migrations, then the parts."
    return 0
  fi
  say "The local run will:"
  printf '%s' "$plan" >&2
  if [ "$is_confirmed" = true ]; then
    return 0
  fi
  if [ ! -t 0 ]; then
    fail "nothing changed: there is no terminal to ask, so pass --yes to proceed"
  fi
  printf 'Proceed? [y/N] ' >&2
  read -r answer || answer=""
  case "$answer" in
    y | Y) ;;
    *) fail "nothing changed" ;;
  esac
}

take_lock() {
  mkdir -p "$STATE_DIR"
  chmod 700 "$STATE_DIR"
  mkdir "$LOCK_DIR" 2> /dev/null \
    || fail "another start holds .local-run/start.lock; when no start runs, remove that folder"
  trap 'rmdir "$LOCK_DIR" 2> /dev/null || true' EXIT
  trap stop_after_interruption INT TERM
}

# The parts of the requested mode, in the order of compose.yaml.
mode_parts() {
  local parts="postgres backend-setup backend frontend"
  if [ "$is_with_ai" = true ]; then parts="$parts ai-service"; fi
  if [ "$is_observability" = true ]; then parts="$parts otel-lgtm"; fi
  echo "$parts"
}

# Run one docker command in the background, as a process group of its own, and wait for it, so
# a signal reaches the trap at once, not only after the command ends. The group holds the
# docker command and its Compose plugin, so the trap can end both before anything else runs.
run_child() {
  local status=0
  set -m
  "$@" < /dev/null &
  child_pid=$!
  set +m
  wait "$child_pid" || status=$?
  child_pid=""
  return "$status"
}

# End the process group of an interrupted docker command: TERM, then KILL after the deadline.
# It fails when the group needed KILL.
stop_child() {
  local waited_s=0
  kill -TERM -- "-$child_pid" || return 0
  while kill -0 -- "-$child_pid" && [ "$waited_s" -lt "$CHILD_STOP_DEADLINE_S" ]; do
    sleep 1
    waited_s=$((waited_s + 1))
  done
  if kill -0 -- "-$child_pid"; then
    kill -KILL -- "-$child_pid" || true
    wait "$child_pid" || true
    return 1
  fi
  wait "$child_pid" || true
}

# On Ctrl+C or TERM: stop the parts that this start launched, keep the volume, and exit 130.
stop_after_interruption() {
  local name launched=""
  trap - INT TERM
  # stop_child writes nothing to standard error: on a terminal, bash would report the ended
  # job there with a line of its own, such as "Terminated: 15".
  if [ -n "$child_pid" ] && ! stop_child 2> /dev/null; then
    say "$SCRIPT_NAME: the docker command did not end within $CHILD_STOP_DEADLINE_S s, so it got KILL."
  fi
  if [ "$is_compose_started" = true ]; then
    if [ -z "$parts_before_start" ]; then
      compose down > /dev/null 2>&1 || true
    else
      for name in $(mode_parts); do
        if ! printf '%s\n' "$parts_before_start" | grep -qx "$name"; then
          launched="$launched $name"
        fi
      done
      # shellcheck disable=SC2086 # one argument for each part
      compose rm --stop --force $launched > /dev/null 2>&1 || true
    fi
  fi
  say "$SCRIPT_NAME: interrupted; the parts that this start launched are stopped, and the data stays."
  exit "$EXIT_INTERRUPTED"
}

write_secrets() {
  local name
  if [ ! -f "$SECRETS_FILE" ]; then
    (
      umask 077
      {
        echo "# Generated by $SCRIPT_NAME (docs/design/local-run.md). Never commit or share it."
        for name in $SECRET_NAMES; do
          printf '%s=%s\n' "$name" "$(generate_secret)"
        done
      } > "$SECRETS_FILE.partial"
      mv "$SECRETS_FILE.partial" "$SECRETS_FILE"
    )
  fi
  if needs_grafana_password; then
    (
      umask 077
      printf '%s=%s\n' "$GRAFANA_PASSWORD_NAME" "$(generate_secret)" >> "$SECRETS_FILE"
    )
  fi
}

record_db_port() {
  printf '%s\n' "$db_port" > "$DB_PORT_FILE.partial"
  mv "$DB_PORT_FILE.partial" "$DB_PORT_FILE"
}

start_compose() {
  local profiles="" started_at first_parts first_names first_verb
  export LOCAL_RUN_UID LOCAL_RUN_GID
  LOCAL_RUN_UID=$(id -u)
  LOCAL_RUN_GID=$(id -g)
  if [ "$is_with_ai" = true ]; then
    profiles=ai
    LOCAL_RELEASE_FOLDER=$(cd "$release_folder" && pwd)
    export LOCAL_RELEASE_FOLDER
  fi
  if [ "$is_observability" = true ]; then
    profiles="${profiles:+$profiles,}observability"
    export LOCAL_TRACE_EXPORTER=otlp
  fi
  export COMPOSE_PROFILES="$profiles"
  say "Building $BACKEND_IMAGE."
  run_child compose build backend || fail "the image $BACKEND_IMAGE did not build"
  say "Building $FRONTEND_IMAGE."
  run_child compose build frontend || fail "the image $FRONTEND_IMAGE did not build"
  if [ "$is_with_ai" = true ]; then
    say "Building $AI_SERVICE_IMAGE."
    run_child compose build ai-service || fail "the image $AI_SERVICE_IMAGE did not build"
  fi
  if ! image_is_present "$POSTGRES_IMAGE"; then
    run_child compose pull postgres || fail "postgres:17.11 did not download"
  fi
  if [ "$is_observability" = true ] && ! image_is_present "$OTEL_LGTM_IMAGE"; then
    run_child compose pull otel-lgtm || fail "grafana/otel-lgtm:0.41.0 did not download"
  fi
  started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  is_compose_started=true
  # ai-service and otel-lgtm first: backend depends on them only optionally, because they
  # belong to profiles, so Compose would start backend even when one of them failed.
  first_parts=""
  first_names=""
  first_verb="it is"
  if [ "$is_with_ai" = true ]; then first_parts=ai-service; first_names=ai-service; fi
  if [ "$is_observability" = true ]; then
    first_parts="${first_parts:+$first_parts }otel-lgtm"
    first_names="${first_names:+$first_names and }otel-lgtm"
  fi
  case "$first_names" in *" and "*) first_verb="they are" ;; esac
  if [ -n "$first_parts" ]; then
    say "Starting $first_names first, and waiting until $first_verb healthy."
    # shellcheck disable=SC2086 # one argument for each part
    if ! run_child compose up --detach --wait --wait-timeout "$COMPOSE_WAIT_TIMEOUT_S" --no-build $first_parts; then
      compose ps --all --format 'table {{.Service}}\t{{.Status}}' >&2 || true
      fail "$first_names did not get ready, so backend and frontend were not started; read the log with: $SCRIPT_NAME logs <part>, then run $SCRIPT_NAME stop"
    fi
  fi
  say "Starting the parts, and waiting until each one is healthy."
  if ! run_child compose up --detach --wait --wait-timeout "$COMPOSE_WAIT_TIMEOUT_S" --no-build; then
    compose ps --all --format 'table {{.Service}}\t{{.Status}}' >&2 || true
    fail "a part did not get ready; read its log with: $SCRIPT_NAME logs <part>; the parts that started run until $SCRIPT_NAME stop"
  fi
  if [ "$is_database_new" = true ] || [ "$recorded_db_port" != "$db_port" ]; then
    record_db_port
  fi
  say "Setup: $(compose logs --no-log-prefix --since "$started_at" backend-setup 2> /dev/null \
    | grep -oE "\"event\":\"($SETUP_EVENTS)\"" | sed -E 's/"event":"([^"]*)"/\1/' \
    | paste -sd ',' - | sed 's/,/, /g')."
}

report_started() {
  say ""
  say "SupportIQ runs at http://localhost:$frontend_port and http://127.0.0.1:$frontend_port."
  if [ "$is_observability" = true ]; then
    say "Grafana runs at http://localhost:$grafana_port. Sign in as admin, with the password"
    say "LOCAL_GRAFANA_ADMIN_PASSWORD of your shell, or of .local-run/secrets.env when your shell has none."
  fi
  if [ "$is_with_ai" = false ]; then
    say "Without AI, staff handle every ticket manually."
  fi
  say "Demo accounts: customer-1 to customer-3, staff-1 and staff-2, manager-1 and manager-2,"
  say "admin-1 and admin-2, with the SEED_PASSWORD_* passwords of .local-run/secrets.env."
  say "PostgreSQL: host 127.0.0.1, port $db_port, database supportiq, user supportiq_owner,"
  say "with the password LOCAL_DB_OWNER_PASSWORD of .local-run/secrets.env."
  say "Follow the logs with: $SCRIPT_NAME logs. Stop with: $SCRIPT_NAME stop"
}

start() {
  parse_start_options "$@"
  load_ports
  stop_when_already_running
  if [ -d "$LOCK_DIR" ]; then
    fail "another start holds .local-run/start.lock; when no start runs, remove that folder"
  fi
  check_docker
  if [ -z "$gaps" ]; then check_ports; fi
  check_ai_mode
  check_secrets_file
  if [ -n "$gaps" ]; then
    say "$SCRIPT_NAME: nothing changed, because:"
    printf '%s' "$gaps" >&2
    exit 1
  fi
  build_plan
  ask_when_due
  take_lock
  write_secrets
  start_compose
  report_started
}

# ----- stop, status, and logs -----

stop() {
  [ "$#" -eq 0 ] || usage
  if ! project_has_containers; then
    say "Nothing of the local run runs."
    return 0
  fi
  docker compose --project-name "$PROJECT" down
  say "Stopped. The data stays in the volume $DATABASE_VOLUME."
}

status() {
  [ "$#" -eq 0 ] || usage
  if ! project_has_containers; then
    say "Nothing of the local run runs."
    return 0
  fi
  say "The local run runs with Compose:"
  docker compose --project-name "$PROJECT" ps --all \
    --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}' >&2
}

# Follow the logs; Ctrl+C ends only the viewing, because the parts run in their containers.
logs() {
  [ "$#" -le 1 ] || usage
  if [ "$#" -eq 1 ]; then
    case " $PARTS " in
      *" $1 "*) ;;
      *) usage ;;
    esac
  fi
  if ! project_has_containers; then
    say "Nothing of the local run runs."
    return 0
  fi
  exec docker compose --project-name "$PROJECT" logs --follow "$@"
}

main() {
  [ "$#" -gt 0 ] || usage
  local command_name=$1
  shift
  refuse_root
  clear_owned_names
  case "$command_name" in
    start) start "$@" ;;
    stop) stop "$@" ;;
    status) status "$@" ;;
    logs) logs "$@" ;;
    *) usage ;;
  esac
}

main "$@"
