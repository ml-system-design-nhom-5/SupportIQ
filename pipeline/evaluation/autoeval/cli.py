"""Command line for SupportIQ automatic evaluation.

  python -m pipeline.evaluation.autoeval run                      # ML + LLM offline (free)
  python -m pipeline.evaluation.autoeval run --suite ml --backend numpy
  python -m pipeline.evaluation.autoeval run --suite llm --llm-mode live [--judge] [--evidence retrieval]
  python -m pipeline.evaluation.autoeval run --compare artifacts/evaluation/autoeval/<run>/report.json
  python -m pipeline.evaluation.autoeval build-data               # regenerate frozen datasets + manifest
  python -m pipeline.evaluation.autoeval parity                   # numpy vs torch logits (needs torch)

Exit code: 0 = every blocking gate passed, 1 = a blocking gate failed (or a regression with
--fail-on-regression), 2 = the evaluation itself could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .datasets import REPO_ROOT, build, verify_manifest

_ALLOWED_SUITES = {"ml", "llm", "all"}
_SECRET_ENV_VARS = ("GEMINI_API_KEY", "DATABASE_URL", "DATABASE_URL_OWNER", "SUPPORTIQ_APPLICATION_SECRETS")
_CRED_URL_RE = re.compile(r"://([^:/@\s]+):([^/@\s]+)@")
_API_KEY_RE = re.compile(r"([?&](?:key|api_key|token)=)([^&\s]+)", re.I)


def _sanitize_text(text: str) -> str:
    out = _CRED_URL_RE.sub(r"://\1:[REDACTED]@", text)
    out = _API_KEY_RE.sub(r"\1[REDACTED]", out)
    for var in _SECRET_ENV_VARS:
        val = os.environ.get(var, "").strip()
        if val and len(val) >= 4:
            out = out.replace(val, "[REDACTED]")
    return out


def _safe_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {_sanitize_text(str(exc))}"


def _resolve_path(raw: str | Path) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p)


def _display_path(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


def _load_config(path: str) -> dict:
    cfg = json.loads(_resolve_path(path).read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or not all(k in cfg for k in ("output_dir", "gates", "autoeval_dir")):
        raise ValueError(f"invalid autoeval config structure: {path}")
    return cfg


def _parse_suites(raw: str) -> set[str]:
    tokens = [s.strip() for s in raw.split(",") if s.strip()]
    unknown = sorted(set(tokens) - _ALLOWED_SUITES)
    if not tokens or unknown:
        raise ValueError(f"invalid --suite {raw!r}; expected comma-separated subset of ml, llm, all")
    return {"ml", "llm"} if "all" in tokens else set(tokens)


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=5).stdout.strip() or None
    except Exception:
        return None


def _jsonable(o):
    if isinstance(o, (set, tuple)):
        return list(o)
    if hasattr(o, "item"):
        return o.item()
    return str(o)


def _write_report(run_dir: Path, report: dict) -> None:
    from .report import render

    (run_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=_jsonable), encoding="utf-8")
    (run_dir / "report.md").write_text(render(report), encoding="utf-8")


def _record_error(run_dir: Path, run_id: str, suites: set[str], args, datasets: dict, t0: float, message: str) -> int:
    safe_msg = _sanitize_text(message)
    (run_dir / "error.txt").write_text(safe_msg + "\n", encoding="utf-8")
    report = {
        "meta": {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "git_commit": _git_commit(),
            "suites": sorted(suites),
            "llm_mode": args.llm_mode if "llm" in suites else None,
            "config": args.config,
            "datasets": datasets,
            "duration_s": time.perf_counter() - t0,
            "python": sys.version.split()[0],
            "error": safe_msg,
        },
        "summary": {"pass": 0, "fail": 0, "warn": 0, "skipped": 0, "not_run": 0, "passed": False, "error": safe_msg},
        "gates": [],
        "results": {},
    }
    _write_report(run_dir, report)
    print(f"[autoeval] {safe_msg}", file=sys.stderr)
    return 2


def cmd_run(args) -> int:
    from . import gates as G

    t0 = time.perf_counter()
    try:
        suites = _parse_suites(args.suite)
        config = _load_config(args.config)
    except Exception as e:
        print(f"[autoeval] setup error: {_safe_error(e)}", file=sys.stderr)
        return 2

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + (f"-{args.tag}" if args.tag else "")
    out_root = _resolve_path(args.out or config["output_dir"])
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    prev_results: dict | None = None
    if args.compare is not None:
        try:
            tol = config.get("regression_tolerance")
            if not isinstance(tol, (int, float)) or isinstance(tol, bool):
                raise ValueError("config missing numeric regression_tolerance")
            compare_path = _resolve_path(args.compare)
            if not args.compare or not compare_path.is_file():
                raise FileNotFoundError(f"--compare file not found: {args.compare}")
            prev = json.loads(compare_path.read_text(encoding="utf-8"))
            if not isinstance(prev, dict) or not isinstance(prev.get("results"), dict):
                raise ValueError(f"--compare file missing valid 'results' object: {args.compare}")
            prev_results = prev["results"]
        except Exception as e:
            return _record_error(run_dir, run_id, suites, args, {"ok": False, "mismatched": []}, t0, f"comparison error: {_safe_error(e)}")

    try:
        datasets = verify_manifest(config)
    except Exception as e:
        datasets = {"ok": False, "error": _safe_error(e), "mismatched": ["manifest"]}
    if not datasets.get("ok") and not args.allow_dataset_drift:
        return _record_error(run_dir, run_id, suites, args, datasets, t0, f"dataset manifest mismatch: {datasets}")

    results: dict = {}
    try:
        if "ml" in suites:
            from . import ml_suite
            results["ml"] = ml_suite.run(config, backend=args.backend)
        if "llm" in suites:
            from . import llm_suite
            results["llm"] = llm_suite.run(
                config,
                mode=args.llm_mode,
                run_dir=run_dir,
                evidence_mode=args.evidence,
                use_judge=args.judge,
                human_labels=_resolve_path(args.human_labels) if args.human_labels else None,
                max_calls=args.max_llm_calls,
            )
    except Exception as e:
        return _record_error(run_dir, run_id, suites, args, datasets, t0, f"evaluation error: {_safe_error(e)}")

    try:
        gate_rows = G.evaluate(results, config["gates"], suites)
    except Exception as e:
        return _record_error(run_dir, run_id, suites, args, datasets, t0, f"gate evaluation error: {_safe_error(e)}")
    summary = {k: sum(g["status"] == k for g in gate_rows) for k in ("pass", "fail", "warn", "skipped", "not_run")}
    summary["passed"] = summary["fail"] == 0 and summary["pass"] > 0
    report = {
        "meta": {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "git_commit": _git_commit(),
            "suites": sorted(suites),
            "llm_mode": args.llm_mode if "llm" in suites else None,
            "config": args.config,
            "datasets": datasets,
            "duration_s": time.perf_counter() - t0,
            "python": sys.version.split()[0],
        },
        "summary": summary,
        "gates": gate_rows,
        "results": results,
    }
    if prev_results is not None:
        try:
            regression_rows = G.regression(results, prev_results, config["regression_tolerance"])
        except Exception as e:
            return _record_error(run_dir, run_id, suites, args, datasets, t0, f"comparison error: {_safe_error(e)}")
        if not regression_rows:
            return _record_error(
                run_dir,
                run_id,
                suites,
                args,
                datasets,
                t0,
                "comparison error: baseline has no comparable metrics for selected suites",
            )
        report["regression"] = regression_rows
        report["summary"]["regressions"] = sum(r["regressed"] for r in regression_rows)

    _write_report(run_dir, report)
    latest = out_root / "latest.txt"
    latest.write_text(_display_path(run_dir) + "\n", encoding="utf-8")
    print(
        f"[autoeval] {'PASSED' if summary['passed'] else 'FAILED'}: {summary['fail']} blocking failures, "
        f"{summary['warn']} warnings, {summary['pass']} passed, {summary['skipped']} skipped, {summary['not_run']} not run "
        f"-> {_display_path(run_dir)}/report.md"
    )
    for g in gate_rows:
        if g["status"] in ("fail", "warn"):
            print(f"  [{g['status'].upper()}] {g['id']}: {g['value']!r} (need {g['op']} {g['threshold']!r})")
    if not summary["passed"]:
        return 1
    if args.fail_on_regression and report.get("summary", {}).get("regressions"):
        return 1
    return 0


def cmd_build(args) -> int:
    m = build(_load_config(args.config))
    print(json.dumps(m, indent=2))
    return 0


def cmd_parity(args) -> int:
    from .backends import parity
    from .datasets import load_jsonl
    config = _load_config(args.config)
    texts = [c["text"] for c in load_jsonl(REPO_ROOT / config["benchmark"])][: args.n]
    res = parity(REPO_ROOT / config["ml"]["model_dir"], texts)
    print(json.dumps(res, indent=2))
    return 0 if res["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.evaluation.autoeval", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="pipeline/configs/autoeval.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run suites and gates")
    r.add_argument("--suite", default="all", help="ml, llm or all (comma separated)")
    r.add_argument("--backend", default="auto", choices=["auto", "torch", "numpy"])
    r.add_argument("--llm-mode", default="offline", choices=["offline", "live"])
    r.add_argument("--evidence", default="oracle", choices=["oracle", "retrieval"], help="live mode: gold KB docs or real retrieval")
    r.add_argument("--judge", action="store_true", help="live mode: LLM-as-judge grounding (extra calls)")
    r.add_argument("--human-labels", help="judge_claims.jsonl with human_label filled in")
    r.add_argument("--max-llm-calls", type=int)
    r.add_argument("--compare", help="previous report.json for regression check")
    r.add_argument("--fail-on-regression", action="store_true")
    r.add_argument("--allow-dataset-drift", action="store_true")
    r.add_argument("--out", help="output root (default from config)")
    r.add_argument("--tag", help="suffix for the run id")
    r.set_defaults(func=cmd_run)
    b = sub.add_parser("build-data", help="regenerate frozen datasets and manifest")
    b.set_defaults(func=cmd_build)
    p = sub.add_parser("parity", help="numpy vs torch logits check")
    p.add_argument("--n", type=int, default=30)
    p.set_defaults(func=cmd_parity)
    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as e:
        print(f"[autoeval] fatal error: {_safe_error(e)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
