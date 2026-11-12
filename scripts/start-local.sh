#!/usr/bin/env bash
# ==============================================================================
# SupportIQ Local Multi-Service Launcher (Linux / macOS)
# ==============================================================================
# Starts:
#   1. SQLite Database setup & seed (scripts/init_db.py)
#   2. AI Service on http://127.0.0.1:8002 (Real BGE vector RAG + Google Gemini LLM)
#   3. Backend & Background Worker on http://127.0.0.1:8080 (serves static UI & API)
# ==============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

LOCAL_DIR="${REPO_ROOT}/.local"
mkdir -p "${LOCAL_DIR}"

BOLD="\033[1m"
GREEN="\033[1;32m"
RED="\033[1;31m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
BLUE="\033[1;34m"
RESET="\033[0m"

# 1. Detect Python
if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    PYTHON="${REPO_ROOT}/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="$(command -v python3)"
else
    echo -e "${RED}[ERROR] Python 3 interpreter not found in .venv or PATH.${RESET}" >&2
    exit 1
fi

export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${CYAN}                      SupportIQ Local Service Launcher                        ${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"

# 2. Check ports 8080 & 8002
check_port() {
    local port="$1"
    if command -v lsof &>/dev/null; then
        lsof -iTCP:"${port}" -sTCP:LISTEN -n -P &>/dev/null
    elif command -v ss &>/dev/null; then
        ss -ltn "sport = :${port}" | grep -q LISTEN
    elif command -v fuser &>/dev/null; then
        fuser "${port}/tcp" &>/dev/null
    else
        python3 -c "import socket; s = socket.socket(); s.connect(('127.0.0.1', ${port})); s.close()" 2>/dev/null
    fi
}

if check_port 8002; then
    echo -e "${YELLOW}[WARN] Port 8002 is already in use. Stopping existing listener...${RESET}"
    fuser -k 8002/tcp 2>/dev/null || true
    sleep 1
fi

if check_port 8080; then
    echo -e "${YELLOW}[WARN] Port 8080 is already in use. Stopping existing listener...${RESET}"
    fuser -k 8080/tcp 2>/dev/null || true
    sleep 1
fi

# 3. Initialize SQLite Database & Demo Logins
echo -e "${BLUE}>>> [1/3] Initializing SQLite database and seeding demo data...${RESET}"
${PYTHON} scripts/init_db.py

# 4. Check Frontend Build
if [[ ! -d "${REPO_ROOT}/apps/frontend/dist" ]]; then
    echo -e "${YELLOW}>>> Frontend dist not found. Building production bundle...${RESET}"
    if command -v npx &>/dev/null; then
        npx -y pnpm --dir apps/frontend build
    else
        echo -e "${RED}[ERROR] Node / npx required to build frontend.${RESET}" >&2
        exit 1
    fi
fi

# 5. Start AI Service (Port 8002)
echo -e "${BLUE}>>> [2/3] Starting AI Service on http://127.0.0.1:8002...${RESET}"
export SUPPORTIQ_ENABLE_LLM="true"
export SUPPORTIQ_DEV_FALLBACK_MODEL="true"

${PYTHON} -m uvicorn apps.ai_service.main:create_app --factory --host 127.0.0.1 --port 8002 --no-access-log > "${LOCAL_DIR}/ai.stdout.log" 2> "${LOCAL_DIR}/ai.stderr.log" &
AI_PID=$!

cleanup() {
    echo -e "\n${YELLOW}Stopping SupportIQ local processes...${RESET}"
    if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
        kill "${BACKEND_PID}" 2>/dev/null || true
    fi
    if [[ -n "${AI_PID:-}" ]] && kill -0 "${AI_PID}" 2>/dev/null; then
        kill "${AI_PID}" 2>/dev/null || true
    fi
    rm -f "${LOCAL_DIR}/processes.json"
    echo -e "${GREEN}All services stopped cleanly.${RESET}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# Wait for AI readiness
echo -n "Waiting for AI service readiness (loading BGE index & Gemini client)..."
AI_READY=false
for i in {1..30}; do
    if curl -s http://127.0.0.1:8002/health/ready 2>/dev/null | grep -q '"status":"ready"'; then
        AI_READY=true
        echo -e " ${GREEN}READY!${RESET}"
        break
    fi
    echo -n "."
    sleep 0.5
done

if [[ "${AI_READY}" != "true" ]]; then
    echo -e "\n${RED}[ERROR] AI service failed to start. Check .local/ai.stderr.log:${RESET}"
    tail -n 20 "${LOCAL_DIR}/ai.stderr.log" || true
    cleanup
fi

# 6. Start Backend & Worker (Port 8080)
echo -e "${BLUE}>>> [3/3] Starting Backend & Suggestion Worker on http://127.0.0.1:8080...${RESET}"
export SUPPORTIQ_DATABASE_URL_APP="sqlite:///${LOCAL_DIR}/supportiq.db"
export SUPPORTIQ_AI_SERVICE_BASE_URL="http://127.0.0.1:8002"
export SUPPORTIQ_SESSION_COOKIE_SECURE="false"

${PYTHON} -m uvicorn apps.backend.main:create_app --factory --host 127.0.0.1 --port 8080 --no-access-log > "${LOCAL_DIR}/backend.stdout.log" 2> "${LOCAL_DIR}/backend.stderr.log" &
BACKEND_PID=$!

# Wait for Backend readiness
echo -n "Waiting for Backend readiness..."
BACKEND_READY=false
for i in {1..20}; do
    if curl -s http://127.0.0.1:8080/health/ready 2>/dev/null | grep -q '"status":"ready"'; then
        BACKEND_READY=true
        echo -e " ${GREEN}READY!${RESET}"
        break
    fi
    echo -n "."
    sleep 0.5
done

if [[ "${BACKEND_READY}" != "true" ]]; then
    echo -e "\n${RED}[ERROR] Backend failed to start. Check .local/backend.stderr.log:${RESET}"
    tail -n 20 "${LOCAL_DIR}/backend.stderr.log" || true
    cleanup
fi

# Record PIDs
cat <<EOF > "${LOCAL_DIR}/processes.json"
[
  {"Kind": "ai-service", "Pid": ${AI_PID}, "Port": 8002},
  {"Kind": "backend", "Pid": ${BACKEND_PID}, "Port": 8080}
]
EOF

echo -e "\n${BOLD}${GREEN}==============================================================================${RESET}"
echo -e "${BOLD}${GREEN}               SupportIQ Local Services Running Successfully!                 ${RESET}"
echo -e "${BOLD}${GREEN}==============================================================================${RESET}"
echo -e "  • Web Application (UI + API):  ${BOLD}${CYAN}http://127.0.0.1:8080${RESET}"
echo -e "  • AI Gateway (RAG + Gemini):   ${BOLD}${CYAN}http://127.0.0.1:8002${RESET}"
echo -e "  • Prometheus Telemetry:        ${BOLD}${CYAN}http://127.0.0.1:8080/metrics${RESET}"
echo -e "  • API Interactive Docs:        ${BOLD}${CYAN}http://127.0.0.1:8080/api/docs${RESET}"
echo -e "------------------------------------------------------------------------------"
echo -e "${BOLD}Demo Accounts (Password: ${YELLOW}password123${RESET}${BOLD}):${RESET}"
echo -e "  - Customer Portal:  ${CYAN}customer-1${RESET}"
echo -e "  - Staff Console:    ${CYAN}staff-1${RESET}"
echo -e "  - Manager Overview: ${CYAN}manager-1${RESET}"
echo -e "  - Admin Governance: ${CYAN}admin-1${RESET}"
echo -e "------------------------------------------------------------------------------"
echo -e "Logs: ${BLUE}.local/ai.stdout.log${RESET} | ${BLUE}.local/backend.stdout.log${RESET}"
echo -e "Press ${YELLOW}Ctrl+C${RESET} in this terminal or run ${YELLOW}./scripts/stop-local.sh${RESET} to terminate."
echo -e "${BOLD}${GREEN}==============================================================================${RESET}\n"

# Wait on background processes
wait "${BACKEND_PID}" "${AI_PID}"
