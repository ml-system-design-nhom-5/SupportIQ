#!/usr/bin/env bash
# ==============================================================================
# SupportIQ Local Multi-Service Stopper (Linux / macOS)
# ==============================================================================

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_DIR="${REPO_ROOT}/.local"

echo "Stopping SupportIQ local processes..."

# 1. Stop recorded PIDs if present
if [[ -f "${LOCAL_DIR}/processes.json" ]]; then
    python3 -c "
import json
from pathlib import Path
import os, signal

p = Path('${LOCAL_DIR}/processes.json')
if p.exists():
    try:
        data = json.loads(p.read_text())
        for proc in data:
            pid = proc.get('Pid')
            if pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                    print(f'Killed {proc.get(\"Kind\")} (PID {pid})')
                except ProcessLookupError:
                    pass
    except Exception as e:
        print('Error reading processes.json:', e)
    p.unlink(missing_ok=True)
" 2>/dev/null || true
fi

# 2. Release ports 8002 & 8080 if lingering
fuser -k 8002/tcp 2>/dev/null || true
fuser -k 8080/tcp 2>/dev/null || true

echo "✓ SupportIQ local services stopped."
