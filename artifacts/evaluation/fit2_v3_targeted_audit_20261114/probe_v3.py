"""Focused paired probe: orig Fit2 (f695b1fe) vs v3 (c2e4eb37) on failures, final_24 drops, and nearest train/cal examples."""
from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any

import torch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.ai_service.engine import Engine
from apps.core_backend.commerce.adapter import CommerceAdapter
from apps.core_backend.intent.routing import RoutingContext, decide_route, load_policy_v2
from apps.core_backend.intent.schemas import IntentPrediction
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from pipeline.evaluation.classifier_acceptance_gate import (
    GateSequenceClassifier,
    _adapt_action,
    _apply_adapter_routing_guard,
    load_jsonl,
    normalize_text,
    token_set,
)
from scripts import run_closure_candidate_audit as A

CAND_ROOT = Path(r"F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates")
RR_V3 = CAND_ROOT / "run-records-fit2-boundary-contrast-v3"
OUT = Path(__file__).resolve().parent / "probes.json"


def metrics_for(clf: GateSequenceClassifier, text: str) -> dict[str, Any]:
    inputs = {k: v.to(clf.device) for k, v in clf.tokenizer(text, max_length=64, padding="max_length", truncation=True, return_tensors="pt").items()}
    with torch.inference_mode():
        logits = clf.model(**inputs).logits[0]
        raw_p = torch.softmax(logits, dim=-1)
        cal_p = torch.softmax(logits / clf.temperature, dim=-1) if clf.calibrated else raw_p
    l_np = logits.cpu()
    max_logit = float(l_np.max())
    lse = float(torch.logsumexp(l_np, dim=-1))
    top_vals, top_idx = torch.topk(cal_p.cpu(), k=5)
    probs_all = cal_p.cpu()
    ent = float(-(probs_all * torch.log(torch.clamp(probs_all, min=1e-12))).sum())
    norm_ent_top5 = float(-(top_vals / top_vals.sum() * torch.log2(torch.clamp(top_vals / top_vals.sum(), min=1e-12))).sum() / math.log2(5))
    return {
        "pred": clf.id2label[int(top_idx[0])],
        "conf": round(float(top_vals[0]), 6),
        "margin": round(float(top_vals[0] - top_vals[1]), 6),
        "max_logit": round(max_logit, 4),
        "energy": round(-lse, 4),
        "entropy_46": round(ent, 4),
        "norm_entropy_top5": round(norm_ent_top5, 4),
        "top5": [{"intent": clf.id2label[int(i)], "prob": round(float(v), 5)} for v, i in zip(top_vals, top_idx)],
    }


def probe_surfaces(clf: GateSequenceClassifier, row: dict[str, Any], engine: Engine, runner: PipelineRunner, pv2: Any) -> dict[str, Any]:
    txt = row.get("text") or row["query"]
    ctx_d = dict(row.get("context") or {})
    if row.get("order_id") and "extracted_slots" not in ctx_d:
        ctx_d["extracted_slots"] = {"order_id": row["order_id"]}
    ctx = lambda: RoutingContext(
        ticket_customer_id=ctx_d.get("ticket_customer_id", "demo-customer"),
        verified_scope=ctx_d.get("verified_scope", "ticket:read order:read"),
        extracted_slots=ctx_d.get("extracted_slots") or {},
        is_personal_lookup=bool(ctx_d.get("is_personal_lookup", False)),
    )
    p = clf.predict(txt)
    dec = decide_route(
        IntentPrediction(intent=p["intent"], confidence=p["confidence"], margin=p["margin"], model_version=clf.name,
                         rejected_by_experimental_adapter=bool(p.get("rejected_by_experimental_adapter", False))),
        ctx(), pv2,
    )
    bare, _ = _apply_adapter_routing_guard(dec.action, p)
    an = engine._analyse({"message": txt, "as_of": row.get("as_of") or "2026-06-15T10:00:00Z"})[0]
    rr = runner.run(txt, ctx(), run_id=f"{clf.name}-{row['id']}")
    return {
        "metrics": metrics_for(clf, txt),
        "bare": {"action": bare, "reasons": dec.reason_codes},
        "engine": {"action": _adapt_action(an["routing"]["recommendation"]), "reasons": an["routing"]["reason_codes"]},
        "runner": {"action": rr["action"], "reasons": rr["reason_codes"]},
    }


def nearest_examples(query: str, pool: list[dict[str, Any]], k: int = 4) -> list[dict[str, Any]]:
    qt = token_set(query)
    scored = []
    for r in pool:
        txt = r.get("text") or r.get("instruction") or ""
        rt = token_set(txt)
        j = len(qt & rt) / len(qt | rt) if (qt and rt) else 0.0
        scored.append((j, r.get("intent") or r.get("true_intent"), r.get("sample_id") or r.get("id"), r.get("source"), txt))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"jaccard": round(j, 3), "intent": i, "id": sid, "source": src, "text": txt} for j, i, sid, src, txt in scored[:k]]


def main() -> None:
    rel = json.loads((REPO / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    allowed = {(d["document_id"], str(d["version"])) for d in rel["documents"]}
    pol_path = REPO / "apps/core_backend/config/policies/intent_policy.v2.json"
    policy, pv2 = json.loads(pol_path.read_text(encoding="utf-8")), load_policy_v2(pol_path)
    retr = RetrievalAdapter(kb_path=str(REPO / "data/knowledge/approved_kb.v2.json"), allowed_document_versions=allowed)
    comm = CommerceAdapter(data_path=str(REPO / "data/knowledge/mock_orders.json"))

    sa = {r["id"]: r for r in load_jsonl(REPO / "data/benchmarks/system/v2/acceptance/cases.jsonl")}
    oos = {r["id"]: r for r in load_jsonl(REPO / "data/benchmarks/autoeval/v1/ml_oos.jsonl")}
    fa = load_jsonl(REPO / "data/benchmarks/final_acceptance/cases.jsonl")
    ev_pos = {r["sample_id"]: r for r in load_jsonl(RR_V3 / "inputs/boundary_pos_evaluation.jsonl")}

    targets = [
        {"id": "oos-other_domain-16", "true_intent": oos["oos-other_domain-16"].get("true_intent") or oos["oos-other_domain-16"].get("category") or "out_of_scope", "text": oos["oos-other_domain-16"]["text"], "suite": "ml_oos"},
        {**sa["uns-track_delivery-01"], "suite": "system_acceptance"},
        {**sa["uns-order_history-01"], "suite": "system_acceptance"},
        {**sa["uns-return_product_in_store-01"], "suite": "system_acceptance"},
        {"id": "contrast_auth_pos_eval_136", "true_intent": ev_pos["contrast_auth_pos_eval_136"]["intent"], "text": ev_pos["contrast_auth_pos_eval_136"]["text"], "suite": "v3_eval_pos"},
    ] + [{**r, "suite": "final_acceptance_ans12"} for r in fa[:12]]

    clfs = {
        "orig_f695": GateSequenceClassifier("orig-f695b1fe", CAND_ROOT / "reconstructed-fit2-supcon-20261113", temperature=1.0, calibrated=True),
        "v3_c2e4": GateSequenceClassifier("v3-c2e4eb37", CAND_ROOT / "fit2-boundary-contrast-v3", temperature=1.0, calibrated=True),
    }

    probe_results: dict[str, Any] = {t["id"]: {"suite": t["suite"], "true_intent": t.get("true_intent") or t.get("expected_intent") or t.get("intent"), "text": t.get("text") or t["query"]} for t in targets}
    with tempfile.TemporaryDirectory() as td:
        for tag, clf in clfs.items():
            eng = Engine(clf, retr, A._MockNoCallLLM(), {"release_id": tag, "model_version": tag}, policy)
            run = PipelineRunner(intent_client=A._MockIntentClient(clf), commerce_adapter=comm, retrieval_adapter=retr,
                                 store=PersistentStore(db_path=str(Path(td) / f"{tag}.sqlite3")), llm_client=A._OfflineValidSpyLLM(), policy=pv2)
            for t in targets:
                probe_results[t["id"]][tag] = probe_surfaces(clf, t, eng, run, pv2)

    trn_pos = load_jsonl(RR_V3 / "inputs/full_train_split.jsonl")
    cal_pos = load_jsonl(RR_V3 / "inputs/full_cal_split.jsonl")
    neg_trn = load_jsonl(RR_V3 / "inputs/boundary_neg_train.jsonl")
    neg_cal = load_jsonl(RR_V3 / "inputs/boundary_neg_calibration.jsonl")

    nearest = {}
    for tid in ("oos-other_domain-16", "uns-track_delivery-01", "contrast_auth_pos_eval_136", "uns-order_history-01", "uns-return_product_in_store-01"):
        txt = probe_results[tid]["text"]
        nearest[tid] = {
            "nearest_train_all": nearest_examples(txt, trn_pos, 4),
            "nearest_cal_all": nearest_examples(txt, cal_pos, 4),
            "nearest_neg_train": nearest_examples(txt, neg_trn, 4),
            "nearest_neg_cal": nearest_examples(txt, neg_cal, 3),
        }

    # Check Bitext + boundary_pos_train/cal counts for track_delivery / return_product_in_store / order_history / ood telecom
    from collections import Counter
    trn_src_by_intent = {}
    for intent in ("track_delivery", "track_order", "return_product_in_store", "return_policy", "order_history", "delivery_issue", "delivery_time", "payment_issue", "request_refund"):
        rows = [r for r in trn_pos if r.get("intent") == intent]
        trn_src_by_intent[intent] = dict(Counter(r.get("source") for r in rows))

    # Semantic cross-split check on negative vs positive train/cal for delivery/tracking/billing/telecom keywords
    neg_cats = dict(Counter(f"{r.get('intent')}:{r.get('category')}" for r in neg_trn))

    OUT.write_text(json.dumps({
        "probes": probe_results,
        "nearest_examples": nearest,
        "train_sources_selected_intents": trn_src_by_intent,
        "neg_train_categories": neg_cats,
        "neg_train_samples": [{"id": r.get("sample_id"), "intent": r.get("intent"), "cat": r.get("category"), "text": r.get("text")} for r in neg_trn],
    }, indent=2), encoding="utf-8")
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
