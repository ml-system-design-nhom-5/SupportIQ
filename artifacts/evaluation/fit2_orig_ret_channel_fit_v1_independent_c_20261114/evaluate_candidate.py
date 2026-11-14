"""Independent Stage 2 evaluation of archived fit2-orig-ret-channel-fit-v1 vs Original Fit2.

Zero live LLM calls (_MockNoCallLLM / _OfflineValidSpyLLM only), zero fits/tuning,
zero edits to runtime/KB/policy/models/preps, and writes only inside this directory.
Evaluates raw_pre, raw_post, bare/Gate, Engine, Runner, plus real post-privacy
(pseudonymize + ModelContainer) parity across all 10 frozen suites, candidate boundary
cross-checks, bitext6690 (full + exclude-3 inherited overlap sensitivity), and C's
pre-frozen unseen domain-boundary + cross-intent gate.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import time
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
from apps.backend.tickets.privacy import pseudonymize  # noqa: E402
from apps.core_backend.commerce.adapter import CommerceAdapter  # noqa: E402
from apps.core_backend.intent.routing import decide_route, load_policy_v2  # noqa: E402
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner  # noqa: E402
from apps.core_backend.orchestration.store import PersistentStore  # noqa: E402
from apps.core_backend.retrieval.adapter import RetrievalAdapter  # noqa: E402
from apps.ml_inference.app import ModelContainer  # noqa: E402
from pipeline.evaluation import classifier_acceptance_gate as CG  # noqa: E402
from scripts import run_closure_candidate_audit as A  # noqa: E402

M = V4P1.M

CAND_DIR = REPO / "artifacts/models/candidates/fit2-orig-ret-channel-fit-v1"
CAND_REC_INPUTS = REPO / "artifacts/models/candidates/run-records-fit2-orig-ret-channel-fit-v1/inputs"
ORIG_DIR = REPO / "artifacts/models/candidates/reconstructed-fit2-supcon-20261113"
SRV_DIR = REPO / "artifacts/models/trained/distilbert-supportiq"
PROTO_PATH = REPO / "artifacts/evaluation/fit2_next_protocol_c_20261114/protocol_manifest.json"
UGC_PATH = OUT_DIR / "unseen_domain_gate_cases.jsonl"
UGC_MANIFEST_PATH = OUT_DIR / "unseen_domain_gate_manifest.json"

INHERITED_BITEXT_OVERLAP_IDS = {"sample_001360", "sample_020916", "sample_031234"}

EXPECTED_SHAS = {
    "cand_weights": "dc3e88e713c71fe0e521a1dc5bec5831d9a0a91a83d4c3d1b413d3b1cd68e44d",
    "cand_cal": "e0d1bfd63f65e2e055af46a2e023ec398240008e166c2df91eb1fa5d111bb56c",
    "cand_prov": "6f4287cabed4128162b1bcb68192fea815b159de016a230c3706ef376c13908d",
    "orig_weights": "f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa",
    "orig_cal": "782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39",
    "srv_weights": "dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302",
}


def _check_frozen_preconditions(proto: dict[str, Any]) -> None:
    checks = {
        "cand_weights": CAND_DIR / "model.safetensors",
        "cand_cal": CAND_DIR / "calibration_manifest.json",
        "cand_prov": CAND_DIR / "candidate_provenance_manifest.json",
        "orig_weights": ORIG_DIR / "model.safetensors",
        "orig_cal": ORIG_DIR / "calibration_manifest.json",
        "srv_weights": SRV_DIR / "model.safetensors",
    }
    for key, p in checks.items():
        actual = CG.compute_file_sha256(p)
        if actual != EXPECTED_SHAS[key]:
            raise RuntimeError(f"BLOCKED hash mismatch on {key} ({p}): {actual} != {EXPECTED_SHAS[key]}")
    for name, info in proto["frozen_evaluation_inputs"].items():
        actual = CG.compute_file_sha256(REPO / info["path"])
        if actual != info["sha256"]:
            raise RuntimeError(f"BLOCKED frozen suite drift on {name}: {actual} != {info['sha256']}")
    ugc_manifest = json.loads(UGC_MANIFEST_PATH.read_text(encoding="utf-8"))
    actual_ugc = CG.compute_file_sha256(UGC_PATH)
    if actual_ugc != ugc_manifest["sha256"]:
        raise RuntimeError(f"BLOCKED unseen_domain_gate drift: {actual_ugc} != {ugc_manifest['sha256']}")


def _verify_manifest_runtime_parity(model_dir: Path, cal_manifest: Path) -> dict[str, Any]:
    """Compare ModelContainer(calibration_manifest_path=...) vs GateSequenceClassifier."""
    import torch

    texts = [
        "How do I return a Tiki Trading item within 30 days?",
        "Where is my package right now?",
        "Can I drop off my parcel at a physical store reception desk for an immediate return inspection?",
        "Can you recommend a coffee recipe?",
    ]
    mc = ModelContainer()
    mc.load(model_dir, calibration_manifest_path=cal_manifest)
    if not mc.is_trained_ready():
        return {"checked": True, "passed": False, "reason": "model_container_not_ready_with_manifest"}
    cal = CG.validate_calibration_manifest(model_dir, cal_manifest)
    rej = cal["rejector"] if (cal["rejector"] and cal["rejector"].get("enabled", True) is not False) else None
    gate = CG.GateSequenceClassifier(
        "parity-manifest",
        model_dir,
        temperature=float(cal["temperature"] or 1.0),
        calibrated=bool(cal["calibrated"]),
        rejector=rej,
    )
    tok_mis, lbl_mis, sk_mis = 0, 0, 0
    max_conf_diff, max_margin_diff = 0.0, 0.0
    for txt in texts:
        mc_tok = mc.tokenizer(txt, max_length=64, padding="max_length", truncation=True, return_tensors="pt")
        g_tok = gate.tokenizer(txt, max_length=64, padding="max_length", truncation=True, return_tensors="pt")
        if not torch.equal(mc_tok["input_ids"], g_tok["input_ids"]) or not torch.equal(mc_tok["attention_mask"], g_tok["attention_mask"]):
            tok_mis += 1
        mp = mc.predict(txt, top_k_count=5, calibrated=bool(cal["calibrated"]))
        gp = gate.predict(txt, top_k_count=5)
        if mp["intent"] != gp["intent"]:
            lbl_mis += 1
        if mp["score_kind"] != gp["score_kind"]:
            sk_mis += 1
        max_conf_diff = max(max_conf_diff, abs(float(mp["confidence"]) - float(gp["confidence"])))
        max_margin_diff = max(max_margin_diff, abs(float(mp["margin"]) - float(gp["margin"])))

    mc_unpinned = ModelContainer()
    mc_unpinned.load(model_dir)
    fail_closed_unpinned = (not mc_unpinned.is_ready()) and (not mc_unpinned.verified)

    passed = (
        mc.validate_label_bijection()
        and tok_mis == 0
        and lbl_mis == 0
        and sk_mis == 0
        and max_conf_diff < 1e-5
        and max_margin_diff < 1e-5
        and fail_closed_unpinned
    )
    return {
        "checked": True,
        "passed": passed,
        "calibration_manifest_path": str(cal_manifest.relative_to(REPO)).replace("\\", "/"),
        "model_version": mc.model_version,
        "temperature": float(cal["temperature"] or 1.0),
        "calibrated": bool(cal["calibrated"]),
        "tokenization_mismatches": tok_mis,
        "label_mismatches": lbl_mis,
        "score_kind_mismatches": sk_mis,
        "max_confidence_abs_diff": round(max_conf_diff, 10),
        "max_margin_abs_diff": round(max_margin_diff, 10),
        "fail_closed_without_manifest": fail_closed_unpinned,
    }


def _eval_case_with_privacy(
    clf: CG.GateSequenceClassifier,
    mc: ModelContainer,
    mc_calibrated: bool,
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
    rec = V4P1._eval_case(
        clf, engine, runner, policy_v2,
        suite=suite, cid=cid, text=text, gold=gold,
        ctx_dict=ctx_dict, as_of=as_of, meta=meta,
    )
    masked_text, pii_map = pseudonymize(text, {})
    changed = masked_text != text

    if changed or suite == "unseen36":
        mc_pred = mc.predict(masked_text, top_k_count=5, calibrated=mc_calibrated)
        gate_masked = clf.predict(masked_text, top_k_count=5) if changed else None
        if gate_masked is not None:
            mc_vs_gate_intent_match = mc_pred["intent"] == gate_masked["intent"]
            mc_vs_gate_conf_diff = abs(float(mc_pred["confidence"]) - float(gate_masked["confidence"]))
        else:
            mc_vs_gate_intent_match = mc_pred["intent"] == rec["pred_intent"]
            mc_vs_gate_conf_diff = abs(float(mc_pred["confidence"]) - float(rec["conf"]))
    else:
        mc_pred = {"intent": rec["pred_intent"], "raw_intent": rec["raw_intent"], "confidence": rec["conf"], "raw_confidence": rec["raw_conf"], "margin": rec["margin"], "raw_margin": rec["raw_margin"], "rejected_by_experimental_adapter": rec["rejected_by_adapter"], "selective_accepted": rec["selective_accepted"]}
        mc_vs_gate_intent_match = True
        mc_vs_gate_conf_diff = 0.0

    if changed:
        priv_raw_post_act, _ = V4P1._raw_threshold_eligible(mc_pred, policy_v2, apply_rejector=True)
        ctx = V4P1.RoutingContext(
            ticket_customer_id=ctx_dict.get("ticket_customer_id", "demo-customer"),
            verified_scope=ctx_dict.get("verified_scope", "ticket:read order:read"),
            extracted_slots=ctx_dict.get("extracted_slots") or {},
            is_personal_lookup=bool(ctx_dict.get("is_personal_lookup", False)),
        )
        priv_dec = decide_route(V4P1._intent_pred(mc_pred, clf.name), ctx, policy_v2)
        priv_bare_act, _ = CG._apply_adapter_routing_guard(priv_dec.action, mc_pred)
        priv_an = engine._analyse({"message": masked_text, "as_of": as_of})[0]
        priv_eng_act = CG._adapt_action(priv_an["routing"]["recommendation"])
        priv_eng_intent = priv_an["intent"]["label"]
        priv_rr = runner.run(masked_text, ctx, run_id=f"{clf.name}-priv-{suite}-{cid}")
        priv_run_act = priv_rr["action"]
        priv_run_intent = priv_rr["predicted_intent"]
    else:
        priv_raw_post_act = rec["raw_post_action"]
        priv_bare_act = rec["bare_action"]
        priv_eng_act = rec["engine_action"]
        priv_eng_intent = rec["engine_intent"]
        priv_run_act = rec["runner_action"]
        priv_run_intent = rec["runner_intent"]

    rec.update({
        "masked_text": masked_text if changed else None,
        "privacy_changed": changed,
        "pii_token_count": len(pii_map),
        "mc_masked_intent": mc_pred["intent"],
        "mc_masked_conf": round(float(mc_pred["confidence"]), 6),
        "mc_vs_gate_intent_match": mc_vs_gate_intent_match,
        "mc_vs_gate_conf_diff": round(mc_vs_gate_conf_diff, 8),
        "priv_raw_post_action": priv_raw_post_act,
        "priv_bare_action": priv_bare_act,
        "priv_engine_action": priv_eng_act,
        "priv_engine_intent": priv_eng_intent,
        "priv_runner_action": priv_run_act,
        "priv_runner_intent": priv_run_intent,
        "priv_flip_intent": mc_pred["intent"] != rec["pred_intent"],
        "priv_flip_raw_post_action": priv_raw_post_act != rec["raw_post_action"],
        "priv_flip_engine_action": priv_eng_act != rec["engine_action"],
        "priv_flip_runner_action": priv_run_act != rec["runner_action"],
    })
    return rec


def _summarize_privacy_suite(recs: list[dict[str, Any]], *, nodraft_golds: set[str] | None = None, all_rows_nodraft: bool = False, excluded_ids: set[str] | None = None) -> dict[str, Any]:
    excl = excluded_ids or set()
    changed = [r for r in recs if r["privacy_changed"]]
    leaks = {}
    if nodraft_golds is not None or all_rows_nodraft:
        for surf, akey, ikey in (
            ("priv_raw_post", "priv_raw_post_action", "mc_masked_intent"),
            ("priv_bare", "priv_bare_action", "mc_masked_intent"),
            ("priv_engine", "priv_engine_action", "priv_engine_intent"),
            ("priv_runner", "priv_runner_action", "priv_runner_intent"),
        ):
            leaks[surf] = [
                {"id": r["id"], "gold": r["gold"], "pred": r[ikey], "conf": r["mc_masked_conf"], "text": r["masked_text"] or r["text"]}
                for r in recs
                if r["id"] not in excl
                and (all_rows_nodraft or (nodraft_golds is not None and r["gold"] in nodraft_golds))
                and r[akey] == "retrieve_draft"
            ]
    return {
        "n": len(recs),
        "privacy_changed_rows": len(changed),
        "mc_vs_gate_intent_mismatches": sum(1 for r in recs if not r["mc_vs_gate_intent_match"]),
        "mc_vs_gate_max_conf_diff": max((r["mc_vs_gate_conf_diff"] for r in recs), default=0.0),
        "intent_flips_raw_vs_postprivacy": [r["id"] for r in changed if r["priv_flip_intent"]],
        "raw_post_action_flips": [r["id"] for r in changed if r["priv_flip_raw_post_action"]],
        "engine_action_flips": [r["id"] for r in changed if r["priv_flip_engine_action"]],
        "runner_action_flips": [r["id"] for r in changed if r["priv_flip_runner_action"]],
        "nodraft_leaks": leaks,
    }


def _eval_bitext_with_sensitivity(clf: CG.GateSequenceClassifier, mc: ModelContainer, mc_calibrated: bool, policy_v2: Any, bitext_path: Path) -> dict[str, Any]:
    rows = CG.load_jsonl(bitext_path)

    def _run_subset(sub_rows: list[dict[str, Any]]) -> dict[str, Any]:
        y_true, y_pred = [], []
        raw_pre_esc_leaks, raw_post_esc_leaks = 0, 0
        raw_pre_sup11_corr, raw_post_sup11_corr = 0, 0
        sup11_n, esc34_n = 0, 0
        leak_examples: list[dict[str, Any]] = []
        for r in sub_rows:
            gold = r["true_intent"]
            pred = clf.predict(r["text"], top_k_count=2)
            y_true.append(gold)
            y_pred.append(pred["intent"])
            pre_act, _ = V4P1._raw_threshold_eligible(pred, policy_v2, apply_rejector=False)
            post_act, _ = V4P1._raw_threshold_eligible(pred, policy_v2, apply_rejector=True)
            if gold in V4P1.SUPPORTED_11:
                sup11_n += 1
                if pre_act == "retrieve_draft" and pred["raw_intent"] == gold:
                    raw_pre_sup11_corr += 1
                if post_act == "retrieve_draft" and pred["intent"] == gold:
                    raw_post_sup11_corr += 1
            elif gold in V4P1.ESCALATED_34_INTENTS:
                esc34_n += 1
                if pre_act == "retrieve_draft":
                    raw_pre_esc_leaks += 1
                if post_act == "retrieve_draft":
                    raw_post_esc_leaks += 1
                    leak_examples.append({
                        "sample_id": r["sample_id"],
                        "gold": gold,
                        "pred": pred["intent"],
                        "conf": round(float(pred["confidence"]), 6),
                        "text": r["text"],
                    })
        return {
            "n": len(sub_rows),
            "accuracy_46": M.accuracy(y_true, y_pred),
            "macro_f1_46": M.macro_f1(y_true, y_pred, labels=V4P1.STANDARD_INTENTS_46),
            "sup11_n": sup11_n,
            "esc34_n": esc34_n,
            "raw_pre_sup11_correct_draft": raw_pre_sup11_corr,
            "raw_post_sup11_correct_draft": raw_post_sup11_corr,
            "raw_pre_esc34_unsafe_leaks": raw_pre_esc_leaks,
            "raw_post_esc34_unsafe_leaks": raw_post_esc_leaks,
            "raw_post_esc34_leak_examples": leak_examples,
        }

    full_res = _run_subset(rows)
    clean_rows = [r for r in rows if r["sample_id"] not in INHERITED_BITEXT_OVERLAP_IDS]
    excl3_res = _run_subset(clean_rows)

    priv_changed = 0
    priv_flips = 0
    priv_esc_leaks = 0
    for r in rows:
        masked, _ = pseudonymize(r["text"], {})
        if masked != r["text"]:
            priv_changed += 1
            mc_p = mc.predict(masked, top_k_count=2, calibrated=mc_calibrated)
            raw_p = clf.predict(r["text"], top_k_count=2)
            if mc_p["intent"] != raw_p["intent"]:
                priv_flips += 1
            act, _ = V4P1._raw_threshold_eligible(mc_p, policy_v2, apply_rejector=True)
            if r["true_intent"] in V4P1.ESCALATED_34_INTENTS and act == "retrieve_draft":
                priv_esc_leaks += 1

    return {
        "full_6690": full_res,
        "exclude_3_inherited_overlaps_6687": excl3_res,
        "excluded_sample_ids": sorted(INHERITED_BITEXT_OVERLAP_IDS),
        "postprivacy_changed_subset": {
            "changed_rows": priv_changed,
            "intent_flips": priv_flips,
            "esc34_unsafe_leaks_on_changed": priv_esc_leaks,
        },
    }


def _summarize_unseen_gate(recs: list[dict[str, Any]]) -> dict[str, Any]:
    groups = sorted({r["meta"]["group_id"] for r in recs})
    slices: dict[str, Any] = {}
    for sname in sorted({r["meta"]["slice"] for r in recs}):
        sub = [r for r in recs if r["meta"]["slice"] == sname]
        s_groups = {r["meta"]["group_id"] for r in sub}
        entry: dict[str, Any] = {
            "n": len(sub),
            "distinct_base_groups": len(s_groups),
            "classifier_intent_acc_raw": sum(1 for r in sub if r["pred_intent"] == r["gold"]) / len(sub) if sname != "novel_ood" else None,
            "classifier_intent_acc_postprivacy": sum(1 for r in sub if r["mc_masked_intent"] == r["gold"]) / len(sub) if sname != "novel_ood" else None,
            "surfaces": {},
        }
        for surf, akey, ikey in (
            ("raw_pre", "raw_pre_action", "raw_intent"),
            ("raw_post", "raw_post_action", "pred_intent"),
            ("bare", "bare_action", "pred_intent"),
            ("engine", "engine_action", "engine_intent"),
            ("runner", "runner_action", "runner_intent"),
            ("priv_raw_post", "priv_raw_post_action", "mc_masked_intent"),
            ("priv_engine", "priv_engine_action", "priv_engine_intent"),
            ("priv_runner", "priv_runner_action", "priv_runner_intent"),
        ):
            if any(r["meta"]["must_not_draft"] for r in sub):
                leaks = [{"id": r["id"], "gold": r["gold"], "pred": r[ikey], "conf": r["conf"]} for r in sub if r[akey] == "retrieve_draft"]
                strict = sum(1 for r in sub if r[akey] in r["meta"]["expected_actions"])
                entry["surfaces"][surf] = {"unsafe_draft_leaks": leaks, "strict_action_match": strict}
            else:
                corr = [r["id"] for r in sub if r[akey] == "retrieve_draft" and r[ikey] == r["gold"]]
                wrong = [{"id": r["id"], "gold": r["gold"], "pred": r[ikey], "conf": r["conf"]} for r in sub if r[akey] == "retrieve_draft" and r[ikey] != r["gold"]]
                dropped = [{"id": r["id"], "gold": r["gold"], "pred": r[ikey], "act": r[akey], "conf": r["conf"]} for r in sub if r[akey] != "retrieve_draft"]
                entry["surfaces"][surf] = {"correct_draft": len(corr), "wrong_draft": wrong, "dropped_or_non_draft": dropped}
        slices[sname] = entry

    return {
        "n": len(recs),
        "distinct_base_groups": len(groups),
        "slices": slices,
        "return_contrast_confusions": [
            {
                "id": r["id"],
                "gold": r["gold"],
                "raw_pred": r["pred_intent"],
                "raw_conf": r["conf"],
                "priv_pred": r["mc_masked_intent"],
                "raw_post_act": r["raw_post_action"],
                "runner_act": r["runner_action"],
                "priv_runner_act": r["priv_runner_action"],
            }
            for r in recs
            if r["meta"]["slice"].startswith("return_contrast")
            and (r["pred_intent"] != r["gold"] or (r["meta"]["must_not_draft"] and (r["raw_post_action"] == "retrieve_draft" or r["runner_action"] == "retrieve_draft")))
        ],
    }


def _paired_diffs(by_tag: dict[str, dict[tuple[str, str], dict[str, Any]]], cand_tag: str, base_tag: str) -> dict[str, Any]:
    diffs: dict[str, Any] = {}
    suites = ("unseen36", "fresh34", "ind36", "sealed72", "final24", "sa156", "noise420", "oos80", "pos175", "neg51", "cand_pos122", "cand_neg39")
    for sname in suites:
        keys = [k for k in by_tag[cand_tag] if k[0] == sname]
        diffs[sname] = {
            "runner_changed": [
                {
                    "id": cid, "gold": by_tag[cand_tag][(s, cid)]["gold"],
                    f"{base_tag}_act": by_tag[base_tag][(s, cid)]["runner_action"],
                    f"{base_tag}_pred": by_tag[base_tag][(s, cid)]["pred_intent"],
                    f"{cand_tag}_act": by_tag[cand_tag][(s, cid)]["runner_action"],
                    f"{cand_tag}_pred": by_tag[cand_tag][(s, cid)]["pred_intent"],
                }
                for s, cid in keys
                if by_tag[base_tag][(s, cid)]["runner_action"] != by_tag[cand_tag][(s, cid)]["runner_action"]
                or by_tag[base_tag][(s, cid)]["pred_intent"] != by_tag[cand_tag][(s, cid)]["pred_intent"]
            ],
            "engine_changed": [
                {
                    "id": cid, "gold": by_tag[cand_tag][(s, cid)]["gold"],
                    f"{base_tag}_act": by_tag[base_tag][(s, cid)]["engine_action"],
                    f"{base_tag}_pred": by_tag[base_tag][(s, cid)]["engine_intent"],
                    f"{cand_tag}_act": by_tag[cand_tag][(s, cid)]["engine_action"],
                    f"{cand_tag}_pred": by_tag[cand_tag][(s, cid)]["engine_intent"],
                }
                for s, cid in keys
                if by_tag[base_tag][(s, cid)]["engine_action"] != by_tag[cand_tag][(s, cid)]["engine_action"]
                or by_tag[base_tag][(s, cid)]["engine_intent"] != by_tag[cand_tag][(s, cid)]["engine_intent"]
            ],
            "raw_post_changed": [
                {
                    "id": cid, "gold": by_tag[cand_tag][(s, cid)]["gold"],
                    f"{base_tag}_act": by_tag[base_tag][(s, cid)]["raw_post_action"],
                    f"{base_tag}_pred": by_tag[base_tag][(s, cid)]["pred_intent"],
                    f"{cand_tag}_act": by_tag[cand_tag][(s, cid)]["raw_post_action"],
                    f"{cand_tag}_pred": by_tag[cand_tag][(s, cid)]["pred_intent"],
                }
                for s, cid in keys
                if by_tag[base_tag][(s, cid)]["raw_post_action"] != by_tag[cand_tag][(s, cid)]["raw_post_action"]
                or by_tag[base_tag][(s, cid)]["pred_intent"] != by_tag[cand_tag][(s, cid)]["pred_intent"]
            ],
            "postprivacy_runner_changed": [
                {
                    "id": cid, "gold": by_tag[cand_tag][(s, cid)]["gold"],
                    f"{base_tag}_act": by_tag[base_tag][(s, cid)]["priv_runner_action"],
                    f"{base_tag}_pred": by_tag[base_tag][(s, cid)]["mc_masked_intent"],
                    f"{cand_tag}_act": by_tag[cand_tag][(s, cid)]["priv_runner_action"],
                    f"{cand_tag}_pred": by_tag[cand_tag][(s, cid)]["mc_masked_intent"],
                }
                for s, cid in keys
                if by_tag[base_tag][(s, cid)]["priv_runner_action"] != by_tag[cand_tag][(s, cid)]["priv_runner_action"]
                or by_tag[base_tag][(s, cid)]["mc_masked_intent"] != by_tag[cand_tag][(s, cid)]["mc_masked_intent"]
            ],
        }
    return diffs


def main() -> None:
    t0 = time.perf_counter()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    proto = json.loads(PROTO_PATH.read_text(encoding="utf-8"))
    _check_frozen_preconditions(proto)

    root = A._bootstrap_target_repo(REPO)
    rel = json.loads((root / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    retr = RetrievalAdapter(
        kb_path=str(root / "data/knowledge/approved_kb.v2.json"),
        allowed_document_versions={(d["document_id"], str(d["version"])) for d in rel["documents"]},
    )
    comm = CommerceAdapter(data_path=str(root / "data/knowledge/mock_orders.json"))
    pol_path = root / "apps/core_backend/config/policies/intent_policy.v2.json"
    policy, pv2 = json.loads(pol_path.read_text(encoding="utf-8")), load_policy_v2(pol_path)

    # 1. Production classifier acceptance gate on candidate vs Serving
    gate_blocker: str | None = None
    gate_report: dict[str, Any] | None = None
    try:
        gate_report = CG.run_classifier_acceptance_gate(
            repo_root=root,
            candidate_name="fit2-orig-ret-channel-fit-v1",
            candidate_dir=CAND_DIR,
            serving_dir=SRV_DIR,
            candidate_manifest_path=CAND_DIR / "candidate_provenance_manifest.json",
            calibration_manifest_path=CAND_DIR / "calibration_manifest.json",
            train_split_path=CAND_REC_INPUTS / "full_train_split.jsonl",
            calibration_split_path=CAND_REC_INPUTS / "full_cal_split.jsonl",
            eval_split_path=CAND_REC_INPUTS / "boundary_pos_evaluation.jsonl",
        )
        (OUT_DIR / "gate_report_cand_fit_v1.json").write_text(
            json.dumps(gate_report, indent=2, default=str) + "\n", encoding="utf-8"
        )
    except Exception as exc:
        gate_blocker = f"{type(exc).__name__}: {exc}"

    # 2. Symmetric runtime parity (calibration_manifest runtime load + serving/fail-closed) + engine rejection check
    runtime_parity = {
        "orig_fit2_manifest_runtime": _verify_manifest_runtime_parity(ORIG_DIR, ORIG_DIR / "calibration_manifest.json"),
        "cand_fit_v1_manifest_runtime": _verify_manifest_runtime_parity(CAND_DIR, CAND_DIR / "calibration_manifest.json"),
        "serving_pinned_and_fail_closed_cand": CG.verify_runtime_score_parity(SRV_DIR, unpinned_dir=CAND_DIR, repo_root=root),
        "engine_rejection_enforcement": CG.verify_engine_rejection_enforcement(root),
    }

    # 3. Load all suites
    unseen36 = CG.load_jsonl(UGC_PATH)
    fresh34 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["fresh34"]["path"])
    ind36 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["ind36"]["path"])
    sealed72 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["old_sealed72"]["path"])
    final24 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["final24"]["path"])
    sa156 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["sa156"]["path"])
    noise420 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["noise420"]["path"])
    oos80 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["oos80"]["path"])
    pos175 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["pos175"]["path"])
    neg51 = CG.load_jsonl(REPO / proto["frozen_evaluation_inputs"]["neg51"]["path"])
    cand_pos122 = CG.load_jsonl(CAND_REC_INPUTS / "boundary_pos_evaluation.jsonl")
    cand_neg39 = CG.load_jsonl(CAND_REC_INPUTS / "boundary_neg_evaluation.jsonl")
    bitext_path = REPO / proto["frozen_evaluation_inputs"]["bitext6690"]["path"]

    models = [
        {
            "tag": "orig_fit2",
            "dir": ORIG_DIR,
            "cal_manifest": ORIG_DIR / "calibration_manifest.json",
            "cand_manifest": ORIG_DIR / "candidate_provenance_manifest.json",
        },
        {
            "tag": "cand_fit_v1",
            "dir": CAND_DIR,
            "cal_manifest": CAND_DIR / "calibration_manifest.json",
            "cand_manifest": CAND_DIR / "candidate_provenance_manifest.json",
        },
    ]

    summaries: dict[str, Any] = {
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "offline_conditions": (
            "0 live LLM calls; _MockNoCallLLM for Engine._analyse only; "
            "_OfflineValidSpyLLM for PipelineRunner draft eligibility/snapshot only. "
            "fresh34 treated strictly as historical regression, not unseen holdout. "
            "bitext6690 reports full 6690 AND exclude-3 inherited noisy train/test overlap sensitivity (6687)."
        ),
        "gate_cand_decision": gate_report["gate_decision"] if gate_report else "BLOCKER",
        "gate_cand_failures": gate_report["failure_reasons"] if gate_report else [gate_blocker],
        "runtime_parity": runtime_parity,
        "models": {},
    }

    all_preds: dict[str, list[dict[str, Any]]] = {}
    with tempfile.TemporaryDirectory() as td:
        for spec in models:
            tm0 = time.perf_counter()
            tag = spec["tag"]
            clf, cal = V4P1._load_clf(spec)
            mc = ModelContainer()
            mc.load(spec["dir"], calibration_manifest_path=spec["cal_manifest"])
            assert mc.is_trained_ready(), f"ModelContainer not ready for {tag}"
            mc_calibrated = bool(cal["calibrated"])

            engine = Engine(clf, retr, A._MockNoCallLLM(), {"release_id": f"eval-{tag}", "model_version": tag}, policy)
            runner = PipelineRunner(
                intent_client=A._MockIntentClient(clf),
                commerce_adapter=comm,
                retrieval_adapter=retr,
                store=PersistentStore(db_path=str(Path(td) / f"{tag}.sqlite3")),
                llm_client=A._OfflineValidSpyLLM(),
                policy=pv2,
            )

            ev = lambda **kw: _eval_case_with_privacy(clf, mc, mc_calibrated, engine, runner, pv2, **kw)

            recs_unseen = [ev(suite="unseen36", cid=r["id"], text=r["text"], gold=r["true_intent"], ctx_dict=r["context"], as_of=r["context"]["as_of"],
                              meta={"slice": r["slice"], "subgroup": r["subgroup"], "group_id": r["group_id"], "must_not_draft": r["must_not_draft"], "expected_actions": r["expected_actions"]}) for r in unseen36]
            recs_fresh = [ev(suite="fresh34", cid=r["id"], text=r["text"], gold=r["true_intent"], ctx_dict=r["context"], as_of=r["context"]["as_of"],
                             meta={"slice": r["slice"], "subgroup": r["subgroup"], "must_not_draft": r["must_not_draft"]}) for r in fresh34]
            recs_ind36 = [ev(suite="ind36", cid=r["id"], text=r["text"], gold=r["true_intent"], ctx_dict=r["context"], as_of=r["context"]["as_of"],
                             meta={"slice": r["slice"], "subgroup": r["subgroup"], "must_not_draft": r["must_not_draft"]}) for r in ind36]
            recs_s72 = [ev(suite="sealed72", cid=r["id"], text=r["text"], gold=r["true_intent"],
                           ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {"order_id": r["order_id"]} if r.get("order_id") else {}, "is_personal_lookup": bool(r.get("order_id"))},
                           as_of="2026-06-15T10:00:00Z",
                           meta={"slice": r["slice"], "subgroup": "answerable" if r["slice"] == "supported_answerable" else r["slice"], "must_not_draft": r["must_not_draft"]}) for r in sealed72]
            recs_fa24 = [ev(suite="final24", cid=r["id"], text=r["query"], gold=r.get("intent"),
                            ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {"order_id": r["order_id"]} if r.get("order_id") else {}, "is_personal_lookup": bool(r.get("order_id"))},
                            as_of=r.get("as_of") or "2026-06-15T10:00:00Z",
                            meta={"is_answerable": bool(r.get("is_answerable")), "fixture_boundary": r.get("fixture_boundary")}) for r in final24]
            recs_sa156 = [ev(suite="sa156", cid=r["id"], text=r["text"], gold=r.get("true_intent"), ctx_dict=r.get("context") or {}, as_of="2026-06-15T10:00:00Z",
                             meta={"draft_expected": bool(r["expected"].get("draft_expected")), "must_escalate": bool(r["expected"].get("must_escalate")), "expected_actions": r["expected"]["actions"]}) for r in sa156]
            recs_noise = [ev(suite="noise420", cid=r["id"], text=r["text"], gold=r["true_intent"],
                             ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
                             as_of="2026-06-15T10:00:00Z", meta={"kind": r.get("kind")}) for r in noise420]
            recs_oos = [ev(suite="oos80", cid=r["id"], text=r["text"], gold="ood",
                           ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
                           as_of="2026-06-15T10:00:00Z", meta={"category": r.get("category")}) for r in oos80]
            recs_pos175 = [ev(suite="pos175", cid=r["sample_id"], text=r["text"], gold=r["true_intent"],
                              ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
                              as_of="2026-06-15T10:00:00Z", meta={"source": r.get("source")}) for r in pos175]
            recs_neg51 = [ev(suite="neg51", cid=r["sample_id"], text=r["text"], gold=r.get("intent") or "ood",
                             ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
                             as_of="2026-06-15T10:00:00Z", meta={"category": r.get("category"), "source": r.get("source")}) for r in neg51]
            recs_cpos122 = [ev(suite="cand_pos122", cid=r["sample_id"], text=r["text"], gold=r["true_intent"],
                               ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
                               as_of="2026-06-15T10:00:00Z", meta={"source": r.get("source")}) for r in cand_pos122]
            recs_cneg39 = [ev(suite="cand_neg39", cid=r["sample_id"], text=r["text"], gold=r.get("intent") or "ood",
                              ctx_dict={"ticket_customer_id": "demo-customer", "extracted_slots": {}, "is_personal_lookup": False},
                              as_of="2026-06-15T10:00:00Z", meta={"category": r.get("category"), "source": r.get("source")}) for r in cand_neg39]

            combined = (
                recs_unseen + recs_fresh + recs_ind36 + recs_s72 + recs_fa24
                + recs_sa156 + recs_noise + recs_oos + recs_pos175 + recs_neg51
                + recs_cpos122 + recs_cneg39
            )
            all_preds[tag] = combined
            (OUT_DIR / f"predictions_{tag}.jsonl").write_text("\n".join(json.dumps(x) for x in combined) + "\n", encoding="utf-8")

            bitext_res = _eval_bitext_with_sensitivity(clf, mc, mc_calibrated, pv2, bitext_path)

            esc34_set = set(V4P1.ESCALATED_34_INTENTS)
            summaries["models"][tag] = {
                "weights_sha256": CG.compute_file_sha256(spec["dir"] / "model.safetensors"),
                "calibration_sha256": CG.compute_file_sha256(spec["cal_manifest"]),
                "temperature": float(cal["temperature"] or 1.0),
                "calibrated": bool(cal["calibrated"]),
                "rejector_enabled": bool(clf.rejector is not None),
                "unseen_domain_gate_36": _summarize_unseen_gate(recs_unseen),
                "historical_fresh_34": V4P1._summarize_holdout_like(recs_fresh, ("novel_ood", "mandatory_escalation")),
                "independent_36": V4P1._summarize_holdout_like(recs_ind36, ("novel_ood", "mandatory_escalation")),
                "old_sealed_72": V4P1._summarize_holdout_like(recs_s72, ("novel_ood", "mandatory_escalation_compound")),
                "final_acceptance_24": V4P1._summarize_final24(recs_fa24),
                "system_acceptance_156": V4P1._summarize_sa156(recs_sa156),
                "ml_noise_420": V4P1._summarize_noise420(recs_noise),
                "ml_oos_80": {
                    surf: [r["id"] for r in recs_oos if r[akey] == "retrieve_draft"]
                    for surf, akey in (("raw_pre", "raw_pre_action"), ("raw_post", "raw_post_action"), ("bare", "bare_action"), ("engine", "engine_action"), ("runner", "runner_action"), ("priv_raw_post", "priv_raw_post_action"), ("priv_engine", "priv_engine_action"), ("priv_runner", "priv_runner_action"))
                },
                "isolated_eval_pos175_neg51": V4P1._summarize_isolated(recs_pos175, recs_neg51),
                "cand_split_boundary_pos122_neg39": V4P1._summarize_isolated(recs_cpos122, recs_cneg39),
                "bitext_test_6690": bitext_res,
                "postprivacy_parity": {
                    "unseen36": _summarize_privacy_suite(recs_unseen, nodraft_golds=esc34_set | {"ood"}),
                    "final24": _summarize_privacy_suite([r for r in recs_fa24 if not r["meta"]["is_answerable"] and r["meta"]["fixture_boundary"] == "active_kb"], all_rows_nodraft=True),
                    "sa156_all": _summarize_privacy_suite(recs_sa156),
                    "sa156_mand63": _summarize_privacy_suite([r for r in recs_sa156 if r["meta"]["must_escalate"]], all_rows_nodraft=True, excluded_ids=set(CG.KNOWN_UNINJECTED_ACCEPTANCE_IDS)),
                    "noise420": _summarize_privacy_suite(recs_noise),
                    "oos80": _summarize_privacy_suite(recs_oos, nodraft_golds={"ood"}),
                    "ind36": _summarize_privacy_suite(recs_ind36, nodraft_golds=esc34_set | {"ood"}),
                    "ind36_must_not_draft": _summarize_privacy_suite([r for r in recs_ind36 if r["meta"]["must_not_draft"]], all_rows_nodraft=True),
                    "old_sealed72": _summarize_privacy_suite([r for r in recs_s72 if r["meta"]["must_not_draft"]], all_rows_nodraft=True),
                    "fresh34": _summarize_privacy_suite([r for r in recs_fresh if r["meta"]["must_not_draft"]], all_rows_nodraft=True),
                    "pos175": _summarize_privacy_suite(recs_pos175, nodraft_golds=esc34_set),
                    "neg51": _summarize_privacy_suite(recs_neg51, nodraft_golds={"ood"}),
                },
                "duration_seconds": round(time.perf_counter() - tm0, 2),
            }
            print(f"FINISHED MODEL {tag} in {summaries['models'][tag]['duration_seconds']}s", flush=True)

    by_tag = {tag: {(r["suite"], r["id"]): r for r in recs} for tag, recs in all_preds.items()}
    summaries["paired_diffs_cand_vs_orig_fit2"] = _paired_diffs(by_tag, "cand_fit_v1", "orig_fit2")

    # 4. Evaluate frozen acceptance criteria on cand_fit_v1
    cm = summaries["models"]["cand_fit_v1"]
    crit = {
        "floor_final24_runner_ans12_ge_10": len(cm["final_acceptance_24"]["runner"]["ans12_correct"]) >= 10,
        "floor_sa156_runner_sup34_ge_25": cm["system_acceptance_156"]["runner"]["sup34_correct_draft"] >= 25,
        "floor_noise420_macro_f1_12_ge_08573": cm["ml_noise_420"]["macro_f1_12"] >= 0.8573,
        "floor_noise420_gate_correct_ge_267": cm["ml_noise_420"]["bare"]["correct_draft"] >= 267,
        "floor_noise420_runner_correct_ge_260": cm["ml_noise_420"]["runner"]["correct_draft"] >= 260,
        "zero_leak_pos175_esc34": all(len(cm["isolated_eval_pos175_neg51"][s]["esc34_leaks"]) == 0 for s in ("raw_pre", "raw_post", "engine", "runner")) and len(cm["postprivacy_parity"]["pos175"]["nodraft_leaks"]["priv_raw_post"]) == 0 and len(cm["postprivacy_parity"]["pos175"]["nodraft_leaks"]["priv_runner"]) == 0,
        "zero_leak_neg51": all(len(cm["isolated_eval_pos175_neg51"][s]["neg51_leaks"]) == 0 for s in ("raw_pre", "raw_post", "engine", "runner")) and len(cm["postprivacy_parity"]["neg51"]["nodraft_leaks"]["priv_raw_post"]) == 0 and len(cm["postprivacy_parity"]["neg51"]["nodraft_leaks"]["priv_runner"]) == 0,
        "zero_leak_oos80": all(len(v) == 0 for v in cm["ml_oos_80"].values()),
        "zero_leak_ind36": all(len(cm["independent_36"][s]["leaks"]) == 0 for s in ("raw_pre", "raw_post", "bare", "engine", "runner")) and len(cm["postprivacy_parity"]["ind36_must_not_draft"]["nodraft_leaks"]["priv_raw_post"]) == 0 and len(cm["postprivacy_parity"]["ind36_must_not_draft"]["nodraft_leaks"]["priv_runner"]) == 0,
        "zero_leak_old_sealed72": all(len(cm["old_sealed_72"][s]["leaks"]) == 0 for s in ("raw_pre", "raw_post", "bare", "engine", "runner")) and len(cm["postprivacy_parity"]["old_sealed72"]["nodraft_leaks"]["priv_raw_post"]) == 0 and len(cm["postprivacy_parity"]["old_sealed72"]["nodraft_leaks"]["priv_runner"]) == 0,
        "zero_leak_fresh34": all(len(cm["historical_fresh_34"][s]["leaks"]) == 0 for s in ("raw_pre", "raw_post", "bare", "engine", "runner")) and len(cm["postprivacy_parity"]["fresh34"]["nodraft_leaks"]["priv_raw_post"]) == 0 and len(cm["postprivacy_parity"]["fresh34"]["nodraft_leaks"]["priv_runner"]) == 0,
        "zero_leak_final24_active_unans8": all(len(cm["final_acceptance_24"][s]["active_unans8_leaks"]) == 0 for s in ("raw_pre", "raw_post", "engine", "runner")) and len(cm["postprivacy_parity"]["final24"]["nodraft_leaks"]["priv_raw_post"]) == 0 and len(cm["postprivacy_parity"]["final24"]["nodraft_leaks"]["priv_runner"]) == 0,
        "zero_leak_sa156_mand63_real": all(len(cm["system_acceptance_156"][s]["mand63_real_leaks"]) == 0 for s in ("raw_pre", "raw_post", "engine", "runner")) and len(cm["postprivacy_parity"]["sa156_mand63"]["nodraft_leaks"]["priv_raw_post"]) == 0 and len(cm["postprivacy_parity"]["sa156_mand63"]["nodraft_leaks"]["priv_runner"]) == 0,
        "zero_leak_bitext6690_esc34": cm["bitext_test_6690"]["full_6690"]["raw_pre_esc34_unsafe_leaks"] == 0 and cm["bitext_test_6690"]["full_6690"]["raw_post_esc34_unsafe_leaks"] == 0 and cm["bitext_test_6690"]["postprivacy_changed_subset"]["esc34_unsafe_leaks_on_changed"] == 0,
        "zero_leak_unseen_domain_gate_36": all(
            len(cm["unseen_domain_gate_36"]["slices"][sl]["surfaces"][sf]["unsafe_draft_leaks"]) == 0
            for sl in ("return_contrast_escalated", "cross_intent_escalated", "novel_ood")
            for sf in ("raw_pre", "raw_post", "bare", "engine", "runner", "priv_raw_post", "priv_engine", "priv_runner")
        ) and len(cm["postprivacy_parity"]["unseen36"]["nodraft_leaks"]["priv_bare"]) == 0,
        "runtime_score_parity_passed": (
            bool(runtime_parity["cand_fit_v1_manifest_runtime"].get("passed"))
            and bool(runtime_parity["serving_pinned_and_fail_closed_cand"].get("passed"))
            and all(v["mc_vs_gate_intent_mismatches"] == 0 and v["mc_vs_gate_max_conf_diff"] < 1e-5 for v in cm["postprivacy_parity"].values())
        ),
    }
    overall = "ACCEPT" if all(crit.values()) else "REJECT"
    summaries["protocol_verdict"] = {
        "verdict": overall,
        "criteria": crit,
        "failed_criteria": [k for k, v in crit.items() if not v],
    }
    summaries["total_duration_seconds"] = round(time.perf_counter() - t0, 2)

    comp_path = OUT_DIR / "suites_comparison.json"
    comp_path.write_text(json.dumps(summaries, indent=2, default=str) + "\n", encoding="utf-8")

    tracked = [
        CAND_DIR / "model.safetensors",
        CAND_DIR / "calibration_manifest.json",
        CAND_DIR / "candidate_provenance_manifest.json",
        ORIG_DIR / "model.safetensors",
        ORIG_DIR / "calibration_manifest.json",
        SRV_DIR / "model.safetensors",
        PROTO_PATH,
        UGC_PATH,
        UGC_MANIFEST_PATH,
        OUT_DIR / "evaluate_candidate.py",
        OUT_DIR / "predictions_orig_fit2.jsonl",
        OUT_DIR / "predictions_cand_fit_v1.jsonl",
        comp_path,
    ]
    if (OUT_DIR / "gate_report_cand_fit_v1.json").exists():
        tracked.append(OUT_DIR / "gate_report_cand_fit_v1.json")

    manifest = {
        "branch": subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, text=True).strip(),
        "git_head": summaries["git_head"],
        "runtime_conditions": summaries["offline_conditions"],
        "commands": [".venv/Scripts/python.exe -B artifacts/evaluation/fit2_orig_ret_channel_fit_v1_independent_c_20261114/evaluate_candidate.py"],
        "sha256": {str(p.relative_to(REPO)).replace("\\", "/"): CG.compute_file_sha256(p) for p in tracked},
    }
    (OUT_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("DONE VERDICT =", overall, "FAILED =", summaries["protocol_verdict"]["failed_criteria"], "SECS =", summaries["total_duration_seconds"])


if __name__ == "__main__":
    main()
