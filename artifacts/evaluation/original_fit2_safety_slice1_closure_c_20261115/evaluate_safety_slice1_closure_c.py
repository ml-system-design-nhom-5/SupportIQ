"""Worker C Bounded Slice 1 CLOSURE Evaluation after Worker B PASS (e8856394) on Worker A Fix (a316377a).

Strictly read-only against source, models, KB, policy, runtime env, and frozen gates:
- Zero training, optimizer, calibrator, rejector, or paid/live LLM calls (_MockNoCallLLM / _OfflineValidSpyLLM / _PreLLMSpy).
- Zero new unbounded gates authored; runs:
  1. Invariant SHA-256 verification (f695b1fe, 782c88db, dc7af8cf, approved_kb, kb-release, intent_policy,
     training_cap 2/2 STOP, adapter.py 3bd797da unchanged since 03eb1231, safety.py a316377a, 12 suites, 43-case gate).
  2. Frozen 43-case unseen gate (27 in 20bb9315 + 16 in c232bd6e) live on HEAD Engine & PipelineRunner
     under natural Orig Fit2 AND isolated gold-intent override (+ gold KB doc scope verification, preserving
     s1ng-sup-03 unmodified <0.55 retrieval distinction with scope_requires_review=False).
  3. All 24 documented Worker B FAIL-OPEN regressions (6+1 original 9b4be434, 9 from 04e63ba3, 8 from c1c2a766)
     live on Engine & PipelineRunner against BOTH real RetrievalAdapter AND injected POL-RET docs with
     _PreLLMSpy(configured=True) asserting 0 external LLM invocations.
  4. All 1,406 rows across all 12 prior frozen suites + bitext6690 sample_031639 live on HEAD Engine,
     PipelineRunner, and post-privacy surfaces, paired vs pre-Slice-1 baseline (94a8f4fc / 1bf9e6af) and
     prior Slice 1 baseline (1325a240). Full 6,690-row bitext DistilBERT classification is carried from
     3bbbe5f (raw weights, calibration, KB, and adapter.py unchanged), with sample_031639 executed live.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent
PRIOR_S1_DIR = REPO / "artifacts/evaluation/original_fit2_safety_slice1_c_20261115"
PRIOR_NEG_DIR = REPO / "artifacts/evaluation/original_fit2_safety_slice1_negation_c_20261115"
PROTO_PATH = REPO / "artifacts/evaluation/fit2_next_protocol_c_20261114/protocol_manifest.json"

GATE27_PATH = PRIOR_S1_DIR / "unseen_slice1_scope_gate_cases.jsonl"
GATE16_PATH = PRIOR_NEG_DIR / "unseen_slice1_negation_gate_cases.jsonl"

sys.path.insert(0, str(REPO))

_neg_spec = importlib.util.spec_from_file_location("neg_eval_c", PRIOR_NEG_DIR / "evaluate_safety_slice1_negation_c.py")
assert _neg_spec and _neg_spec.loader
NEG_C = importlib.util.module_from_spec(_neg_spec)
_neg_spec.loader.exec_module(NEG_C)

S1 = NEG_C.S1
V4P1 = NEG_C.V4P1
PRIOR_C = NEG_C.PRIOR_C
CG = NEG_C.CG
A = NEG_C.A

from apps.ai_service.engine import Engine  # noqa: E402
from apps.backend.tickets.jobs import AI_REASONS  # noqa: E402
from apps.core_backend.commerce.adapter import CommerceAdapter  # noqa: E402
from apps.core_backend.intent.routing import load_policy_v2  # noqa: E402
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner  # noqa: E402
from apps.core_backend.orchestration.store import PersistentStore  # noqa: E402
from apps.core_backend.retrieval.adapter import RetrievalAdapter  # noqa: E402
from apps.core_backend.safety import policy_scope_requires_review  # noqa: E402
from apps.ml_inference.app import ModelContainer  # noqa: E402

SAFETY_A_PIN_SHA = "45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000"
AS_OF_2026 = "2026-11-15T10:00:00Z"

# Documented Worker B end-to-end FAIL-OPEN regressions (verbatim from tests/unit/test_safety_slice1_gap1_a.py & B audits)
B_REGRESSIONS: list[dict[str, str]] = [
    # Original 6+1 Worker B repros (9b4be434)
    {"id": "b-orig-01", "batch": "orig_9b4be434_6plus1", "text": "I can't return this item except at a physical store"},
    {"id": "b-orig-02", "batch": "orig_9b4be434_6plus1", "text": "I cannot return the opened TV without stopping by a physical store"},
    {"id": "b-orig-03", "batch": "orig_9b4be434_6plus1", "text": "I won't return my item instead head to a retail shop"},
    {"id": "b-orig-04", "batch": "orig_9b4be434_6plus1", "text": "I cannot ship my parcel home deliver it at a physical shop"},
    {"id": "b-orig-05", "batch": "orig_9b4be434_6plus1", "text": "Without bringing the box to a physical store, can I still return my headphones?"},
    {"id": "b-orig-06", "batch": "orig_9b4be434_6plus1", "text": "I asked, 'can I walk into a physical shop to return this?'"},
    {"id": "b-orig-07", "batch": "orig_9b4be434_6plus1", "text": "Could support advise, 'bring it to a physical shop', and can I do that now?"},
    # Worker B 9 waiver-review FAIL-OPEN leaks (04e63ba3)
    {"id": "b-w9-01", "batch": "waiver_04e63ba3_9", "text": "I won't return this excluding at a physical store, can I use a courier?"},
    {"id": "b-w9-02", "batch": "waiver_04e63ba3_9", "text": "I can't return it besides at a physical store, or can I use a courier?"},
    {"id": "b-w9-03", "batch": "waiver_04e63ba3_9", "text": "I won't return my item save at a physical store, or can I book a courier?"},
    {"id": "b-w9-04", "batch": "waiver_04e63ba3_9", "text": "My friend said 'walk into a physical store to return it' — is that an option, or courier pickup?"},
    {"id": "b-w9-05", "batch": "waiver_04e63ba3_9", "text": "Someone told me 'return it in-store' — does that work, or should I use the app?"},
    {"id": "b-w9-06", "batch": "waiver_04e63ba3_9", "text": "A friend said 'bring it to a physical store', should I go ahead with that or use courier?"},
    {"id": "b-w9-07", "batch": "waiver_04e63ba3_9", "text": "Can I use the option 'return at a physical store' to send back my order?"},
    {"id": "b-w9-08", "batch": "waiver_04e63ba3_9", "text": "Where do I click the button 'drop off at a physical store' so I can return this?"},
    {"id": "b-w9-09", "batch": "waiver_04e63ba3_9", "text": "I am not using the app, and without visiting a physical store, can I still return this?"},
    # Worker B 8 quote-structure FAIL-OPEN leaks (c1c2a766)
    {"id": "b-q8-01", "batch": "quote_c1c2a766_8", "text": "My friend joked 'walk into a physical store to return it', and I want to do that along with the app."},
    {"id": "b-q8-02", "batch": "quote_c1c2a766_8", "text": "My friend joked 'walk into a physical store to return it' — please tell me I can do that before booking a courier."},
    {"id": "b-q8-03", "batch": "quote_c1c2a766_8", "text": "My friend joked 'walk into a physical store to return it' and I plan to go there instead of waiting for a courier."},
    {"id": "b-q8-04", "batch": "quote_c1c2a766_8", "text": "My friend joked 'walk into a physical store to return it' — is going there fine too, alongside booking a courier?"},
    {"id": "b-q8-05", "batch": "quote_c1c2a766_8", "text": "My friend joked 'just walk into a retail store' — is visiting allowed before booking courier?"},
    {"id": "b-q8-06", "batch": "quote_c1c2a766_8", "text": "Instead of buying online, a friend told me 'return at a physical store' — please confirm if visiting is okay when I use the app."},
    {"id": "b-q8-07", "batch": "quote_c1c2a766_8", "text": "My friend joked yesterday, anyway support told me 'bring it to a physical store', let's check via the app."},
    {"id": "b-q8-08", "batch": "quote_c1c2a766_8", "text": "Because courier isn't available, without visiting a physical store, can I still return this?"},
]


class _StrictPreLLMSpy:
    """Offline spy LLM recording provider invocation attempts; asserts 0 calls on blocked queries."""

    configured = True

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate(self, prompt: str | None = None, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"prompt": prompt, "kwargs_keys": sorted(kwargs.keys())})
        return {"text": "Offline spy draft.", "draft": "Offline spy draft.", "grounded": True}


class _InjectedKBScopeRetriever:
    """Thin read-only retriever wrapper serving approved KB evidence docs for return_product."""

    def __init__(self, base_retr: RetrievalAdapter, docs_by_intent: dict[str, list[dict[str, Any]]]) -> None:
        self.eligible_versions = base_retr.eligible_versions
        self._docs_by_intent = docs_by_intent

    def retrieve(self, query: str, intent: str, role: str = "agent", current_time: datetime | None = None) -> dict[str, Any]:
        docs = list(self._docs_by_intent.get(intent, []))
        if docs:
            return {
                "status": "success",
                "evidence": docs,
                "has_conflict": False,
            }
        return {
            "status": "no_match",
            "evidence": [],
            "reason_codes": ["no_match"],
            "has_conflict": False,
        }


def _eval_b_regressions_pre_llm(
    clf: CG.GateSequenceClassifier,
    retr: RetrievalAdapter,
    comm: CommerceAdapter,
    policy: dict[str, Any],
    pv2: Any,
) -> dict[str, Any]:
    """Run all 24 Worker B regressions through HEAD Engine & PipelineRunner under real & injected POL-RET retrieval."""
    class _ReturnProductClf:
        def __init__(self, base: Any) -> None:
            self._base = base
            self.name = base.name
            self.rejector = None

        def predict(self, text: str, top_k_count: int = 5) -> dict[str, Any]:
            out = dict(self._base.predict(text, top_k_count=top_k_count))
            out.update({
                "intent": "return_product",
                "raw_intent": "return_product",
                "confidence": 0.96,
                "raw_confidence": 0.96,
                "margin": 0.85,
                "raw_margin": 0.85,
                "selective_accepted": True,
                "rejected_by_experimental_adapter": False,
                "top_k": [{"intent": "return_product", "confidence": 0.96}],
            })
            return out

        def __getattr__(self, item: str) -> Any:
            return getattr(self._base, item)

    kb_all = json.loads((REPO / "data/knowledge/approved_kb.v2.json").read_text(encoding="utf-8"))
    pol_ret_raw = [d for d in kb_all if d["document_id"] in ("POL-RET-002", "POL-RET-001")]
    cap_by_doc = {pv.doc_id: list(pv.metadata.answer_capabilities or []) for pv in retr.eligible_versions}
    pol_ret_ev = [
        {
            "source_type": "policy",
            "document_id": d["document_id"],
            "doc_id": d["document_id"],
            "version": str(d.get("version") or "2.0"),
            "title": d["title"],
            "excerpt": d["content"],
            "content": d["content"],
            "text": d["content"],
            "chunk_ids": [f"{d['document_id']}-0"],
            "score": 0.92,
            "unboosted_score": 0.77,
            "capabilities": cap_by_doc.get(d["document_id"], list((d.get("metadata") or {}).get("answer_capabilities") or [])),
            "metadata": d.get("metadata") or {},
        }
        for d in pol_ret_raw
    ]
    inj_retr = _InjectedKBScopeRetriever(retr, {"return_product": pol_ret_ev})
    rp_clf = _ReturnProductClf(clf)
    as_of_dt = datetime.fromisoformat(AS_OF_2026.replace("Z", "+00:00"))

    with tempfile.TemporaryDirectory() as td:
        eng_spy_real = _StrictPreLLMSpy()
        run_spy_real = _StrictPreLLMSpy()
        eng_spy_inj = _StrictPreLLMSpy()
        run_spy_inj = _StrictPreLLMSpy()

        eng_real = Engine(rp_clf, retr, eng_spy_real, {"release_id": "b-repro-real", "model_version": "closure"}, policy)
        run_real = PipelineRunner(
            intent_client=A._MockIntentClient(rp_clf),
            commerce_adapter=comm,
            retrieval_adapter=retr,
            store=PersistentStore(db_path=str(Path(td) / "b_real.sqlite3")),
            llm_client=run_spy_real,
            policy=pv2,
        )
        eng_inj = Engine(rp_clf, inj_retr, eng_spy_inj, {"release_id": "b-repro-inj", "model_version": "closure"}, policy)
        run_inj = PipelineRunner(
            intent_client=A._MockIntentClient(rp_clf),
            commerce_adapter=comm,
            retrieval_adapter=inj_retr,
            store=PersistentStore(db_path=str(Path(td) / "b_inj.sqlite3")),
            llm_client=run_spy_inj,
            policy=pv2,
        )

        rows: list[dict[str, Any]] = []
        rctx = V4P1.RoutingContext(ticket_customer_id="demo-customer", verified_scope="ticket:read order:read", extracted_slots={}, is_personal_lookup=False)
        for item in B_REGRESSIONS:
            q = item["text"]
            real_ret = retr.retrieve(q, "return_product", current_time=as_of_dt)
            scope_inj = bool(policy_scope_requires_review(q, "return_product", pol_ret_raw))

            c0_er, c0_rr = len(eng_spy_real.calls), len(run_spy_real.calls)
            an_r = eng_real._analyse({"message": q, "as_of": AS_OF_2026})[0]
            rr_r = run_real.run(q, rctx, run_id=f"breal-{item['id']}")
            calls_er = len(eng_spy_real.calls) - c0_er
            calls_rr = len(run_spy_real.calls) - c0_rr

            c0_ei, c0_ri = len(eng_spy_inj.calls), len(run_spy_inj.calls)
            an_i = eng_inj._analyse({"message": q, "as_of": AS_OF_2026})[0]
            rr_i = run_inj.run(q, rctx, run_id=f"binj-{item['id']}")
            calls_ei = len(eng_spy_inj.calls) - c0_ei
            calls_ri = len(run_spy_inj.calls) - c0_ri

            rows.append({
                "id": item["id"],
                "batch": item["batch"],
                "real_retrieval_status": real_ret["status"],
                "real_engine_rec": an_r["routing"]["recommendation"],
                "real_engine_llm_calls": calls_er,
                "real_runner_action": rr_r["action"],
                "real_runner_llm_calls": calls_rr,
                "injected_scope_requires_review": scope_inj,
                "injected_engine_rec": an_i["routing"]["recommendation"],
                "injected_engine_reasons": an_i["routing"]["reason_codes"],
                "injected_engine_llm_calls": calls_ei,
                "injected_runner_action": rr_i["action"],
                "injected_runner_reasons": rr_i["reason_codes"],
                "injected_runner_llm_calls": calls_ri,
            })

    failures = [
        r for r in rows
        if r["real_engine_rec"] == "draft"
        or r["real_runner_action"] == "retrieve_draft"
        or r["real_engine_llm_calls"] != 0
        or r["real_runner_llm_calls"] != 0
        or not r["injected_scope_requires_review"]
        or r["injected_engine_rec"] != "escalate"
        or r["injected_runner_action"] != "escalate"
        or r["injected_engine_llm_calls"] != 0
        or r["injected_runner_llm_calls"] != 0
    ]
    return {
        "total_b_regressions": len(rows),
        "by_batch_counts": {
            b: sum(1 for r in rows if r["batch"] == b)
            for b in ("orig_9b4be434_6plus1", "waiver_04e63ba3_9", "quote_c1c2a766_8")
        },
        "real_retrieval_status_counts": {
            st: sum(1 for r in rows if r["real_retrieval_status"] == st)
            for st in sorted({r["real_retrieval_status"] for r in rows})
        },
        "total_external_llm_calls": sum(
            r["real_engine_llm_calls"] + r["real_runner_llm_calls"] + r["injected_engine_llm_calls"] + r["injected_runner_llm_calls"]
            for r in rows
        ),
        "all_blocked_pre_llm": len(failures) == 0,
        "failures": failures,
        "rows": rows,
    }


def main() -> None:
    t0 = time.perf_counter()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    invs = NEG_C._check_all_invariants()
    if invs["source_sha256"]["apps/core_backend/safety.py"] != SAFETY_A_PIN_SHA:
        raise RuntimeError(f"BLOCKED safety.py SHA mismatch vs a316377a: {invs['source_sha256']['apps/core_backend/safety.py']}")

    proto = json.loads(PROTO_PATH.read_text(encoding="utf-8"))
    root = A._bootstrap_target_repo(REPO)

    rel = json.loads((root / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    retr = RetrievalAdapter(
        kb_path=str(root / "data/knowledge/approved_kb.v2.json"),
        allowed_document_versions={(d["document_id"], str(d["version"])) for d in rel["documents"]},
    )
    comm = CommerceAdapter(data_path=str(root / "data/knowledge/mock_orders.json"))
    pol_path = root / "apps/core_backend/config/policies/intent_policy.v2.json"
    policy, pv2 = json.loads(pol_path.read_text(encoding="utf-8")), load_policy_v2(pol_path)

    spec = {
        "tag": "orig_fit2_slice1_closure",
        "dir": S1.ORIG_DIR,
        "cal_manifest": S1.ORIG_DIR / "calibration_manifest.json",
        "cand_manifest": S1.ORIG_DIR / "candidate_provenance_manifest.json",
    }
    clf, cal = V4P1._load_clf(spec)
    mc = ModelContainer()
    mc.load(spec["dir"], calibration_manifest_path=spec["cal_manifest"])
    assert mc.is_trained_ready()
    mc_calibrated = bool(cal["calibrated"])

    runtime_parity = {
        "orig_fit2_manifest_runtime": PRIOR_C._verify_manifest_runtime_parity(S1.ORIG_DIR, S1.ORIG_DIR / "calibration_manifest.json"),
        "serving_pinned_and_fail_closed": CG.verify_runtime_score_parity(S1.SRV_DIR, unpinned_dir=S1.ORIG_DIR, repo_root=root),
        "engine_rejection_enforcement": CG.verify_engine_rejection_enforcement(root),
    }

    cand_rec_inputs = REPO / "artifacts/models/candidates/run-records-fit2-orig-ret-channel-fit-v1/inputs"
    gate27 = CG.load_jsonl(GATE27_PATH)
    gate16 = CG.load_jsonl(GATE16_PATH)
    unseen36 = CG.load_jsonl(S1.PRIOR_C_DIR / "unseen_domain_gate_cases.jsonl")
    fresh34 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["fresh34"]["path"])
    ind36 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["ind36"]["path"])
    sealed72 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["old_sealed72"]["path"])
    final24 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["final24"]["path"])
    sa156 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["sa156"]["path"])
    noise420 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["noise420"]["path"])
    oos80 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["oos80"]["path"])
    pos175 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["pos175"]["path"])
    neg51 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["neg51"]["path"])
    cand_pos122 = CG.load_jsonl(cand_rec_inputs / "boundary_pos_evaluation.jsonl")
    cand_neg39 = CG.load_jsonl(cand_rec_inputs / "boundary_neg_evaluation.jsonl")
    bitext_rows = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["bitext6690"]["path"])
    bitext_leak_row = next(r for r in bitext_rows if r.get("sample_id") == "sample_031639")

    # Isolated gold-intent guards on both frozen gates (43 cases total) + 24 documented B regressions
    iso_gate27 = NEG_C._run_isolated_guard_both_surfaces("unseen_slice1_27", gate27, clf, retr, comm, policy, pv2)
    iso_gate16 = NEG_C._run_isolated_guard_both_surfaces("unseen_slice1_negation_16", gate16, clf, retr, comm, policy, pv2)
    b_repro_res = _eval_b_regressions_pre_llm(clf, retr, comm, policy, pv2)

    with tempfile.TemporaryDirectory() as run_td:
        engine = Engine(clf, retr, A._MockNoCallLLM(), {"release_id": "eval-slice1-closure", "model_version": "fit2-supcon-energy-boundary-v1"}, policy)
        runner = PipelineRunner(
            intent_client=A._MockIntentClient(clf),
            commerce_adapter=comm,
            retrieval_adapter=retr,
            store=PersistentStore(db_path=str(Path(run_td) / "post_closure.sqlite3")),
            llm_client=A._OfflineValidSpyLLM(),
            policy=pv2,
        )
        ev = lambda **kw: S1._eval_case_full(clf, mc, mc_calibrated, engine, runner, pv2, run_prefix="closure", **kw)

        t_eval0 = time.perf_counter()
        recs_gate27 = [
            ev(
                suite="unseen_slice1_27", cid=r["id"], text=r["text"], gold=r["true_intent"],
                ctx_dict=r["context"], as_of=r["context"]["as_of"],
                meta={"slice": r["slice"], "subgroup": r["subgroup"], "group_id": r["group_id"], "kb_basis": r["kb_basis"], "must_not_draft": r["must_not_draft"], "expected_actions": r["expected_actions"]},
            )
            for r in gate27
        ]
        recs_gate16 = [
            ev(
                suite="unseen_slice1_negation_16", cid=r["id"], text=r["text"], gold=r["true_intent"],
                ctx_dict=r["context"], as_of=r["context"]["as_of"],
                meta={"slice": r["slice"], "subgroup": r["subgroup"], "group_id": r["group_id"], "kb_basis": r["kb_basis"], "must_not_draft": r["must_not_draft"], "expected_actions": r["expected_actions"]},
            )
            for r in gate16
        ]
        recs_unseen = [
            ev(
                suite="unseen36", cid=r["id"], text=r["text"], gold=r["true_intent"],
                ctx_dict=r["context"], as_of=r["context"]["as_of"],
                meta={"slice": r["slice"], "subgroup": r["subgroup"], "group_id": r["group_id"], "must_not_draft": r["must_not_draft"], "expected_actions": r["expected_actions"]},
            )
            for r in unseen36
        ]
        recs_fresh = [
            ev(suite="fresh34", cid=r["id"], text=r["text"], gold=r["true_intent"], ctx_dict=r["context"], as_of=r["context"]["as_of"],
               meta={"slice": r["slice"], "subgroup": r["subgroup"], "must_not_draft": r["must_not_draft"]})
            for r in fresh34
        ]
        recs_ind36 = [
            ev(suite="ind36", cid=r["id"], text=r["text"], gold=r["true_intent"], ctx_dict=r["context"], as_of=r["context"]["as_of"],
               meta={"slice": r["slice"], "subgroup": r["subgroup"], "must_not_draft": r["must_not_draft"]})
            for r in ind36
        ]
        recs_s72 = [
            ev(suite="sealed72", cid=r["id"], text=r["text"], gold=r["true_intent"],
               ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {"order_id": r["order_id"]} if r.get("order_id") else {}, "is_personal_lookup": bool(r.get("order_id"))},
               as_of="2026-06-15T10:00:00Z",
               meta={"slice": r["slice"], "subgroup": "answerable" if r["slice"] == "supported_answerable" else r["slice"], "must_not_draft": r["must_not_draft"]})
            for r in sealed72
        ]
        recs_fa24 = [
            ev(suite="final24", cid=r["id"], text=r["query"], gold=r.get("intent"),
               ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {"order_id": r["order_id"]} if r.get("order_id") else {}, "is_personal_lookup": bool(r.get("order_id"))},
               as_of=r.get("as_of") or "2026-06-15T10:00:00Z",
               meta={"is_answerable": bool(r.get("is_answerable")), "fixture_boundary": r.get("fixture_boundary")})
            for r in final24
        ]
        recs_sa156 = [
            ev(suite="sa156", cid=r["id"], text=r["text"], gold=r.get("true_intent"), ctx_dict=r.get("context") or {}, as_of="2026-06-15T10:00:00Z",
               meta={"draft_expected": bool(r["expected"].get("draft_expected")), "must_escalate": bool(r["expected"].get("must_escalate")), "expected_actions": r["expected"]["actions"]})
            for r in sa156
        ]
        recs_noise = [
            ev(suite="noise420", cid=r["id"], text=r["text"], gold=r["true_intent"],
               ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
               as_of="2026-06-15T10:00:00Z", meta={"kind": r.get("kind")})
            for r in noise420
        ]
        recs_oos = [
            ev(suite="oos80", cid=r["id"], text=r["text"], gold="ood",
               ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
               as_of="2026-06-15T10:00:00Z", meta={"category": r.get("category")})
            for r in oos80
        ]
        recs_pos175 = [
            ev(suite="pos175", cid=r["sample_id"], text=r["text"], gold=r["true_intent"],
               ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
               as_of="2026-06-15T10:00:00Z", meta={"source": r.get("source")})
            for r in pos175
        ]
        recs_neg51 = [
            ev(suite="neg51", cid=r["sample_id"], text=r["text"], gold=r.get("intent") or "ood",
               ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
               as_of="2026-06-15T10:00:00Z", meta={"category": r.get("category"), "source": r.get("source")})
            for r in neg51
        ]
        recs_cpos122 = [
            ev(suite="cand_pos122", cid=r["sample_id"], text=r["text"], gold=r["true_intent"],
               ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
               as_of="2026-06-15T10:00:00Z", meta={"source": r.get("source")})
            for r in cand_pos122
        ]
        recs_cneg39 = [
            ev(suite="cand_neg39", cid=r["sample_id"], text=r["text"], gold=r.get("intent") or "ood",
               ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
               as_of="2026-06-15T10:00:00Z", meta={"category": r.get("category"), "source": r.get("source")})
            for r in cand_neg39
        ]
        rec_bitext_leak = ev(
            suite="bitext6690_targeted_leak", cid=bitext_leak_row["sample_id"], text=bitext_leak_row["text"],
            gold=bitext_leak_row["true_intent"],
            ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
            as_of="2026-06-15T10:00:00Z",
            meta={"source": "bitext6690_prior_raw_post_esc34_leak"},
        )
        eval_seconds = round(time.perf_counter() - t_eval0, 2)

    cur_all = (
        recs_gate27 + recs_gate16 + recs_unseen + recs_fresh + recs_ind36 + recs_s72 + recs_fa24
        + recs_sa156 + recs_noise + recs_oos + recs_pos175 + recs_neg51 + recs_cpos122 + recs_cneg39
        + [rec_bitext_leak]
    )
    pred_out_path = OUT_DIR / "predictions_post_slice1_closure_orig_fit2.jsonl"
    pred_out_path.write_text("\n".join(json.dumps(x) for x in cur_all) + "\n", encoding="utf-8")

    # Paired comparisons against pre-Slice-1 baseline (1bf9e6af/94a8f4fc) and prior blocked review (1325a240)
    prior_neg_recs = CG.load_jsonl(PRIOR_NEG_DIR / "predictions_post_slice1_negation_orig_fit2.jsonl")
    sealed_pre_recs = CG.load_jsonl(S1.PRIOR_C_DIR / "predictions_orig_fit2.jsonl")
    pre_gate27_recs = CG.load_jsonl(PRIOR_S1_DIR / "predictions_pre_slice1_gate27.jsonl")

    prior_12_suites = ("unseen36", "fresh34", "ind36", "sealed72", "final24", "sa156", "noise420", "oos80", "pos175", "neg51", "cand_pos122", "cand_neg39")
    paired_vs_1325a240 = NEG_C._diff_records(prior_neg_recs, cur_all, ("unseen_slice1_27", "unseen_slice1_negation_16") + prior_12_suites)
    paired_vs_pre_1bf9e6af = NEG_C._diff_records(pre_gate27_recs + sealed_pre_recs, cur_all, ("unseen_slice1_27",) + prior_12_suites)

    # Contracts across all 1,450 current actual executions
    eng_outside_ai_reasons = [
        {"suite": r["suite"], "id": r["id"], "bad_reasons": sorted(set(r["engine_reasons"]) - set(AI_REASONS))}
        for r in cur_all if not (set(r["engine_reasons"]) <= set(AI_REASONS))
    ]
    priv_eng_outside_ai_reasons = [
        {"suite": r["suite"], "id": r["id"], "bad_reasons": sorted(set(r["priv_engine_reasons"]) - set(AI_REASONS))}
        for r in cur_all if not (set(r["priv_engine_reasons"]) <= set(AI_REASONS))
    ]
    runner_spy_mismatches = [
        {"suite": r["suite"], "id": r["id"], "act": r["runner_action"], "llm_called": r["runner_llm_called"], "draft_kind": r["runner_draft_kind"], "ev": r["runner_evidence_retrieved"]}
        for r in cur_all
        if (
            (r["runner_action"] == "retrieve_draft" and not (r["runner_llm_called"] is True and r["runner_draft_kind"] == "llm" and r["runner_evidence_retrieved"] is True))
            or (r["runner_action"] != "retrieve_draft" and (r["runner_llm_called"] is True or r["runner_draft_kind"] == "llm"))
        )
    ]

    esc34_set = set(V4P1.ESCALATED_34_INTENTS)
    summaries = {
        "unseen_slice1_27": S1._summarize_unseen_slice1_gate(recs_gate27),
        "unseen_slice1_negation_16": S1._summarize_unseen_slice1_gate(recs_gate16),
        "unseen_domain_gate_36": PRIOR_C._summarize_unseen_gate(recs_unseen),
        "historical_fresh_34": V4P1._summarize_holdout_like(recs_fresh, ("novel_ood", "mandatory_escalation")),
        "independent_36": V4P1._summarize_holdout_like(recs_ind36, ("novel_ood", "mandatory_escalation")),
        "old_sealed_72": V4P1._summarize_holdout_like(recs_s72, ("novel_ood", "mandatory_escalation_compound")),
        "final_acceptance_24": V4P1._summarize_final24(recs_fa24),
        "system_acceptance_156": V4P1._summarize_sa156(recs_sa156),
        "ml_noise_420": V4P1._summarize_noise420(recs_noise),
        "ml_oos_80": {
            surf: [r["id"] for r in recs_oos if r[akey] == "retrieve_draft"]
            for surf, akey in (
                ("raw_pre", "raw_pre_action"), ("raw_post", "raw_post_action"), ("bare", "bare_action"),
                ("engine", "engine_action"), ("runner", "runner_action"),
                ("priv_raw_post", "priv_raw_post_action"), ("priv_engine", "priv_engine_action"), ("priv_runner", "priv_runner_action"),
            )
        },
        "isolated_eval_pos175_neg51": V4P1._summarize_isolated(recs_pos175, recs_neg51),
        "cand_split_boundary_pos122_neg39": V4P1._summarize_isolated(recs_cpos122, recs_cneg39),
        "bitext_sample_031639_live": {
            "sample_id": rec_bitext_leak["id"],
            "raw_post_action": rec_bitext_leak["raw_post_action"],
            "engine_action": rec_bitext_leak["engine_action"],
            "engine_reasons": rec_bitext_leak["engine_reasons"],
            "runner_action": rec_bitext_leak["runner_action"],
            "runner_reasons": rec_bitext_leak["runner_reasons"],
            "note_prior_6690_cache": "Full 6,690-row DistilBERT raw pass verified unchanged in 3bbbe5f (acc46=0.996263, macroF1=0.996313, sup11=1600/1613, 1 raw leak=sample_031639); raw weights, calibration, KB, and adapter.py unchanged.",
        },
        "postprivacy_parity": {
            "unseen_slice1_27": PRIOR_C._summarize_privacy_suite(recs_gate27, nodraft_golds=esc34_set | {"ood"}),
            "unseen_slice1_negation_16": PRIOR_C._summarize_privacy_suite(recs_gate16, nodraft_golds=esc34_set | {"ood"}),
            "unseen36": PRIOR_C._summarize_privacy_suite(recs_unseen, nodraft_golds=esc34_set | {"ood"}),
            "final24": PRIOR_C._summarize_privacy_suite([r for r in recs_fa24 if not r["meta"]["is_answerable"] and r["meta"]["fixture_boundary"] == "active_kb"], all_rows_nodraft=True),
            "sa156_all": PRIOR_C._summarize_privacy_suite(recs_sa156),
            "sa156_mand63": PRIOR_C._summarize_privacy_suite([r for r in recs_sa156 if r["meta"]["must_escalate"]], all_rows_nodraft=True, excluded_ids=set(CG.KNOWN_UNINJECTED_ACCEPTANCE_IDS)),
            "noise420": PRIOR_C._summarize_privacy_suite(recs_noise),
            "oos80": PRIOR_C._summarize_privacy_suite(recs_oos, nodraft_golds={"ood"}),
            "ind36_must_not_draft": PRIOR_C._summarize_privacy_suite([r for r in recs_ind36 if r["meta"]["must_not_draft"]], all_rows_nodraft=True),
            "old_sealed72": PRIOR_C._summarize_privacy_suite([r for r in recs_s72 if r["meta"]["must_not_draft"]], all_rows_nodraft=True),
            "fresh34": PRIOR_C._summarize_privacy_suite([r for r in recs_fresh if r["meta"]["must_not_draft"]], all_rows_nodraft=True),
            "pos175": PRIOR_C._summarize_privacy_suite(recs_pos175, nodraft_golds=esc34_set),
            "neg51": PRIOR_C._summarize_privacy_suite(recs_neg51, nodraft_golds={"ood"}),
        },
    }

    reconcile = S1._reconcile_b_vs_frozen_c([r for r in cur_all if r["suite"] in prior_12_suites], sealed_pre_recs)
    hist_diffs_vs_1325a240 = {
        s: {k: v for k, v in paired_vs_1325a240[s].items() if v}
        for s in prior_12_suites
        if any(paired_vs_1325a240[s].values())
    }

    sup_27_ids = {r["id"] for r in recs_gate27 if not r["meta"]["must_not_draft"]}
    gate27_fp_natural_vs_pre = [
        ch for ch in paired_vs_pre_1bf9e6af["unseen_slice1_27"]["engine_changed"] + paired_vs_pre_1bf9e6af["unseen_slice1_27"]["runner_changed"]
        if ch["id"] in sup_27_ids and ch["cur_act"] != "retrieve_draft" and ch["ref_act"] != "escalate" and ch["cur_act"] == "escalate"
    ]
    gate16_nat_sup_scope_blocks = [
        {"id": r["id"], "eng_act": r["engine_action"], "eng_reasons": r["engine_reasons"], "run_act": r["runner_action"], "run_reasons": r["runner_reasons"]}
        for r in recs_gate16
        if not r["meta"]["must_not_draft"] and ("insufficient_evidence" in r["engine_reasons"] and r["engine_action"] == "escalate" and not any(x in r["runner_reasons"] for x in ("no_match", "below_relevance_threshold")))
    ]

    sys_surfs = ("engine", "runner")
    priv_surfs = ("priv_engine", "priv_runner")
    g27_tot = summaries["unseen_slice1_27"]["totals"]
    g16_tot = summaries["unseen_slice1_negation_16"]["totals"]

    criteria = {
        "raw_ml_unchanged_noise420_macro_f1": round(summaries["ml_noise_420"]["macro_f1_12"], 6) == 0.857307,
        "raw_ml_unchanged_noise420_bare_gate_267": summaries["ml_noise_420"]["bare"]["correct_draft"] == 267,
        "floor_final24_runner_ans12_ge_10": len(summaries["final_acceptance_24"]["runner"]["ans12_correct"]) >= 10,
        "floor_final24_runner_ans12_zero_wrong": len(summaries["final_acceptance_24"]["runner"]["ans12_wrong"]) == 0,
        "floor_sa156_runner_sup34_ge_25": summaries["system_acceptance_156"]["runner"]["sup34_correct_draft"] >= 25,
        "floor_noise420_runner_correct_ge_260": summaries["ml_noise_420"]["runner"]["correct_draft"] >= 260,
        "zero_system_leaks_unseen36": all(
            len(summaries["unseen_domain_gate_36"]["slices"][sl]["surfaces"][sf]["unsafe_draft_leaks"]) == 0
            for sl in ("return_contrast_escalated", "cross_intent_escalated", "novel_ood")
            for sf in ("engine", "runner", "priv_engine", "priv_runner")
        ),
        "zero_system_leaks_fresh34": all(len(summaries["historical_fresh_34"][sf]["leaks"]) == 0 for sf in sys_surfs)
            and all(len(summaries["postprivacy_parity"]["fresh34"]["nodraft_leaks"][pf]) == 0 for pf in priv_surfs),
        "zero_system_leaks_ind36": all(len(summaries["independent_36"][sf]["leaks"]) == 0 for sf in sys_surfs)
            and all(len(summaries["postprivacy_parity"]["ind36_must_not_draft"]["nodraft_leaks"][pf]) == 0 for pf in priv_surfs),
        "zero_system_leaks_old_sealed72": all(len(summaries["old_sealed_72"][sf]["leaks"]) == 0 for sf in sys_surfs)
            and all(len(summaries["postprivacy_parity"]["old_sealed72"]["nodraft_leaks"][pf]) == 0 for pf in priv_surfs),
        "zero_system_leaks_final24_active_unans8": all(len(summaries["final_acceptance_24"][sf]["active_unans8_leaks"]) == 0 for sf in sys_surfs)
            and all(len(summaries["postprivacy_parity"]["final24"]["nodraft_leaks"][pf]) == 0 for pf in priv_surfs),
        "zero_system_leaks_sa156_mand63_real": all(len(summaries["system_acceptance_156"][sf]["mand63_real_leaks"]) == 0 for sf in sys_surfs)
            and all(len(summaries["postprivacy_parity"]["sa156_mand63"]["nodraft_leaks"][pf]) == 0 for pf in priv_surfs),
        "zero_system_leaks_oos80": all(len(summaries["ml_oos_80"][sf]) == 0 for sf in ("engine", "runner", "priv_engine", "priv_runner")),
        "zero_system_leaks_pos175_esc34": all(len(summaries["isolated_eval_pos175_neg51"][sf]["esc34_leaks"]) == 0 for sf in sys_surfs)
            and all(len(summaries["postprivacy_parity"]["pos175"]["nodraft_leaks"][pf]) == 0 for pf in priv_surfs),
        "zero_system_leaks_neg51": all(len(summaries["isolated_eval_pos175_neg51"][sf]["neg51_leaks"]) == 0 for sf in sys_surfs)
            and all(len(summaries["postprivacy_parity"]["neg51"]["nodraft_leaks"][pf]) == 0 for pf in priv_surfs),
        "zero_system_leaks_cand_pos122_neg39": all(
            len(summaries["cand_split_boundary_pos122_neg39"][sf]["esc34_leaks"]) == 0
            and len(summaries["cand_split_boundary_pos122_neg39"][sf]["neg51_leaks"]) == 0
            for sf in sys_surfs
        ),
        "bitext_sample_031639_blocked": rec_bitext_leak["engine_action"] == "escalate" and rec_bitext_leak["runner_action"] == "escalate",
        "gate27_zero_leaks_and_zero_false_scope_blocks": (
            all(len(g27_tot[sf]["must_not_draft_leaks"]) == 0 for sf in ("engine", "runner", "priv_engine", "priv_runner"))
            and len(iso_gate27["must_not_draft_leaks"]) == 0
            and len(iso_gate27["supported_false_positive_blocks"]) == 0
            and len(gate27_fp_natural_vs_pre) == 0
        ),
        "gate16_zero_leaks_and_zero_false_scope_blocks": (
            all(len(g16_tot[sf]["must_not_draft_leaks"]) == 0 for sf in ("engine", "runner", "priv_engine", "priv_runner"))
            and len(iso_gate16["must_not_draft_leaks"]) == 0
            and len(iso_gate16["supported_false_positive_blocks"]) == 0
            and len(gate16_nat_sup_scope_blocks) == 0
        ),
        "b_24_regressions_blocked_zero_llm_calls": b_repro_res["all_blocked_pre_llm"],
        "typed_ai_reasons_contract_valid": len(eng_outside_ai_reasons) == 0 and len(priv_eng_outside_ai_reasons) == 0,
        "runner_spy_contract_consistent": len(runner_spy_mismatches) == 0,
        "runtime_score_parity_passed": (
            bool(runtime_parity["orig_fit2_manifest_runtime"].get("passed"))
            and bool(runtime_parity["serving_pinned_and_fail_closed"].get("passed"))
            and bool(runtime_parity["engine_rejection_enforcement"].get("engine_enforces_experimental_rejection"))
            and all(v["mc_vs_gate_intent_mismatches"] == 0 and v["mc_vs_gate_max_conf_diff"] < 1e-5 for v in summaries["postprivacy_parity"].values())
        ),
    }

    verdict = "PASS" if all(criteria.values()) else "BLOCK"
    report = {
        "schema_version": "original_fit2_safety_slice1_closure_c.v1",
        "invariants": invs,
        "model_under_test": {
            "tag": "orig_fit2",
            "weights_sha256": invs["files"]["orig_fit2_weights"]["sha256"],
            "calibration_sha256": invs["files"]["orig_fit2_cal"]["sha256"],
            "temperature": float(cal["temperature"] or 1.0),
            "calibrated": bool(cal["calibrated"]),
            "selective_rejector_enabled": bool(clf.rejector is not None),
        },
        "runtime_parity": runtime_parity,
        "isolated_guard_probes": {
            "unseen_slice1_27": iso_gate27,
            "unseen_slice1_negation_16": iso_gate16,
        },
        "b_24_documented_regressions": b_repro_res,
        "reconciliation_b_vs_frozen_c": reconcile,
        "paired_diffs_vs_1325a240": {
            "unseen_slice1_27": paired_vs_1325a240["unseen_slice1_27"],
            "unseen_slice1_negation_16": paired_vs_1325a240["unseen_slice1_negation_16"],
            "historical_1406_nonempty_diffs": hist_diffs_vs_1325a240,
        },
        "paired_diffs_vs_pre_1bf9e6af": paired_vs_pre_1bf9e6af,
        "gate_fp_checks": {
            "gate27_natural_regressions_vs_pre": gate27_fp_natural_vs_pre,
            "gate16_natural_supported_scope_blocks": gate16_nat_sup_scope_blocks,
        },
        "typed_contracts": {
            "engine_outside_ai_reasons": eng_outside_ai_reasons,
            "priv_engine_outside_ai_reasons": priv_eng_outside_ai_reasons,
            "runner_spy_mismatches": runner_spy_mismatches,
        },
        "summaries": summaries,
        "system_slice1_verdict": {
            "scope": "SYSTEM_SLICE1_ONLY_NOT_RAW_ML_NOT_WHOLE_PROJECT",
            "verdict": verdict,
            "criteria": criteria,
            "failed_criteria": [k for k, v in criteria.items() if not v],
        },
        "durations": {
            "eval_1450_plus_privacy_seconds": eval_seconds,
            "total_script_seconds": round(time.perf_counter() - t0, 2),
        },
    }

    summary_path = OUT_DIR / "slice1_closure_paired_evaluation.json"
    summary_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")

    tracked = [
        OUT_DIR / "evaluate_safety_slice1_closure_c.py",
        pred_out_path,
        summary_path,
    ]
    run_manifest = {
        "branch": invs["git_branch"],
        "git_head": invs["git_head"],
        "command": ".venv/Scripts/python.exe -B artifacts/evaluation/original_fit2_safety_slice1_closure_c_20261115/evaluate_safety_slice1_closure_c.py",
        "verdict": verdict,
        "failed_criteria": report["system_slice1_verdict"]["failed_criteria"],
        "eval_seconds": eval_seconds,
        "total_duration_seconds": report["durations"]["total_script_seconds"],
        "sha256": {str(p.relative_to(REPO)).replace("\\", "/"): CG.compute_file_sha256(p) for p in tracked},
    }
    (OUT_DIR / "run_manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"DONE VERDICT={verdict} FAILED={run_manifest['failed_criteria']} "
        f"EVAL_S={eval_seconds} TOTAL_S={run_manifest['total_duration_seconds']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
