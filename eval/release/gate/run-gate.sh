#!/usr/bin/env bash
# Run the offline evaluation gate of one candidate in Docker (DATA-57, ADR-0021): the guardrail
# tests of backend and of ai-service, then `supportiq-release run-gate`, all from images built
# from the clean worktree, so the record names the commit that every check ran on.
#
# Usage: eval/release/gate/run-gate.sh --candidate <folder> --cases <folder>/cases.json
#
# The candidate is a folder that `supportiq-release build-candidate` wrote. It lies outside the
# repository or in an ignored path, because the worktree must be clean. The folder of the cases
# also holds approval.json. The release records go to eval/releases/ of the repository. The exit
# status is the one of run-gate: 0 passed, 1 failed, 2 invalid input; this script also exits
# with 2 when a step cannot produce its report.
#
# Each report names its suite (junit_suite_name), so that the gate can tell the two apart.
set -euo pipefail

readonly GATE_DIR=eval/release/gate

fail() {
  echo "run-gate.sh: $1" >&2
  exit 2
}

usage() {
  fail "usage: $GATE_DIR/run-gate.sh --candidate <folder> --cases <folder>/cases.json
  --candidate  a folder that \`supportiq-release build-candidate\` wrote, outside the worktree
  --cases      the cases.json of a set; approval.json lies next to it"
}

candidate=""
cases=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --candidate) [ "$#" -ge 2 ] || usage; candidate=$2; shift 2 ;;
    --cases) [ "$#" -ge 2 ] || usage; cases=$2; shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$candidate" ] && [ -n "$cases" ] || usage
[ -d "$candidate" ] || fail "the candidate $candidate is not a folder"
[ -f "$cases" ] || fail "the cases $cases are not a file"
# Absolute paths, taken before the script changes its directory.
candidate=$(cd "$candidate" && pwd -P)
cases_dir=$(cd "$(dirname "$cases")" && pwd -P)
cases_file=$(basename "$cases")

cd "$(git rev-parse --show-toplevel)"

# 1. Images built from a dirty worktree would not match the commit that the record names.
if [ -n "$(git status --porcelain --untracked-files=all)" ]; then
  git status --short --untracked-files=all >&2
  fail "the worktree has changes; commit or remove them, and keep the candidate outside it"
fi

# 2. The commit of every image and of the record.
commit=$(git rev-parse HEAD)
records="$PWD/eval/releases"
# An empty folder is not a change for git, so the worktree stays clean until a record exists.
mkdir -p "$records"

# Only BuildKit reads Dockerfile.dockerignore next to the Dockerfile; the legacy builder would
# send the whole repository as the build context, .env files included (SEC-29).
docker buildx version > /dev/null 2>&1 || fail "BuildKit (docker buildx) is required, because \
the legacy builder ignores Dockerfile.dockerignore and would send the whole repository (SEC-29)"

# 3. Both images from this worktree, with BuildKit always, even when DOCKER_BUILDKIT=0 is set.
gate_image="supportiq-gate:$commit"
backend_image="supportiq-gate-backend-guardrails:$commit"
docker buildx build --load --file "$GATE_DIR/Dockerfile" --target gate --tag "$gate_image" .
docker buildx build --load --file "$GATE_DIR/Dockerfile" --target backend-guardrails \
  --tag "$backend_image" .

# 4. The test reports go to a temporary folder outside the repository.
junit=$(mktemp -d)
export GATE_COMMIT="$commit" GATE_JUNIT_DIR="$junit"
compose=(docker compose --file "$GATE_DIR/compose.yaml")
cleanup() {
  if ! "${compose[@]}" down --volumes --remove-orphans > /dev/null 2>&1; then
    echo "run-gate.sh: docker compose down failed; remove the project supportiq-gate by hand" >&2
  fi
  rm -rf "$junit"
}
trap cleanup EXIT
caller="$(id -u):$(id -g)"

# 5. The guardrail tests of backend. A failed test still writes its report, and the gate
#    records the failure (TEST-20); only a failed setup, such as a failed migration, stops here.
backend_status=0
"${compose[@]}" run --rm --user "$caller" backend-guardrails || backend_status=$?
[ -f "$junit/backend-guardrails.xml" ] || fail \
  "the backend guardrail tests wrote no report (exit $backend_status); see the log above"

# 6. The guardrail tests of ai-service, without network.
ai_service_status=0
docker run --rm --network none --read-only --tmpfs /tmp --env HOME=/tmp --user "$caller" \
  --volume "$junit:/junit" "$gate_image" \
  pytest tests/integration/guardrails --junitxml=/junit/ai-service-guardrails.xml \
  -o junit_suite_name=ai_service_guardrails -p no:cacheprovider || ai_service_status=$?
[ -f "$junit/ai-service-guardrails.xml" ] || fail \
  "the ai-service guardrail tests wrote no report (exit $ai_service_status); see the log above"

# 7. The gate itself, without network: it reads the candidate, the cases, and both reports, and
#    writes one record to eval/releases/.
gate_status=0
docker run --rm --network none --read-only --tmpfs /tmp --env HOME=/tmp \
  --env HF_HOME=/tmp/huggingface --user "$caller" \
  --volume "$candidate:/candidate:ro" --volume "$cases_dir:/cases:ro" \
  --volume "$junit:/junit:ro" --volume "$records:/records" "$gate_image" \
  supportiq-release run-gate --candidate /candidate --cases "/cases/$cases_file" \
  --ai-service-guardrails /junit/ai-service-guardrails.xml \
  --backend-guardrails /junit/backend-guardrails.xml \
  --git-commit "$commit" --release-records /records || gate_status=$?
exit "$gate_status"
