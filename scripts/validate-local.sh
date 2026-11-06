#!/usr/bin/env bash
# ==============================================================================
# SupportIQ Local Full-Pipeline Validation & Regression Suite
# ==============================================================================
# Supported Modes:
#   all          - Full pipeline: Unit tests, E2E journeys, live benchmarks & regression check
#   benchmark    - Execute system acceptance benchmarks (ML Intent, RAG, Grounding)
#   e2e          - Execute full-pipeline end-to-end integration tests (all 29 journeys)
#   escalation   - Execute the 16 escalation condition test journeys
#   edge-cases   - Execute RAG & input edge cases (empty KB, duplicate docs, >64KB, diacritics)
#   security     - Execute PII masking & injection attack sanitization tests
#   evaluate     - Run acceptance evaluation with gap-to-target analysis against ARCHITECTURE.md
#   regression   - Run automated evaluation loop with regression detection against baselines
#
# Usage:
#   ./scripts/validate-local.sh [MODE]
#   ./scripts/validate-local.sh --mode [MODE]
# ==============================================================================

set -uo pipefail

BOLD="\033[1m"
GREEN="\033[1;32m"
RED="\033[1;31m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
BLUE="\033[1;34m"
RESET="\033[0m"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

# Detect Python interpreter
if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    PYTHON="${REPO_ROOT}/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="$(command -v python3)"
else
    echo -e "${RED}[ERROR] Python 3 interpreter not found in .venv or PATH.${RESET}" >&2
    exit 1
fi

export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

# Parse Mode
MODE="all"
if [[ $# -gt 0 ]]; then
    case "$1" in
        --mode)
            MODE="${2:-all}"
            ;;
        --mode=*)
            MODE="${1#*=}"
            ;;
        all|benchmark|e2e|escalation|edge-cases|security|evaluate|regression|frontend)
            MODE="$1"
            ;;
        -h|--help)
            echo "SupportIQ Local Validation Runner"
            echo "Usage: $0 [all|benchmark|e2e|escalation|edge-cases|security|evaluate|regression|frontend]"
            echo ""
            echo "Modes:"
            echo "  all          Run complete local validation (Unit + E2E + Benchmarks + Regression + Frontend)"
            echo "  benchmark    Run ML Intent, RAG, and LLM Grounding benchmarks"
            echo "  e2e          Run all 29 E2E full-pipeline integration journeys"
            echo "  escalation   Run only the 16 escalation condition tests"
            echo "  edge-cases   Run RAG empty/duplicate and large/diacritic input tests"
            echo "  security     Run Luhn PII masking and injection sanitization tests"
            echo "  evaluate     Evaluate metrics against ARCHITECTURE.md targets"
            echo "  regression   Run automated evaluation & regression loop against baseline"
            echo "  frontend     Run frontend Vitest component tests (11 tests)"
            exit 0
            ;;
        *)
            echo -e "${RED}[ERROR] Unknown mode or argument: $1${RESET}" >&2
            echo "Run '$0 --help' for usage."
            exit 1
            ;;
    esac
fi

VALID_MODES="all benchmark e2e escalation edge-cases security evaluate regression frontend"
if [[ ! " ${VALID_MODES} " =~ " ${MODE} " ]]; then
    echo -e "${RED}[ERROR] Invalid mode '${MODE}'. Allowed: ${VALID_MODES}${RESET}" >&2
    exit 1
fi

echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${CYAN}            SupportIQ Local Validation & Observability Suite                 ${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e " Selected Mode: ${BOLD}${YELLOW}${MODE}${RESET}"
echo -e " Python:        ${BLUE}${PYTHON}${RESET} ($(${PYTHON} --version))"
echo -e " Repository:    ${REPO_ROOT}"
echo -e " Timestamp:     $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo -e "${BOLD}${CYAN}------------------------------------------------------------------------------${RESET}"

declare -A STAGE_STATUS
declare -A STAGE_DURATION
OVERALL_SUCCESS=true

run_stage() {
    local stage_id="$1"
    local stage_name="$2"
    local cmd="$3"

    echo -e "\n${BOLD}${BLUE}>>> Running [${stage_name}]...${RESET}"
    local start_time
    start_time=$(date +%s)

    local exit_code=0
    eval "${cmd}" || exit_code=$?

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))
    STAGE_DURATION["${stage_id}"]="${duration}s"

    if [[ ${exit_code} -eq 0 ]]; then
        STAGE_STATUS["${stage_id}"]="${GREEN}PASS${RESET}"
        echo -e "${GREEN}✓ [${stage_name}] passed in ${duration}s.${RESET}"
    else
        STAGE_STATUS["${stage_id}"]="${RED}FAIL (exit ${exit_code})${RESET}"
        echo -e "${RED}✗ [${stage_name}] failed in ${duration}s.${RESET}"
        OVERALL_SUCCESS=false
    fi
}

case "${MODE}" in
    all)
        run_stage "UNIT" "Unit & Observability Tests (389 tests)" "${PYTHON} -m pytest tests/unit/ -q --tb=short"
        run_stage "E2E" "Full-Pipeline E2E Tests (29 journeys)" "${PYTHON} -m pytest tests/e2e/test_full_pipeline.py -q --tb=short"
        if command -v npx &>/dev/null; then
            run_stage "FRONTEND" "Frontend Workspace & Console Tests (11 tests)" "npx -y pnpm --dir apps/frontend test"
        fi
        run_stage "BENCHMARK" "Acceptance Benchmarks (ML / RAG / Grounding)" "${PYTHON} scripts/run_benchmarks.py"
        run_stage "REGRESSION" "Automated Evaluation & Regression Loop" "${PYTHON} scripts/evaluate_regression.py"
        ;;
    frontend)
        run_stage "FRONTEND" "Frontend Workspace & Console Tests (11 tests)" "npx -y pnpm --dir apps/frontend test"
        ;;
    benchmark|evaluate)
        run_stage "BENCHMARK" "Acceptance Benchmarks (ML / RAG / Grounding)" "${PYTHON} scripts/run_benchmarks.py"
        ;;
    e2e)
        run_stage "E2E" "Full-Pipeline E2E Tests (all 29 journeys)" "${PYTHON} -m pytest tests/e2e/test_full_pipeline.py -v --tb=short"
        ;;
    escalation)
        run_stage "ESCALATION" "Escalation Condition Tests (16 triggers)" "${PYTHON} -m pytest tests/e2e/test_full_pipeline.py -k 'escalation' -v --tb=short"
        ;;
    edge-cases)
        run_stage "EDGE_CASES" "RAG & Input Edge Cases" "${PYTHON} -m pytest tests/e2e/test_full_pipeline.py -k 'test_rag or test_input' -v --tb=short"
        ;;
    security)
        run_stage "SECURITY" "PII Masking & Injection Attacks" "${PYTHON} -m pytest tests/e2e/test_full_pipeline.py -k 'test_pii or injection' -v --tb=short"
        ;;
    regression)
        run_stage "REGRESSION" "Automated Evaluation & Regression Loop" "${PYTHON} scripts/evaluate_regression.py"
        ;;
esac

echo -e "\n${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${CYAN}                           Execution Summary                                  ${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
printf "${BOLD}%-40s %-15s %-12s${RESET}\n" "Validation Stage" "Result" "Duration"
echo "------------------------------------------------------------------------------"

for stage_id in "${!STAGE_STATUS[@]}"; do
    printf "%-40s %-25b %-12s\n" "${stage_id}" "${STAGE_STATUS[${stage_id}]}" "${STAGE_DURATION[${stage_id}]}"
done

echo -e "${BOLD}${CYAN}==============================================================================${RESET}"

if [[ "${OVERALL_SUCCESS}" == "true" ]]; then
    echo -e "${BOLD}${GREEN}✔ ALL VALIDATION CHECKS FOR MODE [${MODE}] PASSED SUCCESSFULLY.${RESET}"
    exit 0
else
    echo -e "${BOLD}${RED}✘ VALIDATION CHECKS FAILED FOR MODE [${MODE}]. SEE LOGS ABOVE.${RESET}"
    exit 1
fi
