#!/usr/bin/env bash
# The script tests of deploy/local/local-run.sh (docs/design/local-run.md, Errors and
# guardrails). Each test copies the script, compose.yaml, and local-run.env into a new temporary
# root, with free high ports, a home folder of its own, and the files that the images install
# their dependencies from, and runs it with a PATH of the stubs `docker`, `id`, and `uname` and
# of the system tools without any docker, so no test reaches the real Docker, starts a
# container, downloads a release, or touches the real .local-run/ or release cache, on any
# machine. The tests run in random order (TEST-15); the seed is printed, and TEST_SEED repeats an
# order. They need bash, python3, and git, and no other tool.
#
# No file holds a Gemini key: each test key is made at run time from the seed, and never holds
# a run of 4 characters that the fixture holds or that the start writes, so a test can find any
# part of it in the output.
#
# Usage: deploy/local/tests/test-local-run.sh
set -euo pipefail

REPOSITORY_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
readonly REPOSITORY_ROOT
readonly SECRET_COUNT=8
readonly SECRET_PATTERN='^[0-9a-f]{64}$'
readonly EXIT_INTERRUPTED=130
# The status of the pseudo-terminal driver when a hidden prompt keeps the echo on; local-run.sh
# never exits with it.
readonly ECHO_STAYED_ON=86
readonly RELEASE_ID=release-2026-11-18-02
# 384 MiB exactly, so the plan says "about 384 MiB".
readonly ARCHIVE_SIZE_BYTES=402653184
readonly KEY_PROMPT="Gemini API key (hidden"
readonly QUESTION="Proceed? [y/N]"
readonly IMAGE_INPUT_FILES="backend/pyproject.toml backend/uv.lock backend/README.md \
ai-service/pyproject.toml ai-service/uv.lock ai-service/README.md frontend/package.json \
frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml"

root=""
tools=""
test_seed=""
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
  # shasum of macOS is a Perl script that refuses to run through a link with another name of
  # its folder, so it gets a wrapper.
  if [ -f /usr/bin/shasum ]; then
    rm "$tools/shasum"
    printf '#!/bin/sh\nexec /usr/bin/shasum "$@"\n' > "$tools/shasum"
    chmod +x "$tools/shasum"
  fi
}

write_stubs() {
  cat > "$1/docker" << 'STUB'
#!/usr/bin/env bash
# A stub of docker for the script tests: it logs each call and answers from STUB_* variables.
# It logs whether a Gemini key or a token is set, never their values.
printf '%s\n' "$*" >> "$STUB_DOCKER_LOG"
case "$*" in
  info) exit "${STUB_DOCKER_INFO_STATUS:-0}" ;;
  "info --format {{.MemTotal}}") echo "${STUB_DOCKER_MEMORY_BYTES:-8589934592}"; exit 0 ;;
  "info --format {{.NCPU}}") echo "${STUB_DOCKER_CPUS:-4}"; exit 0 ;;
  "buildx version") exit 0 ;;
  "compose version --short") echo "${STUB_COMPOSE_VERSION:-2.29.1}"; exit 0 ;;
  "version --format"*) echo "${STUB_API_VERSION:-1.51}"; exit 0 ;;
  "image inspect"*) exit "${STUB_IMAGE_INSPECT_STATUS:-0}" ;;
  "volume inspect --format {{.CreatedAt}}"*)
    [ "${STUB_VOLUME_INSPECT_STATUS:-1}" -eq 0 ] || exit 1
    echo "${STUB_VOLUME_CREATED_AT-2026-11-18T14:40:12Z}"
    exit 0
    ;;
  "volume inspect"*) exit "${STUB_VOLUME_INSPECT_STATUS:-1}" ;;
  "inspect --format {{.State.OOMKilled}}"*) echo "${STUB_OOM_KILLED:-false}"; exit 0 ;;
  "inspect --format {{.State.ExitCode}}"*) echo "${STUB_EXIT_CODE:-0}"; exit 0 ;;
  "pull "*) exit "${STUB_PULL_STATUS:-0}" ;;
  "run "*)
    # The download command of #41: the path of the release folder on standard output.
    printf 'environment of run: SUPPORTIQ_RELEASE_CACHE=%s SUPPORTIQ_RELEASE_TOKEN=%s\n' \
      "${SUPPORTIQ_RELEASE_CACHE-unset}" "${SUPPORTIQ_RELEASE_TOKEN+set}" >> "$STUB_DOCKER_LOG"
    if [ "${STUB_DOWNLOAD_STATUS:-0}" -ne 0 ]; then
      echo "stub download-release: the reason of the stub" >&2
      exit "$STUB_DOWNLOAD_STATUS"
    fi
    if [ -n "${STUB_DOWNLOAD_PRINTS:-}" ]; then echo "$STUB_DOWNLOAD_PRINTS"; exit 0; fi
    mkdir -p "$SUPPORTIQ_RELEASE_CACHE/$STUB_RELEASE_ID"
    echo '{}' > "$SUPPORTIQ_RELEASE_CACHE/$STUB_RELEASE_ID/release-manifest.json"
    echo "$SUPPORTIQ_RELEASE_CACHE/$STUB_RELEASE_ID"
    exit 0
    ;;
  *"ps --services --status running"*) printf '%s' "${STUB_RUNNING_SERVICES:-}"; exit 0 ;;
  *"ps --all --quiet"*) printf '%s' "${STUB_CONTAINER_IDS:-}"; exit 0 ;;
  *" build "*)
    # A dependency file that changes while the image builds.
    if [ -n "${STUB_BUILD_CHANGES:-}" ]; then echo "changed during a build" >> "$STUB_BUILD_CHANGES"; fi
    if [ -n "${STUB_BUILD_SLEEP_S:-}" ]; then exec sleep "$STUB_BUILD_SLEEP_S"; fi
    ;;
  *" up "*)
    # What Compose would interpolate from the environment of this call.
    printf 'environment of up: SEED_PASSWORD_CUSTOMER=%s COMPOSE_PROJECT_NAME=%s LOCAL_GRAFANA_ADMIN_PASSWORD=%s GEMINI_MODEL=%s GEMINI_API_KEY=%s LOCAL_RELEASE_FOLDER=%s COMPOSE_PROFILES=%s\n' \
      "${SEED_PASSWORD_CUSTOMER-unset}" "${COMPOSE_PROJECT_NAME-unset}" \
      "${LOCAL_GRAFANA_ADMIN_PASSWORD-unset}" "${GEMINI_MODEL-unset}" "${GEMINI_API_KEY+set}" \
      "${LOCAL_RELEASE_FOLDER-unset}" "${COMPOSE_PROFILES-unset}" >> "$STUB_DOCKER_LOG"
    if [ -n "${STUB_UP_RECORDS_SIGNALS:-}" ]; then
      trap 'echo "stub up got SIGINT" >> "$STUB_DOCKER_LOG"; exit 130' INT
      trap 'echo "stub up got SIGTERM" >> "$STUB_DOCKER_LOG"; exit 143' TERM
      sleep 30 &
      wait
    fi
    if [ -n "${STUB_UP_SLEEP_S:-}" ]; then exec sleep "$STUB_UP_SLEEP_S"; fi
    exit "${STUB_UP_STATUS:-0}"
    ;;
  *" logs "*" ai-service")
    if [ -n "${STUB_AI_SERVICE_RELEASE_INVALID:-}" ]; then
      echo '{"event":"release.invalid","reason":"file_mismatch"}'
    fi
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
  cat > "$1/uname" << 'STUB'
#!/usr/bin/env bash
# A stub of uname for the script tests: STUB_UNAME replaces the system name of `uname -s`.
if [ "${1:-}" = -s ] && [ -n "${STUB_UNAME:-}" ]; then echo "$STUB_UNAME"; exit 0; fi
exec /usr/bin/uname "$@"
STUB
  cat > "$1/mv" << 'STUB'
#!/usr/bin/env bash
# A stub of mv for the script tests: it kills the script, as a power cut would, instead of the
# rename onto STUB_MV_KILLS_AT. Every other rename runs.
if [ -n "${STUB_MV_KILLS_AT:-}" ] && [ "${2:-}" = "$STUB_MV_KILLS_AT" ]; then
  kill -KILL "$PPID"
  exit 1
fi
exec /bin/mv "$@"
STUB
  cat > "$1/od" << 'STUB'
#!/usr/bin/env bash
# A stub of od for the script tests: with STUB_OD_FAILS, no random bytes can be read.
if [ -n "${STUB_OD_FAILS:-}" ]; then exit 1; fi
exec /usr/bin/od "$@"
STUB
  chmod +x "$1/docker" "$1/id" "$1/uname" "$1/mv" "$1/od"
}

free_port() {
  python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'
}

new_root() {
  local file
  root=$(mktemp -d)
  fixture_path="$root/bin:$tools"
  mkdir -p "$root/deploy/local" "$root/bin" "$root/home" "$root/eval/releases" \
    "$root/backend" "$root/ai-service" "$root/frontend"
  cp "$REPOSITORY_ROOT/deploy/local/local-run.sh" "$REPOSITORY_ROOT/deploy/local/compose.yaml" \
    "$root/deploy/local/"
  sed -e "s/^LOCAL_FRONTEND_PORT=.*/LOCAL_FRONTEND_PORT=$(free_port)/" \
    -e "s/^LOCAL_BACKEND_PORT=.*/LOCAL_BACKEND_PORT=$(free_port)/" \
    -e "s/^LOCAL_AI_SERVICE_PORT=.*/LOCAL_AI_SERVICE_PORT=$(free_port)/" \
    -e "s/^LOCAL_DB_PORT=.*/LOCAL_DB_PORT=$(free_port)/" \
    -e "s/^LOCAL_GRAFANA_PORT=.*/LOCAL_GRAFANA_PORT=$(free_port)/" \
    "$REPOSITORY_ROOT/deploy/local/local-run.env" > "$root/deploy/local/local-run.env"
  for file in $IMAGE_INPUT_FILES; do
    echo "the first content of $file" > "$root/$file"
  done
  # The other paths that the download command reads, besides eval/releases/.
  mkdir -p "$root/eval/release/src" "$root/ai-service/app"
  for file in .python-version eval/release/pyproject.toml eval/release/uv.lock \
    eval/release/README.md; do
    echo "the content of $file" > "$root/$file"
  done
  write_stubs "$root/bin"
  : > "$root/docker.log"
}

port_of() {
  sed -n "s/^$1=//p" "$root/deploy/local/local-run.env"
}

cache_dir() {
  echo "$root/home/.cache/supportiq/releases"
}

# Run local-run.sh in the fixture without a terminal; keep its status and its output.
run_script() {
  run_status=0
  run_output=$(PATH="$fixture_path" HOME="$root/home" STUB_DOCKER_LOG="$root/docker.log" \
    bash "$root/deploy/local/local-run.sh" "$@" < /dev/null 2>&1) || run_status=$?
}

# Run local-run.sh on a pseudo-terminal. The arguments are pairs of a text and the answer to
# type once the output holds that text, then --, then the arguments of the script. Before it
# types into a hidden prompt, it waits until the script has turned the echo off; when the echo is
# still on after 5 s, it types nothing, stops the script, and the test fails on that cause.
run_script_on_a_terminal() {
  local -a dialog=()
  while [ "$1" != -- ]; do
    dialog+=("$1")
    shift
  done
  shift
  run_status=0
  run_output=$(PATH="$fixture_path" HOME="$root/home" STUB_DOCKER_LOG="$root/docker.log" \
    ECHO_STAYED_ON_STATUS="$ECHO_STAYED_ON" \
    python3 - "$root/deploy/local/local-run.sh" "${#dialog[@]}" "${dialog[@]}" "$@" << 'PYTHON'
import os
import pty
import signal
import sys
import termios
import time

ECHO_WAIT_S = 5
script, count = sys.argv[1], int(sys.argv[2])
dialog, arguments = sys.argv[3:3 + count], sys.argv[3 + count:]
pairs = list(zip(dialog[0::2], dialog[1::2]))
pid, terminal = pty.fork()
if pid == 0:
    os.execvp("bash", ["bash", script, *arguments])


def echo_is_off():
    try:
        return not termios.tcgetattr(terminal)[3] & termios.ECHO
    except termios.error:
        return False


output = b""
matched = 0
while True:
    try:
        chunk = os.read(terminal, 1024)
    except OSError:
        break
    if not chunk:
        break
    output += chunk
    while pairs:
        text, answer = pairs[0]
        index = output.find(text.encode(), matched)
        if index < 0:
            break
        matched = index + len(text)
        if "hidden" in text:
            deadline = time.monotonic() + ECHO_WAIT_S
            while not echo_is_off() and time.monotonic() < deadline:
                time.sleep(0.05)
            if not echo_is_off():
                # Typing now would show the answer on the terminal.
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
                sys.stdout.write(output.decode(errors="replace"))
                sys.stdout.write(f"\nthe echo was still on {ECHO_WAIT_S} s after: {text}\n")
                sys.exit(int(os.environ["ECHO_STAYED_ON_STATUS"]))
        time.sleep(0.2)
        os.write(terminal, answer.encode() + b"\n")
        pairs.pop(0)
_, status = os.waitpid(pid, 0)
sys.stdout.write(output.decode(errors="replace"))
sys.exit(os.waitstatus_to_exitcode(status))
PYTHON
  ) || run_status=$?
  [ "$run_status" -ne "$ECHO_STAYED_ON" ] \
    || fail_test "a hidden prompt kept the echo on, so its answer was not typed"
}

# Run local-run.sh on a pseudo-terminal, and press Ctrl+C once its output holds a text. The
# terminal sends SIGINT to its foreground process group only, as a person's Ctrl+C does.
run_script_on_a_terminal_and_press_ctrl_c() {
  local text=$1
  shift
  run_status=0
  run_output=$(PATH="$fixture_path" HOME="$root/home" STUB_DOCKER_LOG="$root/docker.log" \
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
  run_output=$(PATH="$fixture_path" HOME="$root/home" STUB_DOCKER_LOG="$root/docker.log" \
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

# The name of the test that runs, from the call stack.
current_test() {
  local name
  for name in "${FUNCNAME[@]}"; do
    case "$name" in test_*) echo "$name"; return 0 ;; esac
  done
}

# A test key that holds no run of 4 characters of any file of the fixture: `valid` has the form
# of an AI Studio key; `space`, `quote`, and `newline` hold a paste mistake; `dollar` holds a $;
# `single-quote` holds a '; `other` has another form. It is deterministic: it comes from the
# seed of the run, the name of the test, and a count of the keys of that test, so TEST_SEED
# repeats a failure (TEST-14). Its characters avoid 0-9 and a-f, so it never matches the
# hexadecimal secrets and hashes, the ports, the IDs, or the times that the start writes later.
# Only the fixed prefix AIza may occur in the fixture.
new_test_key() {
  local count=0
  if [ -f "$root/test-key-count" ]; then count=$(cat "$root/test-key-count"); fi
  echo $((count + 1)) > "$root/test-key-count"
  python3 - "$1" "$root" "$tools" "$test_seed/$(current_test)/$count" << 'PYTHON'
import os
import random
import string
import sys

form, root, tools, label = sys.argv[1:5]
generator = random.Random(label)
corpus = "\n".join([root, tools])
for folder, _, names in os.walk(root):
    for name in names:
        try:
            with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as file:
                corpus += "\n" + file.read()
        except OSError:
            pass
alphabet = string.ascii_uppercase + "ghijklmnopqrstuvwxyz_-"


def random_text(length):
    return "".join(generator.choice(alphabet) for _ in range(length))


forms = {
    "valid": lambda: "AIza" + random_text(35),
    "space": lambda: random_text(16) + " " + random_text(16),
    "quote": lambda: random_text(16) + '"' + random_text(16),
    "newline": lambda: random_text(16) + "\n" + random_text(16),
    "dollar": lambda: random_text(16) + "$" + random_text(16),
    "single-quote": lambda: random_text(16) + "'" + random_text(16),
    "other": lambda: random_text(32),
}
first = 1 if form == "valid" else 0
for _ in range(1000):
    key = forms[form]()
    if not any(key[index:index + 4] in corpus for index in range(first, len(key) - 3)):
        sys.stdout.write(key)
        break
else:
    sys.exit("no test key without a run of 4 characters of the fixture")
PYTHON
}

# A state after a first start: the secrets, the volume, and the recorded port exist.
given_a_first_start() {
  run_script start "$@" --yes
  [ "$run_status" -eq 0 ] || fail_test "the first start failed"
  : > "$root/docker.log"
}

given_a_published_release() {
  mkdir -p "$root/eval/releases/$1"
  echo '{}' > "$root/eval/releases/$1/release-manifest.json"
}

given_the_pinned_release() {
  given_a_published_release "$RELEASE_ID"
  printf 'release_id=%s\narchive_size_bytes=%s\n' "$RELEASE_ID" "$ARCHIVE_SIZE_BYTES" \
    > "$root/eval/releases/pinned-release.txt"
  export STUB_RELEASE_ID="$RELEASE_ID"
}

# The format of deploy/llm-prices.env: comments and empty lines anywhere, and five names in any
# order (docs/design/release-download-and-modal-deploy.md, The price file).
given_the_price_file() {
  printf '%s\n' '# The prices of the script tests.' LLM_PRICES_SOURCE=https://prices.invalid/ \
    '' GEMINI_MODEL=gemini-of-the-tests '# A comment between the values.' \
    LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS=1 LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS=2 \
    LLM_PRICES_READ_ON=2026-11-23 > "$root/deploy/llm-prices.env"
}

# With AI: the pinned release, the price file, and no key anywhere.
given_ai_without_a_key() {
  given_the_pinned_release
  given_the_price_file
}

given_ai_with_a_key_in_the_environment() {
  given_ai_without_a_key
  GEMINI_API_KEY=$(new_test_key valid)
  export GEMINI_API_KEY
}

given_the_release_in_the_cache() {
  mkdir -p "$(cache_dir)/$RELEASE_ID"
  echo '{}' > "$(cache_dir)/$RELEASE_ID/release-manifest.json"
}

given_a_saved_key() {
  mkdir -p "$root/.local-run"
  printf "GEMINI_API_KEY='%s'\n" "$1" > "$root/.local-run/gemini.env"
  chmod 600 "$root/.local-run/gemini.env"
}

given_a_release_folder() {
  mkdir "$root/release"
  echo '{}' > "$root/release/release-manifest.json"
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

expect_output_once() {
  [ "$(printf '%s\n' "$run_output" | grep -cF -- "$1")" -eq 1 ] \
    || fail_test "expected the output to hold once: $1"
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

# No run of 4 characters of the key in the output, in the docker calls, or in the files of
# .local-run/ other than gemini.env.
expect_no_part_of_the_key() {
  local key=$1 index window logged state=""
  logged=$(cat "$root/docker.log")
  if [ -d "$root/.local-run" ]; then
    state=$(find "$root/.local-run" -type f ! -name gemini.env -exec cat {} +)
  fi
  for ((index = 0; index + 4 <= ${#key}; index++)); do
    window=${key:index:4}
    case "$run_output" in *"$window"*) fail_test "the output holds a part of the key" ;; esac
    case "$logged" in *"$window"*) fail_test "a docker call holds a part of the key" ;; esac
    case "$state" in *"$window"*) fail_test "a file of .local-run/ holds a part of the key" ;; esac
  done
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

test_start_refuses_options_that_contradict_each_other() {
  run_script start --without-ai --release "$RELEASE_ID"
  expect_status 2
  run_script start --without-ai --release-folder "$root"
  expect_status 2
  run_script start --release "$RELEASE_ID" --release-folder "$root"
  expect_status 2
  run_script start --release
  expect_status 2
  run_script start --release ""
  expect_status 2
  expect_no_state
}

test_every_command_refuses_root() {
  local command_name
  for command_name in start stop status logs releases set-key; do
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
  run_script start --without-ai --yes
  [ ! -s "$root/docker.log" ] || fail_test "a docker command ran"
  expect_status 1
  expect_output "Docker is missing"
  expect_no_state
}

test_start_with_docker_not_running_stops_before_the_question() {
  STUB_DOCKER_INFO_STATUS=1 run_script start --without-ai --yes
  expect_status 1
  expect_output "Docker does not run"
  expect_no_state
}

test_start_with_compose_v1_stops() {
  STUB_COMPOSE_VERSION=1.29.2 run_script start --without-ai --yes
  expect_status 1
  expect_output "Docker Compose 2.20.2 or later is needed (docker compose, not docker-compose), and this one is 1.29.2"
  expect_no_state
}

test_start_with_compose_2_20_1_stops() {
  STUB_COMPOSE_VERSION=2.20.1 run_script start --without-ai --yes
  expect_status 1
  expect_output "Docker Compose 2.20.2 or later is needed"
  expect_no_state
}

test_start_compares_versions_as_numbers() {
  STUB_COMPOSE_VERSION=2.3.0 run_script start --without-ai --yes
  expect_status 1
  expect_output "Docker Compose 2.20.2 or later is needed (docker compose, not docker-compose), and this one is 2.3.0"
  STUB_API_VERSION=1.9 run_script start --without-ai --yes
  expect_status 1
  expect_output "this one has the API 1.9"
  expect_no_state
}

test_start_accepts_compose_5_0_0() {
  STUB_COMPOSE_VERSION=5.0.0 run_script start --without-ai --yes
  expect_status 0
  expect_no_output "Docker Compose 2.20.2 or later is needed"
}

test_every_compose_call_prints_plain_progress() {
  given_ai_with_a_key_in_the_environment
  run_script start --yes
  expect_status 0
  ! grep -F -- "--file" "$root/docker.log" | grep -vqF -- "compose --progress plain " \
    || fail_test "a compose call lacks --progress plain"
}

test_start_accepts_compose_2_20_2_with_a_suffix() {
  STUB_COMPOSE_VERSION=v2.20.2-desktop.1 run_script start --without-ai --yes
  expect_status 0
  expect_no_output "Docker Compose 2.20.2 or later is needed"
}

test_start_with_docker_api_1_43_stops() {
  STUB_API_VERSION=1.43 run_script start --without-ai --yes
  expect_status 1
  expect_output "Docker Engine 25 or later is needed, with the API 1.44 or later, and this one has the API 1.43"
  expect_no_state
}

test_a_volume_without_its_secrets_file_stops_before_the_question() {
  STUB_VOLUME_INSPECT_STATUS=0 run_script start --without-ai --yes
  expect_status 1
  expect_output ".local-run/secrets.env is missing, but the volume supportiq-local_postgres-data, created on 2026-11-18, holds the database of an earlier start"
  expect_output "This machine has one local database for every folder of the repository, so it may belong to the .local-run/ of another folder: start there instead, or, once no run uses it, remove it with: deploy/local/local-run.sh stop, then docker volume rm supportiq-local_postgres-data"
  expect_no_state
  expect_not_logged " up "
}

test_a_volume_of_an_unknown_date_without_its_secrets_file_says_so() {
  STUB_VOLUME_INSPECT_STATUS=0 STUB_VOLUME_CREATED_AT="" run_script start --without-ai --yes
  expect_status 1
  expect_output "the volume supportiq-local_postgres-data, created on an unknown date, holds the database"
  expect_no_state
}

test_compose_project_name_of_the_environment_changes_nothing() {
  COMPOSE_PROJECT_NAME=another-project run_script start --without-ai --yes
  expect_status 0
  ! grep -F -- "--file" "$root/docker.log" | grep -vqF -- "--project-name supportiq-local" \
    || fail_test "a compose call lacks --project-name supportiq-local"
  expect_logged "environment of up: SEED_PASSWORD_CUSTOMER=unset COMPOSE_PROJECT_NAME=unset"
}

test_an_exported_secret_never_replaces_the_one_of_the_secrets_file() {
  SEED_PASSWORD_CUSTOMER=exported-in-the-shell run_script start --without-ai --yes
  expect_status 0
  expect_logged "environment of up: SEED_PASSWORD_CUSTOMER=unset"
  expect_no_output exported-in-the-shell
}

test_an_empty_grafana_password_counts_as_not_set() {
  LOCAL_GRAFANA_ADMIN_PASSWORD="" run_script start --without-ai --observability --yes
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
  hold_port_and_start "$port" --without-ai --yes
  expect_status 1
  expect_output "port $port on 127.0.0.1 is taken (LOCAL_BACKEND_PORT)"
  expect_no_state
}

test_a_taken_ai_service_port_stops_a_start_with_ai() {
  local port
  given_ai_with_a_key_in_the_environment
  port=$(port_of LOCAL_AI_SERVICE_PORT)
  hold_port_and_start "$port" --yes
  expect_status 1
  expect_output "port $port on 127.0.0.1 is taken (LOCAL_AI_SERVICE_PORT)"
  expect_no_state
}

test_a_taken_database_port_suggests_local_db_port_and_picks_no_other() {
  local port
  port=$(port_of LOCAL_DB_PORT)
  hold_port_and_start "$port" --without-ai --yes
  expect_status 1
  expect_output "port $port on 127.0.0.1 is taken, so PostgreSQL cannot use it; set LOCAL_DB_PORT"
  expect_not_logged " up "
  expect_no_state
}

test_an_invalid_local_db_port_stops() {
  local value
  for value in abc 0 70000 -1; do
    LOCAL_DB_PORT=$value run_script start --without-ai --yes
    expect_status 1
    expect_output "LOCAL_DB_PORT must be a port number from 1 to 65535"
  done
  expect_no_state
}

# ----- the release -----

test_with_ai_the_plan_names_the_pinned_release_its_size_and_the_cache() {
  given_ai_with_a_key_in_the_environment
  STUB_IMAGE_INSPECT_STATUS=1 run_script start
  expect_status 1
  expect_output "download the release $RELEASE_ID, $ARCHIVE_SIZE_BYTES bytes, about 384 MiB, into $(cache_dir)/$RELEASE_ID/ with supportiq-release download-release, which checks it against eval/releases/$RELEASE_ID/release-manifest.json"
  expect_output "download the image ghcr.io/astral-sh/uv:0.11.11-python3.14-trixie-slim of the download command"
  expect_output "create the Docker volume supportiq-local_release-tool and install the packages of eval/release into it"
  expect_output "pass --yes"
  expect_no_state
  [ ! -e "$(cache_dir)" ] || fail_test "the cache was created"
  expect_not_logged "run "
}

test_a_release_id_outside_the_pattern_stops_and_builds_no_path() {
  local value
  for value in ../x a/b .x "$(printf 'a%.0s' {1..65})"; do
    given_ai_with_a_key_in_the_environment
    run_script start --release "$value" --yes
    expect_status 1
    expect_output "--release must name a release ID of the pattern"
    expect_no_output "eval/releases/$value"
  done
  expect_no_state
}

test_a_release_without_its_manifest_names_the_releases_command() {
  given_ai_with_a_key_in_the_environment
  run_script start --release release-of-nobody --yes
  expect_status 1
  expect_output "--release release-of-nobody names no published release: eval/releases/release-of-nobody/release-manifest.json does not exist"
  expect_output "deploy/local/local-run.sh releases"
  expect_no_state
}

test_another_published_release_is_downloaded_by_its_id_with_an_unknown_size() {
  given_ai_with_a_key_in_the_environment
  given_a_published_release release-other
  STUB_RELEASE_ID=release-other run_script start --release release-other --yes
  expect_status 0
  expect_output "download the release release-other, of a size that is not known before the download"
  expect_logged "supportiq-release download-release --release release-other --yes"
  expect_logged "LOCAL_RELEASE_FOLDER=$(cache_dir)/release-other "
}

test_the_pinned_release_named_by_its_id_keeps_its_size_in_the_plan() {
  given_ai_with_a_key_in_the_environment
  run_script start --release "$RELEASE_ID"
  expect_status 1
  expect_output "download the release $RELEASE_ID, $ARCHIVE_SIZE_BYTES bytes, about 384 MiB, into"
}

test_a_missing_pinned_file_stops_a_start_with_ai() {
  given_the_price_file
  GEMINI_API_KEY=$(new_test_key valid) run_script start --yes
  expect_status 1
  expect_output "eval/releases/pinned-release.txt is missing, so no default release is known"
  expect_output "--without-ai"
  expect_no_state
}

test_a_pinned_file_of_another_form_stops() {
  local text
  given_ai_with_a_key_in_the_environment
  for text in "# a comment"$'\n'"release_id=$RELEASE_ID"$'\n'"archive_size_bytes=1"$'\n' \
    "release_id=$RELEASE_ID"$'\r\n'"archive_size_bytes=1"$'\r\n' \
    "release_id=$RELEASE_ID"$'\n'"archive_size_bytes=1"$'\n'"extra=1"$'\n' \
    "release_id=$RELEASE_ID"$'\n'"archive_size_bytes=1" \
    "archive_size_bytes=1"$'\n'"release_id=$RELEASE_ID"$'\n' \
    "release_id=$RELEASE_ID"$'\n'"archive_size_bytes=0"$'\n' \
    "release_id=$RELEASE_ID"$'\n'"archive_size_bytes=012"$'\n' \
    "release_id=$RELEASE_ID"$'\n'"archive_size_bytes=2147483648"$'\n' \
    "release_id=.x"$'\n'"archive_size_bytes=1"$'\n' \
    "release_id= $RELEASE_ID"$'\n'"archive_size_bytes=1"$'\n'; do
    printf '%s' "$text" > "$root/eval/releases/pinned-release.txt"
    run_script start --yes
    expect_status 1
    expect_output "eval/releases/pinned-release.txt must hold exactly the two lines release_id=<id> and archive_size_bytes=<a number from 1 to 2147483647>"
  done
  expect_no_state
}

test_a_pinned_release_without_its_manifest_names_both_files() {
  given_ai_with_a_key_in_the_environment
  rm "$root/eval/releases/$RELEASE_ID/release-manifest.json"
  run_script start --yes
  expect_status 1
  expect_output "eval/releases/pinned-release.txt names $RELEASE_ID, but eval/releases/$RELEASE_ID/release-manifest.json does not exist"
  expect_no_state
}

test_a_relative_cache_path_stops() {
  local value
  given_ai_with_a_key_in_the_environment
  # shellcheck disable=SC2088 # the literal ~ of a quoted value, which the script must refuse
  for value in cache ./cache '~/cache'; do
    SUPPORTIQ_RELEASE_CACHE=$value run_script start --yes
    expect_status 1
    expect_output "SUPPORTIQ_RELEASE_CACHE must be an absolute path"
  done
  expect_no_state
}

test_on_macos_a_cache_outside_home_stops() {
  given_ai_with_a_key_in_the_environment
  STUB_UNAME=Darwin SUPPORTIQ_RELEASE_CACHE="$root/outside/cache" run_script start --yes
  expect_status 1
  expect_output "the release cache $root/outside/cache lies outside your home folder"
  expect_output "SUPPORTIQ_RELEASE_CACHE"
  expect_no_state
  [ ! -e "$root/outside" ] || fail_test "the cache was created"
}

test_on_macos_a_cache_inside_home_through_a_link_and_with_a_slash_is_accepted() {
  given_ai_with_a_key_in_the_environment
  ln -s "$root/home" "$root/home-link"
  STUB_UNAME=Darwin SUPPORTIQ_RELEASE_CACHE="$root/home-link/cache/" run_script start --yes
  expect_status 0
  expect_logged "LOCAL_RELEASE_FOLDER=$root/home-link/cache/$RELEASE_ID "
}

test_on_linux_a_cache_outside_home_is_accepted() {
  given_ai_with_a_key_in_the_environment
  STUB_UNAME=Linux SUPPORTIQ_RELEASE_CACHE="$root/outside/cache" run_script start --yes
  expect_status 0
  expect_logged "environment of run: SUPPORTIQ_RELEASE_CACHE=$root/outside/cache "
}

test_the_download_runs_in_a_container_with_the_cache_path_of_the_host() {
  given_ai_with_a_key_in_the_environment
  run_script start --yes
  expect_status 0
  expect_logged "run --rm --pull never --user $(id -u):$(id -g) --volume $root/.python-version:$root/.python-version:ro --volume $root/eval/release/pyproject.toml:$root/eval/release/pyproject.toml:ro --volume $root/eval/release/uv.lock:$root/eval/release/uv.lock:ro --volume $root/eval/release/README.md:$root/eval/release/README.md:ro --volume $root/eval/release/src:$root/eval/release/src:ro --volume $root/eval/releases:$root/eval/releases:ro --volume $root/ai-service/pyproject.toml:$root/ai-service/pyproject.toml:ro --volume $root/ai-service/README.md:$root/ai-service/README.md:ro --volume $root/ai-service/app:$root/ai-service/app:ro --tmpfs $root/.local-run --volume $(cache_dir):$(cache_dir) --volume supportiq-local_release-tool:/var/tmp --workdir $root --env SUPPORTIQ_RELEASE_CACHE --env SUPPORTIQ_RELEASE_TOKEN "
  expect_logged "ghcr.io/astral-sh/uv:0.11.11-python3.14-trixie-slim@sha256:3e70f580d0e63d78408c35d332d780024b6e1d46d9744c888e22fa944393448e uv run --locked --project eval/release supportiq-release download-release --yes"
  # The user's environment did not set the cache, and the container still gets the host path.
  expect_logged "environment of run: SUPPORTIQ_RELEASE_CACHE=$(cache_dir) "
  [ -d "$(cache_dir)/$RELEASE_ID" ] || fail_test "the printed path does not exist on the host"
  expect_logged "LOCAL_RELEASE_FOLDER=$(cache_dir)/$RELEASE_ID "
  expect_logged "COMPOSE_PROFILES=ai"
  expect_output "ai-service runs with the release folder $(cache_dir)/$RELEASE_ID."
}

test_the_download_container_sees_no_key_no_secret_and_no_env_file() {
  local mount source target secret_file count=0
  given_ai_without_a_key
  given_a_saved_key "$(new_test_key valid)"
  # Empty files with the names of a teammate's own settings; nothing reads them.
  : > "$root/ai-service/.env"
  : > "$root/backend/.env"
  run_script start --yes
  expect_status 0
  expect_logged "--tmpfs $root/.local-run "
  while IFS= read -r mount; do
    count=$((count + 1))
    source=${mount%%:*}
    target=${mount#*:}
    target=${target%%:*}
    case "$source" in
      # The release cache: the home folder of the fixture lies in its root.
      "$root/home" | "$root/home"/*) ;;
      "$root" | "$root"/*)
        [ "${mount##*:}" = ro ] || fail_test "a mount of the repository is writable: $mount"
        [ "$target" = "$source" ] || fail_test "a mount of the repository moves: $mount"
        ;;
    esac
    for secret_file in "$root/.local-run/gemini.env" "$root/.local-run/secrets.env" \
      "$root/ai-service/.env" "$root/backend/.env"; do
      case "$secret_file" in
        "$source" | "$source"/*) fail_test "the mount $mount covers $secret_file" ;;
      esac
    done
  done < <(grep '^run ' "$root/docker.log" | grep -oE -- '--volume [^ ]+' | cut -d' ' -f2)
  # The nine paths of the repository, the cache, and the volume of uv.
  [ "$count" -eq 11 ] || fail_test "expected 11 mounts of the download container, got $count"
}

test_a_missing_path_of_the_download_command_stops_before_the_question() {
  given_ai_with_a_key_in_the_environment
  rm "$root/eval/release/uv.lock"
  run_script start --yes
  expect_status 1
  expect_output "the download command needs eval/release/uv.lock of this working tree, which is missing"
  expect_no_state
  expect_not_logged "run "
  given_the_release_in_the_cache
  run_script start --yes
  expect_status 0
  expect_no_output "the download command needs"
}

test_the_download_comes_after_the_builds_and_before_ai_service() {
  local calls
  given_ai_with_a_key_in_the_environment
  run_script start --yes
  expect_status 0
  calls=$(grep -E '^run | (build|up) ' "$root/docker.log" | sed -E 's/^run .*/run/; s/.* (build [a-z-]+|up).*/\1/')
  [ "$calls" = "$(printf 'build backend\nbuild frontend\nbuild ai-service\nrun\nup\nup')" ] \
    || fail_test "expected the builds, the download, then two ups; got: $calls"
}

test_the_release_token_reaches_the_container_by_name_only() {
  local token
  given_ai_with_a_key_in_the_environment
  token=$(new_test_key other)
  SUPPORTIQ_RELEASE_TOKEN=$token run_script start --yes
  expect_status 0
  expect_logged "--env SUPPORTIQ_RELEASE_TOKEN "
  expect_logged "SUPPORTIQ_RELEASE_TOKEN=set"
  expect_no_part_of_the_key "$token"
}

test_a_printed_path_that_is_no_release_folder_on_the_host_stops() {
  given_ai_with_a_key_in_the_environment
  STUB_DOWNLOAD_PRINTS="$root/nowhere" run_script start --yes
  expect_status 1
  expect_output "the download command printed $root/nowhere, which is no release folder on this machine"
  expect_not_logged " up "
  STUB_DOWNLOAD_PRINTS=relative/path run_script start --yes
  expect_status 1
  expect_output "the download command printed no absolute path of the release folder"
}

test_each_status_of_the_download_command_has_its_message() {
  given_ai_with_a_key_in_the_environment
  STUB_DOWNLOAD_STATUS=5 run_script start --yes
  expect_status 1
  expect_output "did not download because of a network failure; the cache is unchanged: try again, or start with --without-ai"
  STUB_DOWNLOAD_STATUS=6 run_script start --yes
  expect_status 1
  expect_output "the release $RELEASE_ID failed its check, as the download command says above; the cache $(cache_dir)/ keeps no partial release"
  STUB_DOWNLOAD_STATUS=2 run_script start --yes
  expect_status 1
  expect_output "stub download-release: the reason of the stub"
  expect_output "the download command could not use its input, for the reason that it printed above"
  STUB_DOWNLOAD_STATUS=4 run_script start --yes
  expect_status 1
  expect_output "which is a bug of deploy/local/local-run.sh"
  [ ! -e "$(cache_dir)/$RELEASE_ID" ] || fail_test "the cache holds the release"
  expect_not_logged " up "
}

test_a_cached_release_is_used_without_the_download_command() {
  given_ai_with_a_key_in_the_environment
  given_the_release_in_the_cache
  STUB_DOWNLOAD_STATUS=5 run_script start --yes
  expect_status 0
  expect_output "run ai-service with the release $RELEASE_ID of the cache, $(cache_dir)/$RELEASE_ID/, read-only; nothing is downloaded"
  expect_no_output "download the release"
  expect_not_logged "run "
  expect_not_logged "pull "
  expect_logged "LOCAL_RELEASE_FOLDER=$(cache_dir)/$RELEASE_ID "
}

test_a_hidden_staging_entry_is_no_cached_release() {
  given_ai_with_a_key_in_the_environment
  mkdir -p "$(cache_dir)/.$RELEASE_ID.partial-0a1b"
  run_script start --yes
  expect_status 0
  expect_output "download the release $RELEASE_ID"
  expect_logged "supportiq-release download-release --yes"
}

test_a_release_folder_is_used_without_the_cache() {
  given_the_price_file
  given_a_release_folder
  GEMINI_API_KEY=$(new_test_key valid) run_script start --release-folder "$root/release" --yes
  expect_status 0
  expect_output "run ai-service with the release folder $root/release, read-only"
  expect_not_logged "run "
  expect_logged "LOCAL_RELEASE_FOLDER=$root/release "
  [ ! -e "$(cache_dir)" ] || fail_test "the cache was created"
}

test_a_release_folder_without_a_manifest_stops() {
  given_the_price_file
  mkdir "$root/release"
  GEMINI_API_KEY=$(new_test_key valid) run_script start --release-folder "$root/release" --yes
  expect_status 1
  expect_output "holds no readable release-manifest.json"
  GEMINI_API_KEY=$(new_test_key valid) run_script start --release-folder "$root/missing" --yes
  expect_status 1
  expect_output "the release folder $root/missing is not a readable folder"
  expect_no_state
}

test_a_cached_release_that_ai_service_refuses_names_its_folder() {
  given_ai_with_a_key_in_the_environment
  given_the_release_in_the_cache
  STUB_UP_STATUS=1 STUB_AI_SERVICE_RELEASE_INVALID=1 run_script start --yes
  expect_status 1
  expect_output "ai-service refused the cached release $(cache_dir)/$RELEASE_ID/, for example because it was edited: remove that folder, and the next start downloads the release again"
  expect_output "ai-service did not get ready, so backend and frontend were not started"
  [ "$(grep -c ' up ' "$root/docker.log")" -eq 1 ] || fail_test "expected one up, of ai-service"
}

test_a_release_folder_that_ai_service_refuses_is_named() {
  given_the_price_file
  given_a_release_folder
  GEMINI_API_KEY=$(new_test_key valid) STUB_UP_STATUS=1 STUB_AI_SERVICE_RELEASE_INVALID=1 \
    run_script start --release-folder "$root/release" --yes
  expect_status 1
  expect_output "ai-service refused the release folder $root/release: the release.invalid line of its log names the reason"
}

test_ai_service_out_of_memory_is_named() {
  given_ai_with_a_key_in_the_environment
  STUB_UP_STATUS=1 STUB_CONTAINER_IDS=$'abc\n' STUB_OOM_KILLED=true run_script start --yes
  expect_status 1
  expect_output "ai-service ran out of memory: with Colima, run: colima stop, then: colima start --memory <GiB>"
  expect_output "or start with --without-ai"
  [ "$(grep -c ' up ' "$root/docker.log")" -eq 1 ] || fail_test "expected one up, of ai-service"
}

test_too_little_docker_memory_stops_a_start_with_ai() {
  given_ai_with_a_key_in_the_environment
  STUB_DOCKER_MEMORY_BYTES=2000000000 run_script start --yes
  expect_status 1
  expect_output "ai-service needs Docker with 3072 MiB of memory or more, and this one has 1907 MiB: with Colima, run: colima stop, then: colima start --memory <GiB>; with Docker Desktop, raise the memory in Settings, Resources; or start with --without-ai"
  expect_no_state
  STUB_DOCKER_MEMORY_BYTES=2000000000 run_script start --without-ai --yes
  expect_status 0
}

test_a_memory_that_docker_does_not_name_gives_a_warning_and_goes_on() {
  given_ai_with_a_key_in_the_environment
  STUB_DOCKER_MEMORY_BYTES=unknown run_script start --yes
  expect_status 0
  expect_output_once "Warning: docker info names no memory of the Docker engine, so start cannot check that ai-service has 3072 MiB or more"
}

test_two_cpus_with_ai_and_observability_warn_and_go_on() {
  given_ai_with_a_key_in_the_environment
  STUB_DOCKER_CPUS=2 run_script start --observability --yes
  expect_status 0
  expect_output_once "Warning: Docker has 2 CPUs, and with AI and --observability the AI will be too slow"
  expect_output "drop --observability, or start with --without-ai"
}

test_more_cpus_or_one_option_alone_give_no_cpu_warning() {
  given_ai_with_a_key_in_the_environment
  STUB_DOCKER_CPUS=4 run_script start --observability --yes
  expect_status 0
  expect_no_output "Warning: Docker has"
  STUB_DOCKER_CPUS=2 run_script start --yes
  expect_no_output "Warning: Docker has"
  STUB_DOCKER_CPUS=2 run_script start --without-ai --observability --yes
  expect_no_output "Warning: Docker has"
}

test_the_price_file_is_required_with_ai_and_wins_over_the_environment() {
  given_ai_with_a_key_in_the_environment
  rm "$root/deploy/llm-prices.env"
  run_script start --yes
  expect_status 1
  expect_output "deploy/llm-prices.env is missing"
  printf '%s\n' GEMINI_MODEL=gemini-of-the-tests LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS=1 \
    > "$root/deploy/llm-prices.env"
  run_script start --yes
  expect_status 1
  expect_output "deploy/llm-prices.env lacks LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS"
  expect_no_state
  given_the_price_file
  GEMINI_MODEL=model-of-the-shell run_script start --yes
  expect_status 0
  expect_logged "--env-file $root/deploy/llm-prices.env"
  expect_logged "GEMINI_MODEL=unset"
}

test_without_ai_no_release_no_price_file_and_no_key_are_needed() {
  run_script start --without-ai --yes
  expect_status 0
  expect_not_logged "run "
  expect_not_logged "llm-prices.env"
  expect_not_logged "build ai-service"
  grep -q 'COMPOSE_PROFILES=$' "$root/docker.log" || fail_test "expected no profile"
  expect_output "Without AI, staff handle every ticket manually."
}

test_a_missing_image_of_the_download_command_is_pulled_before_the_download() {
  local cached
  given_ai_with_a_key_in_the_environment
  cached="$(cache_dir)/$RELEASE_ID"
  STUB_IMAGE_INSPECT_STATUS=1 run_script start --yes
  expect_status 0
  [ "$(grep -E '^(pull|run) ' "$root/docker.log" | cut -d' ' -f1 | paste -sd ' ' -)" = "pull run" ] \
    || fail_test "expected the pull of the uv image, then the download"
  expect_logged "pull ghcr.io/astral-sh/uv:0.11.11-python3.14-trixie-slim@sha256:3e70f580d0e63d78408c35d332d780024b6e1d46d9744c888e22fa944393448e"
  rm -r "$cached"
  STUB_IMAGE_INSPECT_STATUS=1 STUB_PULL_STATUS=1 run_script start --yes
  expect_status 1
  expect_output "the image ghcr.io/astral-sh/uv:0.11.11-python3.14-trixie-slim did not download; try again, or start with --without-ai"
}

# ----- the Gemini key -----

test_without_a_key_and_without_a_terminal_stops_with_where_to_get_one() {
  given_ai_without_a_key
  run_script start
  expect_status 1
  expect_output "ai-service needs a Gemini API key, and none is set or saved"
  expect_output "https://aistudio.google.com/apikey"
  expect_output "deploy/local/local-run.sh set-key"
  expect_output "--without-ai"
  expect_no_state
  expect_not_logged " build "
}

test_without_a_key_and_with_yes_stops_without_the_prompt() {
  given_ai_without_a_key
  run_script_on_a_terminal "$KEY_PROMPT" "" -- start --yes
  expect_status 1
  expect_output "ai-service needs a Gemini API key, and none is set or saved"
  expect_no_output "$KEY_PROMPT"
  expect_no_state
}

test_a_placeholder_key_counts_as_no_key() {
  local value
  given_ai_without_a_key
  for value in "" replace-with-a-gemini-api-key YOUR_GEMINI_API_KEY; do
    GEMINI_API_KEY=$value run_script start --yes
    expect_status 1
    expect_output "ai-service needs a Gemini API key, and none is set or saved"
  done
  given_a_saved_key replace-with-a-gemini-api-key
  run_script start --yes
  expect_status 1
  expect_output "ai-service needs a Gemini API key, and none is set or saved"
}

test_the_key_prompt_saves_the_key_only_after_y() {
  local key
  given_ai_without_a_key
  key=$(new_test_key valid)
  run_script_on_a_terminal "$KEY_PROMPT" "$key" "$QUESTION" y -- start
  expect_status 0
  expect_output "Create a free one at https://aistudio.google.com/apikey"
  expect_output "Google may use and read the requests: enter only the simulated demo data, never real data"
  expect_output "save the Gemini key that you entered in .local-run/gemini.env, mode 0600"
  [ "$(cat "$root/.local-run/gemini.env")" = "GEMINI_API_KEY='$key'" ] || fail_test "gemini.env lacks the key"
  [ "$(file_mode "$root/.local-run/gemini.env")" = 600 ] || fail_test "gemini.env is not 0600"
  expect_logged "--env-file $root/.local-run/gemini.env"
  expect_no_output "Warning:"
  expect_no_part_of_the_key "$key"
}

test_the_answer_n_after_the_key_prompt_saves_nothing() {
  local key
  given_ai_without_a_key
  key=$(new_test_key valid)
  run_script_on_a_terminal "$KEY_PROMPT" "$key" "$QUESTION" n -- start
  expect_status 1
  expect_output "nothing changed"
  expect_no_state
  expect_not_logged " build "
  expect_no_part_of_the_key "$key"
}

test_an_empty_answer_to_the_key_prompt_runs_without_ai_and_saves_nothing() {
  given_ai_without_a_key
  run_script_on_a_terminal "$KEY_PROMPT" "" "$QUESTION" y -- start
  expect_status 0
  expect_output "This start runs without AI, and nothing is saved."
  [ ! -e "$root/.local-run/gemini.env" ] || fail_test "gemini.env was written"
  expect_no_output "download the release"
  expect_not_logged "run "
  expect_not_logged "build ai-service"
  expect_output "Without AI, staff handle every ticket manually."
}

test_a_key_of_the_environment_is_used_and_never_written() {
  given_ai_with_a_key_in_the_environment
  run_script start --yes
  expect_status 0
  [ ! -e "$root/.local-run/gemini.env" ] || fail_test "gemini.env was written"
  expect_not_logged "gemini.env"
  expect_logged "GEMINI_API_KEY=set"
  expect_no_output "$KEY_PROMPT"
  expect_no_part_of_the_key "$GEMINI_API_KEY"
}

test_a_saved_key_is_used_without_a_prompt_or_a_terminal() {
  local key
  given_ai_without_a_key
  key=$(new_test_key valid)
  given_a_saved_key "$key"
  run_script start --yes
  expect_status 0
  expect_logged "--env-file $root/.local-run/gemini.env"
  expect_no_output "Gemini API key"
  expect_no_part_of_the_key "$key"
}

test_the_key_of_the_environment_wins_over_the_saved_one() {
  given_ai_with_a_key_in_the_environment
  given_a_saved_key "$(new_test_key valid)"
  run_script start --yes
  expect_status 0
  expect_not_logged "gemini.env"
}

test_a_key_with_a_paste_mistake_warns_once_and_shows_no_part_of_it() {
  local form key
  given_ai_without_a_key
  for form in space quote newline; do
    key=$(new_test_key "$form")
    GEMINI_API_KEY=$key run_script start --yes
    expect_status 0
    expect_output_once "Warning: the Gemini key holds a space, a quote, or a line break, which is often a paste mistake"
    expect_output_once "Warning: the Gemini key does not look like an AI Studio key; ignore this if you are sure."
    expect_no_part_of_the_key "$key"
  done
}

test_a_key_of_another_form_warns_once_and_goes_on() {
  local key
  given_ai_without_a_key
  key=$(new_test_key other)
  GEMINI_API_KEY=$key run_script start --yes
  expect_status 0
  expect_output_once "Warning: the Gemini key does not look like an AI Studio key; ignore this if you are sure."
  expect_no_output "paste mistake"
  expect_no_part_of_the_key "$key"
}

test_a_key_of_the_ai_studio_form_gets_no_warning() {
  given_ai_with_a_key_in_the_environment
  run_script start --yes
  expect_status 0
  expect_no_output "Warning:"
}

test_set_key_without_a_terminal_stops_and_changes_nothing() {
  run_script set-key
  expect_status 1
  expect_output "set-key needs a terminal"
  expect_no_state
  given_a_saved_key "$(new_test_key valid)"
  cp "$root/.local-run/gemini.env" "$root/gemini.env.before"
  run_script set-key
  expect_status 1
  cmp -s "$root/.local-run/gemini.env" "$root/gemini.env.before" || fail_test "gemini.env changed"
}

test_set_key_saves_the_key_at_once_and_creates_the_state_folder() {
  local key
  key=$(new_test_key valid)
  run_script_on_a_terminal "$KEY_PROMPT" "$key" -- set-key
  expect_status 0
  [ "$(cat "$root/.local-run/gemini.env")" = "GEMINI_API_KEY='$key'" ] || fail_test "gemini.env lacks the key"
  [ "$(file_mode "$root/.local-run")" = 700 ] || fail_test ".local-run/ is not 0700"
  [ "$(file_mode "$root/.local-run/gemini.env")" = 600 ] || fail_test "gemini.env is not 0600"
  [ ! -e "$root/.local-run/secrets.env" ] || fail_test "set-key wrote secrets.env"
  expect_output "A running ai-service keeps its old key until the next start"
  expect_no_part_of_the_key "$key"
  [ ! -s "$root/docker.log" ] || fail_test "set-key ran a docker command"
}

test_set_key_with_an_empty_answer_keeps_the_saved_key() {
  given_a_saved_key "$(new_test_key valid)"
  cp "$root/.local-run/gemini.env" "$root/gemini.env.before"
  run_script_on_a_terminal "$KEY_PROMPT" "" -- set-key
  expect_status 0
  expect_output "Nothing changed."
  cmp -s "$root/.local-run/gemini.env" "$root/gemini.env.before" || fail_test "gemini.env changed"
}

test_set_key_warns_on_a_key_of_another_form() {
  local key
  key=$(new_test_key other)
  run_script_on_a_terminal "$KEY_PROMPT" "$key" -- set-key
  expect_status 0
  expect_output_once "Warning: the Gemini key does not look like an AI Studio key"
  expect_no_part_of_the_key "$key"
}

test_the_files_of_the_secrets_and_the_key_are_ignored_by_git() {
  (cd "$REPOSITORY_ROOT" && git check-ignore -q .local-run/secrets.env) \
    || fail_test ".local-run/secrets.env is not ignored by git"
  (cd "$REPOSITORY_ROOT" && git check-ignore -q .local-run/gemini.env) \
    || fail_test ".local-run/gemini.env is not ignored by git"
}

test_a_start_killed_while_it_adds_to_secrets_env_leaves_the_old_file_whole() {
  given_a_first_start --without-ai
  cp "$root/.local-run/secrets.env" "$root/secrets.env.before"
  STUB_VOLUME_INSPECT_STATUS=0 STUB_MV_KILLS_AT="$root/.local-run/secrets.env" \
    run_script start --without-ai --observability --yes
  [ "$run_status" -ne 0 ] || fail_test "the start was not killed"
  cmp -s "$root/.local-run/secrets.env" "$root/secrets.env.before" || fail_test "secrets.env changed"
  grep -q '^LOCAL_GRAFANA_ADMIN_PASSWORD=' "$root/.local-run/secrets.env.partial" \
    || fail_test "expected the temporary file of the killed write"
  # The step that the guide gives after a start that was killed.
  rmdir "$root/.local-run/start.lock"
  STUB_VOLUME_INSPECT_STATUS=0 run_script start --without-ai --yes
  expect_status 0
  [ ! -e "$root/.local-run/secrets.env.partial" ] || fail_test "secrets.env.partial stayed"
  cmp -s "$root/.local-run/secrets.env" "$root/secrets.env.before" || fail_test "secrets.env changed"
}

test_a_set_key_killed_while_it_writes_leaves_the_old_key_whole() {
  given_a_saved_key "$(new_test_key valid)"
  cp "$root/.local-run/gemini.env" "$root/gemini.env.before"
  STUB_MV_KILLS_AT="$root/.local-run/gemini.env" \
    run_script_on_a_terminal "$KEY_PROMPT" "$(new_test_key valid)" -- set-key
  [ "$run_status" -ne 0 ] || fail_test "set-key was not killed"
  cmp -s "$root/.local-run/gemini.env" "$root/gemini.env.before" || fail_test "gemini.env changed"
  [ -e "$root/.local-run/gemini.env.partial" ] || fail_test "expected the temporary file of the killed write"
  run_script start --without-ai --yes
  expect_status 0
  [ ! -e "$root/.local-run/gemini.env.partial" ] || fail_test "gemini.env.partial stayed"
  cmp -s "$root/.local-run/gemini.env" "$root/gemini.env.before" || fail_test "gemini.env changed"
}

test_a_failing_producer_never_replaces_secrets_env() {
  given_a_first_start --without-ai
  cp "$root/.local-run/secrets.env" "$root/secrets.env.before"
  STUB_VOLUME_INSPECT_STATUS=0 STUB_OD_FAILS=1 run_script start --without-ai --observability --yes
  expect_status 1
  expect_output ".local-run/secrets.env could not be written, and it is unchanged"
  cmp -s "$root/.local-run/secrets.env" "$root/secrets.env.before" || fail_test "secrets.env changed"
  [ ! -e "$root/.local-run/secrets.env.partial" ] || fail_test "secrets.env.partial stayed"
  expect_not_logged " up "
}

test_a_failing_producer_writes_no_first_secrets_env() {
  STUB_OD_FAILS=1 run_script start --without-ai --yes
  expect_status 1
  expect_output ".local-run/secrets.env could not be written, and it is unchanged"
  [ ! -e "$root/.local-run/secrets.env" ] || fail_test "secrets.env was written"
  [ ! -e "$root/.local-run/secrets.env.partial" ] || fail_test "secrets.env.partial stayed"
  expect_not_logged " build "
}

test_a_leftover_temporary_file_is_removed_at_the_next_start() {
  given_a_first_start --without-ai
  echo "GEMINI_API_KEY=half" > "$root/.local-run/gemini.env.partial"
  STUB_VOLUME_INSPECT_STATUS=0 run_script start --without-ai --yes
  expect_status 0
  [ ! -e "$root/.local-run/gemini.env.partial" ] || fail_test "gemini.env.partial stayed"
}

test_a_key_with_a_dollar_is_saved_in_single_quotes_and_read_back_as_it_is() {
  local key
  given_ai_without_a_key
  key=$(new_test_key dollar)
  run_script_on_a_terminal "$KEY_PROMPT" "$key" -- set-key
  expect_status 0
  [ "$(cat "$root/.local-run/gemini.env")" = "GEMINI_API_KEY='$key'" ] || fail_test "gemini.env lacks the key in single quotes"
  run_script start --yes
  expect_status 0
  # Read back with its quotes, the key would get the warning of a paste mistake.
  expect_no_output "paste mistake"
  expect_output_once "Warning: the Gemini key does not look like an AI Studio key"
  expect_no_part_of_the_key "$key"
}

test_a_saved_key_of_the_ai_studio_form_is_read_back_without_a_warning() {
  local key
  given_ai_without_a_key
  key=$(new_test_key valid)
  run_script_on_a_terminal "$KEY_PROMPT" "$key" -- set-key
  expect_status 0
  run_script start --yes
  expect_status 0
  expect_no_output "Warning:"
}

test_a_key_with_a_single_quote_is_never_saved() {
  local key
  given_ai_without_a_key
  key=$(new_test_key single-quote)
  run_script_on_a_terminal "$KEY_PROMPT" "$key" -- set-key
  expect_status 1
  expect_output "the key that you entered holds a ', which .local-run/gemini.env cannot hold"
  [ ! -e "$root/.local-run/gemini.env" ] || fail_test "gemini.env was written"
  run_script_on_a_terminal "$KEY_PROMPT" "$key" "$QUESTION" y -- start
  expect_status 1
  expect_output "the key that you entered holds a '"
  expect_no_output "$QUESTION"
  expect_no_state
  expect_no_part_of_the_key "$key"
}

# ----- the plan and the question -----

test_a_first_start_without_a_terminal_and_without_yes_changes_nothing() {
  run_script start --without-ai
  expect_status 1
  expect_output "The local run will:"
  expect_output "pass --yes"
  expect_no_state
  expect_not_logged " build "
}

test_a_first_start_names_the_default_port_and_its_source() {
  run_script start --without-ai
  expect_output "PostgreSQL on 127.0.0.1:$(port_of LOCAL_DB_PORT), the default; set LOCAL_DB_PORT to change it"
}

test_a_first_start_answered_n_on_a_terminal_changes_nothing() {
  run_script_on_a_terminal "$QUESTION" n -- start --without-ai
  expect_status 1
  expect_output "$QUESTION"
  expect_no_state
  expect_not_logged " build "
}

test_a_first_start_answered_y_on_a_terminal_starts() {
  run_script_on_a_terminal "$QUESTION" y -- start --without-ai
  expect_status 0
  expect_logged " up --detach --wait"
}

test_a_first_start_with_yes_writes_the_secrets_records_the_port_and_builds_in_order() {
  local name value calls
  run_script start --without-ai --yes
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
  given_a_first_start --without-ai
  first=$(cat "$root/.local-run/secrets.env")
  STUB_VOLUME_INSPECT_STATUS=0 run_script start --without-ai
  expect_status 0
  expect_output "Starting the local run"
  expect_no_output "Proceed?"
  expect_logged " up --detach --wait"
  [ "$(cat "$root/.local-run/secrets.env")" = "$first" ] || fail_test "secrets.env changed"
}

test_a_second_start_with_ai_and_the_release_in_the_cache_asks_nothing() {
  given_ai_with_a_key_in_the_environment
  given_a_first_start
  STUB_VOLUME_INSPECT_STATUS=0 STUB_DOWNLOAD_STATUS=5 run_script start
  expect_status 0
  expect_no_output "Proceed?"
  expect_not_logged "run "
  expect_logged "LOCAL_RELEASE_FOLDER=$(cache_dir)/$RELEASE_ID "
}

# The steps of the CI job local-run-compose-ai, with the dummy key of that job read from the
# workflow itself: `start --yes`, after a download or on a hit of the release cache, then `start`
# without --yes and without a terminal (run_script reads /dev/null), which must ask nothing. The
# key is not of the AI Studio form, so each start warns once, and a key of the environment is
# never saved, so no question is due for it.
run_the_steps_of_the_ci_job_with_ai() {
  local first_start=$1 key
  local warning="Warning: the Gemini key does not look like an AI Studio key; ignore this if you are sure."
  key=$(sed -n 's/^ *GEMINI_API_KEY: //p' "$REPOSITORY_ROOT/.github/workflows/local-run.yml")
  [ -n "$key" ] || fail_test "the job local-run-compose-ai sets no GEMINI_API_KEY"
  given_ai_without_a_key
  if [ "$first_start" = cache-hit ]; then given_the_release_in_the_cache; fi
  GEMINI_API_KEY=$key run_script start --yes
  expect_status 0
  expect_output_once "$warning"
  if [ "$first_start" = cache-hit ]; then expect_not_logged "run "; else expect_logged "run "; fi
  expect_no_part_of_the_key "$key"
  : > "$root/docker.log"
  GEMINI_API_KEY=$key STUB_VOLUME_INSPECT_STATUS=0 STUB_DOWNLOAD_STATUS=5 run_script start
  expect_status 0
  expect_no_output "$QUESTION"
  expect_no_output "$KEY_PROMPT"
  expect_output_once "$warning"
  expect_not_logged "run "
  expect_not_logged "pull "
  expect_logged "LOCAL_RELEASE_FOLDER=$(cache_dir)/$RELEASE_ID "
  [ ! -e "$root/.local-run/gemini.env" ] || fail_test "gemini.env was written"
  expect_no_part_of_the_key "$key"
}

test_the_steps_of_the_ci_job_with_ai_after_a_download_ask_nothing_the_second_time() {
  run_the_steps_of_the_ci_job_with_ai download
}

test_the_steps_of_the_ci_job_with_ai_on_a_cache_hit_ask_nothing_the_second_time() {
  run_the_steps_of_the_ci_job_with_ai cache-hit
}

test_a_missing_image_makes_the_question_due() {
  given_a_first_start --without-ai
  STUB_VOLUME_INSPECT_STATUS=0 STUB_IMAGE_INSPECT_STATUS=1 run_script start --without-ai
  expect_status 1
  expect_output "which downloads its dependencies"
  expect_output "pass --yes"
  expect_not_logged " build "
}

test_a_changed_dependency_file_makes_the_question_due_and_its_rebuild_is_recorded() {
  local file image
  given_ai_with_a_key_in_the_environment
  given_a_first_start
  for file in ai-service/README.md backend/uv.lock frontend/pnpm-lock.yaml; do
    case "$file" in
      ai-service/*) image=supportiq-local-ai-service ;;
      backend/*) image=supportiq-local-backend ;;
      frontend/*) image=supportiq-local-frontend ;;
    esac
    echo "a changed content" >> "$root/$file"
    STUB_VOLUME_INSPECT_STATUS=0 run_script start
    expect_status 1
    expect_output "rebuild the image $image from this working tree: $file changed since its last build, so the rebuild downloads every package of the image again"
    expect_output "pass --yes"
    STUB_VOLUME_INSPECT_STATUS=0 run_script start --yes
    expect_status 0
    STUB_VOLUME_INSPECT_STATUS=0 run_script start
    expect_status 0
    expect_no_output "Proceed?"
  done
}

test_a_failing_sha256_tool_stops_before_the_question() {
  printf '#!/bin/sh\nexit 1\n' > "$root/bin/sha256sum"
  chmod +x "$root/bin/sha256sum"
  run_script start --without-ai --yes
  expect_status 1
  expect_output "the SHA-256 of backend/pyproject.toml backend/uv.lock backend/README.md cannot be computed"
  expect_no_state
}

# The stub changes the file at each build, and frontend builds last without AI, so only a record
# made before the build of frontend can differ from the file after it.
test_a_dependency_file_that_changes_during_the_build_makes_the_next_start_ask() {
  given_a_first_start --without-ai
  STUB_VOLUME_INSPECT_STATUS=0 STUB_BUILD_CHANGES="$root/frontend/pnpm-lock.yaml" \
    run_script start --without-ai --yes
  expect_status 0
  STUB_VOLUME_INSPECT_STATUS=0 run_script start --without-ai
  expect_status 1
  expect_output "rebuild the image supportiq-local-frontend from this working tree: frontend/pnpm-lock.yaml changed since its last build"
}

test_a_present_image_without_a_record_makes_the_question_due() {
  given_a_first_start --without-ai
  rm "$root/.local-run/image-inputs/supportiq-local-frontend.sha256"
  STUB_VOLUME_INSPECT_STATUS=0 run_script start --without-ai
  expect_status 1
  expect_output "rebuild the image supportiq-local-frontend from this working tree: no record of the files that it installs its dependencies from exists yet"
  expect_no_output "rebuild the image supportiq-local-backend from this working tree: no record"
}

test_another_local_db_port_warns_and_asks() {
  local new_port
  given_a_first_start --without-ai
  new_port=$(free_port)
  LOCAL_DB_PORT=$new_port STUB_VOLUME_INSPECT_STATUS=0 run_script start --without-ai
  expect_status 1
  expect_output "move PostgreSQL from 127.0.0.1:$(port_of LOCAL_DB_PORT) to 127.0.0.1:$new_port"
  expect_output "PostgreSQL on 127.0.0.1:$new_port, from LOCAL_DB_PORT"
  [ "$(recorded_port)" = "$(port_of LOCAL_DB_PORT)" ] || fail_test "the record changed"
  LOCAL_DB_PORT=$new_port STUB_VOLUME_INSPECT_STATUS=0 run_script start --without-ai --yes
  expect_status 0
  [ "$(recorded_port)" = "$new_port" ] || fail_test "the new port was not recorded"
}

test_another_local_db_port_answered_n_keeps_the_record() {
  given_a_first_start --without-ai
  LOCAL_DB_PORT=$(free_port) STUB_VOLUME_INSPECT_STATUS=0 \
    run_script_on_a_terminal "$QUESTION" n -- start --without-ai
  expect_status 1
  [ "$(recorded_port)" = "$(port_of LOCAL_DB_PORT)" ] || fail_test "the record changed"
  expect_not_logged " up "
}

test_yes_answers_only_the_question_and_never_a_missing_tool() {
  STUB_DOCKER_INFO_STATUS=1 run_script start --without-ai --yes
  expect_status 1
  expect_no_output "The local run will:"
}

# ----- what already runs -----

test_start_when_every_part_runs_changes_nothing() {
  STUB_RUNNING_SERVICES=$'backend\nfrontend\npostgres\n' run_script start --without-ai
  expect_status 0
  expect_output "already runs"
  expect_output "to run the changes of your working tree, run deploy/local/local-run.sh stop, then start"
  expect_not_logged " build "
  expect_no_state
}

test_start_with_ai_when_every_part_runs_needs_no_key_and_no_release() {
  STUB_RUNNING_SERVICES=$'ai-service\nbackend\nfrontend\npostgres\n' run_script start
  expect_status 0
  expect_output "already runs"
  expect_no_output "Gemini API key"
  expect_no_state
}

test_start_with_another_port_while_every_part_runs_stops() {
  given_a_first_start --without-ai
  LOCAL_DB_PORT=$(free_port) STUB_RUNNING_SERVICES=$'backend\nfrontend\npostgres\n' \
    run_script start --without-ai --yes
  expect_status 1
  expect_output "already runs with PostgreSQL on 127.0.0.1:$(port_of LOCAL_DB_PORT); run deploy/local/local-run.sh stop first"
  expect_not_logged " up "
}

test_start_when_some_parts_run_starts_the_others() {
  STUB_RUNNING_SERVICES=$'postgres\n' run_script start --without-ai --yes
  expect_status 0
  expect_no_output "already runs"
  expect_logged " up --detach --wait"
}

test_start_when_it_runs_in_another_mode_stops() {
  STUB_RUNNING_SERVICES=$'ai-service\nbackend\nfrontend\npostgres\n' run_script start --without-ai --yes
  expect_status 1
  expect_output "already runs in another mode"
  STUB_RUNNING_SERVICES=$'backend\nfrontend\npostgres\n' run_script start --yes
  expect_status 1
  expect_output "already runs in another mode"
  expect_no_state
}

test_start_while_another_start_holds_the_lock_stops() {
  mkdir -p "$root/.local-run/start.lock"
  run_script start --without-ai --yes
  expect_status 1
  expect_output "another start holds .local-run/start.lock"
  expect_not_logged " build "
}

test_a_secrets_file_that_lacks_a_value_stops_and_stays_as_it_is() {
  mkdir -p "$root/.local-run"
  printf 'LOCAL_DB_SUPERUSER_PASSWORD=%064d\n' 0 > "$root/.local-run/secrets.env"
  run_script start --without-ai --yes
  expect_status 1
  expect_output ".local-run/secrets.env lacks LOCAL_DB_OWNER_PASSWORD; it is never rewritten: add the line, or remove the local data with: deploy/local/local-run.sh stop, then docker volume rm supportiq-local_postgres-data, then rm -r .local-run"
  [ "$(wc -l < "$root/.local-run/secrets.env" | tr -d ' ')" = 1 ] || fail_test "secrets.env changed"
}

# ----- observability -----

test_observability_generates_the_grafana_password_once() {
  local first others
  given_a_first_start --without-ai
  others=$(cat "$root/.local-run/secrets.env")
  STUB_VOLUME_INSPECT_STATUS=0 run_script start --without-ai --observability --yes
  expect_status 0
  first=$(secret_value LOCAL_GRAFANA_ADMIN_PASSWORD)
  printf '%s' "$first" | grep -Eq "$SECRET_PATTERN" || fail_test "no generated Grafana password"
  expect_no_output "$first"
  [ "$(grep -v '^LOCAL_GRAFANA_ADMIN_PASSWORD=' "$root/.local-run/secrets.env")" = "$others" ] \
    || fail_test "the other secrets changed"
  [ "$(file_mode "$root/.local-run/secrets.env")" = 600 ] || fail_test "secrets.env is not 0600"
  STUB_VOLUME_INSPECT_STATUS=0 run_script start --without-ai --observability
  expect_status 0
  expect_no_output "Proceed?"
  [ "$(secret_value LOCAL_GRAFANA_ADMIN_PASSWORD)" = "$first" ] || fail_test "it changed"
}

test_observability_takes_the_grafana_password_of_the_environment() {
  LOCAL_GRAFANA_ADMIN_PASSWORD=chosen-by-the-user run_script start --without-ai --observability --yes
  expect_status 0
  [ -z "$(secret_value LOCAL_GRAFANA_ADMIN_PASSWORD)" ] || fail_test "it was written to the file"
  expect_no_output chosen-by-the-user
}

# ----- failures and interruptions -----

test_with_ai_ai_service_starts_first_then_the_others() {
  given_ai_with_a_key_in_the_environment
  run_script start --yes
  expect_status 0
  [ "$(grep -c ' up ' "$root/docker.log")" -eq 2 ] || fail_test "expected two ups"
  grep ' up ' "$root/docker.log" | sed -n 1p | grep -qE -- '--no-build ai-service$' \
    || fail_test "expected the first up for ai-service alone"
  grep ' up ' "$root/docker.log" | sed -n 2p | grep -qE -- '--no-build$' \
    || fail_test "expected the second up for every part"
}

test_with_ai_a_failing_ai_service_starts_neither_backend_nor_frontend() {
  given_ai_with_a_key_in_the_environment
  STUB_UP_STATUS=1 run_script start --yes
  expect_status 1
  expect_output "ai-service did not get ready, so backend and frontend were not started"
  [ "$(grep -c ' up ' "$root/docker.log")" -eq 1 ] || fail_test "expected one up, of ai-service"
  expect_logged "--no-build ai-service"
}

test_with_ai_and_observability_both_start_first() {
  given_ai_with_a_key_in_the_environment
  run_script start --observability --yes
  expect_status 0
  expect_output "Starting ai-service and otel-lgtm first, and waiting until they are healthy."
  expect_logged "--no-build ai-service otel-lgtm"
  expect_output "Sign in as admin, with the password"
  expect_output "LOCAL_GRAFANA_ADMIN_PASSWORD of your shell, or of .local-run/secrets.env"
}

test_with_ai_and_observability_failing_names_both() {
  given_ai_with_a_key_in_the_environment
  STUB_UP_STATUS=1 run_script start --observability --yes
  expect_status 1
  expect_output "ai-service and otel-lgtm did not get ready, so backend and frontend were not started"
}

test_observability_starts_otel_lgtm_first() {
  STUB_UP_STATUS=1 run_script start --without-ai --observability --yes
  expect_status 1
  expect_output "otel-lgtm did not get ready, so backend and frontend were not started"
  expect_logged "--no-build otel-lgtm"
}

test_a_part_that_does_not_get_ready_stops_the_start() {
  STUB_UP_STATUS=1 run_script start --without-ai --yes
  expect_status 1
  expect_output "a part did not get ready"
  [ ! -e "$root/.local-run/start.lock" ] || fail_test "the lock stayed"
}

# The volume is shared by every folder of the repository, so a setup that fails may have met a
# database that only the secrets.env of another folder opens.
test_a_failed_backend_setup_names_a_database_of_another_folder() {
  STUB_UP_STATUS=1 STUB_CONTAINER_IDS=$'abc\n' STUB_EXIT_CODE=1 run_script start --without-ai --yes
  expect_status 1
  expect_output "backend-setup failed. If its log shows a password failure, the volume supportiq-local_postgres-data holds a database that a start in another folder of the repository created"
  expect_output "a part did not get ready"
  expect_logged "ps --all --quiet backend-setup"
}

test_another_part_that_does_not_get_ready_says_nothing_of_another_folder() {
  STUB_UP_STATUS=1 STUB_CONTAINER_IDS=$'abc\n' STUB_EXIT_CODE=0 run_script start --without-ai --yes
  expect_status 1
  expect_output "a part did not get ready"
  expect_no_output "backend-setup failed"
  STUB_UP_STATUS=1 run_script start --without-ai --yes
  expect_status 1
  expect_no_output "backend-setup failed"
}

test_ctrl_c_while_the_parts_start_stops_them_and_keeps_the_volume() {
  STUB_UP_SLEEP_S=30 run_script_and_signal SIGINT "Starting the parts" start --without-ai --yes
  expect_status "$EXIT_INTERRUPTED"
  expect_output "interrupted"
  expect_logged " down"
  expect_not_logged "--volumes"
  [ ! -e "$root/.local-run/start.lock" ] || fail_test "the lock stayed"
}

test_ctrl_c_on_a_terminal_reaches_only_the_script_and_prints_no_job_line() {
  STUB_UP_RECORDS_SIGNALS=1 run_script_on_a_terminal_and_press_ctrl_c "Starting the parts" \
    start --without-ai --yes
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
  STUB_UP_SLEEP_S=30 run_script_and_signal SIGTERM "Starting the parts" start --without-ai --yes
  expect_status "$EXIT_INTERRUPTED"
  expect_logged " down"
}

test_ctrl_c_during_the_build_has_no_part_to_stop() {
  STUB_BUILD_SLEEP_S=30 run_script_and_signal SIGINT "Building supportiq-local-backend" \
    start --without-ai --yes
  expect_status "$EXIT_INTERRUPTED"
  expect_not_logged " down"
  expect_not_logged " up "
}

test_ctrl_c_keeps_the_parts_that_ran_before_this_start() {
  STUB_RUNNING_SERVICES=$'postgres\n' STUB_UP_SLEEP_S=30 \
    run_script_and_signal SIGINT "Starting the parts" start --without-ai --yes
  expect_status "$EXIT_INTERRUPTED"
  expect_logged "rm --stop --force backend-setup backend frontend"
  expect_not_logged "ai-service"
  expect_not_logged " down"
}

# ----- stop, status, logs, and releases -----

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

test_releases_lists_the_published_ones_the_default_and_the_cached_ones() {
  given_the_pinned_release
  given_a_published_release release-other
  mkdir -p "$root/eval/releases/release-without-manifest"
  echo '{}' > "$root/eval/releases/release-without-manifest/gate-run.json"
  given_the_release_in_the_cache
  mkdir -p "$(cache_dir)/.release-other.partial-0a1b"
  run_script releases
  expect_status 0
  printf '%s\n' "$run_output" | grep -qx "  $RELEASE_ID (the default, in the cache)" \
    || fail_test "expected the default release, in the cache"
  printf '%s\n' "$run_output" | grep -qx "  release-other" \
    || fail_test "expected release-other without a mark"
  expect_no_output "release-without-manifest"
  expect_output "Release cache: $(cache_dir)"
  [ ! -s "$root/docker.log" ] || fail_test "releases ran a docker command"
  expect_no_state
}

test_releases_without_a_pinned_file_has_no_default() {
  given_a_published_release "$RELEASE_ID"
  run_script releases
  expect_status 0
  printf '%s\n' "$run_output" | grep -qx "  $RELEASE_ID" || fail_test "expected the release"
  expect_output "No default release: eval/releases/pinned-release.txt is missing"
}

# ----- the runner -----

main() {
  local seed=${TEST_SEED:-$RANDOM} name failed=0 count=0
  test_seed=$seed
  # The settings that a test sets itself never come from the environment of the person.
  unset GEMINI_API_KEY GEMINI_MODEL LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS \
    LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS LOCAL_GRAFANA_ADMIN_PASSWORD LOCAL_DB_PORT \
    SUPPORTIQ_RELEASE_CACHE SUPPORTIQ_RELEASE_TOKEN
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
