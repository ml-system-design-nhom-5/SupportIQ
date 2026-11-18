#!/usr/bin/env bash
# The script tests of deploy/local/local-run.sh (docs/design/local-run.md, Errors and
# guardrails). Each test copies the script, compose.yaml, and local-run.env into a new temporary
# root, with free high ports, and runs it with a PATH of the stubs `docker` and `id` and of the
# system tools without any docker, so no test reaches the real Docker, starts a container, or
# touches the real .local-run/, on any machine. The tests run in random order (TEST-15);
# the seed is printed, and TEST_SEED repeats an order. They need bash and python3, and no other
# tool.
#
# Usage: deploy/local/tests/test-local-run.sh
set -euo pipefail

REPOSITORY_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
readonly REPOSITORY_ROOT
readonly SECRET_COUNT=8
readonly SECRET_PATTERN='^[0-9a-f]{64}$'
readonly EXIT_INTERRUPTED=130

root=""
tools=""
fixture_path=""
run_status=0
run_output=""

# ----- the fixture -----

# A folder of links to every tool of /usr/bin and /bin except docker*. On Linux, the real docker
# lies in /usr/bin, so a PATH with /usr/bin would let a test that removes the stub run the real
# Docker on the project supportiq-local of the person. The tests run with this folder instead.
make_tools() {
  local tool name
  tools=$(mktemp -d)
  for tool in /usr/bin/* /bin/*; do
    name=${tool##*/}
    case "$name" in docker*) continue ;; esac
    # -L, not -e: /bin can be a link to /usr/bin, so a name comes twice, and a broken link of
    # /usr/bin would make -e false and ln fail the second time.
    [ -L "$tools/$name" ] || ln -s "$tool" "$tools/$name"
  done
}

write_stubs() {
  cat > "$1/docker" << 'STUB'
#!/usr/bin/env bash
# A stub of docker for the script tests: it logs each call and answers from STUB_* variables.
printf '%s\n' "$*" >> "$STUB_DOCKER_LOG"
case "$*" in
  info) exit "${STUB_DOCKER_INFO_STATUS:-0}" ;;
  "buildx version") exit 0 ;;
  "compose version --short") echo "${STUB_COMPOSE_VERSION:-2.29.1}"; exit 0 ;;
  "version --format"*) echo "${STUB_API_VERSION:-1.51}"; exit 0 ;;
  "image inspect"*) exit "${STUB_IMAGE_INSPECT_STATUS:-0}" ;;
  "volume inspect"*) exit "${STUB_VOLUME_INSPECT_STATUS:-1}" ;;
  *"ps --services --status running"*) printf '%s' "${STUB_RUNNING_SERVICES:-}"; exit 0 ;;
  *"ps --all --quiet"*) printf '%s' "${STUB_CONTAINER_IDS:-}"; exit 0 ;;
  *" build "*) if [ -n "${STUB_BUILD_SLEEP_S:-}" ]; then exec sleep "$STUB_BUILD_SLEEP_S"; fi ;;
  *" up "*)
    # What Compose would interpolate from the environment of this call.
    printf 'environment of up: SEED_PASSWORD_CUSTOMER=%s COMPOSE_PROJECT_NAME=%s LOCAL_GRAFANA_ADMIN_PASSWORD=%s\n' \
      "${SEED_PASSWORD_CUSTOMER-unset}" "${COMPOSE_PROJECT_NAME-unset}" \
      "${LOCAL_GRAFANA_ADMIN_PASSWORD-unset}" >> "$STUB_DOCKER_LOG"
    if [ -n "${STUB_UP_RECORDS_SIGNALS:-}" ]; then
      trap 'echo "stub up got SIGINT" >> "$STUB_DOCKER_LOG"; exit 130' INT
      trap 'echo "stub up got SIGTERM" >> "$STUB_DOCKER_LOG"; exit 143' TERM
      sleep 30 &
      wait
    fi
    if [ -n "${STUB_UP_SLEEP_S:-}" ]; then exec sleep "$STUB_UP_SLEEP_S"; fi
    exit "${STUB_UP_STATUS:-0}"
    ;;
  *" logs "*"--since"*)
    printf '%s\n' '{"event":"settings.loaded"}' '{"event":"database_role.applied"}' \
      '{"event":"database.migrated"}' '{"event":"seed.loaded"}'
    ;;
esac
exit 0
STUB
  cat > "$1/id" << 'STUB'
#!/usr/bin/env bash
# A stub of id for the script tests: STUB_UID replaces the user ID of `id -u`.
if [ "${1:-}" = -u ] && [ -n "${STUB_UID:-}" ]; then echo "$STUB_UID"; exit 0; fi
exec /usr/bin/id "$@"
STUB
  chmod +x "$1/docker" "$1/id"
}

free_port() {
  python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'
}

new_root() {
  root=$(mktemp -d)
  fixture_path="$root/bin:$tools"
  mkdir -p "$root/deploy/local" "$root/bin"
  cp "$REPOSITORY_ROOT/deploy/local/local-run.sh" "$REPOSITORY_ROOT/deploy/local/compose.yaml" \
    "$root/deploy/local/"
  sed -e "s/^LOCAL_FRONTEND_PORT=.*/LOCAL_FRONTEND_PORT=$(free_port)/" \
    -e "s/^LOCAL_BACKEND_PORT=.*/LOCAL_BACKEND_PORT=$(free_port)/" \
    -e "s/^LOCAL_AI_SERVICE_PORT=.*/LOCAL_AI_SERVICE_PORT=$(free_port)/" \
    -e "s/^LOCAL_DB_PORT=.*/LOCAL_DB_PORT=$(free_port)/" \
    -e "s/^LOCAL_GRAFANA_PORT=.*/LOCAL_GRAFANA_PORT=$(free_port)/" \
    "$REPOSITORY_ROOT/deploy/local/local-run.env" > "$root/deploy/local/local-run.env"
  write_stubs "$root/bin"
  : > "$root/docker.log"
}

port_of() {
  sed -n "s/^$1=//p" "$root/deploy/local/local-run.env"
}

# Run local-run.sh in the fixture without a terminal; keep its status and its output.
run_script() {
  run_status=0
  run_output=$(PATH="$fixture_path" STUB_DOCKER_LOG="$root/docker.log" \
    bash "$root/deploy/local/local-run.sh" "$@" < /dev/null 2>&1) || run_status=$?
}

# Run local-run.sh on a pseudo-terminal, and give this answer to its question.
run_script_on_a_terminal() {
  local answer=$1
  shift
  run_status=0
  run_output=$(PATH="$fixture_path" STUB_DOCKER_LOG="$root/docker.log" \
    python3 - "$answer" "$root/deploy/local/local-run.sh" "$@" << 'PYTHON'
import os
import pty
import sys

answer, script, arguments = sys.argv[1], sys.argv[2], sys.argv[3:]
pid, terminal = pty.fork()
if pid == 0:
    os.execvp("bash", ["bash", script, *arguments])
output = b""
answered = False
while True:
    try:
        chunk = os.read(terminal, 1024)
    except OSError:
        break
    if not chunk:
        break
    output += chunk
    if not answered and b"Proceed? [y/N]" in output:
        os.write(terminal, answer.encode() + b"\n")
        answered = True
_, status = os.waitpid(pid, 0)
sys.stdout.write(output.decode(errors="replace"))
sys.exit(os.waitstatus_to_exitcode(status))
PYTHON
  ) || run_status=$?
}

# Run local-run.sh on a pseudo-terminal, and press Ctrl+C once its output holds a text. The
# terminal sends SIGINT to its foreground process group only, as a person's Ctrl+C does.
run_script_on_a_terminal_and_press_ctrl_c() {
  local text=$1
  shift
  run_status=0
  run_output=$(PATH="$fixture_path" STUB_DOCKER_LOG="$root/docker.log" \
    python3 - "$text" "$root/deploy/local/local-run.sh" "$@" << 'PYTHON'
import os
import pty
import sys
import time

text, script, arguments = sys.argv[1].encode(), sys.argv[2], sys.argv[3:]
pid, terminal = pty.fork()
if pid == 0:
    os.execvp("bash", ["bash", script, *arguments])
output = b""
pressed = False
while True:
    try:
        chunk = os.read(terminal, 1024)
    except OSError:
        break
    if not chunk:
        break
    output += chunk
    if not pressed and text in output:
        time.sleep(1)
        os.write(terminal, b"\x03")
        pressed = True
_, status = os.waitpid(pid, 0)
sys.stdout.write(output.decode(errors="replace"))
sys.exit(os.waitstatus_to_exitcode(status))
PYTHON
  ) || run_status=$?
}

# Run local-run.sh, and send it a signal once its output holds a text.
run_script_and_signal() {
  local signal_name=$1 text=$2
  shift 2
  run_status=0
  run_output=$(PATH="$fixture_path" STUB_DOCKER_LOG="$root/docker.log" \
    python3 - "$signal_name" "$text" "$root/deploy/local/local-run.sh" "$@" << 'PYTHON'
import signal
import subprocess
import sys
import time

signal_name, text, script, arguments = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
process = subprocess.Popen(
    ["bash", script, *arguments],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
output = b""
for line in process.stdout:
    output += line
    if text.encode() in output:
        time.sleep(1)
        process.send_signal(getattr(signal, signal_name))
        break
rest, _ = process.communicate(timeout=30)
sys.stdout.write((output + rest).decode(errors="replace"))
sys.exit(process.returncode)
PYTHON
  ) || run_status=$?
}

# A state after a first start: the secrets, the volume, and the recorded port exist.
given_a_first_start() {
  run_script start --yes
  [ "$run_status" -eq 0 ] || fail_test "the first start failed"
  : > "$root/docker.log"
}

# ----- assertions -----

# Each test runs in a subshell of its own, so a failed assertion ends only that test. It exits,
# because `set -e` does not apply inside the `if` of the runner.
fail_test() {
  printf 'FAILED: %s\n%s\n' "$1" "$run_output" >&2
  exit 1
}

expect_status() {
  [ "$run_status" -eq "$1" ] || fail_test "expected status $1, got $run_status"
}

expect_output() {
  printf '%s' "$run_output" | grep -qF -- "$1" || fail_test "expected the output to hold: $1"
}

expect_no_output() {
  ! printf '%s' "$run_output" | grep -qF -- "$1" || fail_test "expected the output to lack: $1"
}

expect_no_state() {
  [ ! -e "$root/.local-run" ] || fail_test "expected no .local-run/"
}

expect_logged() {
  grep -qF -- "$1" "$root/docker.log" || fail_test "expected a docker call with: $1"
}

expect_not_logged() {
  ! grep -qF -- "$1" "$root/docker.log" || fail_test "expected no docker call with: $1"
}

secret_value() {
  sed -n "s/^$1=//p" "$root/.local-run/secrets.env"
}

recorded_port() {
  cat "$root/.local-run/db-port"
}

file_mode() {
  stat -c %a "$1" 2> /dev/null || stat -f %Lp "$1"
}

# ----- usage and root -----

test_a_command_is_required() {
  run_script
  expect_status 2
  expect_output "usage:"
}

test_start_refuses_an_unknown_option() {
  run_script start --native
  expect_status 2
  expect_no_state
}

test_every_command_refuses_root() {
  local command_name
  for command_name in start stop status logs; do
    STUB_UID=0 run_script "$command_name"
    expect_status 1
    expect_output "do not run it as root or with sudo"
  done
  expect_no_state
  [ ! -s "$root/docker.log" ] || fail_test "root ran a docker command"
}

# ----- requirements -----

test_start_without_docker_names_it_and_changes_nothing() {
  rm "$root/bin/docker"
  [ -z "$(PATH="$fixture_path" bash -c 'command -v docker' || true)" ] \
    || fail_test "the PATH of the fixture reaches a real docker"
  run_script start --yes
  [ ! -s "$root/docker.log" ] || fail_test "a docker command ran"
  expect_status 1
  expect_output "Docker is missing"
  expect_no_state
}

test_start_with_docker_not_running_stops_before_the_question() {
  STUB_DOCKER_INFO_STATUS=1 run_script start --yes
  expect_status 1
  expect_output "Docker does not run"
  expect_no_state
}

test_start_with_compose_v1_stops() {
  STUB_COMPOSE_VERSION=1.29.2 run_script start --yes
  expect_status 1
  expect_output "Docker Compose 2.20.2 or later is needed (docker compose, not docker-compose), and this one is 1.29.2"
  expect_no_state
}

test_start_with_compose_2_20_1_stops() {
  STUB_COMPOSE_VERSION=2.20.1 run_script start --yes
  expect_status 1
  expect_output "Docker Compose 2.20.2 or later is needed"
  expect_no_state
}

test_start_compares_versions_as_numbers() {
  STUB_COMPOSE_VERSION=2.3.0 run_script start --yes
  expect_status 1
  expect_output "Docker Compose 2.20.2 or later is needed (docker compose, not docker-compose), and this one is 2.3.0"
  STUB_API_VERSION=1.9 run_script start --yes
  expect_status 1
  expect_output "this one has the API 1.9"
  expect_no_state
}

test_start_accepts_compose_5_0_0() {
  STUB_COMPOSE_VERSION=5.0.0 run_script start --yes
  expect_status 0
  expect_no_output "Docker Compose 2.20.2 or later is needed"
}

test_every_compose_call_prints_plain_progress() {
  run_script start --yes
  expect_status 0
  ! grep -F -- "--file" "$root/docker.log" | grep -vqF -- "compose --progress plain " \
    || fail_test "a compose call lacks --progress plain"
}

test_start_accepts_compose_2_20_2_with_a_suffix() {
  STUB_COMPOSE_VERSION=v2.20.2-desktop.1 run_script start --yes
  expect_status 0
  expect_no_output "Docker Compose 2.20.2 or later is needed"
}

test_start_with_docker_api_1_43_stops() {
  STUB_API_VERSION=1.43 run_script start --yes
  expect_status 1
  expect_output "Docker Engine 25 or later is needed, with the API 1.44 or later, and this one has the API 1.43"
  expect_no_state
}

test_a_volume_without_its_secrets_file_stops_before_the_question() {
  STUB_VOLUME_INSPECT_STATUS=0 run_script start --yes
  expect_status 1
  expect_output ".local-run/secrets.env is missing, but the volume supportiq-local_postgres-data still holds the database"
  expect_output "Remove the local data"
  expect_no_state
  expect_not_logged " up "
}

test_compose_project_name_of_the_environment_changes_nothing() {
  COMPOSE_PROJECT_NAME=another-project run_script start --yes
  expect_status 0
  ! grep -F -- "--file" "$root/docker.log" | grep -vqF -- "--project-name supportiq-local" \
    || fail_test "a compose call lacks --project-name supportiq-local"
  expect_logged "environment of up: SEED_PASSWORD_CUSTOMER=unset COMPOSE_PROJECT_NAME=unset"
}

test_an_exported_secret_never_replaces_the_one_of_the_secrets_file() {
  SEED_PASSWORD_CUSTOMER=exported-in-the-shell run_script start --yes
  expect_status 0
  expect_logged "environment of up: SEED_PASSWORD_CUSTOMER=unset"
  expect_no_output exported-in-the-shell
}

test_an_empty_grafana_password_counts_as_not_set() {
  LOCAL_GRAFANA_ADMIN_PASSWORD="" run_script start --observability --yes
  expect_status 0
  secret_value LOCAL_GRAFANA_ADMIN_PASSWORD | grep -Eq "$SECRET_PATTERN" \
    || fail_test "no generated Grafana password"
  expect_logged "LOCAL_GRAFANA_ADMIN_PASSWORD=unset"
}

hold_port_and_start() {
  local port=$1 listener
  shift
  python3 -c 'import socket, sys, time
s = socket.socket(); s.bind(("127.0.0.1", int(sys.argv[1]))); s.listen(); time.sleep(30)' "$port" &
  listener=$!
  sleep 1
  run_script start "$@"
  kill "$listener"
  wait "$listener" 2> /dev/null || true
}

test_a_taken_backend_port_names_the_port_and_its_setting() {
  local port
  port=$(port_of LOCAL_BACKEND_PORT)
  hold_port_and_start "$port" --yes
  expect_status 1
  expect_output "port $port on 127.0.0.1 is taken (LOCAL_BACKEND_PORT)"
  expect_no_state
}

test_a_taken_database_port_suggests_local_db_port_and_picks_no_other() {
  local port
  port=$(port_of LOCAL_DB_PORT)
  hold_port_and_start "$port" --yes
  expect_status 1
  expect_output "port $port on 127.0.0.1 is taken, so PostgreSQL cannot use it; set LOCAL_DB_PORT"
  expect_not_logged " up "
  expect_no_state
}

test_an_invalid_local_db_port_stops() {
  local value
  for value in abc 0 70000 -1; do
    LOCAL_DB_PORT=$value run_script start --yes
    expect_status 1
    expect_output "LOCAL_DB_PORT must be a port number from 1 to 65535"
  done
  expect_no_state
}

test_start_with_ai_without_its_settings_names_each_setting() {
  mkdir "$root/release"
  : > "$root/release/release-manifest.json"
  run_script start --with-ai "$root/release" --yes
  expect_status 1
  expect_output "--with-ai needs GEMINI_API_KEY in the environment"
  expect_output "--with-ai needs LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS in the environment"
  expect_output "--with-ai needs LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS in the environment"
  expect_no_state
}

test_start_with_ai_without_a_manifest_stops() {
  mkdir "$root/release"
  GEMINI_API_KEY=key LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS=1 \
    LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS=1 run_script start --with-ai "$root/release" --yes
  expect_status 1
  expect_output "holds no readable release-manifest.json"
  expect_no_output "--with-ai needs"
  expect_no_state
}

# ----- the plan and the question -----

test_a_first_start_without_a_terminal_and_without_yes_changes_nothing() {
  run_script start
  expect_status 1
  expect_output "The local run will:"
  expect_output "pass --yes"
  expect_no_state
  expect_not_logged " build "
}

test_a_first_start_names_the_default_port_and_its_source() {
  run_script start
  expect_output "PostgreSQL on 127.0.0.1:$(port_of LOCAL_DB_PORT), the default; set LOCAL_DB_PORT to change it"
}

test_a_first_start_answered_n_on_a_terminal_changes_nothing() {
  run_script_on_a_terminal n start
  expect_status 1
  expect_output "Proceed? [y/N]"
  expect_no_state
  expect_not_logged " build "
}

test_a_first_start_answered_y_on_a_terminal_starts() {
  run_script_on_a_terminal y start
  expect_status 0
  expect_logged " up --detach --wait"
}

test_a_first_start_with_yes_writes_the_secrets_records_the_port_and_builds_in_order() {
  local name value calls
  run_script start --yes
  expect_status 0
  [ "$(file_mode "$root/.local-run/secrets.env")" = 600 ] || fail_test "secrets.env is not 0600"
  [ "$(grep -c '^[A-Z_]*=' "$root/.local-run/secrets.env")" -eq "$SECRET_COUNT" ] \
    || fail_test "expected $SECRET_COUNT secrets"
  for name in LOCAL_DB_SUPERUSER_PASSWORD LOCAL_DB_OWNER_PASSWORD LOCAL_DB_APP_PASSWORD \
    LOCAL_SERVICE_TOKEN SEED_PASSWORD_CUSTOMER SEED_PASSWORD_STAFF SEED_PASSWORD_MANAGER \
    SEED_PASSWORD_ADMIN; do
    value=$(secret_value "$name")
    printf '%s' "$value" | grep -Eq "$SECRET_PATTERN" || fail_test "$name is not 64 hex digits"
    expect_no_output "$value"
  done
  [ "$(recorded_port)" = "$(port_of LOCAL_DB_PORT)" ] || fail_test "the port was not recorded"
  calls=$(grep -E ' (build|up) ' "$root/docker.log" | sed -E 's/.* (build [a-z-]+|up).*/\1/')
  [ "$calls" = "$(printf 'build backend\nbuild frontend\nup')" ] \
    || fail_test "expected build backend, build frontend, then up; got: $calls"
  expect_output "Setup: database_role.applied, database.migrated, seed.loaded."
  expect_output "http://localhost:$(port_of LOCAL_FRONTEND_PORT) and http://127.0.0.1:$(port_of LOCAL_FRONTEND_PORT)"
  expect_output "PostgreSQL: host 127.0.0.1, port $(port_of LOCAL_DB_PORT), database supportiq, user supportiq_owner"
  [ ! -e "$root/.local-run/start.lock" ] || fail_test "the lock stayed"
}

test_a_second_start_with_nothing_new_asks_nothing_even_without_a_terminal() {
  local first
  given_a_first_start
  first=$(cat "$root/.local-run/secrets.env")
  STUB_VOLUME_INSPECT_STATUS=0 run_script start
  expect_status 0
  expect_output "Starting the local run"
  expect_no_output "Proceed?"
  expect_logged " up --detach --wait"
  [ "$(cat "$root/.local-run/secrets.env")" = "$first" ] || fail_test "secrets.env changed"
}

test_a_missing_image_makes_the_question_due() {
  given_a_first_start
  STUB_VOLUME_INSPECT_STATUS=0 STUB_IMAGE_INSPECT_STATUS=1 run_script start
  expect_status 1
  expect_output "which downloads its dependencies"
  expect_output "pass --yes"
  expect_not_logged " build "
}

test_another_local_db_port_warns_and_asks() {
  local new_port
  given_a_first_start
  new_port=$(free_port)
  LOCAL_DB_PORT=$new_port STUB_VOLUME_INSPECT_STATUS=0 run_script start
  expect_status 1
  expect_output "move PostgreSQL from 127.0.0.1:$(port_of LOCAL_DB_PORT) to 127.0.0.1:$new_port"
  expect_output "PostgreSQL on 127.0.0.1:$new_port, from LOCAL_DB_PORT"
  [ "$(recorded_port)" = "$(port_of LOCAL_DB_PORT)" ] || fail_test "the record changed"
  LOCAL_DB_PORT=$new_port STUB_VOLUME_INSPECT_STATUS=0 run_script start --yes
  expect_status 0
  [ "$(recorded_port)" = "$new_port" ] || fail_test "the new port was not recorded"
}

test_another_local_db_port_answered_n_keeps_the_record() {
  given_a_first_start
  LOCAL_DB_PORT=$(free_port) STUB_VOLUME_INSPECT_STATUS=0 run_script_on_a_terminal n start
  expect_status 1
  [ "$(recorded_port)" = "$(port_of LOCAL_DB_PORT)" ] || fail_test "the record changed"
  expect_not_logged " up "
}

test_yes_answers_only_the_question_and_never_a_missing_tool() {
  STUB_DOCKER_INFO_STATUS=1 run_script start --yes
  expect_status 1
  expect_no_output "The local run will:"
}

# ----- what already runs -----

test_start_when_every_part_runs_changes_nothing() {
  STUB_RUNNING_SERVICES=$'backend\nfrontend\npostgres\n' run_script start
  expect_status 0
  expect_output "already runs"
  expect_output "to run the changes of your working tree, run deploy/local/local-run.sh stop, then start"
  expect_not_logged " build "
  expect_no_state
}

test_start_with_another_port_while_every_part_runs_stops() {
  given_a_first_start
  LOCAL_DB_PORT=$(free_port) STUB_RUNNING_SERVICES=$'backend\nfrontend\npostgres\n' \
    run_script start --yes
  expect_status 1
  expect_output "already runs with PostgreSQL on 127.0.0.1:$(port_of LOCAL_DB_PORT); run deploy/local/local-run.sh stop first"
  expect_not_logged " up "
}

test_start_when_some_parts_run_starts_the_others() {
  STUB_RUNNING_SERVICES=$'postgres\n' run_script start --yes
  expect_status 0
  expect_no_output "already runs"
  expect_logged " up --detach --wait"
}

test_start_when_it_runs_in_another_mode_stops() {
  STUB_RUNNING_SERVICES=$'ai-service\nbackend\nfrontend\npostgres\n' run_script start --yes
  expect_status 1
  expect_output "already runs in another mode"
  expect_no_state
}

test_start_while_another_start_holds_the_lock_stops() {
  mkdir -p "$root/.local-run/start.lock"
  run_script start --yes
  expect_status 1
  expect_output "another start holds .local-run/start.lock"
  expect_not_logged " build "
}

test_a_secrets_file_that_lacks_a_value_stops_and_stays_as_it_is() {
  mkdir -p "$root/.local-run"
  printf 'LOCAL_DB_SUPERUSER_PASSWORD=%064d\n' 0 > "$root/.local-run/secrets.env"
  run_script start --yes
  expect_status 1
  expect_output ".local-run/secrets.env lacks LOCAL_DB_OWNER_PASSWORD"
  [ "$(wc -l < "$root/.local-run/secrets.env" | tr -d ' ')" = 1 ] || fail_test "secrets.env changed"
}

# ----- observability -----

test_observability_generates_the_grafana_password_once() {
  local first
  run_script start --observability --yes
  expect_status 0
  first=$(secret_value LOCAL_GRAFANA_ADMIN_PASSWORD)
  printf '%s' "$first" | grep -Eq "$SECRET_PATTERN" || fail_test "no generated Grafana password"
  expect_no_output "$first"
  STUB_VOLUME_INSPECT_STATUS=0 run_script start --observability
  expect_status 0
  expect_no_output "Proceed?"
  [ "$(secret_value LOCAL_GRAFANA_ADMIN_PASSWORD)" = "$first" ] || fail_test "it changed"
}

test_observability_takes_the_grafana_password_of_the_environment() {
  LOCAL_GRAFANA_ADMIN_PASSWORD=chosen-by-the-user run_script start --observability --yes
  expect_status 0
  [ -z "$(secret_value LOCAL_GRAFANA_ADMIN_PASSWORD)" ] || fail_test "it was written to the file"
  expect_no_output chosen-by-the-user
}

# ----- failures and interruptions -----

given_a_release_folder_and_the_ai_settings() {
  mkdir "$root/release"
  : > "$root/release/release-manifest.json"
  export GEMINI_API_KEY=not-a-real-key LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS=1 \
    LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS=1
}

test_with_ai_ai_service_starts_first_then_the_others() {
  given_a_release_folder_and_the_ai_settings
  run_script start --with-ai "$root/release" --yes
  expect_status 0
  [ "$(grep -c ' up ' "$root/docker.log")" -eq 2 ] || fail_test "expected two ups"
  grep ' up ' "$root/docker.log" | sed -n 1p | grep -qE -- '--no-build ai-service$' \
    || fail_test "expected the first up for ai-service alone"
  grep ' up ' "$root/docker.log" | sed -n 2p | grep -qE -- '--no-build$' \
    || fail_test "expected the second up for every part"
}

test_with_ai_a_failing_ai_service_starts_neither_backend_nor_frontend() {
  given_a_release_folder_and_the_ai_settings
  STUB_UP_STATUS=1 run_script start --with-ai "$root/release" --yes
  expect_status 1
  expect_output "ai-service did not get ready, so backend and frontend were not started"
  [ "$(grep -c ' up ' "$root/docker.log")" -eq 1 ] || fail_test "expected one up, of ai-service"
  expect_logged "--no-build ai-service"
}

test_with_ai_and_observability_both_start_first() {
  given_a_release_folder_and_the_ai_settings
  run_script start --with-ai "$root/release" --observability --yes
  expect_status 0
  expect_output "Starting ai-service and otel-lgtm first, and waiting until they are healthy."
  expect_logged "--no-build ai-service otel-lgtm"
  expect_output "Sign in as admin, with the password"
  expect_output "LOCAL_GRAFANA_ADMIN_PASSWORD of your shell, or of .local-run/secrets.env"
}

test_with_ai_and_observability_failing_names_both() {
  given_a_release_folder_and_the_ai_settings
  STUB_UP_STATUS=1 run_script start --with-ai "$root/release" --observability --yes
  expect_status 1
  expect_output "ai-service and otel-lgtm did not get ready, so backend and frontend were not started"
}

test_observability_starts_otel_lgtm_first() {
  STUB_UP_STATUS=1 run_script start --observability --yes
  expect_status 1
  expect_output "otel-lgtm did not get ready, so backend and frontend were not started"
  expect_logged "--no-build otel-lgtm"
}

test_a_part_that_does_not_get_ready_stops_the_start() {
  STUB_UP_STATUS=1 run_script start --yes
  expect_status 1
  expect_output "a part did not get ready"
  [ ! -e "$root/.local-run/start.lock" ] || fail_test "the lock stayed"
}

test_ctrl_c_while_the_parts_start_stops_them_and_keeps_the_volume() {
  STUB_UP_SLEEP_S=30 run_script_and_signal SIGINT "Starting the parts" start --yes
  expect_status "$EXIT_INTERRUPTED"
  expect_output "interrupted"
  expect_logged " down"
  expect_not_logged "--volumes"
  [ ! -e "$root/.local-run/start.lock" ] || fail_test "the lock stayed"
}

test_ctrl_c_on_a_terminal_reaches_only_the_script_and_prints_no_job_line() {
  STUB_UP_RECORDS_SIGNALS=1 run_script_on_a_terminal_and_press_ctrl_c "Starting the parts" start --yes
  expect_status "$EXIT_INTERRUPTED"
  # The docker command runs as a group of its own, so only the trap of the script ends it.
  expect_not_logged "stub up got SIGINT"
  expect_logged "stub up got SIGTERM"
  [ "$(printf '%s' "$run_output" | grep -c 'interrupted')" -eq 1 ] \
    || fail_test "expected exactly one line of the interruption"
  expect_no_output "Terminated"
  expect_no_output "[1]"
  expect_no_output "Killed"
  expect_no_output "did not end within"
  expect_logged " down"
}

test_term_while_the_parts_start_stops_them() {
  STUB_UP_SLEEP_S=30 run_script_and_signal SIGTERM "Starting the parts" start --yes
  expect_status "$EXIT_INTERRUPTED"
  expect_logged " down"
}

test_ctrl_c_during_the_build_has_no_part_to_stop() {
  STUB_BUILD_SLEEP_S=30 run_script_and_signal SIGINT "Building supportiq-local-backend" start --yes
  expect_status "$EXIT_INTERRUPTED"
  expect_not_logged " down"
  expect_not_logged " up "
}

test_ctrl_c_keeps_the_parts_that_ran_before_this_start() {
  STUB_RUNNING_SERVICES=$'postgres\n' STUB_UP_SLEEP_S=30 \
    run_script_and_signal SIGINT "Starting the parts" start --yes
  expect_status "$EXIT_INTERRUPTED"
  expect_logged "rm --stop --force backend-setup backend frontend"
  expect_not_logged "ai-service"
  expect_not_logged " down"
}

# ----- stop, status, and logs -----

test_stop_with_nothing_running_says_so() {
  run_script stop
  expect_status 0
  expect_output "Nothing of the local run runs."
  expect_not_logged " down"
}

test_stop_removes_the_containers_and_keeps_the_volume() {
  STUB_CONTAINER_IDS=$'abc\n' run_script stop
  expect_status 0
  expect_logged "compose --project-name supportiq-local down"
  expect_not_logged "--volumes"
}

test_status_with_nothing_running_says_so() {
  run_script status
  expect_status 0
  expect_output "Nothing of the local run runs."
}

test_logs_refuses_an_unknown_part() {
  run_script logs database
  expect_status 2
}

test_logs_with_nothing_running_says_so() {
  run_script logs
  expect_status 0
  expect_output "Nothing of the local run runs."
}

test_logs_follows_one_part() {
  STUB_CONTAINER_IDS=$'abc\n' run_script logs backend
  expect_status 0
  expect_logged "compose --project-name supportiq-local logs --follow backend"
}

# ----- the runner -----

main() {
  local seed=${TEST_SEED:-$RANDOM} name failed=0 count=0
  # The settings that a test sets itself never come from the environment of the person.
  unset GEMINI_API_KEY LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS \
    LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS LOCAL_GRAFANA_ADMIN_PASSWORD LOCAL_DB_PORT
  echo "test-local-run.sh: seed $seed"
  trap 'rm -rf "$tools"' EXIT
  make_tools
  for name in $(declare -F | awk '{print $3}' | grep '^test_' \
    | awk -v seed="$seed" 'BEGIN { srand(seed) } { print rand() "\t" $0 }' | sort | cut -f2-); do
    count=$((count + 1))
    new_root
    if (set -e; "$name"); then
      echo "ok $name"
    else
      echo "not ok $name"
      failed=$((failed + 1))
    fi
    rm -rf "$root"
  done
  echo "test-local-run.sh: $count tests, $failed failed"
  [ "$failed" -eq 0 ]
}

main "$@"
