"""Contracts, typed schemas, and provenance validation for System Evaluation."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field, ConfigDict, field_validator

from pipeline.evaluation import EvaluationError
from pipeline.preparation.utils import (
    STANDARD_INTENTS,
    CORE_PRODUCT_INTENTS,
    compute_sha256,
)

ALLOWED_FAULT_SCENARIOS = frozenset([
    "ml_timeout",
    "ml_unavailable",
    "ml_error",
    "encoder_unavailable",
    "encoder_failure",
    "llm_timeout",
    "llm_unavailable",
    "llm_error",
    "llm_rate_limited",
    "llm_invalid_citations",
    "llm_blocked",
    "commerce_unauthorized",
    "commerce_not_found",
    "corrupt_input",
])

# Standard 46 Bitext intent labels
STANDARD_46_LABELS = frozenset(STANDARD_INTENTS)


class SystemCaseContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_customer_id: str
    verified_scope: str = "ticket:read"
    is_personal_lookup: bool = False
    extracted_slots: Dict[str, Any] = Field(default_factory=dict)


class SystemCaseExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: List[str]
    team: Optional[str] = None
    reason_any: List[str] = Field(default_factory=list)
    must_escalate: bool = False
    must_not_draft: bool = False
    retrieval_applicable: bool = False
    answerable: bool = False
    gold_sources: List[Dict[str, str]] = Field(default_factory=list)
    draft_expected: bool = False


class SystemCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    primary_slice: str
    tags: List[str] = Field(default_factory=list)
    text: str = Field(..., min_length=1)
    true_intent: Optional[str] = None
    context: SystemCaseContext
    expected: SystemCaseExpected
    fault: Optional[str] = None

    @field_validator("id")
    @classmethod
    def validate_case_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Case ID cannot be empty")
        if re.search(r"[\s/\\]", v):
            raise ValueError(f"Case ID '{v}' contains invalid characters or whitespace")
        return v.strip()

    @field_validator("true_intent")
    @classmethod
    def validate_true_intent(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in STANDARD_46_LABELS:
            raise ValueError(f"true_intent '{v}' is outside expected taxonomy of 46 standard labels")
        return v

    @field_validator("fault")
    @classmethod
    def validate_fault(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ALLOWED_FAULT_SCENARIOS:
            raise ValueError(f"fault scenario '{v}' is not in allowed whitelist: {sorted(ALLOWED_FAULT_SCENARIOS)}")
        return v


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    repetition: int = 1
    profile: str
    scope: str  # "component", "e2e", "oversight"
    execution_status: str  # "ok", "timeout", "error", "not_run"
    error_code: Optional[str] = None
    routing_action: Optional[str] = None
    final_action: Optional[str] = None
    requested_team: Optional[str] = None
    target_queue: Optional[str] = None
    reason_codes: List[str] = Field(default_factory=list)
    predicted_intent: Optional[str] = None
    final_intent: Optional[str] = None
    prediction_confidence: Optional[float] = None
    prediction_margin: Optional[float] = None
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    draft_body: Optional[str] = None
    draft_kind: Optional[str] = None
    draft_hash: Optional[str] = None
    llm_called: bool = False
    llm_metadata: Optional[Dict[str, Any]] = None
    llm_usage: Optional[Dict[str, Any]] = None
    stage_elapsed_ms: Dict[str, float] = Field(default_factory=dict)
    total_elapsed_ms: float = 0.0
    audit_evidence: Optional[Dict[str, Any]] = None


class SystemConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "v1.0"
    seed: int = 42
    concurrency: int = 1
    allow_draft_suite: bool = False
    warmup_requests: int = 5
    latency_requests: int = 100
    max_llm_calls: int = 200
    deadline_seconds: float = 30.0
    ml_timeout_seconds: float = 3.0
    llm_timeout_seconds: float = 15.0
    demo_timeout_seconds: float = 20.0
    max_estimated_cost_usd: Optional[float] = 1.0
    pricing: Optional[Dict[str, Any]] = Field(default_factory=lambda: {
        "model": "gemini-3.1-flash-lite",
        "currency": "USD",
        "input_cost_per_million": 0.075,
        "output_cost_per_million": 0.30,
    })
    mandatory_gates: List[str] = Field(default_factory=list)
    thresholds: Dict[str, float] = Field(default_factory=dict)


@dataclass(frozen=True)
class VerifiedSystemInputs:
    """Verified immutable system inputs with guaranteed provenance and integrity."""
    cases: List[SystemCase]
    config: SystemConfig
    source_paths: Dict[str, Path]
    input_hashes: Dict[str, str]
    as_of: datetime
    coverage: Dict[str, Any]
    manifest: Dict[str, Any]


def resolve_contained_path(path_str: str, base_dir: Path, repo_root: Path) -> Path:
    """Resolve a path relative to base_dir or repo_root and strictly ensure it is contained within repo_root."""
    root_resolved = repo_root.resolve()
    p = Path(path_str)
    if p.is_absolute():
        resolved = p.resolve()
    else:
        cand1 = (base_dir / p).resolve()
        cand2 = (repo_root / p).resolve()
        if cand1.exists():
            resolved = cand1
        elif cand2.exists():
            resolved = cand2
        else:
            resolved = cand1

    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise EvaluationError(f"Path '{path_str}' escapes repo root '{repo_root}'")
    return resolved


def load_system_inputs(
    repo_root: Path | str,
    suite_path: Path | str,
    config_path: Path | str,
    profile: str = "mock",
) -> VerifiedSystemInputs:
    """Load, strictly validate, and verify provenance for all system evaluation benchmark inputs."""
    repo_root_p = Path(repo_root).resolve()
    suite_p = Path(suite_path)
    if not suite_p.is_absolute():
        suite_p = (repo_root_p / suite_p).resolve()

    config_p = Path(config_path)
    if not config_p.is_absolute():
        config_p = (repo_root_p / config_p).resolve()

    if not suite_p.exists():
        raise EvaluationError(f"Suite manifest file not found: {suite_p}")
    if not config_p.exists():
        raise EvaluationError(f"Evaluation config file not found: {config_p}")

    # 1. Parse and validate configuration
    try:
        with open(config_p, "r", encoding="utf-8") as f:
            cfg_raw = json.load(f)
        config = SystemConfig.model_validate(cfg_raw)
    except Exception as exc:
        raise EvaluationError(f"Failed to validate config at {config_p}: {exc}") from exc

    # 2. Parse and validate suite manifest
    try:
        with open(suite_p, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as exc:
        raise EvaluationError(f"Failed to parse suite manifest JSON at {suite_p}: {exc}") from exc

    if not isinstance(manifest, dict):
        raise EvaluationError("Suite manifest must be a JSON object")

    suite_status = manifest.get("status", "draft")
    if profile == "live" and suite_status == "draft" and not config.allow_draft_suite:
        raise EvaluationError("Suite in 'draft' status cannot be used for live acceptance evaluation")

    as_of_str = manifest.get("as_of")
    if not as_of_str:
        as_of = datetime.now(timezone.utc)
    else:
        try:
            as_of = datetime.fromisoformat(as_of_str.replace("Z", "+00:00"))
        except Exception as exc:
            raise EvaluationError(f"Invalid as_of timestamp '{as_of_str}': {exc}") from exc

    files_dict = manifest.get("files", {})
    if not isinstance(files_dict, dict) or "cases" not in files_dict:
        raise EvaluationError("Suite manifest must declare 'files' dictionary containing 'cases'")

    # 3. Check and verify SHA-256 for all declared files
    source_paths: Dict[str, Path] = {
        "suite_manifest": suite_p,
        "config": config_p,
    }
    input_hashes: Dict[str, str] = {
        "suite_manifest": compute_sha256(suite_p),
        "config": compute_sha256(config_p),
    }

    manifest_dir = suite_p.parent
    for file_key, file_meta in files_dict.items():
        if not isinstance(file_meta, dict) or "path" not in file_meta or "sha256" not in file_meta:
            raise EvaluationError(f"File declaration for '{file_key}' missing path or sha256 checksum")
        
        target_path = resolve_contained_path(file_meta["path"], manifest_dir, repo_root_p)
        if not target_path.exists():
            raise EvaluationError(f"Declared file '{file_key}' does not exist at {target_path}")

        actual_sha = compute_sha256(target_path)
        expected_sha = file_meta["sha256"]
        if actual_sha != expected_sha:
            raise EvaluationError(f"Declared file '{file_key}' checksum mismatch: expected {expected_sha}, got {actual_sha}")

        source_paths[file_key] = target_path
        input_hashes[file_key] = actual_sha

    # 4. Load and validate KB documents for temporal & ACL eligibility checking
    kb_docs_map: Dict[str, Dict[str, Any]] = {}
    if "kb" in source_paths:
        try:
            with open(source_paths["kb"], "r", encoding="utf-8") as f:
                kb_data = json.load(f)
            for d in kb_data:
                d_id = d.get("doc_id") or d.get("document_id")
                raw_ver = str(d.get("version", "1"))
                kb_docs_map[(d_id, raw_ver)] = d
                if "." not in raw_ver:
                    kb_docs_map[(d_id, f"{raw_ver}.0")] = d
                elif raw_ver.endswith(".0"):
                    kb_docs_map[(d_id, raw_ver[:-2])] = d
        except Exception as exc:
            raise EvaluationError(f"Failed to load KB snapshot at {source_paths['kb']}: {exc}") from exc

    # 5. Load cases.jsonl and validate each case
    cases_file = source_paths["cases"]
    cases: List[SystemCase] = []
    seen_ids: Set[str] = set()
    slice_counts: Dict[str, int] = {}
    intent_counts: Dict[str, int] = {}

    with open(cases_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue
            try:
                c_json = json.loads(line_str)
                case = SystemCase.model_validate(c_json)
            except Exception as exc:
                raise EvaluationError(f"Case at line {line_num} failed validation: {exc}") from exc

            if case.id in seen_ids:
                raise EvaluationError(f"Found duplicate case ID '{case.id}' at line {line_num}")
            seen_ids.add(case.id)

            # Validate gold sources when answerable
            if case.expected.answerable:
                if not case.expected.gold_sources:
                    raise EvaluationError(f"Case '{case.id}' is answerable but provides no gold_sources")
                for gs in case.expected.gold_sources:
                    doc_id = gs.get("doc_id")
                    ver = str(gs.get("version", "1.0"))
                    doc_key = (doc_id, ver)
                    if doc_key not in kb_docs_map:
                        raise EvaluationError(f"Case '{case.id}' gold source {doc_key} not found in KB snapshot")
                    doc = kb_docs_map[doc_key]
                    
                    # Verify approval status
                    if doc.get("status") != "approved":
                        raise EvaluationError(f"Case '{case.id}' references unapproved gold document {doc_key}")

                    # Verify temporal validity as of as_of timestamp
                    valid_to_str = doc.get("valid_to")
                    if valid_to_str:
                        vt = datetime.fromisoformat(valid_to_str.replace("Z", "+00:00"))
                        if as_of >= vt:
                            raise EvaluationError(f"Case '{case.id}' references expired or ineligible gold document {doc_key} (expired {vt} <= as_of {as_of})")

                    valid_from_str = doc.get("valid_from")
                    if valid_from_str:
                        vf = datetime.fromisoformat(valid_from_str.replace("Z", "+00:00"))
                        if as_of < vf:
                            raise EvaluationError(f"Case '{case.id}' references not yet effective gold document {doc_key}")

            cases.append(case)
            slice_counts[case.primary_slice] = slice_counts.get(case.primary_slice, 0) + 1
            if case.true_intent:
                intent_counts[case.true_intent] = intent_counts.get(case.true_intent, 0) + 1

    # 5b. Validate expected outcomes across all cases
    outcome_validation = validate_expected_outcomes(cases, kb_docs_map, as_of=as_of, strict=True)
    if manifest.get('enforce_split_contract'):
        if manifest.get('total_cases') != len(cases) or manifest.get('slice_quotas') != slice_counts:
            raise EvaluationError('Benchmark count/slice quota mismatch')
        if manifest.get('split') == 'acceptance':
            from pipeline.preparation.utils import get_near_duplicate_key
            current = {get_near_duplicate_key(c.text) for c in cases}
            for key in ('dev_cases', 'retired_cases'):
                if key not in source_paths:
                    raise EvaluationError(f'Acceptance must pin {key}')
                other = {get_near_duplicate_key(json.loads(line)['text'])
                         for line in source_paths[key].read_text(encoding='utf-8').splitlines() if line.strip()}
                if current & other:
                    raise EvaluationError(f'Acceptance text overlap with {key}')

    # 6. Compute coverage statistics
    # KB coverage gap reflects actual approved KB evidence coverage, not just query presence
    kb_covered_intents = {
        c.true_intent
        for c in cases
        if c.expected.answerable and c.expected.gold_sources and c.true_intent in CORE_PRODUCT_INTENTS
    }
    missing_core_kb_intents = set(CORE_PRODUCT_INTENTS) - kb_covered_intents
    missing_core_query_intents = set(CORE_PRODUCT_INTENTS) - set(intent_counts.keys())
    coverage = {
        "total_cases": len(cases),
        "slice_counts": slice_counts,
        "intent_counts": intent_counts,
        "missing_core_intents": sorted(missing_core_query_intents),
        "kb_covered_intents": sorted(kb_covered_intents),
        "missing_core_kb_intents": sorted(missing_core_kb_intents),
        "kb_coverage_gap": len(missing_core_kb_intents) > 0,
    }

    return VerifiedSystemInputs(
        cases=cases,
        config=config,
        source_paths=source_paths,
        input_hashes=input_hashes,
        as_of=as_of,
        coverage=coverage,
        manifest=manifest,
    )


def verify_input_snapshot(inputs: VerifiedSystemInputs) -> None:
    """Verify that all input files remain strictly unmodified before/after benchmark execution."""
    for key, path in inputs.source_paths.items():
        if not path.exists():
            raise EvaluationError(f"Input file missing mid-run: {path}")
        current_hash = compute_sha256(path)
        expected_hash = inputs.input_hashes.get(key)
        if current_hash != expected_hash:
            raise EvaluationError(f"Input file modified mid-run: '{key}' at {path}")


def validate_expected_outcomes(
    cases: List[SystemCase],
    kb_snapshot: List[Dict[str, Any]] | Dict[Tuple[str, str], Dict[str, Any]],
    as_of: Optional[datetime] = None,
    strict: bool = True,
) -> Dict[str, Any]:
    """Validate expected benchmark case outcomes against logical constraints and KB evidence.
    Enforces:
    - No contradictions: must_escalate cannot expect draft; must_not_draft cannot contain retrieve_draft.
    - Full evidence verification: answerable cases must have approved, temporally valid, ACL-permissible gold docs.
    - Coverage by intent analytics.
    Raises EvaluationError on contract violation if strict=True.
    """
    check_time = as_of or datetime.now(timezone.utc)

    # Normalize kb_snapshot to map by (doc_id, version)
    kb_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if isinstance(kb_snapshot, dict):
        for k, v in kb_snapshot.items():
            if isinstance(k, tuple):
                kb_map[(str(k[0]), str(k[1]))] = v
            else:
                d_id = v.get("doc_id") or v.get("document_id") or str(k)
                raw_ver = str(v.get("version", "1.0"))
                kb_map[(d_id, raw_ver)] = v
    elif isinstance(kb_snapshot, list):
        for doc in kb_snapshot:
            d_id = doc.get("doc_id") or doc.get("document_id")
            raw_ver = str(doc.get("version", "1.0"))
            kb_map[(d_id, raw_ver)] = doc
            if "." not in raw_ver:
                kb_map[(d_id, f"{raw_ver}.0")] = doc
            elif raw_ver.endswith(".0"):
                kb_map[(d_id, raw_ver[:-2])] = doc

    contradictions: List[str] = []
    missing_evidence: List[str] = []
    coverage_by_intent: Dict[str, Dict[str, int]] = {}

    for c in cases:
        intent = c.true_intent or "unknown"
        if intent not in coverage_by_intent:
            coverage_by_intent[intent] = {
                "total": 0,
                "answerable_count": 0,
                "escalate_count": 0,
                "clarify_count": 0,
                "draft_expected_count": 0,
            }
        coverage_by_intent[intent]["total"] += 1
        if c.expected.answerable:
            coverage_by_intent[intent]["answerable_count"] += 1
        if c.expected.must_escalate or "escalate" in c.expected.actions:
            coverage_by_intent[intent]["escalate_count"] += 1
        if "clarify" in c.expected.actions:
            coverage_by_intent[intent]["clarify_count"] += 1
        if c.expected.draft_expected:
            coverage_by_intent[intent]["draft_expected_count"] += 1

        # 1. Check logical contradictions in expectations
        if c.expected.must_escalate and c.expected.draft_expected:
            err = f"Case '{c.id}' has contradiction: must_escalate=True cannot expect draft"
            contradictions.append(err)
            if strict:
                raise EvaluationError(err)

        if c.expected.must_not_draft and ("retrieve_draft" in c.expected.actions or c.expected.draft_expected):
            err = f"Case '{c.id}' has contradiction: must_not_draft=True cannot contain retrieve_draft action or draft_expected"
            contradictions.append(err)
            if strict:
                raise EvaluationError(err)

        if c.expected.must_escalate and "retrieve_draft" in c.expected.actions:
            err = f"Case '{c.id}' has contradiction: must_escalate=True cannot contain retrieve_draft action"
            contradictions.append(err)
            if strict:
                raise EvaluationError(err)

        if not c.expected.answerable and c.expected.draft_expected:
            err = f"Case '{c.id}' has contradiction: unanswerable case cannot have draft_expected=True"
            contradictions.append(err)
            if strict:
                raise EvaluationError(err)

        # 2. Check gold evidence presence and validity if answerable
        if c.expected.answerable:
            if not c.expected.gold_sources:
                err = f"Case '{c.id}' is answerable but provides no gold_sources"
                missing_evidence.append(err)
                if strict:
                    raise EvaluationError(err)

            for gs in c.expected.gold_sources:
                doc_id = gs.get("doc_id")
                ver = str(gs.get("version", "1.0"))
                doc_key = (doc_id, ver)
                doc = (
                    kb_map.get(doc_key)
                    or kb_map.get((doc_id, f"{ver}.0"))
                    or kb_map.get((doc_id, ver.rstrip(".0")))
                )
                if doc is None:
                    err = f"Case '{c.id}' gold source {doc_key} not found in KB snapshot"
                    missing_evidence.append(err)
                    if strict:
                        raise EvaluationError(err)
                    continue

                if doc.get("status") != "approved":
                    err = f"Case '{c.id}' references unapproved gold document {doc_key} (status: '{doc.get('status')}')"
                    missing_evidence.append(err)
                    if strict:
                        raise EvaluationError(err)

                # Temporal validity
                vt = doc.get("valid_to")
                if vt:
                    try:
                        dt_vt = datetime.fromisoformat(str(vt).replace("Z", "+00:00"))
                        if check_time >= dt_vt:
                            err = f"Case '{c.id}' references expired or ineligible gold document {doc_key} (expired {dt_vt} <= as_of {check_time})"
                            missing_evidence.append(err)
                            if strict:
                                raise EvaluationError(err)
                    except ValueError:
                        err = f"Case '{c.id}' has invalid valid_to format on {doc_key}"
                        missing_evidence.append(err)
                        if strict:
                            raise EvaluationError(err)

                vf = doc.get("valid_from")
                if vf:
                    try:
                        dt_vf = datetime.fromisoformat(str(vf).replace("Z", "+00:00"))
                        if check_time < dt_vf:
                            err = f"Case '{c.id}' references not yet effective gold document {doc_key}"
                            missing_evidence.append(err)
                            if strict:
                                raise EvaluationError(err)
                    except ValueError:
                        err = f"Case '{c.id}' has invalid valid_from format on {doc_key}"
                        missing_evidence.append(err)
                        if strict:
                            raise EvaluationError(err)

    return {
        "total_cases": len(cases),
        "contradictions": contradictions,
        "missing_evidence": missing_evidence,
        "coverage_by_intent": coverage_by_intent,
    }


# ---------------------------------------------------------------------------
# Task 3 / IMP-10 & IMP-11 Contracts: Provenance, Manifest, and Comparability
# ---------------------------------------------------------------------------

class MetricProvenance(BaseModel):
    model_config = ConfigDict(extra="ignore")

    metric: str
    value: Optional[float] = None
    status: str = "NOT_EVALUATED"  # "PASS", "FAIL", "OBSERVE", "NOT_EVALUATED", "INSUFFICIENT_EVIDENCE"
    evidence_ref: Optional[str] = None
    evidence_kind: str = "simulated"
    model_mode: Optional[str] = None
    evaluator_type: Optional[str] = None  # "human", "ai", "none"
    study_type: Optional[str] = None      # "user_study", "agent_simulation", "none"
    target: Optional[float] = None
    operator: Optional[str] = None
    previous: Optional[float] = None
    delta: Optional[float] = None
    regressed: bool = False
    diagnosis: Optional[str] = None
    recommendation: Optional[str] = None


class EvaluationManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "v1.1"
    run_id: str
    created_at: str
    git_commit: Optional[str] = None
    evidence_kind: str = "simulated"  # "live", "simulated", "cached", "live_experimental", "mixed"
    model_mode: str = "trained"       # "trained", "heuristic_demo", "unavailable", "synthetic"
    evaluator_type: str = "none"      # "human", "ai", "none"
    study_type: str = "none"          # "user_study", "agent_simulation", "none"
    execution_mode: str = "new_execution"  # "new_execution", "cached_only"
    hashes: Dict[str, Optional[str]] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)
    counts: Dict[str, int] = Field(default_factory=dict)
    environment: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, MetricProvenance] = Field(default_factory=dict)
    files: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    all_mandatory_passed: bool = False
    summary_reason: Optional[str] = None


def check_regression_comparability(
    run_a: Dict[str, Any],
    run_b: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """Determine whether two evaluation runs share identical KB, dataset split, model, prompt, and config.
    Requires complete, non-empty provenance for both runs.
    Returns (True, []) if comparable under identical conditions, or (False, reasons) if configurations differ or provenance is missing.
    """
    reasons: List[str] = []

    def _extract_provenance(r: Dict[str, Any]) -> Dict[str, Optional[str]]:
        h = dict(r.get("hashes", {}))
        manifest = r.get("manifest", {})
        if isinstance(manifest, dict):
            h.update(manifest.get("hashes", {}))
            files = manifest.get("files", {})
            if "kb" in files and "kb_hash" not in h:
                h["kb_hash"] = files["kb"].get("sha256")
            if "cases" in files and "split_hash" not in h:
                h["split_hash"] = files["cases"].get("sha256")
            if "model" in files and "model_hash" not in h:
                h["model_hash"] = files["model"].get("sha256")

        meta = r.get("metadata", {})
        if "kb_hash" not in h and "kb_sha256" in meta:
            h["kb_hash"] = meta["kb_sha256"]
        if "split_hash" not in h and "suite_sha256" in meta:
            h["split_hash"] = meta["suite_sha256"]
        if "model_hash" not in h and "weights_sha256" in meta:
            h["model_hash"] = meta["weights_sha256"]
        if "prompt_hash" not in h and "prompt_sha256" in meta:
            h["prompt_hash"] = meta["prompt_sha256"]
        if "config_hash" not in h and "config_sha256" in meta:
            h["config_hash"] = meta["config_sha256"]

        summary = r.get("summary", {})
        if isinstance(summary, dict):
            s_meta = summary.get("metadata", {})
            if "kb_hash" not in h and "kb_sha256" in s_meta:
                h["kb_hash"] = s_meta["kb_sha256"]
            if "split_hash" not in h and "suite_sha256" in s_meta:
                h["split_hash"] = s_meta["suite_sha256"]
            if "model_hash" not in h and "weights_sha256" in s_meta:
                h["model_hash"] = s_meta["weights_sha256"]

        return h

    h_a = _extract_provenance(run_a)
    h_b = _extract_provenance(run_b)

    # Required provenance: KB, split, and model hashes must be non-empty in BOTH runs
    required_hashes = ("kb_hash", "split_hash", "model_hash")
    for key in required_hashes:
        val_a = h_a.get(key)
        val_b = h_b.get(key)
        if not val_a:
            reasons.append(f"Missing required hash '{key}' in current run")
        if not val_b:
            reasons.append(f"Missing required hash '{key}' in baseline run")
        if val_a and val_b and val_a != val_b:
            reasons.append(f"{key} mismatch: {val_a} != {val_b}")

    # Optional hashes (prompt, config) must match if present in both
    for opt_key in ("prompt_hash", "config_hash"):
        opt_a = h_a.get(opt_key)
        opt_b = h_b.get(opt_key)
        if opt_a and opt_b and opt_a != opt_b:
            reasons.append(f"{opt_key} mismatch: {opt_a} != {opt_b}")

    # Evidence kind must match between runs
    def _extract_kind(r: Dict[str, Any]) -> Optional[str]:
        return r.get("evidence_kind") or r.get("manifest", {}).get("evidence_kind") if isinstance(r.get("manifest"), dict) else None

    kind_a = _extract_kind(run_a)
    kind_b = _extract_kind(run_b)
    if kind_a and kind_b and kind_a != kind_b:
        reasons.append(f"evidence_kind mismatch: '{kind_a}' vs '{kind_b}'")

    return (len(reasons) == 0, reasons)


def check_mixed_evidence(manifest_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Verify that a live certification run does not mix mock components or unverified heuristics.
    Returns (True, reasons) if mixed evidence is detected, or (False, []) if pure/consistent.
    """
    reasons: List[str] = []
    evidence_kind = manifest_data.get("evidence_kind", "simulated")
    model_mode = manifest_data.get("model_mode")
    profile = manifest_data.get("profile")

    if evidence_kind == "live":
        if model_mode in ("heuristic_demo", "unavailable", "synthetic", "unverified", "unknown", None):
            reasons.append(f"Live evidence declared with unverified/non-live model_mode: '{model_mode}'")
        if profile in ("mock", "simulated"):
            reasons.append(f"Live evidence declared with mock execution profile: '{profile}'")
        
        # Check metrics for mixed kinds
        metrics = manifest_data.get("metrics", {})
        if isinstance(metrics, dict):
            for m_name, m_val in metrics.items():
                m_dict = m_val if isinstance(m_val, dict) else (m_val.model_dump() if hasattr(m_val, "model_dump") else {})
                if m_dict.get("evidence_kind") in ("simulated", "mock", "cached", "unverified"):
                    reasons.append(f"Metric '{m_name}' has non-live evidence kind: '{m_dict.get('evidence_kind')}'")
                if m_dict.get("model_mode") in ("heuristic_demo", "synthetic", "unverified", "unknown"):
                    reasons.append(f"Metric '{m_name}' has unverified model mode: '{m_dict.get('model_mode')}'")

    return (len(reasons) > 0, reasons)


def audit_synthetic_benchmark(summary: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Audit anomaly heuristic: checks whether benchmark metrics match known static/synthetic templates.
    NOTE: Absence of synthetic signatures is NOT positive evidence authentication. Positive certification
    requires a cryptographically verified manifest, valid model hashes, and raw inference records.
    """
    reasons: List[str] = []

    grounding = summary.get("grounding", {}) or summary.get("llm_grounding", {})
    total_claims = grounding.get("total_claims")
    grounded_claims = grounding.get("grounded_claims")
    claim_rate = grounding.get("claim_grounding_rate")
    hallucination_rate = grounding.get("hallucination_rate")

    # Signature of static synthetic grounding benchmark in run_benchmarks.py: lines 506-535
    if total_claims == 68 and grounded_claims == 68 and claim_rate == 1.0 and hallucination_rate == 0.0:
        reasons.append("Detected static synthetic grounding signature (68/68 hardcoded claims, 0.0 hallucination rate)")

    intent = summary.get("intent_classification", {})
    # Exact accuracy from regex-fallback matching on 156 acceptance cases
    if intent.get("accuracy") == 0.9679 and intent.get("total_cases") == 156:
        reasons.append("Detected static keyword-fallback intent accuracy (0.9679 on 156 cases)")

    return (len(reasons) > 0, reasons)

