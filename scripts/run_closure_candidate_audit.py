"""Independent closure audit for locked Fit2 (f695b1fe) vs Old Closure (95a940b6) vs Serving (dc7af8cf).

Zero live LLM provider calls. Reuses pipeline.evaluation.classifier_acceptance_gate and
integrated root apps/ (Engine + PipelineRunner) to separate bare intent-stage eligibility
from guarded product runtime exposure.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EV_ROOT = Path(__file__).resolve().parents[1]


def _module_is_from_root(mod: Any, resolved: Path) -> bool:
    """Return True only if a loaded module or namespace package resolves strictly inside resolved."""
    mod_file = getattr(mod, "__file__", None)
    if mod_file:
        return Path(mod_file).resolve().is_relative_to(resolved)
    locs = getattr(mod, "__path__", None)
    if locs is None:
        spec = getattr(mod, "__spec__", None)
        locs = getattr(spec, "submodule_search_locations", None)
    try:
        loc_list = list(locs) if locs is not None else []
    except KeyError:
        return False
    return bool(loc_list) and all(Path(loc).resolve().is_relative_to(resolved) for loc in loc_list)


def _bootstrap_target_repo(main_root: Path) -> Path:
    """Ensure target main_root is first on sys.path and evict stale apps/pipeline modules from other roots."""
    resolved = main_root.resolve()
    candidates = [
        mod_name
        for mod_name in list(sys.modules)
        if mod_name == "apps" or mod_name.startswith("apps.") or mod_name == "pipeline" or mod_name.startswith("pipeline.")
    ]
    to_evict = [
        mod_name
        for mod_name in candidates
        if not _module_is_from_root(sys.modules[mod_name], resolved)
    ]
    for mod_name in sorted(to_evict, key=lambda name: name.count("."), reverse=True):
        sys.modules.pop(mod_name, None)
    sys.path = [p for p in sys.path if p != str(resolved)]
    sys.path.insert(0, str(resolved))
    importlib.invalidate_caches()
    return resolved


def resolve_audit_paths(main_root: Path, candidate_root: Path, output_dir: Path | None = None) -> dict[str, Path]:
    """Resolve expected artifact, KB, policy, and dataset paths beneath main_root and candidate_root."""
    m_root = main_root.resolve()
    c_root = candidate_root.resolve()
    return {
        "main_root": m_root,
        "candidate_root": c_root,
        "serving_dir": m_root / "artifacts/models/trained/distilbert-supportiq",
        "old_dir": c_root / "artifacts/evaluation/task_a_closure_20261113/candidate_model",
        "fit2_dir": c_root / "artifacts/evaluation/task_a_boundary_20261113/candidate_model_fit2",
        "b_ds": c_root / "artifacts/evaluation/task_a_boundary_20261113/datasets",
        "sealed_path": m_root / "artifacts/evaluation/sealed_holdout_20261113/sealed_holdout_cases.jsonl",
        "sa_cases_path": m_root / "data/benchmarks/system/v2/acceptance/cases.jsonl",
        "release_path": m_root / "apps/ai_service/kb-release.json",
        "policy_path": m_root / "apps/core_backend/config/policies/intent_policy.v2.json",
        "kb_path": m_root / "data/knowledge/approved_kb.v2.json",
        "commerce_path": m_root / "data/knowledge/mock_orders.json",
        "out_dir": output_dir.resolve() if output_dir is not None else (m_root / "artifacts/evaluation/closure_candidate_audit_20261113"),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Independent offline closure audit for Fit2 vs Old Closure vs Serving.",
    )
    parser.add_argument(
        "--main-root",
        type=Path,
        default=EV_ROOT,
        help="Repository root hosting target apps/, serving weights, KB, and sealed holdout (defaults to script repository).",
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        required=True,
        help="Workspace root hosting task_a_closure_20261113 and task_a_boundary_20261113 under artifacts/evaluation.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory for audit report JSON/JSONL outputs (defaults to <main-root>/artifacts/evaluation/closure_candidate_audit_20261113).",
    )
    return parser.parse_args(argv)


class _OfflineValidSpyLLM:
    configured = True

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate(self, message: str, intent: str, evidence: list[dict[str, Any]], business_context: dict[str, Any] | None = None) -> dict[str, Any]:
        from apps.core_backend.llm.gemini import prepare_llm_input

        self.calls.append({"message": message, "intent": intent})
        snapshot = prepare_llm_input(message, intent, evidence, business_context)
        sid = snapshot["sources"][0]["source_id"] if snapshot.get("sources") else "S1"
        return {
            "answerable": True,
            "body": f"Grounded policy guidance [{sid}].",
            "citations": [sid],
            "provider": "spy_offline",
            "model": "none",
            "usage": {"promptTokenCount": 1, "candidatesTokenCount": 1},
            "latency_seconds": 0.001,
            "input_snapshot": snapshot,
        }


class _MockIntentClient:
    def __init__(self, clf: Any) -> None:
        self.clf = clf

    def classify_intent(self, text: str, top_k_count: int = 5, request_id: str | None = None) -> Any:
        from apps.core_backend.intent.schemas import IntentPrediction

        p = self.clf.predict(text, top_k_count=top_k_count)
        return IntentPrediction(
            intent=p["intent"],
            confidence=p["confidence"],
            margin=p["margin"],
            top_k=p.get("top_k", []),
            alternatives=p.get("alternatives", []),
            is_in_scope=p.get("is_in_scope", False),
            source=p.get("source", "model"),
            model_version=self.clf.name,
            score_kind=p.get("score_kind", "uncalibrated_softmax"),
            model_mode=p.get("model_mode", "trained"),
            verified=bool(p.get("verified", True)),
            temperature=p.get("temperature"),
            selective_accepted=p.get("selective_accepted"),
            selective_score=p.get("selective_score"),
            selective_threshold=p.get("selective_threshold"),
            rejected_by_experimental_adapter=bool(p.get("rejected_by_experimental_adapter", False)),
            rejector_decision=p.get("rejector_decision"),
        )


def _check_zero_sealed_overlap(sealed_rows: list[dict[str, Any]], dataset_paths: dict[str, Path]) -> dict[str, Any]:
    from pipeline.evaluation.classifier_acceptance_gate import load_jsonl, normalize_text, token_set

    s_norms = {normalize_text(r["text"]): r["id"] for r in sealed_rows}
    s_toks = [(r["id"], token_set(r["text"])) for r in sealed_rows]
    exact_hits: list[dict[str, str]] = []
    jaccard_hits: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for label, path in dataset_paths.items():
        rows = load_jsonl(path)
        counts[label] = len(rows)
        for idx, row in enumerate(rows):
            txt = str(row.get("text") or row.get("query") or row.get("instruction") or "")
            rn = normalize_text(txt)
            if rn in s_norms:
                exact_hits.append({"sealed_id": s_norms[rn], "dataset": label, "row_idx": str(idx)})
            rt = token_set(txt)
            for sid, st in s_toks:
                if rt and st:
                    j = len(rt & st) / len(rt | st)
                    if j >= 0.70:
                        jaccard_hits.append({"sealed_id": sid, "dataset": label, "jaccard": round(j, 4), "text": txt})
    return {"dataset_counts": counts, "exact_hits": exact_hits, "jaccard_ge_0_70_hits": jaccard_hits, "clean": not exact_hits and not jaccard_hits}


def _eval_three_surfaces(
    *,
    clf: Any,
    rows: list[dict[str, Any]],
    retriever: Any,
    commerce: Any,
    policy: dict[str, Any],
    policy_v2: Any,
    tmp_store: Path,
) -> dict[str, Any]:
    from apps.ai_service.engine import Engine
    from apps.core_backend.intent.routing import RoutingContext
    from apps.core_backend.intent.schemas import IntentPrediction
    from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
    from apps.core_backend.orchestration.store import PersistentStore
    from pipeline.evaluation.classifier_acceptance_gate import _adapt_action, _apply_adapter_routing_guard, decide_route

    engine = Engine(clf, retriever, _MockNoCallLLM(), {"release_id": f"audit-{clf.name}", "model_version": clf.name}, policy)
    spy_llm = _OfflineValidSpyLLM()
    runner = PipelineRunner(
        intent_client=_MockIntentClient(clf),
        commerce_adapter=commerce,
        retrieval_adapter=retriever,
        store=PersistentStore(db_path=str(tmp_store / "orch.sqlite3")),
        llm_client=spy_llm,
        policy=policy_v2,
    )

    per_slice: dict[str, Any] = {}
    case_records: list[dict[str, Any]] = []
    for sl in ("supported_answerable", "novel_ood", "mandatory_escalation_compound"):
        sub = [r for r in rows if r["slice"] == sl]
        counts = {
            "n": len(sub),
            "bare": {"draft": 0, "escalate": 0, "manual_fallback": 0, "expected_match": 0, "intent_match": 0, "correct_intent_draft": 0, "unsafe_draft_leaks": []},
            "engine": {"draft": 0, "escalate": 0, "abstain": 0, "expected_match": 0, "unsafe_draft_leaks": []},
            "runner": {"draft": 0, "escalate": 0, "manual_fallback": 0, "clarify": 0, "expected_match": 0, "unsafe_draft_leaks": []},
        }
        for r in sub:
            txt = r["text"]
            pred = clf.predict(txt)
            dec = decide_route(
                IntentPrediction(
                    intent=pred["intent"], confidence=pred["confidence"], margin=pred["margin"],
                    model_version=clf.name, rejected_by_experimental_adapter=bool(pred.get("rejected_by_experimental_adapter", False)),
                ),
                RoutingContext(ticket_customer_id="audit-eval", extracted_slots={}, is_personal_lookup=False),
                policy_v2,
            )
            bare_act, _ = _apply_adapter_routing_guard(dec.action, pred)
            counts["bare"]["draft" if bare_act == "retrieve_draft" else ("escalate" if bare_act == "escalate" else "manual_fallback")] += 1
            if bare_act in r["expected_actions"]:
                counts["bare"]["expected_match"] += 1
            if pred["intent"] == r["true_intent"]:
                counts["bare"]["intent_match"] += 1
                if bare_act == "retrieve_draft":
                    counts["bare"]["correct_intent_draft"] += 1
            if bare_act == "retrieve_draft" and r["must_not_draft"]:
                counts["bare"]["unsafe_draft_leaks"].append({"id": r["id"], "pred_intent": pred["intent"], "conf": round(pred["confidence"], 4)})

            eng_an = engine._analyse({"message": txt, "as_of": "2026-06-15T10:00:00Z"})[0]
            eng_act = _adapt_action(eng_an["routing"]["recommendation"])
            counts["engine"]["draft" if eng_act == "retrieve_draft" else ("escalate" if eng_act == "escalate" else "abstain")] += 1
            if eng_act in r["expected_actions"]:
                counts["engine"]["expected_match"] += 1
            if eng_act == "retrieve_draft" and r["must_not_draft"]:
                counts["engine"]["unsafe_draft_leaks"].append({"id": r["id"], "pred_intent": eng_an["intent"]["label"], "reasons": eng_an["routing"]["reason_codes"]})

            run_res = runner.run(txt, RoutingContext(ticket_customer_id="audit-eval", extracted_slots={}, is_personal_lookup=False), run_id=f"{clf.name}-{r['id']}")
            r_act = run_res["action"]
            r_bucket = "draft" if r_act == "retrieve_draft" else (r_act if r_act in ("escalate", "clarify") else "manual_fallback")
            counts["runner"][r_bucket] += 1
            if r_act in r["expected_actions"]:
                counts["runner"]["expected_match"] += 1
            if r_act == "retrieve_draft" and r["must_not_draft"]:
                counts["runner"]["unsafe_draft_leaks"].append({"id": r["id"], "pred_intent": run_res["predicted_intent"], "reasons": run_res["reason_codes"]})

            case_records.append({
                "model": clf.name, "id": r["id"], "slice": sl, "true_intent": r["true_intent"],
                "pred_intent": pred["intent"], "conf": round(pred["confidence"], 5),
                "bare_act": bare_act, "engine_act": eng_act, "engine_reasons": eng_an["routing"]["reason_codes"],
                "runner_act": r_act, "runner_reasons": run_res["reason_codes"],
            })
        per_slice[sl] = counts
    return {"per_slice": per_slice, "case_records": case_records}


class _MockNoCallLLM:
    def generate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("LLM must not be called during closure audit")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    main_root = _bootstrap_target_repo(args.main_root)
    paths = resolve_audit_paths(main_root, args.candidate_root, args.output_dir)

    import apps
    from apps.ai_service.engine import Engine
    from apps.core_backend.commerce.adapter import CommerceAdapter
    from apps.core_backend.intent.routing import RoutingContext, load_policy_v2
    from apps.core_backend.intent.schemas import IntentPrediction
    from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
    from apps.core_backend.orchestration.store import PersistentStore
    from apps.core_backend.retrieval.adapter import RetrievalAdapter
    from pipeline.evaluation.classifier_acceptance_gate import (
        GateSequenceClassifier,
        _apply_adapter_routing_guard,
        compute_file_sha256,
        decide_route,
        evaluate_model_on_suites,
        load_jsonl,
        run_classifier_acceptance_gate,
        validate_calibration_manifest,
    )

    out_dir = paths["out_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    serving_dir = paths["serving_dir"]
    old_dir = paths["old_dir"]
    fit2_dir = paths["fit2_dir"]
    b_ds = paths["b_ds"]

    sealed_path = paths["sealed_path"]
    sealed_rows = load_jsonl(sealed_path)
    sealed_overlap = _check_zero_sealed_overlap(
        sealed_rows,
        {
            "fit2_full_train": b_ds / "full_train_split.jsonl",
            "fit2_full_cal": b_ds / "full_cal_split.jsonl",
            "fit2_pos_eval": b_ds / "boundary_pos_evaluation.jsonl",
            "fit2_neg_train": b_ds / "boundary_neg_train.jsonl",
            "fit2_neg_cal": b_ds / "boundary_neg_calibration.jsonl",
            "fit2_neg_eval": b_ds / "boundary_neg_evaluation.jsonl",
        },
    )

    fit2_gate = run_classifier_acceptance_gate(
        repo_root=main_root,
        candidate_name="fit2-supcon-energy-boundary-v1",
        candidate_dir=fit2_dir,
        serving_dir=serving_dir,
        candidate_manifest_path=fit2_dir / "candidate_provenance_manifest.json",
        calibration_manifest_path=fit2_dir / "calibration_manifest.json",
        train_split_path=b_ds / "full_train_split.jsonl",
        calibration_split_path=b_ds / "full_cal_split.jsonl",
        eval_split_path=b_ds / "boundary_pos_evaluation.jsonl",
        verify_parity=True,
    )
    (out_dir / "gate_report_fit2.json").write_text(json.dumps(fit2_gate, indent=2) + "\n", encoding="utf-8")

    old_cal = validate_calibration_manifest(old_dir, old_dir / "calibration_manifest.json")
    fit2_cal = validate_calibration_manifest(fit2_dir, fit2_dir / "calibration_manifest.json")
    old_suites = evaluate_model_on_suites(
        "old-closure-c6cae7a", old_dir, main_root,
        temperature=float(old_cal["temperature"] or 1.0), calibrated=bool(old_cal["calibrated"]), rejector=old_cal["rejector"],
    )

    release = json.loads(paths["release_path"].read_text(encoding="utf-8"))
    allowed = {(d["document_id"], str(d["version"])) for d in release["documents"]}
    policy_path = paths["policy_path"]
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy_v2 = load_policy_v2(policy_path)
    retriever = RetrievalAdapter(kb_path=str(paths["kb_path"]), allowed_document_versions=allowed)
    commerce = CommerceAdapter(data_path=str(paths["commerce_path"]))

    sa_map = {r["id"]: r for r in load_jsonl(paths["sa_cases_path"])}
    leak_targets = [sa_map["uns-order_history-01"], sa_map["uns-return_product_in_store-01"], sa_map["una-product_information-01"]]

    clfs = [
        GateSequenceClassifier("serving-dc7af8cf", serving_dir, calibrated=False),
        GateSequenceClassifier("old-closure-95a940b6", old_dir, temperature=float(old_cal["temperature"] or 1.0), calibrated=bool(old_cal["calibrated"]), rejector=old_cal["rejector"]),
        GateSequenceClassifier("fit2-f695b1fe", fit2_dir, temperature=float(fit2_cal["temperature"] or 1.0), calibrated=bool(fit2_cal["calibrated"]), rejector=fit2_cal["rejector"]),
    ]

    sealed_results: dict[str, Any] = {}
    leak_exposure: dict[str, list[dict[str, Any]]] = {}
    all_case_records: list[dict[str, Any]] = []
    for clf in clfs:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            res = _eval_three_surfaces(
                clf=clf, rows=sealed_rows, retriever=retriever, commerce=commerce,
                policy=policy, policy_v2=policy_v2, tmp_store=td_path / "sealed",
            )
            sealed_results[clf.name] = res["per_slice"]
            all_case_records.extend(res["case_records"])

            engine = Engine(clf, retriever, _MockNoCallLLM(), {"release_id": f"leak-{clf.name}", "model_version": clf.name}, policy)
            runner = PipelineRunner(
                intent_client=_MockIntentClient(clf),
                commerce_adapter=commerce,
                retrieval_adapter=retriever,
                store=PersistentStore(db_path=str(td_path / "leak.sqlite3")),
                llm_client=_OfflineValidSpyLLM(),
                policy=policy_v2,
            )
            rows_out = []
            for lc in leak_targets:
                pred = clf.predict(lc["text"])
                dec = decide_route(
                    IntentPrediction(intent=pred["intent"], confidence=pred["confidence"], margin=pred["margin"], model_version=clf.name, rejected_by_experimental_adapter=bool(pred.get("rejected_by_experimental_adapter", False))),
                    RoutingContext(ticket_customer_id="demo-customer", extracted_slots={}, is_personal_lookup=False),
                    policy_v2,
                )
                bare_act, _ = _apply_adapter_routing_guard(dec.action, pred)
                eng_an = engine._analyse({"message": lc["text"], "as_of": "2026-06-15T10:00:00Z"})[0]
                run_res = runner.run(lc["text"], RoutingContext(ticket_customer_id="demo-customer", extracted_slots={}, is_personal_lookup=False), run_id=f"leak-{clf.name}-{lc['id']}")
                rows_out.append({
                    "case_id": lc["id"], "true_intent": lc["true_intent"],
                    "pred_intent": pred["intent"], "conf": round(pred["confidence"], 5),
                    "bare_decide_route_action": bare_act, "bare_reasons": dec.reason_codes,
                    "engine_recommendation": eng_an["routing"]["recommendation"], "engine_reasons": eng_an["routing"]["reason_codes"],
                    "pipeline_runner_action": run_res["action"], "pipeline_runner_reasons": run_res["reason_codes"],
                })
            leak_exposure[clf.name] = rows_out

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "apps_loaded_from": str(Path(apps.__file__).resolve()),
        "serving_weights_sha256": compute_file_sha256(serving_dir / "model.safetensors"),
        "old_closure_weights_sha256": compute_file_sha256(old_dir / "model.safetensors"),
        "fit2_weights_sha256": compute_file_sha256(fit2_dir / "model.safetensors"),
        "sealed_holdout_sha256": compute_file_sha256(sealed_path),
        "sealed_overlap_against_fit2_splits": sealed_overlap,
        "fit2_gate_decision": fit2_gate["gate_decision"],
        "fit2_gate_failure_reasons": fit2_gate["failure_reasons"],
        "fit2_runtime_parity_passed": fit2_gate["runtime_parity_audit"]["passed"],
        "fit2_split_isolation_passed": fit2_gate["split_isolation_and_contamination"]["passed"],
        "suites_comparison": {
            "serving_dc7af8cf": fit2_gate["serving_baseline_evaluation"],
            "old_closure_95a940b6": old_suites,
            "fit2_f695b1fe": fit2_gate.get("candidate_calibrated_evaluation") or fit2_gate["candidate_evaluation"],
        },
        "sealed_72_holdout_comparison": sealed_results,
        "mandatory_leak_product_exposure": leak_exposure,
        "live_provider_calls": 0,
    }
    comp_path = out_dir / "three_model_comparison.json"
    comp_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    pred_path = out_dir / "sealed_holdout_predictions.jsonl"
    pred_path.write_text("\n".join(json.dumps(r) for r in all_case_records) + "\n", encoding="utf-8")
    hashes = {
        "gate_report_fit2.json": compute_file_sha256(out_dir / "gate_report_fit2.json"),
        "three_model_comparison.json": compute_file_sha256(comp_path),
        "sealed_holdout_predictions.jsonl": compute_file_sha256(pred_path),
    }
    (out_dir / "report_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print("DONE! Fit2 Gate:", fit2_gate["gate_decision"], fit2_gate["failure_reasons"])
    print("Sealed overlap clean:", sealed_overlap["clean"])
    print("Sealed 72 summary:", json.dumps(sealed_results, indent=2))
    print("Leak exposure:", json.dumps(leak_exposure, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
