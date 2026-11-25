#!/usr/bin/env bash
# The one command of the local run of the whole system (docs/design/local-run.md, the guide
# docs/guides/local-run.md):
#
#   deploy/local/local-run.sh start [--without-ai | --release <id> | --release-folder <folder>]
#                                   [--observability] [--yes]
#   deploy/local/local-run.sh stop
#   deploy/local/local-run.sh status
#   deploy/local/local-run.sh logs [part]
#   deploy/local/local-run.sh releases
#   deploy/local/local-run.sh set-key
#
# `start` runs the Compose project of compose.yaml, with ai-service unless --without-ai is given.
# It checks every requirement first. With AI, it takes the release that
# eval/releases/pinned-release.txt names, or the one of --release, from the release cache, where
# `supportiq-release download-release` of eval/release downloads and checks it when it is missing;
# the Gemini key comes from the environment, from .local-run/gemini.env, or from a hidden prompt.
# When this start downloads or creates something, or moves PostgreSQL to another host port, it
# prints its plan and asks one question, which --yes answers; otherwise it starts without a
# question. It never installs system software, never runs as root, and never runs sudo: a missing
# tool stops it with the command to run. It writes only in .local-run/, which git ignores, in the
# release cache through the download command, and in the Docker objects of the project
# supportiq-local; `stop` deletes no data. Its messages go to standard error and never hold a
# secret. It runs with the bash 3.2 of macOS.
# Exit status: 0 done, 1 stopped, 2 wrong usage, 130 interrupted.
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
readonly ROOT_DIR
readonly SCRIPT_NAME=deploy/local/local-run.sh
readonly COMPOSE_YAML="$ROOT_DIR/deploy/local/compose.yaml"
readonly SHARED_ENV_FILE="$ROOT_DIR/deploy/local/local-run.env"
readonly PRICES_FILE="$ROOT_DIR/deploy/llm-prices.env"
readonly RELEASE_RECORDS_DIR="$ROOT_DIR/eval/releases"
readonly PINNED_FILE="$RELEASE_RECORDS_DIR/pinned-release.txt"
readonly STATE_DIR="$ROOT_DIR/.local-run"
readonly SECRETS_FILE="$STATE_DIR/secrets.env"
readonly GEMINI_FILE="$STATE_DIR/gemini.env"
readonly DB_PORT_FILE="$STATE_DIR/db-port"
readonly IMAGE_INPUTS_DIR="$STATE_DIR/image-inputs"
readonly RELEASE_PATH_FILE="$STATE_DIR/release-path"
readonly LOCK_DIR="$STATE_DIR/start.lock"
readonly PROJECT=supportiq-local
readonly DATABASE_VOLUME="${PROJECT}_postgres-data"
readonly BACKEND_IMAGE=supportiq-local-backend
readonly FRONTEND_IMAGE=supportiq-local-frontend
readonly AI_SERVICE_IMAGE=supportiq-local-ai-service
readonly POSTGRES_IMAGE=postgres:17.11@sha256:748a18a54d3842d43bc156f0840d78029b8d349e0feca98c12b9c4ce3404a6b3
readonly OTEL_LGTM_IMAGE=grafana/otel-lgtm:0.41.0@sha256:2e3290657f2f2a256c7a9175f097424a3ac5b54840741ace433e108e109348b6
# The image of the download command: uv 0.11.11 with Python 3.14.4, the version of
# .python-version, so no Python is downloaded. A multi-platform index (amd64 and arm64), read on
# ghcr.io on 2026-11-23.
readonly RELEASE_TOOL_IMAGE=ghcr.io/astral-sh/uv:0.11.11-python3.14-trixie-slim@sha256:3e70f580d0e63d78408c35d332d780024b6e1d46d9744c888e22fa944393448e
# The named volume that holds the uv environment of eval/release. It is mounted at /var/tmp,
# whose mode 1777 a new volume takes from the image, so the user of the script can write in it.
readonly RELEASE_TOOL_VOLUME="${PROJECT}_release-tool"
readonly RELEASE_TOOL_HOME=/var/tmp/release-tool
# The only paths of the repository that the download command reads, each mounted read-only: the
# Python version, what uv needs to build eval/release and its path dependency ai-service, and
# the release records. The container runs packages of PyPI with network access, so it never sees
# the rest of the repository: not .local-run/ with the Gemini key and the secrets, and not a
# .env file of a teammate.
readonly RELEASE_TOOL_PATHS=".python-version eval/release/pyproject.toml eval/release/uv.lock \
eval/release/README.md eval/release/src eval/releases ai-service/pyproject.toml \
ai-service/README.md ai-service/app"
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
# The memory that the Docker engine needs with AI: ai-service loads torch and two models. It is
# about twice the measured peak of all containers together, 1570 MiB, because docker stats
# leaves out the inactive file cache, the Docker engine, and the system
# (docs/design/local-run.md, Testing and evaluation).
readonly MINIMUM_DOCKER_MEMORY_BYTES=3221225472
# With AI and --observability, this many CPUs or fewer make the AI too slow (the guide, With the
# local Grafana stack).
readonly SLOW_CPU_COUNT=2
readonly BYTES_PER_MIB=1048576
readonly HIGHEST_PORT=65535
readonly EXIT_INTERRUPTED=130
# The exit statuses of `supportiq-release download-release` (docs/design/
# release-download-and-modal-deploy.md, Exit statuses).
readonly DOWNLOAD_BAD_INPUT=2
readonly DOWNLOAD_DECLINED=4
readonly DOWNLOAD_NETWORK_FAILURE=5
readonly DOWNLOAD_CHECK_FAILED=6
# The pattern of release_id in contracts/schemas/AssetVersions.yaml, and the rules of the pinned
# file (docs/design/release-download-and-modal-deploy.md, The pinned file).
readonly RELEASE_ID_PATTERN='^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
readonly ARCHIVE_SIZE_PATTERN='^[1-9][0-9]{0,9}$'
readonly HIGHEST_ARCHIVE_SIZE_BYTES=2147483647
readonly RELEASE_MANIFEST=release-manifest.json
# The form of a key of Google AI Studio. A key of another form only gets a warning.
readonly GEMINI_KEY_PATTERN='^AIza[0-9A-Za-z_-]{35}$'
readonly GEMINI_KEY_ADDRESS=https://aistudio.google.com/apikey
# The placeholder of ai-service/.env.example, and a common one. Each counts as no key.
readonly GEMINI_KEY_PLACEHOLDERS="replace-with-a-gemini-api-key YOUR_GEMINI_API_KEY"
readonly PRICE_NAMES="GEMINI_MODEL LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS \
LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS"
readonly SECRET_NAMES="LOCAL_DB_SUPERUSER_PASSWORD LOCAL_DB_OWNER_PASSWORD LOCAL_DB_APP_PASSWORD \
LOCAL_SERVICE_TOKEN SEED_PASSWORD_CUSTOMER SEED_PASSWORD_STAFF SEED_PASSWORD_MANAGER \
SEED_PASSWORD_ADMIN"
readonly GRAFANA_PASSWORD_NAME=LOCAL_GRAFANA_ADMIN_PASSWORD
# The names that this script sets for Compose, and the model and prices of the price file. A
# value of the environment would win over the env files when Compose interpolates, so the script
# clears them first. LOCAL_DB_PORT, LOCAL_GRAFANA_ADMIN_PASSWORD, GEMINI_API_KEY,
# SUPPORTIQ_RELEASE_TOKEN, and SUPPORTIQ_RELEASE_CACHE stay: the guide documents them as settings
# of the user.
readonly OWNED_NAMES="$SECRET_NAMES $PRICE_NAMES LOCAL_ALLOWED_ORIGINS LOCAL_BACKEND_BUILD_VERSION \
LOCAL_TRACE_EXPORTER LOCAL_RELEASE_FOLDER LOCAL_RUN_UID LOCAL_RUN_GID COMPOSE_PROFILES COMPOSE_FILE \
COMPOSE_PROJECT_NAME COMPOSE_ENV_FILES"
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
  say "usage: $SCRIPT_NAME start [--without-ai | --release <id> | --release-folder <folder>]
                                [--observability] [--yes]
       $SCRIPT_NAME stop
       $SCRIPT_NAME status
       $SCRIPT_NAME logs [part]
       $SCRIPT_NAME releases
       $SCRIPT_NAME set-key
  --without-ai      run without ai-service: staff handle every ticket manually
  --release         run ai-service with this published release instead of the default one
  --release-folder  run ai-service with a release folder on this machine, without the cache
  --observability   also run the local Grafana stack
  --yes             answer the question of start with yes; it never enters a Gemini key
  releases          list the published releases, the default one, and those in the cache
  set-key           enter or replace the Gemini API key in .local-run/gemini.env
  part              one of: $PARTS"
  exit 2
}

refuse_root() {
  if [ "$(id -u)" -eq 0 ]; then
    fail "do not run it as root or with sudo: run it as your normal user; nothing changed"
  fi
}

is_missing_key() {
  case " $GEMINI_KEY_PLACEHOLDERS " in
    *" $1 "*) return 0 ;;
  esac
  [ -z "$1" ]
}

clear_owned_names() {
  # shellcheck disable=SC2086 # one name for each word
  unset $OWNED_NAMES
  # An empty password counts as not set; Compose would otherwise pass the empty value on.
  if [ -z "${LOCAL_GRAFANA_ADMIN_PASSWORD:-}" ]; then unset LOCAL_GRAFANA_ADMIN_PASSWORD; fi
  # An empty key or a placeholder counts as no key, and must not win over gemini.env.
  if is_missing_key "${GEMINI_API_KEY:-}"; then unset GEMINI_API_KEY; fi
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

# The value of one NAME=value line of an env file, or nothing. The file is read, never run. A
# value in single quotes, as gemini.env holds the key, loses its quotes, as Compose reads it.
env_value() {
  local value
  value=$(sed -n "s/^$1=//p" "$2" | tail -n 1)
  case "$value" in
    "'"*"'") value=${value#"'"} && value=${value%"'"} ;;
  esac
  printf '%s' "$value"
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

docker_memory_hint() {
  echo "with Colima, run: colima stop, then: colima start --memory <GiB>; with Docker Desktop, raise the memory in Settings, Resources; or start with --without-ai"
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

# Write what a producer prints to a file of .local-run/, as the only one who can read it: into
# a temporary file first, renamed over the file only when the producer succeeded, so a failure
# or an interrupted write leaves the old file whole. Each producer returns 1 on any failure.
write_private_file() {
  local file=$1
  shift
  if ! (umask 077 && "$@" > "$file.partial"); then
    rm -f "$file.partial"
    fail "${file#"$ROOT_DIR"/} could not be written, and it is unchanged"
  fi
  mv "$file.partial" "$file"
}

remove_partial_files() {
  rm -f "$SECRETS_FILE.partial" "$GEMINI_FILE.partial" "$DB_PORT_FILE.partial" \
    "$RELEASE_PATH_FILE.partial" "$IMAGE_INPUTS_DIR"/*.partial
}

docker_is_ready() {
  command -v docker > /dev/null 2>&1 && docker info > /dev/null 2>&1
}

image_is_present() {
  docker image inspect "$1" > /dev/null 2>&1
}

volume_is_present() {
  docker volume inspect "$1" > /dev/null 2>&1
}

# The date on which Docker created a volume, as YYYY-MM-DD, or "an unknown date".
volume_created_on() {
  local created
  created=$(docker volume inspect --format '{{.CreatedAt}}' "$1" 2> /dev/null || true)
  if [[ $created =~ ^([0-9]{4}-[0-9]{2}-[0-9]{2}) ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
  else
    printf 'an unknown date'
  fi
}

# Whether the setup of this start exited with an error. backend-setup runs once and exits, so a
# container that still runs, or none at all, is no failure of it.
backend_setup_failed() {
  local container code
  container=$(compose ps --all --quiet backend-setup 2> /dev/null | head -n 1 || true)
  [ -n "$container" ] || return 1
  code=$(docker inspect --format '{{.State.ExitCode}}' "$container" 2> /dev/null || true)
  [ -n "$code" ] && [ "$code" != 0 ]
}

project_has_containers() {
  docker_is_ready && [ -n "$(docker compose --project-name "$PROJECT" ps --all --quiet 2> /dev/null)" ]
}

running_services() {
  docker compose --project-name "$PROJECT" ps --services --status running 2> /dev/null || true
}

mib_of() {
  echo $(( ($1 + BYTES_PER_MIB / 2) / BYTES_PER_MIB ))
}

# ----- the release -----

pinned_release_id=""
pinned_archive_size_bytes=""

# Read the pinned file: exactly `release_id=<id>` and `archive_size_bytes=<decimal>`, each ended
# by LF, without anything else. It fails, and sets nothing, for a missing file or another text.
read_pinned_file() {
  local content id size
  pinned_release_id=""
  pinned_archive_size_bytes=""
  [ -f "$PINNED_FILE" ] && [ -r "$PINNED_FILE" ] || return 1
  # The x keeps the final line breaks, which $(...) would remove.
  content=$(cat "$PINNED_FILE"; printf x)
  content=${content%x}
  id=$(sed -n '1s/^release_id=//p' "$PINNED_FILE")
  size=$(sed -n '2s/^archive_size_bytes=//p' "$PINNED_FILE")
  [ "$content" = "release_id=$id"$'\n'"archive_size_bytes=$size"$'\n' ] || return 1
  [[ $id =~ $RELEASE_ID_PATTERN ]] || return 1
  [[ $size =~ $ARCHIVE_SIZE_PATTERN ]] || return 1
  [ "$size" -le "$HIGHEST_ARCHIVE_SIZE_BYTES" ] || return 1
  pinned_release_id=$id
  pinned_archive_size_bytes=$size
}

is_published_release() {
  [ -f "$RELEASE_RECORDS_DIR/$1/$RELEASE_MANIFEST" ]
}

without_trailing_slashes() {
  local path=$1
  while [ "$path" != / ] && [ "${path%/}" != "$path" ]; do path=${path%/}; done
  printf '%s' "$path"
}

# The physical path of an absolute path: the nearest folder that exists, with its links resolved
# by `pwd -P`, followed by the rest, which does not exist yet.
physical_path() {
  local path rest=""
  path=$(without_trailing_slashes "$1")
  while [ ! -d "$path" ]; do
    rest="/${path##*/}$rest"
    path=${path%/*}
    [ -n "$path" ] || path=/
  done
  path=$(cd "$path" && pwd -P)
  printf '%s%s' "${path%/}" "$rest"
}

# The release cache of the download command: SUPPORTIQ_RELEASE_CACHE when it is set, otherwise
# $HOME/.cache/supportiq/releases, without XDG_CACHE_HOME. It must be an absolute path.
release_cache_path() {
  local cache=${SUPPORTIQ_RELEASE_CACHE:-$HOME/.cache/supportiq/releases}
  case "$cache" in
    /*) without_trailing_slashes "$cache" ;;
    *) return 1 ;;
  esac
}

# A cached release is the folder <cache>/<release_id>, never a link. The hidden staging entries
# of the download command start with a dot, so they never match an ID.
is_cached_release() {
  [ -d "$1/$2" ] && [ ! -L "$1/$2" ]
}

# ----- start -----

is_with_ai=true
is_observability=false
is_confirmed=false
release_folder=""
release_id=""
release_id_option=""
release_cache=""
is_release_cached=false
is_download_due=false
gemini_key_source=""
entered_key=""
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
started_at=""
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
  local is_without_ai=false
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --without-ai) is_without_ai=true; shift ;;
      --release)
        [ "$#" -ge 2 ] && [ -n "$2" ] || usage
        release_id_option=$2
        shift 2
        ;;
      --release-folder)
        [ "$#" -ge 2 ] && [ -n "$2" ] || usage
        release_folder=$2
        shift 2
        ;;
      --observability) is_observability=true; shift ;;
      --yes) is_confirmed=true; shift ;;
      *) usage ;;
    esac
  done
  # One source of the release at most, and none without AI.
  if [ -n "$release_id_option" ] && [ -n "$release_folder" ]; then usage; fi
  if [ "$is_without_ai" = true ]; then
    if [ -n "$release_id_option" ] || [ -n "$release_folder" ]; then usage; fi
    is_with_ai=false
  fi
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

check_release_folder() {
  if [ ! -d "$release_folder" ] || [ ! -r "$release_folder" ]; then
    add_gap "the release folder $release_folder is not a readable folder"
  elif [ ! -f "$release_folder/$RELEASE_MANIFEST" ] || [ ! -r "$release_folder/$RELEASE_MANIFEST" ]; then
    add_gap "the release folder $release_folder holds no readable $RELEASE_MANIFEST"
  fi
}

# The release ID, from --release or the pinned file, decided in bash before the question: the
# download command is not installed yet on a fresh machine (docs/design/local-run.md, Release).
check_release_id() {
  if [ -n "$release_id_option" ]; then
    # The value never becomes part of a path, nor of a message, before it matches the pattern.
    if ! [[ $release_id_option =~ $RELEASE_ID_PATTERN ]]; then
      add_gap "--release must name a release ID of the pattern $RELEASE_ID_PATTERN"
      return 1
    fi
    if ! is_published_release "$release_id_option"; then
      add_gap "--release $release_id_option names no published release: eval/releases/$release_id_option/$RELEASE_MANIFEST does not exist; list the published ones with: $SCRIPT_NAME releases"
      return 1
    fi
    release_id=$release_id_option
    # The size of the plan, when --release names the pinned release.
    read_pinned_file || true
    return 0
  fi
  if [ ! -f "$PINNED_FILE" ]; then
    add_gap "eval/releases/pinned-release.txt is missing, so no default release is known: run git pull, pass --release <id>, or start with --without-ai"
    return 1
  fi
  if ! read_pinned_file; then
    add_gap "eval/releases/pinned-release.txt must hold exactly the two lines release_id=<id> and archive_size_bytes=<a number from 1 to $HIGHEST_ARCHIVE_SIZE_BYTES>, each ended by LF, without comments or CR"
    return 1
  fi
  if ! is_published_release "$pinned_release_id"; then
    add_gap "eval/releases/pinned-release.txt names $pinned_release_id, but eval/releases/$pinned_release_id/$RELEASE_MANIFEST does not exist, so the two are out of step: run git pull, or pass --release <id>"
    return 1
  fi
  release_id=$pinned_release_id
}

check_release_cache() {
  local physical_cache physical_home
  if ! release_cache=$(release_cache_path); then
    add_gap "SUPPORTIQ_RELEASE_CACHE must be an absolute path, such as \$HOME/.cache/supportiq/releases, without a ~ in quotes; unset it to use that default"
    return 1
  fi
  # Colima shares only the home folder with its virtual machine by default, and a bind mount of
  # a path that it does not share silently creates an empty folder inside the virtual machine.
  if [ "$(platform)" = macos ]; then
    physical_cache=$(physical_path "$release_cache")
    physical_home=$(physical_path "$HOME")
    case "$physical_cache/" in
      "$physical_home"/*) ;;
      *)
        add_gap "the release cache $release_cache lies outside your home folder, which is the only folder that Colima and Docker Desktop share with Docker by default: set SUPPORTIQ_RELEASE_CACHE to a folder in $HOME, or unset it"
        return 1
        ;;
    esac
  fi
  if is_cached_release "$release_cache" "$release_id"; then
    is_release_cached=true
  else
    check_release_tool_paths
  fi
}

# Docker would create a missing source of a bind mount as a folder owned by root.
check_release_tool_paths() {
  local path
  for path in $RELEASE_TOOL_PATHS; do
    if [ ! -e "$ROOT_DIR/$path" ]; then
      add_gap "the download command needs $path of this working tree, which is missing"
    fi
  done
}

check_prices() {
  local name
  if [ ! -f "$PRICES_FILE" ]; then
    add_gap "deploy/llm-prices.env is missing: it names the Gemini model of ai-service and its two prices"
    return 0
  fi
  for name in $PRICE_NAMES; do
    if [ -z "$(env_value "$name" "$PRICES_FILE")" ]; then
      add_gap "deploy/llm-prices.env lacks $name"
    fi
  done
}

# ai-service loads torch and two models, and the default virtual machine of Colima has 2 GiB.
check_docker_memory() {
  local memory
  memory=$(docker info --format '{{.MemTotal}}' 2> /dev/null || true)
  case "$memory" in
    '' | *[!0-9]*)
      say "Warning: docker info names no memory of the Docker engine, so start cannot check that ai-service has $(mib_of "$MINIMUM_DOCKER_MEMORY_BYTES") MiB or more; when ai-service runs out of memory, start says so."
      return 0
      ;;
  esac
  if [ "$memory" -lt "$MINIMUM_DOCKER_MEMORY_BYTES" ]; then
    add_gap "ai-service needs Docker with $(mib_of "$MINIMUM_DOCKER_MEMORY_BYTES") MiB of memory or more, and this one has $(mib_of "$memory") MiB: $(docker_memory_hint)"
  fi
}

check_ai_mode() {
  local is_docker_checked=$1
  [ "$is_with_ai" = true ] || return 0
  check_prices
  if [ "$is_docker_checked" = true ]; then check_docker_memory; fi
  if [ -n "$release_folder" ]; then
    check_release_folder
    return 0
  fi
  check_release_id || return 0
  check_release_cache || return 0
}

check_secrets_file() {
  local name
  if [ ! -f "$SECRETS_FILE" ]; then
    # New passwords would not open the database of the volume, so the setup would fail later
    # with an error that does not name the cause. The project name, and so the volume, is the
    # same for every folder of the repository, while .local-run/ is per folder.
    if volume_is_present "$DATABASE_VOLUME"; then
      add_gap ".local-run/secrets.env is missing, but the volume $DATABASE_VOLUME, created on $(volume_created_on "$DATABASE_VOLUME"), holds the database of an earlier start, which only the passwords of that start open. This machine has one local database for every folder of the repository, so it may belong to the .local-run/ of another folder: start there instead, or, once no run uses it, remove it with: $SCRIPT_NAME stop, then docker volume rm $DATABASE_VOLUME"
    fi
    return 0
  fi
  for name in $SECRET_NAMES; do
    if ! secret_is_generated "$name"; then
      add_gap ".local-run/secrets.env lacks $name; it is never rewritten: add the line, or remove the local data with: $SCRIPT_NAME stop, then docker volume rm $DATABASE_VOLUME, then rm -r .local-run"
    fi
  done
}

warn_when_cpus_are_few() {
  local cpus
  [ "$is_with_ai" = true ] && [ "$is_observability" = true ] || return 0
  cpus=$(docker info --format '{{.NCPU}}' 2> /dev/null || true)
  case "$cpus" in '' | *[!0-9]*) return 0 ;; esac
  if [ "$cpus" -le "$SLOW_CPU_COUNT" ]; then
    say "Warning: Docker has $cpus CPUs, and with AI and --observability the AI will be too slow: tickets will go to manual handling, and the start can stop when Compose marks ai-service unhealthy. Give Docker more CPUs (Colima: colima stop, then colima start --cpu <count>; Docker Desktop: Settings, Resources), drop --observability, or start with --without-ai."
  fi
}

# Warn, once, on a key that holds a paste mistake or that has another form than a key of Google
# AI Studio. The warning never shows the key or a part of it, and the start goes on.
warn_on_key_form() {
  case "$1" in
    *[[:space:]\"\']*) say "Warning: the Gemini key holds a space, a quote, or a line break, which is often a paste mistake; set it again with: $SCRIPT_NAME set-key" ;;
  esac
  if ! [[ $1 =~ $GEMINI_KEY_PATTERN ]]; then
    say "Warning: the Gemini key does not look like an AI Studio key; ignore this if you are sure."
  fi
}

saved_key() {
  if [ -f "$GEMINI_FILE" ]; then env_value GEMINI_API_KEY "$GEMINI_FILE"; fi
}

# Ask for the key with hidden input. It is never shown, echoed, or part of a command line.
prompt_for_key() {
  say "ai-service needs a Gemini API key. Create a free one at $GEMINI_KEY_ADDRESS"
  say "Under the free plan, Google may use and read the requests: enter only the simulated demo data, never real data (SEC-07; the guide, With AI)."
  printf 'Gemini API key (hidden; press Enter alone to %s): ' "$1" >&2
  entered_key=""
  IFS= read -r -s entered_key || entered_key=""
  printf '\n' >&2
  if is_missing_key "$entered_key"; then entered_key=""; fi
}

# The key of this start: the environment, then gemini.env, then the prompt on a terminal. An
# empty answer runs this start without AI. A key from the prompt stays in memory until the
# question is answered, and is saved only after y (docs/design/local-run.md, Gemini key).
resolve_gemini_key() {
  local key
  [ "$is_with_ai" = true ] || return 0
  if [ -n "${GEMINI_API_KEY:-}" ]; then
    gemini_key_source=environment
    warn_on_key_form "$GEMINI_API_KEY"
    return 0
  fi
  key=$(saved_key)
  if ! is_missing_key "$key"; then
    gemini_key_source=saved
    warn_on_key_form "$key"
    return 0
  fi
  if [ ! -t 0 ] || [ "$is_confirmed" = true ]; then
    fail "nothing changed: ai-service needs a Gemini API key, and none is set or saved. Create a free key at $GEMINI_KEY_ADDRESS, then save it with $SCRIPT_NAME set-key in a terminal, or set GEMINI_API_KEY; or start with --without-ai"
  fi
  prompt_for_key "start without AI"
  if [ -z "$entered_key" ]; then
    is_with_ai=false
    say "This start runs without AI, and nothing is saved."
    return 0
  fi
  gemini_key_source=prompt
  warn_on_key_form "$entered_key"
  refuse_a_key_with_a_single_quote "$entered_key"
}

needs_grafana_password() {
  [ "$is_observability" = true ] && [ -z "${LOCAL_GRAFANA_ADMIN_PASSWORD:-}" ] \
    && ! secret_is_generated "$GRAFANA_PASSWORD_NAME"
}

# The files that an image installs its dependencies from, which its Dockerfile copies before it
# installs them. A change of one makes the next build download every package of the image again.
image_inputs() {
  case "$1" in
    "$BACKEND_IMAGE") echo "backend/pyproject.toml backend/uv.lock backend/README.md" ;;
    "$AI_SERVICE_IMAGE") echo "ai-service/pyproject.toml ai-service/uv.lock ai-service/README.md" ;;
    "$FRONTEND_IMAGE") echo "frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml" ;;
  esac
}

# One line `<SHA-256>  <path>` for each file. shasum of macOS, sha256sum of Linux.
image_input_hashes() {
  local tool="shasum -a 256"
  if command -v sha256sum > /dev/null 2>&1; then tool=sha256sum; fi
  # shellcheck disable=SC2046,SC2086 # one argument for each word
  (cd "$ROOT_DIR" && $tool $(image_inputs "$1"))
}

# The record of the dependency files needs a working SHA-256 tool, so a failure stops the start
# instead of hiding a change.
check_hash_tool() {
  local image
  for image in $BACKEND_IMAGE $FRONTEND_IMAGE $AI_SERVICE_IMAGE; do
    if ! image_input_hashes "$image" > /dev/null 2>&1; then
      add_gap "the SHA-256 of $(image_inputs "$image") cannot be computed: on Linux, install coreutils, which holds sha256sum; on macOS, shasum comes with the system"
      return 0
    fi
  done
}

# The files whose hash differs from the record of the last build of the image.
changed_image_inputs() {
  local record="$IMAGE_INPUTS_DIR/$1.sha256" line changed=""
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    if ! grep -qxF -- "$line" "$record"; then changed="$changed, ${line#*  }"; fi
  done <<< "$(image_input_hashes "$1")"
  printf '%s' "${changed#, }"
}

plan_image() {
  local image=$1 changed
  if ! image_is_present "$image"; then
    add_plan_with_question "build the image $image from this working tree, which downloads its dependencies"
  elif [ ! -f "$IMAGE_INPUTS_DIR/$image.sha256" ]; then
    add_plan_with_question "rebuild the image $image from this working tree: no record of the files that it installs its dependencies from exists yet, so the rebuild can download every package of the image again"
  else
    changed=$(changed_image_inputs "$image")
    if [ -n "$changed" ]; then
      add_plan_with_question "rebuild the image $image from this working tree: $changed changed since its last build, so the rebuild downloads every package of the image again"
    else
      add_plan "rebuild the image $image from this working tree, with the cache"
    fi
  fi
}

plan_release() {
  local size_text="of a size that is not known before the download"
  if [ -n "$release_folder" ]; then
    add_plan "run ai-service with the release folder $release_folder, read-only"
    return 0
  fi
  if [ "$is_release_cached" = true ]; then
    add_plan "run ai-service with the release $release_id of the cache, $release_cache/$release_id/, read-only; nothing is downloaded"
    return 0
  fi
  is_download_due=true
  if [ "$release_id" = "$pinned_release_id" ]; then
    size_text="$pinned_archive_size_bytes bytes, about $(mib_of "$pinned_archive_size_bytes") MiB"
  fi
  add_plan_with_question "download the release $release_id, $size_text, into $release_cache/$release_id/ with supportiq-release download-release, which checks it against eval/releases/$release_id/$RELEASE_MANIFEST"
  if ! image_is_present "$RELEASE_TOOL_IMAGE"; then
    add_plan_with_question "download the image ${RELEASE_TOOL_IMAGE%@*} of the download command"
  fi
  if ! volume_is_present "$RELEASE_TOOL_VOLUME"; then
    add_plan_with_question "create the Docker volume $RELEASE_TOOL_VOLUME and install the packages of eval/release into it, ai-service included without torch"
  fi
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
  if [ "$gemini_key_source" = prompt ]; then
    add_plan_with_question "save the Gemini key that you entered in .local-run/gemini.env, mode 0600"
  fi
  if [ "$is_with_ai" = true ]; then
    images="$images $AI_SERVICE_IMAGE"
    parts="$parts, ai-service"
    plan_release
  fi
  for image in $images; do
    plan_image "$image"
  done
  if ! image_is_present "$POSTGRES_IMAGE"; then add_plan_with_question "download postgres:17.11"; fi
  if [ "$is_observability" = true ]; then
    parts="$parts, otel-lgtm"
    if ! image_is_present "$OTEL_LGTM_IMAGE"; then
      add_plan_with_question "download grafana/otel-lgtm:0.41.0"
    fi
  fi
  if ! volume_is_present "$DATABASE_VOLUME"; then
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
  # A start or a set-key that was killed while it wrote can leave a temporary file behind.
  remove_partial_files
}

# The parts of the requested mode, in the order of compose.yaml.
mode_parts() {
  local parts="postgres backend-setup backend frontend"
  if [ "$is_with_ai" = true ]; then parts="$parts ai-service"; fi
  if [ "$is_observability" = true ]; then parts="$parts otel-lgtm"; fi
  echo "$parts"
}

# The progress is plain text: with the progress of a terminal, Compose 5.0.0 in a process group
# of its own did not end within 60 s of an INT or a TERM, and with plain text it ends within 1 s.
# With AI, Compose also reads the model and prices of the price file, and the saved key unless
# the environment sets one, which would win anyway.
compose() {
  local -a env_files
  env_files=(--env-file "$SHARED_ENV_FILE" --env-file "$SECRETS_FILE")
  if [ "$is_with_ai" = true ]; then
    env_files+=(--env-file "$PRICES_FILE")
    if [ "$gemini_key_source" != environment ] && [ -f "$GEMINI_FILE" ]; then
      env_files+=(--env-file "$GEMINI_FILE")
    fi
  fi
  docker compose --progress plain --project-name "$PROJECT" --file "$COMPOSE_YAML" \
    "${env_files[@]}" "$@"
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

# One generated secret as NAME=value, or a failure, never a line without its value.
secret_line() {
  local secret
  secret=$(generate_secret) || return 1
  [ "${#secret}" -eq $((SECRET_BYTES * 2)) ] || return 1
  printf '%s=%s\n' "$1" "$secret"
}

# The producers of write_private_file: each stops at its first failure.
new_secrets_text() {
  local name
  echo "# Generated by $SCRIPT_NAME (docs/design/local-run.md). Never commit or share it."
  for name in $SECRET_NAMES; do
    secret_line "$name" || return 1
  done
}

secrets_text_with_grafana_password() {
  local last
  cat "$SECRETS_FILE" || return 1
  # A file edited by hand can lack its last line break.
  last=$(tail -c 1 "$SECRETS_FILE") || return 1
  if [ -n "$last" ]; then echo; fi
  secret_line "$GRAFANA_PASSWORD_NAME"
}

# In single quotes, so Compose reads a $ of the key as it is. printf is a builtin of bash, so the
# key never becomes part of a command line.
gemini_env_text() {
  printf "GEMINI_API_KEY='%s'\n" "$1"
}

write_secrets() {
  if [ ! -f "$SECRETS_FILE" ]; then
    write_private_file "$SECRETS_FILE" new_secrets_text
  fi
  if needs_grafana_password; then
    write_private_file "$SECRETS_FILE" secrets_text_with_grafana_password
  fi
}

write_gemini_key() {
  write_private_file "$GEMINI_FILE" gemini_env_text "$1"
}

# A key in single quotes cannot hold a single quote, and no key of AI Studio holds one.
refuse_a_key_with_a_single_quote() {
  case "$1" in
    *"'"*) fail "nothing changed: the key that you entered holds a ', which .local-run/gemini.env cannot hold and which is a paste mistake; enter the key again" ;;
  esac
}

record_db_port() {
  printf '%s\n' "$db_port" > "$DB_PORT_FILE.partial"
  mv "$DB_PORT_FILE.partial" "$DB_PORT_FILE"
}

# The record holds the hashes from before the build, so a file that changes while the image
# builds makes the next start ask again; it is written only after the build succeeded.
build_image() {
  local service=$1 image=$2 hashes
  hashes=$(image_input_hashes "$image") || fail "the SHA-256 of $(image_inputs "$image") cannot be computed"
  say "Building $image."
  run_child compose build "$service" || fail "the image $image did not build"
  mkdir -p "$IMAGE_INPUTS_DIR"
  write_private_file "$IMAGE_INPUTS_DIR/$image.sha256" printf '%s\n' "$hashes"
}

# Run `supportiq-release download-release` of #41 in a container of the uv image: as the user of
# the script, only the paths of RELEASE_TOOL_PATHS read-only at their paths of the host, an empty
# tmpfs over .local-run/ in case a later mount ever covers it, the cache writable at the same
# absolute path as on the host, and the uv environment in a named volume. The command prints only
# the path of the release folder on standard output (docs/design/local-run.md, Release).
download_release() {
  local status=0 printed path
  local -a release_option mounts
  release_option=()
  if [ -n "$release_id_option" ]; then release_option=(--release "$release_id"); fi
  mounts=()
  for path in $RELEASE_TOOL_PATHS; do
    mounts+=(--volume "$ROOT_DIR/$path:$ROOT_DIR/$path:ro")
  done
  if ! image_is_present "$RELEASE_TOOL_IMAGE"; then
    say "Downloading the image ${RELEASE_TOOL_IMAGE%@*}."
    run_child docker pull "$RELEASE_TOOL_IMAGE" \
      || fail "the image ${RELEASE_TOOL_IMAGE%@*} did not download; try again, or start with --without-ai"
  fi
  # Docker would create a missing folder of a bind mount as root.
  mkdir -p "$release_cache"
  # Always the path of the host: inside the container, HOME points into the volume, so the
  # default of the command would name a folder there.
  export SUPPORTIQ_RELEASE_CACHE="$release_cache"
  say "Downloading the release $release_id into $release_cache/$release_id/, and checking it."
  # SUPPORTIQ_RELEASE_TOKEN goes by name only, so its value is never part of a command line.
  run_child docker run --rm --pull never --user "$LOCAL_RUN_UID:$LOCAL_RUN_GID" \
    "${mounts[@]}" --tmpfs "$STATE_DIR" --volume "$release_cache:$release_cache" \
    --volume "$RELEASE_TOOL_VOLUME:/var/tmp" --workdir "$ROOT_DIR" \
    --env SUPPORTIQ_RELEASE_CACHE --env SUPPORTIQ_RELEASE_TOKEN \
    --env "HOME=$RELEASE_TOOL_HOME/home" \
    --env "UV_PROJECT_ENVIRONMENT=$RELEASE_TOOL_HOME/environment" \
    --env "UV_CACHE_DIR=$RELEASE_TOOL_HOME/cache" \
    --env "UV_PYTHON_INSTALL_DIR=$RELEASE_TOOL_HOME/python" \
    "$RELEASE_TOOL_IMAGE" \
    uv run --locked --project eval/release supportiq-release download-release \
    ${release_option[@]+"${release_option[@]}"} --yes > "$RELEASE_PATH_FILE.partial" || status=$?
  case "$status" in
    0) ;;
    "$DOWNLOAD_NETWORK_FAILURE")
      fail "the release $release_id did not download because of a network failure; the cache is unchanged: try again, or start with --without-ai"
      ;;
    "$DOWNLOAD_CHECK_FAILED")
      fail "the release $release_id failed its check, as the download command says above; the cache $release_cache/ keeps no partial release: start with --without-ai, or --release with another published release"
      ;;
    "$DOWNLOAD_BAD_INPUT")
      fail "the download command could not use its input, for the reason that it printed above; the cache is unchanged"
      ;;
    "$DOWNLOAD_DECLINED")
      fail "the download command declined although $SCRIPT_NAME passed --yes, which is a bug of $SCRIPT_NAME; please report it"
      ;;
    *) fail "the download command ended with status $status; the cache keeps no partial release: try again, or start with --without-ai" ;;
  esac
  printed=$(cat "$RELEASE_PATH_FILE.partial")
  rm -f "$RELEASE_PATH_FILE.partial"
  case "$printed" in
    /*) ;;
    *) fail "the download command printed no absolute path of the release folder; nothing was started" ;;
  esac
  if [ ! -d "$printed" ] || [ ! -f "$printed/$RELEASE_MANIFEST" ]; then
    fail "the download command printed $printed, which is no release folder on this machine; nothing was started"
  fi
  release_folder=$printed
}

# After ai-service did not get ready: name the cause when it is known.
explain_ai_service_failure() {
  local container logs
  container=$(compose ps --all --quiet ai-service 2> /dev/null | head -n 1 || true)
  if [ -n "$container" ] \
    && [ "$(docker inspect --format '{{.State.OOMKilled}}' "$container" 2> /dev/null || true)" = true ]; then
    say "$SCRIPT_NAME: ai-service ran out of memory: $(docker_memory_hint)."
    return 0
  fi
  logs=$(compose logs --no-log-prefix --since "$started_at" ai-service 2> /dev/null || true)
  case "$logs" in
    *'"event":"release.invalid"'*)
      if [ -n "$release_cache" ] && [ "$release_folder" = "$release_cache/$release_id" ]; then
        say "$SCRIPT_NAME: ai-service refused the cached release $release_cache/$release_id/, for example because it was edited: remove that folder, and the next start downloads the release again."
      else
        say "$SCRIPT_NAME: ai-service refused the release folder $release_folder: the release.invalid line of its log names the reason."
      fi
      ;;
  esac
}

start_compose() {
  local profiles="" first_parts first_names first_verb
  export LOCAL_RUN_UID LOCAL_RUN_GID
  LOCAL_RUN_UID=$(id -u)
  LOCAL_RUN_GID=$(id -g)
  if [ "$is_with_ai" = true ]; then profiles=ai; fi
  if [ "$is_observability" = true ]; then
    profiles="${profiles:+$profiles,}observability"
    export LOCAL_TRACE_EXPORTER=otlp
  fi
  export COMPOSE_PROFILES="$profiles"
  build_image backend "$BACKEND_IMAGE"
  build_image frontend "$FRONTEND_IMAGE"
  if [ "$is_with_ai" = true ]; then build_image ai-service "$AI_SERVICE_IMAGE"; fi
  if ! image_is_present "$POSTGRES_IMAGE"; then
    run_child compose pull postgres || fail "postgres:17.11 did not download"
  fi
  if [ "$is_observability" = true ] && ! image_is_present "$OTEL_LGTM_IMAGE"; then
    run_child compose pull otel-lgtm || fail "grafana/otel-lgtm:0.41.0 did not download"
  fi
  if [ "$is_with_ai" = true ]; then
    if [ "$is_download_due" = true ]; then
      download_release
    elif [ -z "$release_folder" ]; then
      release_folder="$release_cache/$release_id"
    fi
    LOCAL_RELEASE_FOLDER=$(cd "$release_folder" && pwd)
    export LOCAL_RELEASE_FOLDER
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
      if [ "$is_with_ai" = true ]; then explain_ai_service_failure; fi
      fail "$first_names did not get ready, so backend and frontend were not started; read the log with: $SCRIPT_NAME logs <part>, then run $SCRIPT_NAME stop"
    fi
  fi
  say "Starting the parts, and waiting until each one is healthy."
  if ! run_child compose up --detach --wait --wait-timeout "$COMPOSE_WAIT_TIMEOUT_S" --no-build; then
    compose ps --all --format 'table {{.Service}}\t{{.Status}}' >&2 || true
    if backend_setup_failed; then
      say "$SCRIPT_NAME: backend-setup failed. If its log shows a password failure, the volume $DATABASE_VOLUME holds a database that a start in another folder of the repository created: this machine has one local database, and only the .local-run/secrets.env of that folder opens it (the guide, Remove the local data)."
    fi
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
  if [ "$is_with_ai" = true ]; then
    say "ai-service runs with the release folder $release_folder."
  else
    say "Without AI, staff handle every ticket manually."
  fi
  say "Demo accounts: customer-1 to customer-3, staff-1 and staff-2, manager-1 and manager-2,"
  say "admin-1 and admin-2, with the SEED_PASSWORD_* passwords of .local-run/secrets.env."
  say "PostgreSQL: host 127.0.0.1, port $db_port, database supportiq, user supportiq_owner,"
  say "with the password LOCAL_DB_OWNER_PASSWORD of .local-run/secrets.env."
  say "Follow the logs with: $SCRIPT_NAME logs. Stop with: $SCRIPT_NAME stop"
}

start() {
  local is_docker_checked=false
  parse_start_options "$@"
  load_ports
  stop_when_already_running
  if [ -d "$LOCK_DIR" ]; then
    fail "another start holds .local-run/start.lock; when no start runs, remove that folder"
  fi
  check_docker
  if [ -z "$gaps" ]; then
    is_docker_checked=true
    check_ports
  fi
  check_ai_mode "$is_docker_checked"
  check_secrets_file
  check_hash_tool
  if [ -n "$gaps" ]; then
    say "$SCRIPT_NAME: nothing changed, because:"
    printf '%s' "$gaps" >&2
    exit 1
  fi
  warn_when_cpus_are_few
  # After every check, so nobody is asked for a key by a start that would stop anyway.
  resolve_gemini_key
  build_plan
  ask_when_due
  take_lock
  write_secrets
  if [ "$gemini_key_source" = prompt ]; then write_gemini_key "$entered_key"; fi
  start_compose
  report_started
}

# ----- stop, status, logs, releases, and set-key -----

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

# List the published releases, the default one, and those in the cache. Bash only: it downloads
# and changes nothing, and needs no network.
releases() {
  local manifest id marks cache="" count=0
  [ "$#" -eq 0 ] || usage
  read_pinned_file || true
  cache=$(release_cache_path) || cache=""
  say "Published releases, from eval/releases/*/$RELEASE_MANIFEST:"
  for manifest in "$RELEASE_RECORDS_DIR"/*/"$RELEASE_MANIFEST"; do
    [ -f "$manifest" ] || continue
    id=${manifest%/*}
    id=${id##*/}
    marks=""
    if [ "$id" = "$pinned_release_id" ]; then marks="$marks, the default"; fi
    if [ -n "$cache" ] && is_cached_release "$cache" "$id"; then marks="$marks, in the cache"; fi
    say "  $id${marks:+ (${marks#, })}"
    count=$((count + 1))
  done
  if [ "$count" -eq 0 ]; then say "  none"; fi
  if [ -z "$pinned_release_id" ]; then
    say "No default release: eval/releases/pinned-release.txt is missing or does not hold a release ID and a size."
  fi
  if [ -n "$cache" ]; then
    say "Release cache: $cache"
  else
    say "Release cache: unknown, because SUPPORTIQ_RELEASE_CACHE is not an absolute path."
  fi
  say "Start with another one with: $SCRIPT_NAME start --release <id>"
}

# Enter or replace the saved key at once: the command itself is the user's request. It needs a
# terminal, because a key on a command line or in a pipe could end up in the shell history or
# the process list.
set_key() {
  [ "$#" -eq 0 ] || usage
  if [ ! -t 0 ]; then
    fail "set-key needs a terminal, so that the key is typed hidden and never passes through a command line or a pipe; .local-run/gemini.env is unchanged"
  fi
  prompt_for_key "keep the saved key"
  if [ -z "$entered_key" ]; then
    say "Nothing changed."
    return 0
  fi
  warn_on_key_form "$entered_key"
  refuse_a_key_with_a_single_quote "$entered_key"
  mkdir -p "$STATE_DIR"
  chmod 700 "$STATE_DIR"
  write_gemini_key "$entered_key"
  say "Saved in .local-run/gemini.env, which git ignores. Remove that file to forget the key. A running ai-service keeps its old key until the next start: run $SCRIPT_NAME stop, then start."
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
    releases) releases "$@" ;;
    set-key) set_key "$@" ;;
    *) usage ;;
  esac
}

main "$@"
