"""Offline Fit2 independent gate evaluator (0 live LLM calls). Rules below were fixed BEFORE any model output was seen.

PASS (candidate) requires ALL of:
  R1 new holdout: 0 drafts on novel_ood + mandatory_escalation + human_agent via Engine AND PipelineRunner.
  R2 new holdout supported-answerable(11), PipelineRunner: correct-intent drafts >= unchanged serving's, wrong-intent drafts <= serving's, correct >= 1 (no all-abstain).
  R3 fixed gate (run_classifier_acceptance_gate: mandatory63/OOS80/noise420/system156/final24 + provenance/parity) == PASS.
  R4 old sealed72: 0 drafts on novel_ood + mandatory_escalation_compound via Engine AND PipelineRunner.
Bare classifier route is reported separately and is not a pass criterion (not HTTP-reachable). No threshold or gold edits.
Usage: python evaluate.py --name N --model-dir D [--calibration-manifest M --candidate-manifest P --splits DIR --gate] ; python evaluate.py verdict SERVING.json CAND.json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
import gate as G  # noqa: E402
from scripts import run_closure_candidate_audit as A  # noqa: E402

NODRAFT = ("novel_ood", "mandatory_escalation")


def eval_holdout(clf, rows, retriever, commerce, policy, policy_v2, tmp):
    from apps.ai_service.engine import Engine
    from apps.core_backend.intent.routing import RoutingContext
    from apps.core_backend.intent.schemas import IntentPrediction
    from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
    from apps.core_backend.orchestration.store import PersistentStore
    from pipeline.evaluation.classifier_acceptance_gate import _adapt_action, _apply_adapter_routing_guard, decide_route

    engine = Engine(clf, retriever, A._MockNoCallLLM(), {"release_id": f"gate-{clf.name}", "model_version": clf.name}, policy)
    runner = PipelineRunner(intent_client=A._MockIntentClient(clf), commerce_adapter=commerce, retrieval_adapter=retriever,
                            store=PersistentStore(db_path=str(tmp / "o.sqlite3")), llm_client=A._OfflineValidSpyLLM(), policy=policy_v2)
    recs = []
    for r in rows:
        c = r["context"]
        ctx = lambda: RoutingContext(ticket_customer_id=c["ticket_customer_id"], extracted_slots=c["extracted_slots"], is_personal_lookup=c["is_personal_lookup"])
        p = clf.predict(r["text"])
        d = decide_route(IntentPrediction(intent=p["intent"], confidence=p["confidence"], margin=p["margin"], model_version=clf.name,
                                          rejected_by_experimental_adapter=bool(p.get("rejected_by_experimental_adapter", False))), ctx(), policy_v2)
        bare, _ = _apply_adapter_routing_guard(d.action, p)
        an = engine._analyse({"message": r["text"], "as_of": c["as_of"]})[0]
        rr = runner.run(r["text"], ctx(), run_id=f"{clf.name}-{r['id']}")
        recs.append({"id": r["id"], "slice": r["slice"], "subgroup": r["subgroup"], "true_intent": r["true_intent"],
                     "pred_intent": p["intent"], "conf": round(p["confidence"], 5),
                     "bare_action": bare, "bare_reasons": d.reason_codes,
                     "engine_action": _adapt_action(an["routing"]["recommendation"]), "engine_intent": an["intent"]["label"], "engine_reasons": an["routing"]["reason_codes"],
                     "runner_action": rr["action"], "runner_intent": rr["predicted_intent"], "runner_reasons": rr["reason_codes"]})
    return recs


def summarize(recs):
    out = {}
    for surf in ("bare", "engine", "runner"):
        act = lambda x: x[f"{surf}_action"]
        inten = lambda x: x["pred_intent"] if surf == "bare" else x[f"{'engine' if surf == 'engine' else 'runner'}_intent"]
        ans = [x for x in recs if x["subgroup"] == "answerable"]
        leaks = [x["id"] for x in recs if act(x) == "retrieve_draft" and (x["slice"] in NODRAFT or x["subgroup"] == "human_agent_escalation")]
        out[surf] = {
            "answerable_n": len(ans),
            "answerable_correct_draft": [x["id"] for x in ans if act(x) == "retrieve_draft" and inten(x) == x["true_intent"]],
            "answerable_wrong_draft": [x["id"] for x in ans if act(x) == "retrieve_draft" and inten(x) != x["true_intent"]],
            "answerable_not_drafted": [x["id"] for x in ans if act(x) != "retrieve_draft"],
            "no_draft_leaks": leaks, "leak_count": len(leaks),
            "human_agent_escalated": [x["id"] for x in recs if x["subgroup"] == "human_agent_escalation" and act(x) == "escalate"],
            "ood_actions": dict(__import__("collections").Counter(act(x) for x in recs if x["slice"] == "novel_ood")),
            "mandatory_actions": dict(__import__("collections").Counter(act(x) for x in recs if x["slice"] == "mandatory_escalation")),
            "mandatory_strict_escalate": sum(1 for x in recs if x["slice"] == "mandatory_escalation" and act(x) == "escalate"),
        }
    return out


def run(a):
    from apps.core_backend.commerce.adapter import CommerceAdapter
    from apps.core_backend.intent.routing import load_policy_v2
    from apps.core_backend.retrieval.adapter import RetrievalAdapter
    from pipeline.evaluation import classifier_acceptance_gate as CG

    root = A._bootstrap_target_repo(REPO)
    mdir = Path(a.model_dir)
    cal = CG.validate_calibration_manifest(mdir, Path(a.calibration_manifest)) if a.calibration_manifest else {"temperature": 1.0, "calibrated": False, "rejector": None}
    clf = CG.GateSequenceClassifier(a.name, mdir, temperature=float(cal["temperature"] or 1.0), calibrated=bool(cal["calibrated"]), rejector=cal["rejector"])
    rel = json.loads((root / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    retr = RetrievalAdapter(kb_path=str(root / "data/knowledge/approved_kb.v2.json"), allowed_document_versions={(d["document_id"], str(d["version"])) for d in rel["documents"]})
    commerce = CommerceAdapter(data_path=str(root / "data/knowledge/mock_orders.json"))
    pol_path = root / "apps/core_backend/config/policies/intent_policy.v2.json"
    policy, pv2 = json.loads(pol_path.read_text(encoding="utf-8")), load_policy_v2(pol_path)
    with tempfile.TemporaryDirectory() as td:
        recs = eval_holdout(clf, G.load_cases(), retr, commerce, policy, pv2, Path(td))
        s72 = A._eval_three_surfaces(clf=clf, rows=CG.load_jsonl(root / "artifacts/evaluation/sealed_holdout_20261113/sealed_holdout_cases.jsonl"),
                                     retriever=retr, commerce=commerce, policy=policy, policy_v2=pv2, tmp_store=Path(td) / "s72")
    res = {"name": a.name, "model_dir": str(mdir), "weights_sha256": CG.compute_file_sha256(mdir / "model.safetensors"),
           "calibration": {k: cal[k] for k in ("temperature", "calibrated")} | {"rejector_enabled": cal["rejector"] is not None},
           "cases_sha256": G.sha256(G.CASES), "git_head": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
           "new_holdout": summarize(recs), "old_sealed72": {k: {s: {"leaks": v[s]["unsafe_draft_leaks"], "draft": v[s]["draft"]} for s in ("bare", "engine", "runner")} for k, v in s72["per_slice"].items()},
           "live_provider_calls": 0}
    res["suites"] = CG.evaluate_model_on_suites(a.name, mdir, root, temperature=float(cal["temperature"] or 1.0), calibrated=bool(cal["calibrated"]), rejector=cal["rejector"])
    if a.gate:
        sp = Path(a.splits) if a.splits else None
        pick = lambda *ns: next((sp / n for n in ns if (sp / n).exists()), None) if sp else None
        srv_dir = Path(a.serving_dir) if a.serving_dir else (root / "artifacts/models/trained/distilbert-supportiq")
        res["fixed_gate"] = CG.run_classifier_acceptance_gate(
            repo_root=root, candidate_name=a.name, candidate_dir=mdir, serving_dir=srv_dir,
            candidate_manifest_path=Path(a.candidate_manifest) if a.candidate_manifest else None, calibration_manifest_path=Path(a.calibration_manifest) if a.calibration_manifest else None,
            train_split_path=pick("full_train_split.jsonl", "train.jsonl"), calibration_split_path=pick("full_cal_split.jsonl", "cal.jsonl"),
            eval_split_path=pick("boundary_pos_evaluation.jsonl", "eval.jsonl"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"predictions_{a.name}.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    (out / f"results_{a.name}.json").write_text(json.dumps(res, indent=2, default=str) + "\n", encoding="utf-8")
    print(a.name, json.dumps(res["new_holdout"], indent=1))


def verdict(srv_path, cand_path):
    s, c = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (srv_path, cand_path))
    nh, sh = c["new_holdout"], s["new_holdout"]
    fails = []
    if nh["engine"]["leak_count"] or nh["runner"]["leak_count"]:
        fails.append("R1_new_holdout_draft_leak")
    rc, sc = nh["runner"], sh["runner"]
    if len(rc["answerable_correct_draft"]) < max(1, len(sc["answerable_correct_draft"])):
        fails.append("R2_supported_coverage_below_serving_or_all_abstain")
    if len(rc["answerable_wrong_draft"]) > len(sc["answerable_wrong_draft"]):
        fails.append("R2_wrong_drafts_above_serving")
    fg = c.get("fixed_gate")
    if fg is None:
        fails.append("R3_fixed_gate_not_run")
    elif fg["gate_decision"] != "PASS":
        fails += [f"R3_{x}" for x in fg["failure_reasons"]]
    for k in ("novel_ood", "mandatory_escalation_compound"):
        for surf in ("engine", "runner"):
            if c["old_sealed72"][k][surf]["leaks"]:
                fails.append(f"R4_sealed72_{k}_{surf}_leak")
    v = {"verdict": "PASS" if not fails else "REJECT", "failures": fails, "candidate": c["name"], "weights_sha256": c["weights_sha256"], "serving_sha256": s["weights_sha256"]}
    print(json.dumps(v, indent=2))
    return v


if __name__ == "__main__":
    if sys.argv[1:2] == ["verdict"]:
        verdict(sys.argv[2], sys.argv[3])
    else:
        ap = argparse.ArgumentParser()
        ap.add_argument("--name", required=True)
        ap.add_argument("--model-dir", required=True)
        ap.add_argument("--serving-dir")
        ap.add_argument("--calibration-manifest")
        ap.add_argument("--candidate-manifest")
        ap.add_argument("--splits")
        ap.add_argument("--gate", action="store_true")
        ap.add_argument("--out", default=str(HERE / "results"))
        run(ap.parse_args())
