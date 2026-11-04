import hashlib
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class PolicyDocument(BaseModel):
    doc_id: str
    category: str
    title: str
    content: str
    version: str
    is_active: bool
    tags: List[str] = Field(default_factory=list)

class PolicyMetadata(BaseModel):
    # P1: Required approval metadata; no silent unapproved defaults
    status: str  # Must be explicitly provided: "approved", "draft", "revoked"
    approved_by: str
    approved_at: str
    valid_from: str
    valid_to: Optional[str] = None  # None indicates indefinite validity
    allowed_roles: List[str]
    policy_key: Optional[str] = None
    rule_assertions: List[Dict[str, Any]] = Field(default_factory=list)

class PolicyVersion(BaseModel):
    doc_id: str
    version: str
    category: str
    title: str
    content: str
    content_hash: str
    is_active: bool
    metadata: PolicyMetadata

def conditions_overlap(c1: Optional[Dict[str, Any]], c2: Optional[Dict[str, Any]]) -> bool:
    """P2: Check if two condition dictionaries overlap.
    Two conditions overlap if there is no key present in both dictionaries with different values.
    For example: {'seller': 'X'} and {'seller': 'X', 'market': 'US'} overlap!
    However, {'seller': 'X'} and {'seller': 'Y'} do not overlap.
    """
    if not c1 or not c2:
        return True
    for k in set(c1.keys()) & set(c2.keys()):
        if c1[k] != c2[k]:
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
                # If conditions overlap and values contradict -> conflict!
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
            # P1: Quarantine if required approval fields (approved_by, approved_at, valid_from, etc.) are missing
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
    """Filter versions strictly by role ACL and temporal validity."""
    now = as_of or datetime.now(timezone.utc)
    results: List[PolicyVersion] = []

    for v in versions:
        if not v.is_active or v.metadata.status != "approved":
            continue

        # P1: Enforce strict ACL without silently adding customer role
        if role not in v.metadata.allowed_roles:
            continue

        # Check temporal window
        v_from = v.metadata.valid_from
        v_to = v.metadata.valid_to

        if v_from:
            try:
                dt_from = datetime.fromisoformat(v_from.replace("Z", "+00:00"))
                if now < dt_from:
                    continue
            except Exception:
                pass

        if v_to:
            try:
                dt_to = datetime.fromisoformat(v_to.replace("Z", "+00:00"))
                if now > dt_to:
                    continue
            except Exception:
                pass

        results.append(v)

    return results
