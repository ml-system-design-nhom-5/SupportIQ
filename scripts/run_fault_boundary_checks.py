#!/usr/bin/env python3
"""Run Task C fault-boundary verification across Backend+PG and PipelineRunner (0 live LLM calls)."""
from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.evaluation.fault_boundary_runner import run_fault_boundary_suite
from scripts.native_runtime import configure_runtime_environment


def main() -> int:
    configure_runtime_environment(REPO_ROOT)
    out = run_fault_boundary_suite(worktree_root=REPO_ROOT)
    report = out["report"]
    print(
        json.dumps(
            {
                "output_dir": out["output_dir"],
                "live_http_requests_attempted": report["live_http_requests_attempted"],
                "live_http_budget_max": report["live_http_budget_max"],
                "pg_namespace_verified_absent": report["pg_cleanup"]["pg_namespace_verified_absent"],
                "summary": report["summary"],
                "hashes": out["hashes"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
