"""Worker C Bounded Independent Final Re-Review of System Safety Slice 1 Negation Fix (34733574 / B PASS ebf6c72).

Strictly read-only against source, models, KB, policy, runtime env, and prior archives:
- Zero training, optimizer, calibrator, rejector, or paid/live LLM calls (_MockNoCallLLM / _OfflineValidSpyLLM).
- Verifies SHA-256 invariants (f695b1fe, 782c88db, dc7af8cf, approved_kb, kb-release, intent_policy,
  training_cap 2/2 STOPPED, adapter.py 3bd797da unchanged since 03eb1231, all 12 frozen suites, 27-case gate).
- Re-runs Worker C's frozen 27-case unseen gate (20bb9315...) on actual HEAD Engine & PipelineRunner
  under BOTH natural Orig Fit2 AND isolated gold-intent override, distinguishing classifier vs guard.
- Evaluates newly frozen 16-case independent negation/contrast/quote/multichannel gate (c232bd6e...,
  0 overlap with Worker A's tests and all prior suites) under BOTH natural Orig Fit2 AND isolated override.
- Executes actual current HEAD Engine & PipelineRunner across all 1,406 rows of all 12 frozen prior suites
  plus bitext6690 sample_031639 ("how to return an item in stroe") and performs 3-way paired diff vs
  pre-Slice-1 baseline (94a8f4fc / 1bf9e6af) and prior blocked Slice 1 (3bbbe5f / faac0e72).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent
PRIOR_S1_DIR = REPO / "artifacts/evaluation/original_fit2_safety_slice1_c_20261115"
PRIOR_C_DIR = REPO / "artifacts/evaluation/fit2_orig_ret_channel_fit_v1_independent_c_20261114"
V4P1_DIR = REPO / "artifacts/evaluation/fit2_v4p1_independent_20261114"
PROTO_PATH = REPO / "artifacts/evaluation/fit2_next_protocol_c_20261114/protocol_manifest.json"

GATE27_CASES_PATH = PRIOR_S1_DIR / "unseen_slice1_scope_gate_cases.jsonl"
GATE27_MANIFEST_PATH = PRIOR_S1_DIR / "unseen_slice1_scope_gate_manifest.json"
GATE16_CASES_PATH = OUT_DIR / "unseen_slice1_negation_gate_cases.jsonl"
GATE16_MANIFEST_PATH = OUT_DIR / "unseen_slice1_negation_gate_manifest.json"

sys.path.insert(0, str(REPO))

_s1_spec = importlib.util.spec_from_file_location("s1_eval_c", PRIOR_S1_DIR / "evaluate_safety_slice1_c.py")
assert _s1_spec and _s1_spec.loader
S1 = importlib.util.module_from_spec(_s1_spec)
_s1_spec.loader.exec_module(S1)

V4P1 = S1.V4P1
PRIOR_C = S1.PRIOR_C
CG = S1.CG
A = S1.A

from apps.ai_service.engine import Engine  # noqa: E402
from apps.backend.tickets.jobs import AI_REASONS  # noqa: E402
from apps.core_backend.commerce.adapter import CommerceAdapter  # noqa: E402
from apps.core_backend.intent.routing import load_policy_v2  # noqa: E402
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner  # noqa: E402
from apps.core_backend.orchestration.store import PersistentStore  # noqa: E402
from apps.core_backend.retrieval.adapter import RetrievalAdapter  # noqa: E402
from apps.core_backend.safety import policy_scope_requires_review  # noqa: E402
from apps.ml_inference.app import ModelContainer  # noqa: E402

ADAPTER_PIN_SHA = "3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f"
GATE27_PIN_SHA = "20bb9315c8d4be4670fd2e8157053eea29ee43eec6a7510029ccbb49a66b84d8"
GATE16_PIN_SHA = "c232bd6e21db2c497bc566ddc9e668f5efa3ca11e638fa3e6f6ba67fcc825a3a"
FROZEN_S1_COMMIT = "12d358d3b301680a5d1ab910d684a1102bcd509c"


def _check_all_invariants() -> dict[str, Any]:
    invs = S1._check_invariants()
    if invs["source_sha256"]["apps/core_backend/retrieval/adapter.py"] != ADAPTER_PIN_SHA:
        raise RuntimeError("BLOCKED adapter.py drifted from 03eb1231/12d358d3!")
    if invs["gate_cases_sha256"] != GATE27_PIN_SHA:
        raise RuntimeError(f"BLOCKED 27-case gate drifted: {invs['gate_cases_sha256']} != {GATE27_PIN_SHA}")

    gate16_manifest = json.loads(GATE16_MANIFEST_PATH.read_text(encoding="utf-8"))
    act_gate16 = CG.compute_file_sha256(GATE16_CASES_PATH)
    if act_gate16 != GATE16_PIN_SHA or act_gate16 != gate16_manifest["cases_sha256"]:
        raise RuntimeError(f"BLOCKED 16-case negation gate drifted: {act_gate16}")

    diff_12d3_to_head = subprocess.check_output(
        ["git", "diff", "--name-only", f"{FROZEN_S1_COMMIT}..HEAD", "--", "apps/", "data/"],
        cwd=REPO,
        text=True,
    ).splitlines()
    if diff_12d3_to_head != ["apps/core_backend/safety.py"]:
        raise RuntimeError(f"BLOCKED unexpected source/data edits since 12d358d3: {diff_12d3_to_head}")

    invs["gate16_cases_sha256"] = act_gate16
    invs["adapter_unchanged_since_12d358d3"] = True
    invs["diff_12d358d3_to_head_apps_data"] = diff_12d3_to_head
    return invs


def _run_isolated_guard_both_surfaces(
    suite_name: str,
    gate_rows: list[dict[str, Any]],
    clf: CG.GateSequenceClassifier,
    retr: RetrievalAdapter,
    comm: CommerceAdapter,
    policy: dict[str, Any],
    pv2: Any,
) -> dict[str, Any]:
    """Run actual Engine AND PipelineRunner at high-confidence gold intent + direct policy_scope_requires_review."""

    class _GoldIntentOverrideClf:
        def __init__(self, base: Any, intent_map: dict[str, str]) -> None:
            self._base = base
            self._intent_map = intent_map
            self.name = base.name
            self.rejector = None

        def predict(self, text: str, top_k_count: int = 5) -> dict[str, Any]:
            base_out = dict(self._base.predict(text, top_k_count=top_k_count))
            gold = self._intent_map[text]
            base_out.update({
                "intent": gold,
                "raw_intent": gold,
                "confidence": 0.99,
                "raw_confidence": 0.99,
                "margin": 0.98,
                "raw_margin": 0.98,
                "selective_accepted": True,
                "rejected_by_experimental_adapter": False,
                "top_k": [{"intent": gold, "confidence": 0.99}],
            })
            return base_out

        def __getattr__(self, item: str) -> Any:
            return getattr(self._base, item)

    intent_map = {r["text"]: ("policy_general" if r["true_intent"] == "ood" else r["true_intent"]) for r in gate_rows}
    override_clf = _GoldIntentOverrideClf(clf, intent_map)

    with tempfile.TemporaryDirectory() as td:
        iso_engine = Engine(
            override_clf,
            retr,
            A._MockNoCallLLM(),
            {"release_id": f"iso-{suite_name}", "model_version": "gold-intent-probe"},
            policy,
        )
        iso_runner = PipelineRunner(
            intent_client=A._MockIntentClient(override_clf),
            commerce_adapter=comm,
            retrieval_adapter=retr,
            store=PersistentStore(db_path=str(Path(td) / f"iso_{suite_name}.sqlite3")),
            llm_client=A._OfflineValidSpyLLM(),
            policy=pv2,
        )

        kb_all = json.loads((REPO / "data/knowledge/approved_kb.v2.json").read_text(encoding="utf-8"))
        pol_ret_docs = [d for d in kb_all if d["document_id"] in ("POL-RET-001", "POL-RET-002", "POL-RET-003")]
        pol_ord_docs = [d for d in kb_all if d["document_id"] == "POL-ORD-001"]

        rows_out: list[dict[str, Any]] = []
        for r in gate_rows:
            ctx_dict = r["context"]
            as_of_dt = datetime.fromisoformat(ctx_dict["as_of"].replace("Z", "+00:00"))
            pred_intent = intent_map[r["text"]]
            ret_docs = retr.retrieve(r["text"], pred_intent, current_time=as_of_dt).get("evidence") or []
            scope_flag = bool(policy_scope_requires_review(r["text"], pred_intent, ret_docs))
            gold_kb_docs = pol_ord_docs if pred_intent in ("track_order", "order_history") else pol_ret_docs
            scope_with_gold_kb = bool(policy_scope_requires_review(r["text"], pred_intent, gold_kb_docs))

            an = iso_engine._analyse({"message": r["text"], "as_of": ctx_dict["as_of"]})[0]
            eng_act = CG._adapt_action(an["routing"]["recommendation"])

            rctx = V4P1.RoutingContext(
                ticket_customer_id=ctx_dict.get("ticket_customer_id", "demo-customer"),
                verified_scope=ctx_dict.get("verified_scope", "ticket:read order:read"),
                extracted_slots=ctx_dict.get("extracted_slots") or {},
                is_personal_lookup=bool(ctx_dict.get("is_personal_lookup", False)),
            )
            rr = iso_runner.run(r["text"], rctx, run_id=f"iso-{suite_name}-{r['id']}")

            rows_out.append({
                "id": r["id"],
                "slice": r["slice"],
                "subgroup": r["subgroup"],
                "true_intent": r["true_intent"],
                "must_not_draft": bool(r["must_not_draft"]),
                "scope_requires_review": scope_flag,
                "scope_requires_review_with_gold_kb": scope_with_gold_kb,
                "isolated_engine_action": eng_act,
                "isolated_engine_reasons": an["routing"]["reason_codes"],
                "isolated_runner_action": rr["action"],
                "isolated_runner_reasons": rr["reason_codes"],
                "isolated_runner_llm_called": bool(rr.get("llm_called")),
                "retrieved_doc_ids": [d.get("document_id") for d in ret_docs],
            })

    must_not = [x for x in rows_out if x["must_not_draft"]]
    supported = [x for x in rows_out if not x["must_not_draft"]]
    must_not_leaks = [
        x for x in must_not
        if not x["scope_requires_review"]
        or x["isolated_engine_action"] == "retrieve_draft"
        or x["isolated_runner_action"] == "retrieve_draft"
    ]
    supported_scope_fp_blocks = [
        x for x in supported
        if x["scope_requires_review"] or x["scope_requires_review_with_gold_kb"]
    ]
    supported_retrieval_only_misses = [
        x for x in supported
        if not x["scope_requires_review"]
        and not x["scope_requires_review_with_gold_kb"]
        and (x["isolated_engine_action"] != "retrieve_draft" or x["isolated_runner_action"] != "retrieve_draft")
    ]
    return {
        "n": len(rows_out),
        "must_not_draft_n": len(must_not),
        "supported_n": len(supported),
        "must_not_draft_all_blocked_scope_true": sum(1 for x in must_not if x["scope_requires_review"] and x["isolated_engine_action"] == "escalate" and x["isolated_runner_action"] == "escalate"),
        "supported_all_drafted_scope_false": sum(1 for x in supported if not x["scope_requires_review"] and x["isolated_engine_action"] == "retrieve_draft" and x["isolated_runner_action"] == "retrieve_draft"),
        "must_not_draft_leaks": must_not_leaks,
        "supported_false_positive_blocks": supported_scope_fp_blocks,
        "supported_retrieval_only_misses": supported_retrieval_only_misses,
        "rows": rows_out,
    }


def _diff_records(
    ref_recs: list[dict[str, Any]],
    cur_recs: list[dict[str, Any]],
    suites: tuple[str, ...],
) -> dict[str, Any]:
    ref_map = {(r["suite"], r["id"]): r for r in ref_recs}
    cur_map = {(r["suite"], r["id"]): r for r in cur_recs}
    out: dict[str, Any] = {}
    for sname in suites:
        keys = [k for k in cur_map if k[0] == sname]
        out[sname] = {
            "raw_post_changed": [
                {"id": cid, "ref": ref_map[(s, cid)]["raw_post_action"], "cur": cur_map[(s, cid)]["raw_post_action"]}
                for s, cid in keys
                if ref_map[(s, cid)]["raw_post_action"] != cur_map[(s, cid)]["raw_post_action"]
                or ref_map[(s, cid)]["pred_intent"] != cur_map[(s, cid)]["pred_intent"]
            ],
            "engine_changed": [
                {
                    "id": cid, "gold": cur_map[(s, cid)]["gold"],
                    "ref_act": ref_map[(s, cid)]["engine_action"], "cur_act": cur_map[(s, cid)]["engine_action"],
                    "ref_reasons": ref_map[(s, cid)].get("engine_reasons"), "cur_reasons": cur_map[(s, cid)]["engine_reasons"],
                    "pred": cur_map[(s, cid)]["engine_intent"], "conf": cur_map[(s, cid)]["conf"],
                }
                for s, cid in keys
                if ref_map[(s, cid)]["engine_action"] != cur_map[(s, cid)]["engine_action"]
                or ref_map[(s, cid)]["engine_intent"] != cur_map[(s, cid)]["engine_intent"]
            ],
            "runner_changed": [
                {
                    "id": cid, "gold": cur_map[(s, cid)]["gold"],
                    "ref_act": ref_map[(s, cid)]["runner_action"], "cur_act": cur_map[(s, cid)]["runner_action"],
                    "cur_reasons": cur_map[(s, cid)]["runner_reasons"],
                    "pred": cur_map[(s, cid)]["runner_intent"], "conf": cur_map[(s, cid)]["conf"],
                }
                for s, cid in keys
                if ref_map[(s, cid)]["runner_action"] != cur_map[(s, cid)]["runner_action"]
                or ref_map[(s, cid)]["runner_intent"] != cur_map[(s, cid)]["runner_intent"]
            ],
            "priv_engine_changed": [
                {"id": cid, "ref_act": ref_map[(s, cid)]["priv_engine_action"], "cur_act": cur_map[(s, cid)]["priv_engine_action"]}
                for s, cid in keys
                if ref_map[(s, cid)]["priv_engine_action"] != cur_map[(s, cid)]["priv_engine_action"]
            ],
            "priv_runner_changed": [
                {"id": cid, "ref_act": ref_map[(s, cid)]["priv_runner_action"], "cur_act": cur_map[(s, cid)]["priv_runner_action"]}
                for s, cid in keys
                if ref_map[(s, cid)]["priv_runner_action"] != cur_map[(s, cid)]["priv_runner_action"]
            ],
        }
    return out


def main() -> None:
    t0 = time.perf_counter()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    invs = _check_all_invariants()
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
        "tag": "orig_fit2_post_slice1_negation",
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
    gate27 = CG.load_jsonl(GATE27_CASES_PATH)
    gate16 = CG.load_jsonl(GATE16_CASES_PATH)
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

    # Isolated high-confidence gold-intent guard probes on BOTH unseen gates (Engine + Runner + direct safety.py)
    iso_gate27 = _run_isolated_guard_both_surfaces("unseen_slice1_27", gate27, clf, retr, comm, policy, pv2)
    iso_gate16 = _run_isolated_guard_both_surfaces("unseen_slice1_negation_16", gate16, clf, retr, comm, policy, pv2)

    with tempfile.TemporaryDirectory() as run_td:
        engine = Engine(clf, retr, A._MockNoCallLLM(), {"release_id": "eval-slice1-negation", "model_version": "fit2-supcon-energy-boundary-v1"}, policy)
        runner = PipelineRunner(
            intent_client=A._MockIntentClient(clf),
            commerce_adapter=comm,
            retrieval_adapter=retr,
            store=PersistentStore(db_path=str(Path(run_td) / "post_slice1_neg.sqlite3")),
            llm_client=A._OfflineValidSpyLLM(),
            policy=pv2,
        )
        ev = lambda **kw: S1._eval_case_full(clf, mc, mc_calibrated, engine, runner, pv2, run_prefix="post_neg", **kw)

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
    pred_out_path = OUT_DIR / "predictions_post_slice1_negation_orig_fit2.jsonl"
    pred_out_path.write_text("\n".join(json.dumps(x) for x in cur_all) + "\n", encoding="utf-8")

    # Reference logs for exact paired diffs
    prior_s1_recs = CG.load_jsonl(PRIOR_S1_DIR / "predictions_post_slice1_orig_fit2.jsonl")
    sealed_pre_recs = CG.load_jsonl(S1.PRIOR_C_DIR / "predictions_orig_fit2.jsonl")
    pre_gate27_recs = CG.load_jsonl(PRIOR_S1_DIR / "predictions_pre_slice1_gate27.jsonl")

    prior_12_suites = ("unseen36", "fresh34", "ind36", "sealed72", "final24", "sa156", "noise420", "oos80", "pos175", "neg51", "cand_pos122", "cand_neg39")
    paired_vs_prior_s1_3bbbe5f = _diff_records(prior_s1_recs, cur_all, ("unseen_slice1_27",) + prior_12_suites)
    paired_vs_pre_slice1_1bf9e6af = _diff_records(pre_gate27_recs + sealed_pre_recs, cur_all, ("unseen_slice1_27",) + prior_12_suites)

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
            "note_prior_6690_cache": "Full 6,690-row DistilBERT raw pass verified unchanged in 3bbbe5f (acc46=0.996263, macroF1=0.996313, sup11=1600/1613, 1 raw leak=sample_031639); diff 12d358d3..HEAD modified safety.py only.",
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

    # Historical invariance check: zero changes across the 1,406 prior rows vs 3bbbe5f except intended? Wait: did ANY historical row change between 3bbbe5f and 34733574?
    hist_diffs_vs_3bbbe5f = {
        s: {k: v for k, v in paired_vs_prior_s1_3bbbe5f[s].items() if v}
        for s in prior_12_suites
        if any(paired_vs_prior_s1_3bbbe5f[s].values())
    }

    # Check natural Orig Fit2 regressions vs pre-Slice-1 baseline on supported cases in BOTH unseen gates
    sup_27_ids = {r["id"] for r in recs_gate27 if not r["meta"]["must_not_draft"]}
    gate27_fp_natural_vs_pre = [
        ch for ch in paired_vs_pre_slice1_1bf9e6af["unseen_slice1_27"]["engine_changed"] + paired_vs_pre_slice1_1bf9e6af["unseen_slice1_27"]["runner_changed"]
        if ch["id"] in sup_27_ids and ch["cur_act"] != "retrieve_draft" and ch["ref_act"] != "escalate" and ch["cur_act"] == "escalate"
    ]
    # On unseen_slice1_negation_16: verify natural Engine/Runner NEVER have false insufficient_evidence scope escalation on supported cases
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
        "bitext_sample_031639_blocked": (
            rec_bitext_leak["engine_action"] == "escalate" and rec_bitext_leak["runner_action"] == "escalate"
        ),
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
        "schema_version": "original_fit2_safety_slice1_final_review_c.v1",
        "invariants": invs,
        "model_under_test": {
            "tag": "orig_fit2",
            "weights_sha256": invs["files"]["orig_fit2_weights"]["sha256"],
            "calibration_sha256": invs["files"]["orig_fit2_cal"]["sha256"],
            "temperature": float(cal["temperature"] or 1.0),
            "calibrated": bool(cal["calibrated"]),
            "selective_rejector_enabled": bool(clf.rejector is not None),
        },
        "execution_mode": (
            "Actual current HEAD (ebf6c72 / source fix 34733574) Engine + PipelineRunner + production KB retrieval executed across "
            "27-case frozen gate (20bb9315), 16-case newly frozen negation/contrast gate (c232bd6e), 1,406 historical rows across all 12 prior suites, "
            "and bitext6690 sample_031639 (1,450 live case evaluations + 43 isolated gold-intent Engine/Runner probe runs). "
            "Reference predictions from 3bbbe5f and 1bf9e6af used solely for paired comparison; bitext6690 6,690-row DistilBERT pass carried from 3bbbe5f."
        ),
        "runtime_parity": runtime_parity,
        "isolated_guard_probes": {
            "unseen_slice1_27": iso_gate27,
            "unseen_slice1_negation_16": iso_gate16,
        },
        "reconciliation_b_vs_frozen_c": reconcile,
        "paired_diffs_vs_prior_slice1_3bbbe5f": {
            "unseen_slice1_27": paired_vs_prior_s1_3bbbe5f["unseen_slice1_27"],
            "historical_1406_nonempty_diffs": hist_diffs_vs_3bbbe5f,
        },
        "paired_diffs_vs_pre_slice1_baseline_1bf9e6af": paired_vs_pre_slice1_1bf9e6af,
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

    summary_path = OUT_DIR / "slice1_negation_paired_evaluation.json"
    summary_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")

    tracked = [
        GATE16_CASES_PATH,
        GATE16_MANIFEST_PATH,
        OUT_DIR / "evaluate_safety_slice1_negation_c.py",
        pred_out_path,
        summary_path,
    ]
    run_manifest = {
        "branch": invs["git_branch"],
        "git_head": invs["git_head"],
        "command": ".venv/Scripts/python.exe -B artifacts/evaluation/original_fit2_safety_slice1_negation_c_20261115/evaluate_safety_slice1_negation_c.py",
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
