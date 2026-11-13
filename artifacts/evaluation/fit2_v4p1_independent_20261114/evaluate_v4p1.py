"""Independent Task C evaluation of frozen fit2-boundary-contrast-v4p1 vs Serving and Original Fit2.

Zero live LLM calls, zero training/calibration fits, zero threshold/gold edits.
Evaluates raw classifier (pre/post selective rejector), bare decide_route, Engine._analyse,
and PipelineRunner.run (offline _OfflineValidSpyLLM for draft eligibility only).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from apps.ai_service.engine import Engine  # noqa: E402
from apps.core_backend.commerce.adapter import CommerceAdapter  # noqa: E402
from apps.core_backend.intent.routing import (  # noqa: E402
    ESCALATED_34_INTENTS,
    STANDARD_INTENTS_46,
    SUPPORTED_12_INTENTS,
    RoutingContext,
    decide_route,
    load_policy_v2,
)
from apps.core_backend.intent.schemas import IntentPrediction  # noqa: E402
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner  # noqa: E402
from apps.core_backend.orchestration.store import PersistentStore  # noqa: E402
from apps.core_backend.retrieval.adapter import RetrievalAdapter  # noqa: E402
from pipeline.evaluation import classifier_acceptance_gate as CG  # noqa: E402
from pipeline.evaluation.autoeval import metrics as M  # noqa: E402
from scripts import run_closure_candidate_audit as A  # noqa: E402

SUPPORTED_11 = [i for i in SUPPORTED_12_INTENTS if i != "human_agent"]
RR_INPUTS = REPO / "artifacts/models/candidates/run-records-fit2-boundary-contrast-v4p1/inputs"

MODELS = [
    {
        "tag": "serving",
        "dir": REPO / "artifacts/models/trained/distilbert-supportiq",
        "cal_manifest": None,
        "cand_manifest": None,
    },
    {
        "tag": "orig_fit2",
        "dir": REPO / "artifacts/models/candidates/reconstructed-fit2-supcon-20261113",
        "cal_manifest": REPO / "artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json",
        "cand_manifest": REPO / "artifacts/models/candidates/reconstructed-fit2-supcon-20261113/candidate_provenance_manifest.json",
    },
    {
        "tag": "v4p1",
        "dir": REPO / "artifacts/models/candidates/fit2-boundary-contrast-v4p1",
        "cal_manifest": REPO / "artifacts/models/candidates/fit2-boundary-contrast-v4p1/calibration_manifest.json",
        "cand_manifest": REPO / "artifacts/models/candidates/fit2-boundary-contrast-v4p1/candidate_provenance_manifest.json",
    },
]


def _load_clf(spec: dict[str, Any]) -> tuple[CG.GateSequenceClassifier, dict[str, Any]]:
    if spec["cal_manifest"]:
        cal = CG.validate_calibration_manifest(spec["dir"], spec["cal_manifest"])
        rej = cal["rejector"] if (cal["rejector"] and cal["rejector"].get("enabled", True) is not False) else None
        clf = CG.GateSequenceClassifier(
            spec["tag"],
            spec["dir"],
            temperature=float(cal["temperature"] or 1.0),
            calibrated=bool(cal["calibrated"]),
            rejector=rej,
        )
    else:
        cal = {"temperature": 1.0, "calibrated": False, "rejector": None, "valid": False}
        clf = CG.GateSequenceClassifier(spec["tag"], spec["dir"], temperature=1.0, calibrated=False, rejector=None)
    return clf, cal


def _raw_threshold_eligible(pred: dict[str, Any], policy_v2: Any, *, apply_rejector: bool) -> tuple[str, list[str]]:
    """Classifier draft eligibility WITHOUT missing_order_id slot masking."""
    intent = pred["intent"] if apply_rejector else pred["raw_intent"]
    conf = float(pred["confidence"] if apply_rejector else pred["raw_confidence"])
    margin = float(pred["margin"] if apply_rejector else pred["raw_margin"])
    if intent == "human_agent" or intent in ESCALATED_34_INTENTS:
        return "escalate", ["outside_supported_11"]
    if intent not in SUPPORTED_12_INTENTS:
        return "manual_fallback", ["unmapped_intent"]
    c_th = policy_v2.confidence_thresholds.get(intent, policy_v2.default_confidence_threshold)
    m_th = policy_v2.margin_thresholds.get(intent, policy_v2.default_margin_threshold)
    if apply_rejector and pred.get("rejected_by_experimental_adapter"):
        return "manual_fallback", ["selective_rejected"]
    if conf < c_th or margin < m_th:
        return "clarify", ["low_conf_or_margin"]
    return "retrieve_draft", []


def _intent_pred(pred: dict[str, Any], name: str) -> IntentPrediction:
    return IntentPrediction(
        intent=pred["intent"],
        confidence=pred["confidence"],
        margin=pred["margin"],
        model_version=name,
        score_kind=pred.get("score_kind", "uncalibrated_softmax"),
        model_mode=pred.get("model_mode", "trained"),
        verified=bool(pred.get("verified", True)),
        selective_accepted=pred.get("selective_accepted"),
        selective_score=pred.get("selective_score"),
        selective_threshold=pred.get("selective_threshold"),
        rejected_by_experimental_adapter=bool(pred.get("rejected_by_experimental_adapter", False)),
        rejector_decision=pred.get("rejector_decision"),
    )


def _eval_case(
    clf: CG.GateSequenceClassifier,
    engine: Engine,
    runner: PipelineRunner,
    policy_v2: Any,
    *,
    suite: str,
    cid: str,
    text: str,
    gold: str | None,
    ctx_dict: dict[str, Any],
    as_of: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    pred = clf.predict(text, top_k_count=5)
    raw_pre_act, raw_pre_reasons = _raw_threshold_eligible(pred, policy_v2, apply_rejector=False)
    raw_post_act, raw_post_reasons = _raw_threshold_eligible(pred, policy_v2, apply_rejector=True)

    ctx = lambda: RoutingContext(
        ticket_customer_id=ctx_dict.get("ticket_customer_id", "demo-customer"),
        verified_scope=ctx_dict.get("verified_scope", "ticket:read order:read"),
        extracted_slots=ctx_dict.get("extracted_slots") or {},
        is_personal_lookup=bool(ctx_dict.get("is_personal_lookup", False)),
    )
    dec = decide_route(_intent_pred(pred, clf.name), ctx(), policy_v2)
    bare_act, _ = CG._apply_adapter_routing_guard(dec.action, pred)
    an = engine._analyse({"message": text, "as_of": as_of})[0]
    eng_act = CG._adapt_action(an["routing"]["recommendation"])
    rr = runner.run(text, ctx(), run_id=f"{clf.name}-{suite}-{cid}")

    return {
        "suite": suite,
        "id": cid,
        "text": text,
        "gold": gold,
        "meta": meta,
        "raw_intent": pred["raw_intent"],
        "raw_conf": round(float(pred["raw_confidence"]), 6),
        "raw_margin": round(float(pred["raw_margin"]), 6),
        "pred_intent": pred["intent"],
        "conf": round(float(pred["confidence"]), 6),
        "margin": round(float(pred["margin"]), 6),
        "top2": pred["top_k"][:2],
        "selective_accepted": pred.get("selective_accepted"),
        "selective_score": pred.get("rejection_score"),
        "rejected_by_adapter": bool(pred.get("rejected_by_experimental_adapter", False)),
        "raw_pre_action": raw_pre_act,
        "raw_pre_reasons": raw_pre_reasons,
        "raw_post_action": raw_post_act,
        "raw_post_reasons": raw_post_reasons,
        "bare_action": bare_act,
        "bare_reasons": dec.reason_codes,
        "engine_action": eng_act,
        "engine_intent": an["intent"]["label"],
        "engine_reasons": an["routing"]["reason_codes"],
        "runner_action": rr["action"],
        "runner_intent": rr["predicted_intent"],
        "runner_reasons": rr["reason_codes"],
    }


def _summarize_holdout_like(recs: list[dict[str, Any]], nodraft_slices: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for surf, akey, ikey in (
        ("raw_pre", "raw_pre_action", "raw_intent"),
        ("raw_post", "raw_post_action", "pred_intent"),
        ("bare", "bare_action", "pred_intent"),
        ("engine", "engine_action", "engine_intent"),
        ("runner", "runner_action", "runner_intent"),
    ):
        ans = [r for r in recs if r["meta"].get("subgroup") == "answerable"]
        leaks = [
            {"id": r["id"], "slice": r["meta"].get("slice"), "gold": r["gold"], "pred": r[ikey], "conf": r["conf"]}
            for r in recs
            if r[akey] == "retrieve_draft" and (r["meta"].get("slice") in nodraft_slices or r["meta"].get("must_not_draft"))
        ]
        ood = [r for r in recs if r["meta"].get("slice") == "novel_ood"]
        mand = [r for r in recs if r["meta"].get("slice") in ("mandatory_escalation", "mandatory_escalation_compound")]
        out[surf] = {
            "answerable_n": len(ans),
            "answerable_correct_draft": [r["id"] for r in ans if r[akey] == "retrieve_draft" and r[ikey] == r["gold"]],
            "answerable_wrong_draft": [r["id"] for r in ans if r[akey] == "retrieve_draft" and r[ikey] != r["gold"]],
            "answerable_not_drafted": [r["id"] for r in ans if r[akey] != "retrieve_draft"],
            "human_agent_escalated": [r["id"] for r in recs if r["gold"] == "human_agent" and r[akey] == "escalate"],
            "leak_count": len(leaks),
            "leaks": leaks,
            "ood_actions": dict(Counter(r[akey] for r in ood)),
            "mand_actions": dict(Counter(r[akey] for r in mand)),
            "mand_strict_escalate": sum(1 for r in mand if r[akey] == "escalate"),
            "mand_n": len(mand),
        }
    return out


def _summarize_final24(recs: list[dict[str, Any]]) -> dict[str, Any]:
    ans = [r for r in recs if r["meta"]["is_answerable"]]
    active_unans = [r for r in recs if not r["meta"]["is_answerable"] and r["meta"]["fixture_boundary"] == "active_kb"]
    inj = [r for r in recs if not r["meta"]["is_answerable"] and r["meta"]["fixture_boundary"] != "active_kb"]
    out: dict[str, Any] = {}
    for surf, akey, ikey in (
        ("raw_pre", "raw_pre_action", "raw_intent"),
        ("raw_post", "raw_post_action", "pred_intent"),
        ("engine", "engine_action", "engine_intent"),
        ("runner", "runner_action", "runner_intent"),
    ):
        out[surf] = {
            "ans12_correct": [r["id"] for r in ans if r[akey] == "retrieve_draft" and r[ikey] == r["gold"]],
            "ans12_wrong": [r["id"] for r in ans if r[akey] == "retrieve_draft" and r[ikey] != r["gold"]],
            "ans12_dropped": [r["id"] for r in ans if r[akey] != "retrieve_draft"],
            "active_unans8_leaks": [r["id"] for r in active_unans if r[akey] == "retrieve_draft"],
            "injected_uninjected4_drafted": [r["id"] for r in inj if r[akey] == "retrieve_draft"],
        }
    return out


def _summarize_sa156(recs: list[dict[str, Any]]) -> dict[str, Any]:
    d34 = [r for r in recs if r["meta"]["draft_expected"]]
    mand = [r for r in recs if r["meta"]["must_escalate"]]
    labeled = [r for r in recs if r["gold"]]
    esc34 = [r for r in labeled if r["gold"] in ESCALATED_34_INTENTS]
    out: dict[str, Any] = {
        "labeled_153_acc": M.accuracy([r["gold"] for r in labeled], [r["pred_intent"] for r in labeled]),
        "labeled_153_macro_f1": M.macro_f1([r["gold"] for r in labeled], [r["pred_intent"] for r in labeled], labels=STANDARD_INTENTS_46),
        "esc34_n": len(esc34),
        "esc34_acc": M.accuracy([r["gold"] for r in esc34], [r["pred_intent"] for r in esc34]),
        "esc34_macro_f1": M.macro_f1([r["gold"] for r in esc34], [r["pred_intent"] for r in esc34], labels=ESCALATED_34_INTENTS),
    }
    for surf, akey, ikey in (
        ("raw_pre", "raw_pre_action", "raw_intent"),
        ("raw_post", "raw_post_action", "pred_intent"),
        ("engine", "engine_action", "engine_intent"),
        ("runner", "runner_action", "runner_intent"),
    ):
        real_leaks = [
            {"id": r["id"], "gold": r["gold"], "pred": r[ikey], "conf": r["conf"]}
            for r in mand
            if r[akey] == "retrieve_draft" and r["id"] not in CG.KNOWN_UNINJECTED_ACCEPTANCE_IDS
        ]
        out[surf] = {
            "sup34_raw_draft": sum(1 for r in d34 if r[akey] == "retrieve_draft"),
            "sup34_correct_draft": sum(1 for r in d34 if r[akey] == "retrieve_draft" and r[ikey] == r["gold"]),
            "sup34_wrong_draft": [r["id"] for r in d34 if r[akey] == "retrieve_draft" and r[ikey] != r["gold"]],
            "mand63_strict_match": sum(1 for r in mand if r[akey] in r["meta"]["expected_actions"]),
            "mand63_real_leaks": real_leaks,
        }
    return out


def _summarize_noise420(recs: list[dict[str, Any]]) -> dict[str, Any]:
    y_true = [r["gold"] for r in recs]
    y_pred = [r["pred_intent"] for r in recs]
    confs = [r["conf"] for r in recs]
    corr = [r["pred_intent"] == r["gold"] for r in recs]
    out: dict[str, Any] = {
        "n": len(recs),
        "acc_12": M.accuracy(y_true, y_pred),
        "macro_f1_12": M.macro_f1(y_true, y_pred, labels=SUPPORTED_12_INTENTS),
        "ece_10bin": M.expected_calibration_error(confs, corr, n_bins=10)[0],
        "brier": CG.binary_top_label_brier(confs, corr),
    }
    for surf, akey, ikey in (
        ("raw_pre", "raw_pre_action", "raw_intent"),
        ("raw_post", "raw_post_action", "pred_intent"),
        ("bare", "bare_action", "pred_intent"),
        ("engine", "engine_action", "engine_intent"),
        ("runner", "runner_action", "runner_intent"),
    ):
        raw_d = sum(1 for r in recs if r[akey] == "retrieve_draft")
        corr_d = sum(1 for r in recs if r[akey] == "retrieve_draft" and r[ikey] == r["gold"])
        safe = sum(1 for r in recs if r[akey] != "retrieve_draft" or r[ikey] == r["gold"])
        out[surf] = {
            "raw_draft": raw_d,
            "correct_draft": corr_d,
            "wrong_draft": raw_d - corr_d,
            "safe_routing_rate": safe / len(recs),
        }
    return out


def _summarize_isolated(pos_recs: list[dict[str, Any]], neg_recs: list[dict[str, Any]]) -> dict[str, Any]:
    sup11_pos = [r for r in pos_recs if r["gold"] in SUPPORTED_11]
    hum_pos = [r for r in pos_recs if r["gold"] == "human_agent"]
    esc34_pos = [r for r in pos_recs if r["gold"] in ESCALATED_34_INTENTS]
    out: dict[str, Any] = {
        "pos175_acc_46": M.accuracy([r["gold"] for r in pos_recs], [r["pred_intent"] for r in pos_recs]),
        "pos175_macro_f1_46": M.macro_f1([r["gold"] for r in pos_recs], [r["pred_intent"] for r in pos_recs], labels=STANDARD_INTENTS_46),
        "sup11_n": len(sup11_pos),
        "hum_n": len(hum_pos),
        "esc34_n": len(esc34_pos),
        "neg_n": len(neg_recs),
        "esc34_acc": M.accuracy([r["gold"] for r in esc34_pos], [r["pred_intent"] for r in esc34_pos]),
    }
    for surf, akey, ikey in (
        ("raw_pre", "raw_pre_action", "raw_intent"),
        ("raw_post", "raw_post_action", "pred_intent"),
        ("engine", "engine_action", "engine_intent"),
        ("runner", "runner_action", "runner_intent"),
    ):
        out[surf] = {
            "sup11_raw_draft": sum(1 for r in sup11_pos if r[akey] == "retrieve_draft"),
            "sup11_correct_draft": sum(1 for r in sup11_pos if r[akey] == "retrieve_draft" and r[ikey] == r["gold"]),
            "hum_leaks": [r["id"] for r in hum_pos if r[akey] == "retrieve_draft"],
            "esc34_leaks": [{"id": r["id"], "gold": r["gold"], "pred": r[ikey], "conf": r["conf"], "text": r["text"]} for r in esc34_pos if r[akey] == "retrieve_draft"],
            "neg51_leaks": [{"id": r["id"], "cat": r["meta"].get("category"), "pred": r[ikey], "conf": r["conf"], "text": r["text"]} for r in neg_recs if r[akey] == "retrieve_draft"],
        }
    return out


def _eval_bitext(clf: CG.GateSequenceClassifier, policy_v2: Any) -> dict[str, Any]:
    rows = CG.load_jsonl(RR_INPUTS / "bitext_test_6690.jsonl")
    y_true, y_pred = [], []
    raw_pre_esc_leaks, raw_post_esc_leaks = 0, 0
    raw_pre_sup11_corr, raw_post_sup11_corr = 0, 0
    sup11_n, esc34_n = 0, 0
    for r in rows:
        gold = r["true_intent"]
        pred = clf.predict(r["text"], top_k_count=2)
        y_true.append(gold)
        y_pred.append(pred["intent"])
        pre_act, _ = _raw_threshold_eligible(pred, policy_v2, apply_rejector=False)
        post_act, _ = _raw_threshold_eligible(pred, policy_v2, apply_rejector=True)
        if gold in SUPPORTED_11:
            sup11_n += 1
            if pre_act == "retrieve_draft" and pred["raw_intent"] == gold:
                raw_pre_sup11_corr += 1
            if post_act == "retrieve_draft" and pred["intent"] == gold:
                raw_post_sup11_corr += 1
        elif gold in ESCALATED_34_INTENTS:
            esc34_n += 1
            if pre_act == "retrieve_draft":
                raw_pre_esc_leaks += 1
            if post_act == "retrieve_draft":
                raw_post_esc_leaks += 1
    return {
        "n": len(rows),
        "accuracy_46": M.accuracy(y_true, y_pred),
        "macro_f1_46": M.macro_f1(y_true, y_pred, labels=STANDARD_INTENTS_46),
        "sup11_n": sup11_n,
        "esc34_n": esc34_n,
        "raw_pre_sup11_correct_draft": raw_pre_sup11_corr,
        "raw_post_sup11_correct_draft": raw_post_sup11_corr,
        "raw_pre_esc34_unsafe_leaks": raw_pre_esc_leaks,
        "raw_post_esc34_unsafe_leaks": raw_post_esc_leaks,
    }


def main() -> None:
    root = A._bootstrap_target_repo(REPO)
    rel = json.loads((root / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    retr = RetrievalAdapter(
        kb_path=str(root / "data/knowledge/approved_kb.v2.json"),
        allowed_document_versions={(d["document_id"], str(d["version"])) for d in rel["documents"]},
    )
    comm = CommerceAdapter(data_path=str(root / "data/knowledge/mock_orders.json"))
    pol_path = root / "apps/core_backend/config/policies/intent_policy.v2.json"
    policy, pv2 = json.loads(pol_path.read_text(encoding="utf-8")), load_policy_v2(pol_path)

    # 1. Authoritative classifier acceptance gate on v4p1 vs Serving
    v4p1_dir = root / "artifacts/models/candidates/fit2-boundary-contrast-v4p1"
    srv_dir = root / "artifacts/models/trained/distilbert-supportiq"
    gate_report = CG.run_classifier_acceptance_gate(
        repo_root=root,
        candidate_name="fit2-boundary-contrast-v4p1",
        candidate_dir=v4p1_dir,
        serving_dir=srv_dir,
        candidate_manifest_path=v4p1_dir / "candidate_provenance_manifest.json",
        calibration_manifest_path=v4p1_dir / "calibration_manifest.json",
        train_split_path=RR_INPUTS / "full_train_split.jsonl",
        calibration_split_path=RR_INPUTS / "full_cal_split.jsonl",
        eval_split_path=RR_INPUTS / "boundary_pos_evaluation.jsonl",
    )
    (OUT_DIR / "gate_report_v4p1.json").write_text(json.dumps(gate_report, indent=2, default=str) + "\n", encoding="utf-8")

    # 2. Evaluate orig_fit2 on evaluate_model_on_suites under identical conditions
    orig_dir = root / "artifacts/models/candidates/reconstructed-fit2-supcon-20261113"
    orig_cal = CG.validate_calibration_manifest(orig_dir, orig_dir / "calibration_manifest.json")
    orig_suites = CG.evaluate_model_on_suites(
        "orig_fit2", orig_dir, root,
        holdout_rows=CG.load_jsonl(RR_INPUTS / "boundary_pos_evaluation.jsonl"),
        temperature=float(orig_cal["temperature"] or 1.0),
        calibrated=bool(orig_cal["calibrated"]),
        rejector=None,
    )

    # 3. Three-surface evaluation across all suites for all 3 frozen checkpoints
    fresh34 = CG.load_jsonl(OUT_DIR / "fresh_holdout_34.jsonl")
    ind36 = CG.load_jsonl(root / "artifacts/evaluation/fit2_independent_gate_20261113/cases.jsonl")
    sealed72 = CG.load_jsonl(root / "artifacts/evaluation/sealed_holdout_20261113/sealed_holdout_cases.jsonl")
    final24 = CG.load_jsonl(root / "data/benchmarks/final_acceptance/cases.jsonl")
    sa156 = CG.load_jsonl(root / "data/benchmarks/system/v2/acceptance/cases.jsonl")
    noise420 = CG.load_jsonl(root / "data/benchmarks/autoeval/v1/ml_noise.jsonl")
    oos80 = CG.load_jsonl(root / "data/benchmarks/autoeval/v1/ml_oos.jsonl")
    pos175 = CG.load_jsonl(RR_INPUTS / "boundary_pos_evaluation.jsonl")
    neg51 = CG.load_jsonl(RR_INPUTS / "boundary_neg_evaluation.jsonl")

    summaries: dict[str, Any] = {
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "offline_conditions": "0 live LLM calls; _MockNoCallLLM for Engine; _OfflineValidSpyLLM for PipelineRunner draft eligibility only.",
        "gate_v4p1_decision": gate_report["gate_decision"],
        "gate_v4p1_failures": gate_report["failure_reasons"],
        "orig_fit2_gate_suites": orig_suites,
        "models": {},
    }

    all_preds: dict[str, list[dict[str, Any]]] = {}
    with tempfile.TemporaryDirectory() as td:
        for spec in MODELS:
            tag = spec["tag"]
            clf, cal = _load_clf(spec)
            engine = Engine(clf, retr, A._MockNoCallLLM(), {"release_id": f"eval-{tag}", "model_version": tag}, policy)
            runner = PipelineRunner(
                intent_client=A._MockIntentClient(clf),
                commerce_adapter=comm,
                retrieval_adapter=retr,
                store=PersistentStore(db_path=str(Path(td) / f"{tag}.sqlite3")),
                llm_client=A._OfflineValidSpyLLM(),
                policy=pv2,
            )

            recs_fresh = [_eval_case(clf, engine, runner, pv2, suite="fresh34", cid=r["id"], text=r["text"], gold=r["true_intent"],
                                     ctx_dict=r["context"], as_of=r["context"]["as_of"],
                                     meta={"slice": r["slice"], "subgroup": r["subgroup"], "must_not_draft": r["must_not_draft"]}) for r in fresh34]
            recs_ind36 = [_eval_case(clf, engine, runner, pv2, suite="ind36", cid=r["id"], text=r["text"], gold=r["true_intent"],
                                     ctx_dict=r["context"], as_of=r["context"]["as_of"],
                                     meta={"slice": r["slice"], "subgroup": r["subgroup"], "must_not_draft": r["must_not_draft"]}) for r in ind36]
            recs_s72 = [_eval_case(clf, engine, runner, pv2, suite="sealed72", cid=r["id"], text=r["text"], gold=r["true_intent"],
                                   ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {"order_id": r["order_id"]} if r.get("order_id") else {}, "is_personal_lookup": bool(r.get("order_id"))},
                                   as_of="2026-06-15T10:00:00Z",
                                   meta={"slice": r["slice"], "subgroup": "answerable" if r["slice"] == "supported_answerable" else r["slice"], "must_not_draft": r["must_not_draft"]}) for r in sealed72]
            recs_fa24 = [_eval_case(clf, engine, runner, pv2, suite="final24", cid=r["id"], text=r["query"], gold=r.get("intent"),
                                    ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {"order_id": r["order_id"]} if r.get("order_id") else {}, "is_personal_lookup": bool(r.get("order_id"))},
                                    as_of=r.get("as_of") or "2026-06-15T10:00:00Z",
                                    meta={"is_answerable": bool(r.get("is_answerable")), "fixture_boundary": r.get("fixture_boundary")}) for r in final24]
            recs_sa156 = [_eval_case(clf, engine, runner, pv2, suite="sa156", cid=r["id"], text=r["text"], gold=r.get("true_intent"),
                                     ctx_dict=r.get("context") or {}, as_of="2026-06-15T10:00:00Z",
                                     meta={"draft_expected": bool(r["expected"].get("draft_expected")), "must_escalate": bool(r["expected"].get("must_escalate")), "expected_actions": r["expected"]["actions"]}) for r in sa156]
            recs_noise = [_eval_case(clf, engine, runner, pv2, suite="noise420", cid=r["id"], text=r["text"], gold=r["true_intent"],
                                     ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
                                     as_of="2026-06-15T10:00:00Z", meta={"kind": r.get("kind")}) for r in noise420]
            recs_oos = [_eval_case(clf, engine, runner, pv2, suite="oos80", cid=r["id"], text=r["text"], gold="ood",
                                   ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
                                   as_of="2026-06-15T10:00:00Z", meta={"category": r.get("category")}) for r in oos80]
            recs_pos175 = [_eval_case(clf, engine, runner, pv2, suite="pos175", cid=r["sample_id"], text=r["text"], gold=r["true_intent"],
                                      ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
                                      as_of="2026-06-15T10:00:00Z", meta={"source": r.get("source")}) for r in pos175]
            recs_neg51 = [_eval_case(clf, engine, runner, pv2, suite="neg51", cid=r["sample_id"], text=r["text"], gold=r.get("intent"),
                                     ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
                                     as_of="2026-06-15T10:00:00Z", meta={"category": r.get("category"), "source": r.get("source")}) for r in neg51]

            combined = recs_fresh + recs_ind36 + recs_s72 + recs_fa24 + recs_sa156 + recs_noise + recs_oos + recs_pos175 + recs_neg51
            all_preds[tag] = combined
            (OUT_DIR / f"predictions_{tag}.jsonl").write_text("\n".join(json.dumps(x) for x in combined) + "\n", encoding="utf-8")

            bitext_res = _eval_bitext(clf, pv2)
            summaries["models"][tag] = {
                "weights_sha256": CG.compute_file_sha256(spec["dir"] / "model.safetensors"),
                "temperature": float(cal["temperature"] or 1.0),
                "calibrated": bool(cal["calibrated"]),
                "rejector_enabled": bool(clf.rejector is not None),
                "fresh_holdout_34": _summarize_holdout_like(recs_fresh, ("novel_ood", "mandatory_escalation")),
                "independent_36": _summarize_holdout_like(recs_ind36, ("novel_ood", "mandatory_escalation")),
                "old_sealed_72": _summarize_holdout_like(recs_s72, ("novel_ood", "mandatory_escalation_compound")),
                "final_acceptance_24": _summarize_final24(recs_fa24),
                "system_acceptance_156": _summarize_sa156(recs_sa156),
                "ml_noise_420": _summarize_noise420(recs_noise),
                "ml_oos_80": {
                    surf: [r["id"] for r in recs_oos if r[akey] == "retrieve_draft"]
                    for surf, akey in (("raw_pre", "raw_pre_action"), ("raw_post", "raw_post_action"), ("engine", "engine_action"), ("runner", "runner_action"))
                },
                "isolated_eval_pos175_neg51": _summarize_isolated(recs_pos175, recs_neg51),
                "bitext_test_6690": bitext_res,
            }

    # 4. Paired lost/gained analysis (v4p1 vs orig_fit2 and vs serving) on key suites
    by_tag = {tag: {(r["suite"], r["id"]): r for r in recs} for tag, recs in all_preds.items()}
    diffs: dict[str, Any] = {}
    for suite_name in ("fresh34", "ind36", "final24", "sa156", "noise420", "oos80", "pos175", "neg51"):
        keys = [k for k in by_tag["v4p1"] if k[0] == suite_name]
        diffs[suite_name] = {
            "runner_changed_vs_orig": [
                {"id": cid, "gold": by_tag["v4p1"][(s, cid)]["gold"],
                 "orig_act": by_tag["orig_fit2"][(s, cid)]["runner_action"], "orig_pred": by_tag["orig_fit2"][(s, cid)]["pred_intent"],
                 "v4p1_act": by_tag["v4p1"][(s, cid)]["runner_action"], "v4p1_pred": by_tag["v4p1"][(s, cid)]["pred_intent"],
                 "v4p1_rej": by_tag["v4p1"][(s, cid)]["rejected_by_adapter"]}
                for s, cid in keys
                if by_tag["orig_fit2"][(s, cid)]["runner_action"] != by_tag["v4p1"][(s, cid)]["runner_action"]
                or by_tag["orig_fit2"][(s, cid)]["pred_intent"] != by_tag["v4p1"][(s, cid)]["pred_intent"]
            ][:80],
            "engine_changed_vs_orig": [
                {"id": cid, "gold": by_tag["v4p1"][(s, cid)]["gold"],
                 "orig_act": by_tag["orig_fit2"][(s, cid)]["engine_action"], "orig_pred": by_tag["orig_fit2"][(s, cid)]["pred_intent"],
                 "v4p1_act": by_tag["v4p1"][(s, cid)]["engine_action"], "v4p1_pred": by_tag["v4p1"][(s, cid)]["pred_intent"],
                 "v4p1_rej": by_tag["v4p1"][(s, cid)]["rejected_by_adapter"]}
                for s, cid in keys
                if by_tag["orig_fit2"][(s, cid)]["engine_action"] != by_tag["v4p1"][(s, cid)]["engine_action"]
            ][:80],
        }
    summaries["paired_diffs_vs_orig"] = diffs

    (OUT_DIR / "suites_comparison.json").write_text(json.dumps(summaries, indent=2, default=str) + "\n", encoding="utf-8")
    print("DONE. gate_decision =", gate_report["gate_decision"], "failures =", gate_report["failure_reasons"])


if __name__ == "__main__":
    main()
