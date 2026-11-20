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
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .datasets import REPO_ROOT, build, verify_manifest


def _load_config(path: str) -> dict:
    return json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))


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


def cmd_run(args) -> int:
    from . import gates as G
    from .report import render
    config = _load_config(args.config)
    suites = {s.strip() for s in args.suite.split(",") if s.strip()}
    if "all" in suites:
        suites = {"ml", "llm"}
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + (f"-{args.tag}" if args.tag else "")
    run_dir = REPO_ROOT / (args.out or config["output_dir"]) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    datasets = verify_manifest(config)
    if not datasets["ok"] and not args.allow_dataset_drift:
        print(f"[autoeval] dataset manifest mismatch: {datasets}. Run `build-data` or pass --allow-dataset-drift.", file=sys.stderr)
        return 2
    results: dict = {}
    try:
        if "ml" in suites:
            from . import ml_suite
            results["ml"] = ml_suite.run(config, backend=args.backend)
        if "llm" in suites:
            from . import llm_suite
            results["llm"] = llm_suite.run(config, mode=args.llm_mode, run_dir=run_dir, evidence_mode=args.evidence,
                                           use_judge=args.judge, human_labels=Path(args.human_labels) if args.human_labels else None,
                                           max_calls=args.max_llm_calls)
    except Exception as e:
        (run_dir / "error.txt").write_text(f"{type(e).__name__}: {e}\n", encoding="utf-8")
        print(f"[autoeval] evaluation error: {type(e).__name__}: {e}", file=sys.stderr)
        raise
    gate_rows = G.evaluate(results, config["gates"], suites)
    summary = {k: sum(g["status"] == k for g in gate_rows) for k in ("pass", "fail", "warn", "skipped", "not_run")}
    summary["passed"] = summary["fail"] == 0
    report = {"meta": {"run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(), "git_commit": _git_commit(),
                       "suites": sorted(suites), "llm_mode": args.llm_mode if "llm" in suites else None,
                       "config": args.config, "datasets": datasets, "duration_s": time.perf_counter() - t0, "python": sys.version.split()[0]},
              "summary": summary, "gates": gate_rows, "results": results}
    compare = Path(args.compare) if args.compare else None
    if compare and not compare.is_absolute():
        compare = REPO_ROOT / compare
    if compare and not compare.exists():
        print(f"[autoeval] --compare file not found, regression check skipped: {args.compare}", file=sys.stderr)
        compare = None
    if compare:
        prev = json.loads(compare.read_text(encoding="utf-8"))
        report["regression"] = G.regression(results, prev["results"], config["regression_tolerance"])
        report["summary"]["regressions"] = sum(r["regressed"] for r in report["regression"])
    (run_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=_jsonable), encoding="utf-8")
    (run_dir / "report.md").write_text(render(report), encoding="utf-8")
    latest = REPO_ROOT / (args.out or config["output_dir"]) / "latest.txt"
    latest.write_text(str(run_dir.relative_to(REPO_ROOT)).replace("\\", "/") + "\n", encoding="utf-8")
    print(f"[autoeval] {'PASSED' if summary['passed'] else 'FAILED'}: {summary['fail']} blocking failures, {summary['warn']} warnings, "
          f"{summary['pass']} passed -> {run_dir.relative_to(REPO_ROOT)}/report.md")
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
    except Exception:
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
