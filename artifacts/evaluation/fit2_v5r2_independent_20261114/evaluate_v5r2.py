"""Independent Stage 2 evaluation of frozen fit2-taxonomy-audit-v5-r2 vs v4p1, orig_fit2, and Serving.

Zero live LLM calls, zero training/calibration fits, zero threshold/gold edits, zero shared-code edits.
Evaluates raw_pre, raw_post, bare decide_route, Engine._analyse, and PipelineRunner.run
(_MockNoCallLLM / _OfflineValidSpyLLM for draft eligibility only) on the frozen reviewed runtime.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent
V4P1_DIR = REPO / "artifacts/evaluation/fit2_v4p1_independent_20261114"
sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location("evaluate_v4p1", V4P1_DIR / "evaluate_v4p1.py")
assert _spec and _spec.loader
V4P1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(V4P1)

from apps.ai_service.engine import Engine  # noqa: E402
from apps.core_backend.commerce.adapter import CommerceAdapter  # noqa: E402
from apps.core_backend.intent.routing import load_policy_v2  # noqa: E402
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner  # noqa: E402
from apps.core_backend.orchestration.store import PersistentStore  # noqa: E402
from apps.core_backend.retrieval.adapter import RetrievalAdapter  # noqa: E402
from pipeline.evaluation import classifier_acceptance_gate as CG  # noqa: E402
from scripts import run_closure_candidate_audit as A  # noqa: E402

RR_V5_INPUTS = REPO / "artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2/inputs"
RR_V4_INPUTS = REPO / "artifacts/models/candidates/run-records-fit2-boundary-contrast-v4p1/inputs"

MODELS = [
    *V4P1.MODELS,
    {
        "tag": "v5_r2",
        "dir": REPO / "artifacts/models/candidates/fit2-taxonomy-audit-v5-r2",
        "cal_manifest": REPO / "artifacts/models/candidates/fit2-taxonomy-audit-v5-r2/calibration_manifest.json",
        "cand_manifest": REPO / "artifacts/models/candidates/fit2-taxonomy-audit-v5-r2/candidate_provenance_manifest.json",
    },
]

V5R2_EXPECTED_WEIGHTS_SHA = "0b2d26c2adc22928a52bdbafe580fa1673d8ae1d112c42f3def643e137eaa33d"
V5R2_EXPECTED_CAL_SHA = "ca3d711c78f9c1e960ebf2d700b4445c4538e0bd4b52cc2dd6fb502dc8e472c1"


def _verify_parity_inputs() -> dict[str, str]:
    shared = (
        "bitext_test_6690.jsonl",
        "boundary_pos_evaluation.jsonl",
        "boundary_neg_evaluation.jsonl",
        "full_cal_split.jsonl",
    )
    hashes: dict[str, str] = {}
    for name in shared:
        h5 = CG.compute_file_sha256(RR_V5_INPUTS / name)
        h4 = CG.compute_file_sha256(RR_V4_INPUTS / name)
        if h5 != h4:
            raise RuntimeError(f"Parity mismatch on {name}: v5_r2={h5} vs v4p1={h4}")
        hashes[name] = h5
    return hashes


def _paired_diffs(by_tag: dict[str, dict[tuple[str, str], dict[str, Any]]], base_tag: str) -> dict[str, Any]:
    diffs: dict[str, Any] = {}
    for suite_name in ("fresh34", "ind36", "sealed72", "final24", "sa156", "noise420", "oos80", "pos175", "neg51"):
        keys = [k for k in by_tag["v5_r2"] if k[0] == suite_name]
        diffs[suite_name] = {
            "runner_changed": [
                {
                    "id": cid,
                    "gold": by_tag["v5_r2"][(s, cid)]["gold"],
                    f"{base_tag}_act": by_tag[base_tag][(s, cid)]["runner_action"],
                    f"{base_tag}_pred": by_tag[base_tag][(s, cid)]["pred_intent"],
                    "v5_r2_act": by_tag["v5_r2"][(s, cid)]["runner_action"],
                    "v5_r2_pred": by_tag["v5_r2"][(s, cid)]["pred_intent"],
                    "v5_r2_rej": by_tag["v5_r2"][(s, cid)]["rejected_by_adapter"],
                }
                for s, cid in keys
                if by_tag[base_tag][(s, cid)]["runner_action"] != by_tag["v5_r2"][(s, cid)]["runner_action"]
                or by_tag[base_tag][(s, cid)]["pred_intent"] != by_tag["v5_r2"][(s, cid)]["pred_intent"]
            ],
            "engine_changed": [
                {
                    "id": cid,
                    "gold": by_tag["v5_r2"][(s, cid)]["gold"],
                    f"{base_tag}_act": by_tag[base_tag][(s, cid)]["engine_action"],
                    f"{base_tag}_pred": by_tag[base_tag][(s, cid)]["engine_intent"],
                    "v5_r2_act": by_tag["v5_r2"][(s, cid)]["engine_action"],
                    "v5_r2_pred": by_tag["v5_r2"][(s, cid)]["engine_intent"],
                    "v5_r2_rej": by_tag["v5_r2"][(s, cid)]["rejected_by_adapter"],
                }
                for s, cid in keys
                if by_tag[base_tag][(s, cid)]["engine_action"] != by_tag["v5_r2"][(s, cid)]["engine_action"]
                or by_tag[base_tag][(s, cid)]["engine_intent"] != by_tag["v5_r2"][(s, cid)]["engine_intent"]
            ],
            "raw_post_changed": [
                {
                    "id": cid,
                    "gold": by_tag["v5_r2"][(s, cid)]["gold"],
                    f"{base_tag}_act": by_tag[base_tag][(s, cid)]["raw_post_action"],
                    f"{base_tag}_pred": by_tag[base_tag][(s, cid)]["pred_intent"],
                    "v5_r2_act": by_tag["v5_r2"][(s, cid)]["raw_post_action"],
                    "v5_r2_pred": by_tag["v5_r2"][(s, cid)]["pred_intent"],
                }
                for s, cid in keys
                if by_tag[base_tag][(s, cid)]["raw_post_action"] != by_tag["v5_r2"][(s, cid)]["raw_post_action"]
                or by_tag[base_tag][(s, cid)]["pred_intent"] != by_tag["v5_r2"][(s, cid)]["pred_intent"]
            ],
        }
    return diffs


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shared_input_hashes = _verify_parity_inputs()
    V4P1.RR_INPUTS = RR_V5_INPUTS

    v5_spec = MODELS[-1]
    actual_w_sha = CG.compute_file_sha256(v5_spec["dir"] / "model.safetensors")
    actual_c_sha = CG.compute_file_sha256(v5_spec["cal_manifest"])
    assert actual_w_sha == V5R2_EXPECTED_WEIGHTS_SHA, f"weights sha mismatch: {actual_w_sha}"
    assert actual_c_sha == V5R2_EXPECTED_CAL_SHA, f"cal sha mismatch: {actual_c_sha}"

    root = A._bootstrap_target_repo(REPO)
    rel = json.loads((root / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    retr = RetrievalAdapter(
        kb_path=str(root / "data/knowledge/approved_kb.v2.json"),
        allowed_document_versions={(d["document_id"], str(d["version"])) for d in rel["documents"]},
    )
    comm = CommerceAdapter(data_path=str(root / "data/knowledge/mock_orders.json"))
    pol_path = root / "apps/core_backend/config/policies/intent_policy.v2.json"
    policy, pv2 = json.loads(pol_path.read_text(encoding="utf-8")), load_policy_v2(pol_path)

    # 1. Production classifier acceptance gate on frozen v5-r2 vs Serving
    srv_dir = root / "artifacts/models/trained/distilbert-supportiq"
    gate_blocker: str | None = None
    gate_report: dict[str, Any] | None = None
    try:
        gate_report = CG.run_classifier_acceptance_gate(
            repo_root=root,
            candidate_name="fit2-taxonomy-audit-v5-r2",
            candidate_dir=v5_spec["dir"],
            serving_dir=srv_dir,
            candidate_manifest_path=v5_spec["cand_manifest"],
            calibration_manifest_path=v5_spec["cal_manifest"],
            train_split_path=RR_V5_INPUTS / "full_train_split.jsonl",
            calibration_split_path=RR_V5_INPUTS / "full_cal_split.jsonl",
            eval_split_path=RR_V5_INPUTS / "boundary_pos_evaluation.jsonl",
        )
        (OUT_DIR / "gate_report_v5r2.json").write_text(json.dumps(gate_report, indent=2, default=str) + "\n", encoding="utf-8")
    except Exception as exc:  # Report contract blocker without mutating shared code
        gate_blocker = f"{type(exc).__name__}: {exc}"

    # 2. Load unchanged benchmark + holdout/regression suites
    fresh34_path = V4P1_DIR / "fresh_holdout_34.jsonl"
    fresh34 = CG.load_jsonl(fresh34_path)
    ind36 = CG.load_jsonl(root / "artifacts/evaluation/fit2_independent_gate_20261113/cases.jsonl")
    sealed72 = CG.load_jsonl(root / "artifacts/evaluation/sealed_holdout_20261113/sealed_holdout_cases.jsonl")
    final24 = CG.load_jsonl(root / "data/benchmarks/final_acceptance/cases.jsonl")
    sa156 = CG.load_jsonl(root / "data/benchmarks/system/v2/acceptance/cases.jsonl")
    noise420 = CG.load_jsonl(root / "data/benchmarks/autoeval/v1/ml_noise.jsonl")
    oos80 = CG.load_jsonl(root / "data/benchmarks/autoeval/v1/ml_oos.jsonl")
    pos175 = CG.load_jsonl(RR_V5_INPUTS / "boundary_pos_evaluation.jsonl")
    neg51 = CG.load_jsonl(RR_V5_INPUTS / "boundary_neg_evaluation.jsonl")

    summaries: dict[str, Any] = {
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "reviewed_runtime_sha": "183cdf6935ad392e2e01e6af331d56a326dfabb9",
        "offline_conditions": (
            "0 live LLM calls; _MockNoCallLLM for Engine._analyse/routing only; "
            "_OfflineValidSpyLLM for PipelineRunner draft eligibility/snapshot only (not real LLM generation). "
            "existingfresh34 is treated strictly as historical regression, not unseen holdout."
        ),
        "injected_fault_exclusions": {
            "final24_injected_boundary_ids": sorted(r["id"] for r in final24 if not r.get("is_answerable") and r.get("fixture_boundary") != "active_kb"),
            "sa156_known_uninjected_ids": sorted(CG.KNOWN_UNINJECTED_ACCEPTANCE_IDS),
        },
        "gate_v5r2_decision": gate_report["gate_decision"] if gate_report else "BLOCKER",
        "gate_v5r2_failures": gate_report["failure_reasons"] if gate_report else [gate_blocker],
        "gate_blocker": gate_blocker,
        "shared_eval_input_hashes": shared_input_hashes,
        "models": {},
    }

    all_preds: dict[str, list[dict[str, Any]]] = {}
    with tempfile.TemporaryDirectory() as td:
        for spec in MODELS:
            tag = spec["tag"]
            clf, cal = V4P1._load_clf(spec)
            engine = Engine(clf, retr, A._MockNoCallLLM(), {"release_id": f"eval-{tag}", "model_version": tag}, policy)
            runner = PipelineRunner(
                intent_client=A._MockIntentClient(clf),
                commerce_adapter=comm,
                retrieval_adapter=retr,
                store=PersistentStore(db_path=str(Path(td) / f"{tag}.sqlite3")),
                llm_client=A._OfflineValidSpyLLM(),
                policy=pv2,
            )

            recs_fresh = [V4P1._eval_case(clf, engine, runner, pv2, suite="fresh34", cid=r["id"], text=r["text"], gold=r["true_intent"],
                                          ctx_dict=r["context"], as_of=r["context"]["as_of"],
                                          meta={"slice": r["slice"], "subgroup": r["subgroup"], "must_not_draft": r["must_not_draft"]}) for r in fresh34]
            recs_ind36 = [V4P1._eval_case(clf, engine, runner, pv2, suite="ind36", cid=r["id"], text=r["text"], gold=r["true_intent"],
                                          ctx_dict=r["context"], as_of=r["context"]["as_of"],
                                          meta={"slice": r["slice"], "subgroup": r["subgroup"], "must_not_draft": r["must_not_draft"]}) for r in ind36]
            recs_s72 = [V4P1._eval_case(clf, engine, runner, pv2, suite="sealed72", cid=r["id"], text=r["text"], gold=r["true_intent"],
                                        ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {"order_id": r["order_id"]} if r.get("order_id") else {}, "is_personal_lookup": bool(r.get("order_id"))},
                                        as_of="2026-06-15T10:00:00Z",
                                        meta={"slice": r["slice"], "subgroup": "answerable" if r["slice"] == "supported_answerable" else r["slice"], "must_not_draft": r["must_not_draft"]}) for r in sealed72]
            recs_fa24 = [V4P1._eval_case(clf, engine, runner, pv2, suite="final24", cid=r["id"], text=r["query"], gold=r.get("intent"),
                                         ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {"order_id": r["order_id"]} if r.get("order_id") else {}, "is_personal_lookup": bool(r.get("order_id"))},
                                         as_of=r.get("as_of") or "2026-06-15T10:00:00Z",
                                         meta={"is_answerable": bool(r.get("is_answerable")), "fixture_boundary": r.get("fixture_boundary")}) for r in final24]
            recs_sa156 = [V4P1._eval_case(clf, engine, runner, pv2, suite="sa156", cid=r["id"], text=r["text"], gold=r.get("true_intent"),
                                          ctx_dict=r.get("context") or {}, as_of="2026-06-15T10:00:00Z",
                                          meta={"draft_expected": bool(r["expected"].get("draft_expected")), "must_escalate": bool(r["expected"].get("must_escalate")), "expected_actions": r["expected"]["actions"]}) for r in sa156]
            recs_noise = [V4P1._eval_case(clf, engine, runner, pv2, suite="noise420", cid=r["id"], text=r["text"], gold=r["true_intent"],
                                          ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
                                          as_of="2026-06-15T10:00:00Z", meta={"kind": r.get("kind")}) for r in noise420]
            recs_oos = [V4P1._eval_case(clf, engine, runner, pv2, suite="oos80", cid=r["id"], text=r["text"], gold="ood",
                                        ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
                                        as_of="2026-06-15T10:00:00Z", meta={"category": r.get("category")}) for r in oos80]
            recs_pos175 = [V4P1._eval_case(clf, engine, runner, pv2, suite="pos175", cid=r["sample_id"], text=r["text"], gold=r["true_intent"],
                                           ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
                                           as_of="2026-06-15T10:00:00Z", meta={"source": r.get("source")}) for r in pos175]
            recs_neg51 = [V4P1._eval_case(clf, engine, runner, pv2, suite="neg51", cid=r["sample_id"], text=r["text"], gold=r.get("intent"),
                                          ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
                                          as_of="2026-06-15T10:00:00Z", meta={"category": r.get("category"), "source": r.get("source")}) for r in neg51]

            combined = recs_fresh + recs_ind36 + recs_s72 + recs_fa24 + recs_sa156 + recs_noise + recs_oos + recs_pos175 + recs_neg51
            all_preds[tag] = combined
            (OUT_DIR / f"predictions_{tag}.jsonl").write_text("\n".join(json.dumps(x) for x in combined) + "\n", encoding="utf-8")

            bitext_res = V4P1._eval_bitext(clf, pv2)
            rej = clf.rejector or {}
            summaries["models"][tag] = {
                "weights_sha256": CG.compute_file_sha256(spec["dir"] / "model.safetensors"),
                "calibration_sha256": CG.compute_file_sha256(spec["cal_manifest"]) if spec["cal_manifest"] else None,
                "temperature": float(cal["temperature"] or 1.0),
                "calibrated": bool(cal["calibrated"]),
                "rejector_enabled": bool(clf.rejector is not None),
                "rejector_threshold": rej.get("threshold") if rej else None,
                "rejector_c": rej.get("c") if rej else None,
                "historical_fresh_34": V4P1._summarize_holdout_like(recs_fresh, ("novel_ood", "mandatory_escalation")),
                "independent_36": V4P1._summarize_holdout_like(recs_ind36, ("novel_ood", "mandatory_escalation")),
                "old_sealed_72": V4P1._summarize_holdout_like(recs_s72, ("novel_ood", "mandatory_escalation_compound")),
                "final_acceptance_24": V4P1._summarize_final24(recs_fa24),
                "system_acceptance_156": V4P1._summarize_sa156(recs_sa156),
                "ml_noise_420": V4P1._summarize_noise420(recs_noise),
                "ml_oos_80": {
                    surf: [r["id"] for r in recs_oos if r[akey] == "retrieve_draft"]
                    for surf, akey in (("raw_pre", "raw_pre_action"), ("raw_post", "raw_post_action"), ("bare", "bare_action"), ("engine", "engine_action"), ("runner", "runner_action"))
                },
                "isolated_eval_pos175_neg51": V4P1._summarize_isolated(recs_pos175, recs_neg51),
                "bitext_test_6690": bitext_res,
            }

    by_tag = {tag: {(r["suite"], r["id"]): r for r in recs} for tag, recs in all_preds.items()}
    summaries["paired_diffs_v5r2_vs_v4p1"] = _paired_diffs(by_tag, "v4p1")
    summaries["paired_diffs_v5r2_vs_orig_fit2"] = _paired_diffs(by_tag, "orig_fit2")
    summaries["paired_diffs_v5r2_vs_serving"] = _paired_diffs(by_tag, "serving")

    comp_path = OUT_DIR / "suites_comparison.json"
    comp_path.write_text(json.dumps(summaries, indent=2, default=str) + "\n", encoding="utf-8")

    # Record run_manifest.json with exact file hashes
    tracked_files = [
        REPO / "artifacts/models/candidates/fit2-taxonomy-audit-v5-r2/model.safetensors",
        REPO / "artifacts/models/candidates/fit2-taxonomy-audit-v5-r2/calibration_manifest.json",
        REPO / "artifacts/models/candidates/fit2-taxonomy-audit-v5-r2/candidate_provenance_manifest.json",
        REPO / "artifacts/models/candidates/fit2-boundary-contrast-v4p1/model.safetensors",
        REPO / "artifacts/models/candidates/fit2-boundary-contrast-v4p1/calibration_manifest.json",
        REPO / "artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors",
        REPO / "artifacts/models/trained/distilbert-supportiq/model.safetensors",
        REPO / "data/knowledge/approved_kb.v2.json",
        REPO / "apps/ai_service/kb-release.json",
        REPO / "apps/core_backend/config/policies/intent_policy.v2.json",
        REPO / "data/benchmarks/final_acceptance/cases.jsonl",
        REPO / "data/benchmarks/system/v2/acceptance/cases.jsonl",
        REPO / "data/benchmarks/autoeval/v1/ml_noise.jsonl",
        REPO / "data/benchmarks/autoeval/v1/ml_oos.jsonl",
        REPO / "artifacts/evaluation/fit2_independent_gate_20261113/cases.jsonl",
        REPO / "artifacts/evaluation/sealed_holdout_20261113/sealed_holdout_cases.jsonl",
        RR_V5_INPUTS / "boundary_pos_evaluation.jsonl",
        RR_V5_INPUTS / "boundary_neg_evaluation.jsonl",
        RR_V5_INPUTS / "bitext_test_6690.jsonl",
        fresh34_path,
        OUT_DIR / "evaluate_v5r2.py",
        comp_path,
    ]
    for tag in ("serving", "orig_fit2", "v4p1", "v5_r2"):
        tracked_files.append(OUT_DIR / f"predictions_{tag}.jsonl")
    if (OUT_DIR / "gate_report_v5r2.json").exists():
        tracked_files.append(OUT_DIR / "gate_report_v5r2.json")

    manifest = {
        "branch": subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, text=True).strip(),
        "git_head": summaries["git_head"],
        "reviewed_runtime_sha": summaries["reviewed_runtime_sha"],
        "candidate_training_git_commit": json.loads(v5_spec["cand_manifest"].read_text(encoding="utf-8"))["git_commit"],
        "runtime_conditions": summaries["offline_conditions"],
        "commands": [".venv/Scripts/python.exe -B artifacts/evaluation/fit2_v5r2_independent_20261114/evaluate_v5r2.py"],
        "sha256": {str(p.relative_to(REPO)).replace("\\", "/"): CG.compute_file_sha256(p) for p in tracked_files},
    }
    (OUT_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("DONE. gate_decision =", summaries["gate_v5r2_decision"], "failures =", summaries["gate_v5r2_failures"])


if __name__ == "__main__":
    main()
