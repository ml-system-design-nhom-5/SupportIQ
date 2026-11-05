import hashlib
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, field_validator

def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string ensuring valid format and UTC timezone."""
    if dt_str is None:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as exc:
        raise ValueError(f"Invalid ISO datetime string '{dt_str}': {exc}") from exc

class PolicyDocument(BaseModel):
    doc_id: str
    category: str
    title: str
    content: str
    version: str
    is_active: bool
    tags: List[str] = Field(default_factory=list)

class PolicyMetadata(BaseModel):
    # P1: Required approval metadata; strictly validates dates
    status: str  # Must be explicitly provided: "approved", "draft", "revoked"
    approved_by: str
    approved_at: str
    valid_from: str
    valid_to: Optional[str] = None  # None indicates indefinite validity
    allowed_roles: List[str]
    policy_key: Optional[str] = None
    rule_assertions: List[Dict[str, Any]] = Field(default_factory=list)
    supported_intents: List[str] = Field(default_factory=list)
    answer_capabilities: List[str] = Field(default_factory=list)

    @field_validator('approved_by')
    @classmethod
    def reviewer_not_blank(cls, value):
        if not value.strip():
            raise ValueError('approved_by cannot be blank')
        return value

    @field_validator("allowed_roles")
    @classmethod
    def validate_allowed_roles(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("allowed_roles cannot be empty")
        valid_roles = {"customer", "agent", "staff", "manager", "admin"}
        for r in v:
            if r not in valid_roles:
                raise ValueError(f"Invalid role '{r}' in allowed_roles (expected one of {valid_roles})")
        return v

    @field_validator("valid_from", "approved_at")
    @classmethod
    def validate_required_dates(cls, v: str) -> str:
        parse_iso_datetime(v)
        return v

    @field_validator("valid_to")
    @classmethod
    def validate_optional_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            parse_iso_datetime(v)
        return v

class PolicyVersion(BaseModel):
    doc_id: str
    version: str
    category: str
    title: str
    content: str
    content_hash: str
    is_active: bool
    metadata: PolicyMetadata

def normalize_condition(cond: Any) -> Dict[str, Any]:
    """Normalize condition representation.
    If condition is 'all', None, empty, or string, convert to dictionary.
    """
    if not cond or cond == "all":
        return {}
    if isinstance(cond, dict):
        return cond
    return {"scope": str(cond)}

def conditions_overlap(c1: Any, c2: Any) -> bool:
    """Check if two conditions overlap.
    Handles universal/string condition 'all' gracefully.
    Two conditions overlap if there is no key present in both dictionaries with different values.
    """
    d1 = normalize_condition(c1)
    d2 = normalize_condition(c2)
    if not d1 or not d2:
        return True
    for k in set(d1.keys()) & set(d2.keys()):
        if d1[k] != d2[k]:
            return False
    return True

def detect_rule_conflicts(rules: List[Dict[str, Any]]) -> bool:
    """Detect if two rules have the exact same key and overlapping conditions but contradictory values."""
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for r in rules:
        k = r.get("key")
        if not k:
            continue
        by_key.setdefault(k, []).append(r)

    for k, items in by_key.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                r1, r2 = items[i], items[j]
                cond1 = r1.get("condition")
                cond2 = r2.get("condition")
                if conditions_overlap(cond1, cond2) and r1.get("value") != r2.get("value"):
                    return True
    return False

def import_policies(
    policies_data: List[Dict[str, Any]],
    metadata_data: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """Import and validate policies against versioned metadata sidecar."""
    eligible: List[PolicyVersion] = []
    quarantined: List[Dict[str, Any]] = []

    for p in policies_data:
        doc_id = p.get("doc_id")
        ver = str(p.get("version", "1.0"))
        meta_key = f"{doc_id}:{ver}"
        raw_meta = metadata_data.get(meta_key)

        if not raw_meta:
            quarantined.append({"doc_id": doc_id, "reason": "missing_metadata"})
            continue

        try:
            meta = PolicyMetadata(**raw_meta)
        except Exception as e:
            # P1: Invalid date format or missing required approval metadata is quarantined
            quarantined.append({"doc_id": doc_id, "reason": f"invalid_approval_metadata: {e}"})
            continue

        content = p.get("content", "")
        c_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        policy_ver = PolicyVersion(
            doc_id=doc_id,
            version=ver,
            category=p.get("category", "general"),
            title=p.get("title", ""),
            content=content,
            content_hash=c_hash,
            is_active=bool(p.get("is_active", True)),
            metadata=meta,
        )

        if policy_ver.is_active and meta.status == "approved":
            eligible.append(policy_ver)
        else:
            quarantined.append({"doc_id": doc_id, "reason": "inactive_or_not_approved"})

    return {
        "imported_count": len(policies_data),
        "eligible": eligible,
        "quarantined_count": len(quarantined),
        "quarantined": quarantined,
    }

def eligible_versions(
    versions: List[PolicyVersion],
    role: str = "customer",
    as_of: Optional[datetime] = None
) -> List[PolicyVersion]:
    """Filter versions strictly by role ACL and temporal validity:
    valid_from <= as_of < valid_to.
    P1 FIX: If date parsing fails, version is treated as unverifiable and excluded.
    P2 FIX: Excluded when as_of >= valid_to (strict upper bound < valid_to).
    """
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    results: List[PolicyVersion] = []

    for v in versions:
        if not v.is_active or v.metadata.status != "approved":
            continue

        # Enforce strict ACL without silently adding customer role
        if role not in v.metadata.allowed_roles:
            continue

        # Check temporal window: valid_from <= now < valid_to
        v_from_str = v.metadata.valid_from
        v_to_str = v.metadata.valid_to

        # P1: Validate valid_from parsing
        try:
            dt_from = parse_iso_datetime(v_from_str)
            if dt_from is not None and now < dt_from:
                continue
        except Exception:
            # Unverifiable validity date -> exclude!
            continue

        # P1 & P2: Validate valid_to parsing and enforce strict upper bound: now >= valid_to is excluded!
        if v_to_str:
            try:
                dt_to = parse_iso_datetime(v_to_str)
                if dt_to is not None and now >= dt_to:
                    continue
            except Exception:
                # Unverifiable validity date -> exclude!
                continue

        results.append(v)

    return results


def publish_approved_kb(staging_path: Union[str, Any], output_path: Union[str, Any]) -> Any:
    """Validate and atomically publish approved knowledge base records.
    Refuses to overwrite an existing published version file.
    Verifies human approval metadata, dates, real SHA-256 content hashes,
    applicability metadata, and absence of rule conflicts.
    """
    from pathlib import Path
    s_path = Path(staging_path)
    out_path = Path(output_path)

    if not s_path.exists():
        raise FileNotFoundError(f"Staging KB file not found at {s_path}")

    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing published KB file at {out_path}")

    with open(s_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    if not isinstance(records, list) or not records:
        raise ValueError("Staging KB must contain a non-empty list of document records")

    verified_records = []
    for rec in records:
        doc_id = rec.get("doc_id") or rec.get("document_id")
        if not doc_id:
            raise ValueError("Record missing document_id or doc_id")

        status = rec.get("status")
        if status != "approved":
            raise ValueError(f"Record '{doc_id}' is not approved (status: '{status}')")

        content = rec.get("content", rec.get("sanitized_excerpt", ""))
        real_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        declared_hash = rec.get("content_hash")
        if not declared_hash or declared_hash.lower() != real_hash.lower():
            raise ValueError(f"Record '{doc_id}' content hash mismatch: declared '{declared_hash}', expected '{real_hash}'")

        # Validate metadata with PolicyMetadata
        meta = PolicyMetadata(
            status=status,
            approved_by=rec.get("approved_by", ""),
            approved_at=rec.get("approved_at", ""),
            valid_from=rec.get("valid_from", ""),
            valid_to=rec.get("valid_to"),
            allowed_roles=rec.get("allowed_roles", []),
            policy_key=rec.get("policy_key"),
            rule_assertions=rec.get("rule_assertions", []),
            supported_intents=rec.get("supported_intents", []),
            answer_capabilities=rec.get("answer_capabilities", []),
        )

        if detect_rule_conflicts(meta.rule_assertions):
            raise ValueError(f"Record '{doc_id}' has conflicting rule assertions")

        rec_copy = dict(rec)
        rec_copy["document_id"] = doc_id
        rec_copy["doc_id"] = doc_id
        rec_copy["content_hash"] = real_hash
        rec_copy["supported_intents"] = meta.supported_intents
        rec_copy["answer_capabilities"] = meta.answer_capabilities
        verified_records.append(rec_copy)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out_path.with_suffix(".tmp")
    tmp_out.write_text(json.dumps(verified_records, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_out.replace(out_path)
    return out_path

