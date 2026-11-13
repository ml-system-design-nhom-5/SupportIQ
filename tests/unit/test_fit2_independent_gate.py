"""Integrity, semantics, novelty and hash-lock checks for the 36-case Fit2 independent holdout."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

_G = Path(__file__).resolve().parents[2] / "artifacts/evaluation/fit2_independent_gate_20261113/gate.py"
_spec = importlib.util.spec_from_file_location("fit2_gate", _G)
g = importlib.util.module_from_spec(_spec)
sys.modules["fit2_gate"] = g
_spec.loader.exec_module(g)


def _active_docs() -> set[str]:
    rel = json.loads((g.REPO / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    kb = json.loads((g.REPO / "data/knowledge/approved_kb.v2.json").read_text(encoding="utf-8"))
    ok = {f"{d['document_id']}:{d['version']}" for d in kb if d["status"] == "approved"}
    return ok & {f"{d['document_id']}:{d['version']}" for d in rel["documents"]}


def test_shape_and_gold_semantics() -> None:
    rows = g.load_cases()
    assert len(rows) == 36 and len({r["id"] for r in rows}) == 36
    assert Counter(r["slice"] for r in rows) == {"supported": 12, "novel_ood": 12, "mandatory_escalation": 12}
    sup = [r for r in rows if r["slice"] == "supported"]
    assert sorted(r["true_intent"] for r in sup) == sorted(g.SUPPORTED_12)
    docs = _active_docs()
    for r in rows:
        assert r["context"]["as_of"] and r["context"]["ticket_customer_id"]
        assert all(d in docs for d in r["expected_docs"]), r["id"]
        if r["subgroup"] == "answerable":
            assert r["expected_actions"] == ["retrieve_draft"] and not r["must_not_draft"] and r["expected_docs"]
        else:  # human_agent, OOD, mandatory: never drafted
            assert r["must_not_draft"] and "retrieve_draft" not in r["expected_actions"]
        if r["slice"] == "mandatory_escalation" or r["subgroup"] == "human_agent_escalation":
            assert r["must_escalate"] and r["expected_actions"] == ["escalate"]
    assert [r["subgroup"] for r in sup].count("human_agent_escalation") == 1
    comp = [r for r in rows if r["subgroup"] == "compound"]
    assert len(comp) == 6 and all(r["expected_docs"] for r in comp)


def test_novel_vs_all_prior_and_internal() -> None:
    rows = g.load_cases()
    corpus, files = g.historical_corpus()
    assert files > 100 and len(corpus) > 5000  # guards against an empty/vacuous corpus
    ov = g.overlap_report(rows, corpus)
    assert ov["exact_overlap"] == [] and ov["near_duplicates"] == [] and ov["internal_duplicates"] == []


def test_manifest_hash_lock() -> None:
    m = json.loads(g.MANIFEST.read_text(encoding="utf-8"))
    assert m["cases_sha256"] == g.sha256(g.CASES) and m["total_cases"] == 36
    kb_path = g.REPO / "data/knowledge/approved_kb.v2.json"
    kb_lf_sha = hashlib.sha256(kb_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert m["approved_kb_sha256"] in {g.sha256(kb_path), kb_lf_sha}
