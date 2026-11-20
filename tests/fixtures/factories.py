"""Small, explicit fixture factories for SupportIQ test cases and environments."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from apps.core_backend.intent.schemas import IntentPrediction
from apps.core_backend.intent.routing import load_policy_v2
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore
from pipeline.evaluation.system_contracts import (
    SystemCase,
    SystemCaseContext,
    SystemCaseExpected,
)


def compute_sha256(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def make_system_case(
    case_id: str = "case-fact-001",
    primary_slice: str = "supported",
    text: str = "What is the return policy?",
    true_intent: str = "return_policy",
    actions: Optional[List[str]] = None,
    must_escalate: bool = False,
    must_not_draft: bool = False,
    answerable: bool = True,
    gold_sources: Optional[List[Dict[str, str]]] = None,
    draft_expected: bool = True,
    ticket_customer_id: str = "cust-001",
    fault: Optional[str] = None,
    **kwargs: Any,
) -> SystemCase:
    """Create a minimal, strongly-typed SystemCase instance."""
    context = SystemCaseContext(
        ticket_customer_id=ticket_customer_id,
        verified_scope=kwargs.get("verified_scope", "ticket:read"),
        is_personal_lookup=kwargs.get("is_personal_lookup", False),
        extracted_slots=kwargs.get("extracted_slots", {}),
    )
    expected = SystemCaseExpected(
        actions=actions or (["escalate"] if must_escalate else ["retrieve_draft"]),
        team=kwargs.get("team"),
        reason_any=kwargs.get("reason_any", []),
        must_escalate=must_escalate,
        must_not_draft=must_not_draft,
        retrieval_applicable=kwargs.get("retrieval_applicable", answerable),
        answerable=answerable,
        gold_sources=gold_sources or [{"doc_id": "KB-01", "version": "1.0"}],
        draft_expected=draft_expected if not must_escalate else False,
    )
    return SystemCase(
        id=case_id,
        primary_slice=primary_slice,
        tags=kwargs.get("tags", ["policy"]),
        text=text,
        true_intent=true_intent,
        context=context,
        expected=expected,
        fault=fault,
    )


def write_suite_fixture(
    root: Path,
    cases: List[Dict[str, Any]],
    kb_data: List[Dict[str, Any]],
) -> Dict[str, Path]:
    """Write valid suite manifest, cases.jsonl, and approved_kb.v1.json with real SHA-256 hashes."""
    suite_dir = root / "suite_test"
    suite_dir.mkdir(parents=True, exist_ok=True)

    cases_file = suite_dir / "cases.jsonl"
    with open(cases_file, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")

    kb_file = suite_dir / "approved_kb.v1.json"
    kb_file.write_text(json.dumps(kb_data, indent=2), encoding="utf-8")

    manifest_data = {
        "schema_version": "v1.0",
        "benchmark_version": "v1.0-test",
        "status": "approved",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": {
            "cases.jsonl": {"path": "cases.jsonl", "sha256": compute_sha256(cases_file)},
            "approved_kb.v1.json": {"path": "approved_kb.v1.json", "sha256": compute_sha256(kb_file)},
        },
    }
    manifest_file = suite_dir / "suite_manifest.json"
    manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    return {
        "suite_dir": suite_dir,
        "manifest_file": manifest_file,
        "cases_file": cases_file,
        "kb_file": kb_file,
    }


def make_human_annotation(
    case_id: str,
    draft_sha256: str,
    claims: List[Dict[str, Any]],
    reviewer: str = "lead_compliance",
    reviewed_at: str = "2026-11-05T00:00:00Z",
) -> Dict[str, Any]:
    """Generate a valid, non-fabricated claim annotation record requiring human actor and timestamp."""
    return {
        "case_id": case_id,
        "draft_sha256": draft_sha256,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "claims": claims,
    }
