"""CLI runner for Task C bounded Gemini 3.5 Flash-Lite acceptance evaluation.

Safety guarantees:
- Defaults to zero-network dry-run preflight unless --execute-live is explicitly passed.
- Refuses --max-requests > 24 so live generation traffic never exceeds the authorized 24 HTTP calls.
- Never prints or persists GEMINI_API_KEY or database passwords.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

WORKTREE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKTREE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKTREE_ROOT))

from pipeline.evaluation.flash_lite_acceptance import (
    DEFAULT_ROOT_REPO,
    MAX_APPLICATION_LIVE_HTTP_REQUESTS,
    run_bounded_flash_lite_acceptance,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bounded real-application Gemini 3.5 Flash-Lite acceptance collector (max 24 HTTP calls)."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run zero-network preflight, OOF lineage check, and serving model verification (0 HTTP calls).",
    )
    mode.add_argument(
        "--execute-live",
        action="store_true",
        help="Execute the bounded live real-application run (max 24 actual HTTP calls total).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=WORKTREE_ROOT / "artifacts" / "evaluation",
        help="Base output directory where run subdirectory is created.",
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=MAX_APPLICATION_LIVE_HTTP_REQUESTS,
        help="Hard cap on actual Gemini HTTP generation requests (must be <= 24).",
    )
    parser.add_argument(
        "--env-path",
        type=Path,
        default=None,
        help="Optional path to .env containing GEMINI_API_KEY (defaults to root repo .env).",
    )
    parser.add_argument(
        "--worktree-root",
        type=Path,
        default=WORKTREE_ROOT,
        help="Worktree repository root containing frozen benchmark & approved KB.",
    )
    parser.add_argument(
        "--root-repo",
        type=Path,
        default=DEFAULT_ROOT_REPO,
        help="Root repository holding .env, .local/application.json, and trained model artifacts.",
    )
    parser.add_argument(
        "--poll-timeout-seconds",
        type=float,
        default=25.0,
        help="Wall-clock timeout polling each backend suggestion job to terminal state.",
    )
    parser.add_argument(
        "--no-override-diagnostics",
        action="store_true",
        help="Disable Phase 2 separately labeled staff intent-override diagnostic calls.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_requests < 0 or args.max_requests > MAX_APPLICATION_LIVE_HTTP_REQUESTS:
        raise ValueError(
            f"--max-requests must be between 0 and {MAX_APPLICATION_LIVE_HTTP_REQUESTS}; got {args.max_requests}"
        )

    worktree_root = Path(args.worktree_root).resolve()
    os.chdir(worktree_root)

    result = run_bounded_flash_lite_acceptance(
        output_base_dir=Path(args.output_dir),
        worktree_root=worktree_root,
        root_repo=Path(args.root_repo).resolve(),
        env_path=Path(args.env_path).resolve() if args.env_path else None,
        max_requests=args.max_requests,
        poll_timeout_seconds=args.poll_timeout_seconds,
        execute_live=bool(args.execute_live),
        run_override_diagnostics=not args.no_override_diagnostics,
    )

    if not result["executed_live"]:
        pre = result["preflight"]
        summary = {
            "run_id": result["run_id"],
            "output_dir": result["output_dir"],
            "executed_live": False,
            "configured_model": pre["configured_provider"]["model"],
            "preflight_budget": pre["budget_preflight"]["preflight_budget"],
            "serving_weights_match_pinned": pre["serving_classifier"]["matches_pinned_expected_manifest"],
            "postgres_connected": pre["postgres_isolated_connectivity"]["connected"],
            "oof_total_rows": pre["oof_lineage_audit"]["distilbert_oof"]["total_rows"],
            "oof_macro_f1_mean": pre["oof_lineage_audit"]["distilbert_oof"]["macro_f1_mean"],
            "oof_matches_serving_report": pre["oof_lineage_audit"]["serving_training_report_linkage"].get(
                "matches_oof_macro_f1_mean_within_1e12"
            ),
        }
    else:
        rep = result["report"]
        summary = {
            "run_id": result["run_id"],
            "output_dir": result["output_dir"],
            "executed_live": True,
            "actual_http_requests_made": rep["budget_accounting"]["actual_http_requests_made"],
            "authorized_max_http_requests": rep["budget_accounting"]["authorized_max_http_requests"],
            "rejected_before_network_count": rep["budget_accounting"]["rejected_before_network_count"],
            "phase1_automatic_correct_intent_drafts": rep["phase1_primary_automatic_application"][
                "answerable_automatic_correct_intent_draft_ready_count"
            ],
            "phase1_wrong_intent_drafts": rep["phase1_primary_automatic_application"][
                "answerable_automatic_wrong_intent_draft_ready_count"
            ],
            "phase2_override_drafts": rep["phase2_oracle_staff_override_diagnostic"][
                "draft_ready_and_source_verified_count"
            ],
            "combined_unique_answerable_drafts": rep["combined_unique_answerable_correct_intent_drafts"][
                "automatic_plus_staff_override_count"
            ],
            "safety_unsafe_drafts": rep["phase1_primary_automatic_application"]["safety_unsafe_draft_count"],
            "complete_cost_known": rep["tokens_and_cost"]["complete_cost_known"],
        }

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
