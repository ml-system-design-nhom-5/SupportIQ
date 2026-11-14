"""Single-factor TRAIN-only return-channel contrast extension for Original Fit2.

Anchors strictly to Original Fit2 (`f695b1fe...`) by reusing the canonical
`prepare_and_lock_splits(..., apply_active_kb_audit=False, exclude_noisy_test_overlap=False)`
pipeline untouched for all Bitext replay, noise, CAL, EVAL, and boundary negative
splits, and appends ONLY a small, balanced, KB-grounded TRAIN contrast slice
separating general/online return eligibility (`return_policy`, SUPPORTED_12) from
unsupported walk-in physical retail store returns (`return_product_in_store`,
ESCALATED_34) per `approved_kb.v2.json` (`POL-RET-001/002/003`).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from apps.backend.tickets.privacy import pseudonymize
from pipeline.evaluation.classifier_acceptance_gate import (
    ESCALATED_34_INTENTS,
    STANDARD_INTENTS_46,
    check_split_isolation_and_gold_contamination,
)
from pipeline.training.domain_templates import FROZEN_BENCHMARK_PATHS
from pipeline.training.selective_domain_data import _jaccard, _normalize_text, _token_f1, _token_set
from pipeline.training.train_boundary_candidate import (
    classify_row_kb_semantics,
    prepare_and_lock_splits,
    validate_boundary_split_taxonomy,
)

EXTENSION_VERSION = "orig_fit2_return_channel_contrast_v2"
KB_VERSION = "approved_kb.v2.json"
POLICY_VERSION = "intent_policy.v2.json"
KB_RATIONALE = (
    "approved_kb.v2.json POL-RET-001/002/003 define online return windows (30d Tiki Trading / "
    "7d marketplace), packaging/seal/gift and restricted category rules, My Orders Request Return "
    "photo/video submission, and courier pickup or designated partner post office drop-off under "
    "return_policy (SUPPORTED_12). Physical brick-and-mortar retail storefront/branch walk-in "
    "returns are an unsupported offline channel belonging to return_product_in_store (ESCALATED_34)."
)

# Frozen evaluation/holdout suites referenced in protocol_manifest.json + FROZEN_BENCHMARK_PATHS.
FROZEN_PROTOCOL_HOLDOUT_PATHS: Tuple[str, ...] = tuple(
    dict.fromkeys(
        list(FROZEN_BENCHMARK_PATHS)
        + [
            "artifacts/evaluation/fit2_independent_gate_20261113/cases.jsonl",
            "artifacts/evaluation/sealed_holdout_20261113/sealed_holdout_cases.jsonl",
            "artifacts/evaluation/fit2_v4p1_independent_20261114/fresh_holdout_34.jsonl",
            "artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2/inputs/boundary_pos_evaluation.jsonl",
            "artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2/inputs/boundary_neg_evaluation.jsonl",
            "artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2/inputs/bitext_test_6690.jsonl",
            "artifacts/models/candidates/run-records-faithful-fit2-20261113/stage2_inputs/boundary_pos_evaluation.jsonl",
            "artifacts/models/candidates/run-records-faithful-fit2-20261113/stage2_inputs/boundary_neg_evaluation.jsonl",
        ]
    )
)

ORIG_FIT2_STAGE2_REL = "artifacts/models/candidates/run-records-faithful-fit2-20261113/stage2_inputs"
EXPECTED_ORIG_STAGE2_LOCKED_FILES: Tuple[str, ...] = (
    "split_manifest.json",
    "boundary_pos_train.jsonl",
    "boundary_neg_train.jsonl",
    "boundary_pos_calibration.jsonl",
    "boundary_neg_calibration.jsonl",
    "boundary_pos_evaluation.jsonl",
    "boundary_neg_evaluation.jsonl",
    "bitext_train_clean.jsonl",
    "bitext_train_noisy.jsonl",
    "bitext_cal.jsonl",
    "bitext_test_6690.jsonl",
    "full_train_split.jsonl",
    "full_cal_split.jsonl",
)


@dataclass(frozen=True)
class ReturnContrastRowSpec:
    """One KB-grounded TRAIN-only contrast example."""

    sample_id: str
    group_id: str
    intent: str
    policy_source: str
    text: str


# 10 return_policy (rep=4 -> 40 effective) + 8 return_product_in_store (rep=5 -> 40 effective).
# All 18 rows sit in 4 paired TRAIN-only thematic groups targeting general/online eligibility vs
# physical brick-and-mortar retail store walk-in channel. Zero CAL/EVAL rows are added.
ORIG_FIT2_RETURN_CONTRAST_ROWS: Tuple[ReturnContrastRowSpec, ...] = (
    # Group 1: Channel & eligibility deadlines (POL-RET-001/002 vs physical branch desk)
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g01_rp_00",
        group_id="orig_ret_ch_g01",
        intent="return_policy",
        policy_source="POL-RET-001",
        text="Which return window applies to marketplace sellers versus direct Tiki Trading purchases under your return policy?",
    ),
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g01_rp_01",
        group_id="orig_ret_ch_g01",
        intent="return_policy",
        policy_source="POL-RET-001",
        text="Are standard marketplace returns eligible when filed eight days after order delivery?",
    ),
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g01_rp_02",
        group_id="orig_ret_ch_g01",
        intent="return_policy",
        policy_source="POL-RET-002",
        text="Does the courier pickup option or designated partner post office apply when an eligible parcel goes back?",
    ),
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g01_ris_00",
        group_id="orig_ret_ch_g01",
        intent="return_product_in_store",
        policy_source="POL-RET-002_vs_physical_store",
        text="Can shoppers hand back a recent online purchase at a physical retail branch desk?",
    ),
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g01_ris_01",
        group_id="orig_ret_ch_g01",
        intent="return_product_in_store",
        policy_source="POL-RET-002_vs_physical_store",
        text="Do you operate local brick-and-mortar storefronts where buyers can turn in unwanted orders?",
    ),
    # Group 2: Packaging, media evidence & condition eligibility vs walk-in store counter
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g02_rp_00",
        group_id="orig_ret_ch_g02",
        intent="return_policy",
        policy_source="POL-RET-001",
        text="Must original promotional gifts and factory seals stay unbroken to qualify for a return or exchange?",
    ),
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g02_rp_01",
        group_id="orig_ret_ch_g02",
        intent="return_policy",
        policy_source="POL-RET-002",
        text="How many unboxing photos or video clips are required in Order Management to submit a return?",
    ),
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g02_rp_02",
        group_id="orig_ret_ch_g02",
        intent="return_policy",
        policy_source="POL-RET-001",
        text="Must a returned product stay unwashed and unused with its original boxes, accessories, and invoices included?",
    ),
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g02_ris_00",
        group_id="orig_ret_ch_g02",
        intent="return_product_in_store",
        policy_source="POL-RET-002_vs_physical_store",
        text="Is there an in-person store counter near downtown that handles walk-in return drop-offs?",
    ),
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g02_ris_01",
        group_id="orig_ret_ch_g02",
        intent="return_product_in_store",
        policy_source="POL-RET-002_vs_physical_store",
        text="Can a cashier at a neighborhood retail shop take my defective parcel directly across the register?",
    ),
    # Group 3: Restricted categories & exceptions vs mall showroom / outlet register
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g03_rp_00",
        group_id="orig_ret_ch_g03",
        intent="return_policy",
        policy_source="POL-RET-003",
        text="Why are opened beauty formulas, perishable groceries, and digital vouchers barred from change-of-mind returns?",
    ),
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g03_rp_01",
        group_id="orig_ret_ch_g03",
        intent="return_policy",
        policy_source="POL-RET-003",
        text="When do restricted swimwear or non-returnable clearance outlet items still qualify for a return or exchange?",
    ),
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g03_ris_00",
        group_id="orig_ret_ch_g03",
        intent="return_product_in_store",
        policy_source="POL-RET-002_vs_physical_store",
        text="Could I visit your mall showroom branch to hand my parcel over to a retail clerk instead of booking pickup?",
    ),
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g03_ris_01",
        group_id="orig_ret_ch_g03",
        intent="return_product_in_store",
        policy_source="POL-RET-002_vs_physical_store",
        text="Are any brick-and-mortar outlet counters authorized to inspect and take back web purchases on site?",
    ),
    # Group 4: Order Management status, pickup window & partner post office vs physical branch receipt
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g04_rp_00",
        group_id="orig_ret_ch_g04",
        intent="return_policy",
        policy_source="POL-RET-002",
        text="Which order status enables Request Return/Exchange in Order Management, and within how many business days does courier pickup occur?",
    ),
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g04_rp_01",
        group_id="orig_ret_ch_g04",
        intent="return_policy",
        policy_source="POL-RET-002",
        text="Where should buyers lodge a return request after delivery before dropping the parcel at a partner post office?",
    ),
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g04_ris_00",
        group_id="orig_ret_ch_g04",
        intent="return_product_in_store",
        policy_source="POL-RET-002_vs_physical_store",
        text="Will a retail storefront employee give me a receipt if I leave my returned merchandise at a physical branch?",
    ),
    ReturnContrastRowSpec(
        sample_id="orig_ret_ch_g04_ris_01",
        group_id="orig_ret_ch_g04",
        intent="return_product_in_store",
        policy_source="POL-RET-002_vs_physical_store",
        text="Does your chain offer walk-in returns at retail locations when customers skip app courier scheduling?",
    ),
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> str:
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    path.write_text(payload, encoding="utf-8")
    return _sha256_file(path)


def _extract_row_text(row: Dict[str, Any]) -> str:
    return str(row.get("text") or row.get("instruction") or row.get("query") or "").strip()


def build_orig_fit2_return_contrast_rows() -> List[Dict[str, Any]]:
    """Build deterministic TRAIN-only return-channel contrast rows with provenance hashes."""
    seen_ids: set[str] = set()
    rows: List[Dict[str, Any]] = []
    for spec in ORIG_FIT2_RETURN_CONTRAST_ROWS:
        if spec.sample_id in seen_ids:
            raise ValueError(f"Duplicate sample_id in extension spec: {spec.sample_id}")
        if spec.intent not in ("return_policy", "return_product_in_store"):
            raise ValueError(f"Unexpected intent in single-factor return contrast: {spec.intent}")
        seen_ids.add(spec.sample_id)
        canonical_payload = json.dumps(
            {
                "sample_id": spec.sample_id,
                "group_id": spec.group_id,
                "intent": spec.intent,
                "policy_source": spec.policy_source,
                "kb_version": KB_VERSION,
                "text": spec.text,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        source_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest().lower()
        text_sha = hashlib.sha256(spec.text.encode("utf-8")).hexdigest().lower()
        row = {
            "sample_id": spec.sample_id,
            "parent_sample_id": spec.sample_id,
            "text": spec.text,
            "instruction": spec.text,
            "intent": spec.intent,
            "true_intent": spec.intent,
            "group_id": spec.group_id,
            "split": "train",
            "source": EXTENSION_VERSION,
            "policy_source": spec.policy_source,
            "kb_version": KB_VERSION,
            "text_sha256": text_sha,
            "source_hash": source_hash,
            "selective_label": 1,
            "is_negative": 0,
        }
        sem = classify_row_kb_semantics(row)
        if sem["status"] != "valid":
            raise ValueError(
                f"Extension row failed KB semantic check ({sem['status']}: {sem['reason']}): {spec.sample_id}"
            )
        rows.append(row)
    return rows


def compute_effective_train_exposure(
    *,
    pos_train: Sequence[Dict[str, Any]],
    bitext_clean: Sequence[Dict[str, Any]],
    bitext_noisy: Sequence[Dict[str, Any]],
    neg_train: Sequence[Dict[str, Any]],
    neg_repeat: int = 12,
) -> Dict[str, Any]:
    """Compute raw and effective training exposure mirroring `run_fit_and_lock_candidate`."""
    raw_pos_by_intent: Counter[str] = Counter(str(r["intent"]) for r in pos_train)
    eff_pos_by_intent: Counter[str] = Counter()
    for r in pos_train:
        intent = str(r["intent"])
        rep = 5 if intent in ESCALATED_34_INTENTS else 4
        eff_pos_by_intent[intent] += rep

    bitext_raw_by_intent: Counter[str] = Counter(str(r["intent"]) for r in list(bitext_clean) + list(bitext_noisy))
    total_eff_by_intent: Counter[str] = Counter(eff_pos_by_intent)
    total_eff_by_intent.update(bitext_raw_by_intent)

    eff_neg_total = sum(
        int(r["neg_repeat"]) if isinstance(r.get("neg_repeat"), int) else neg_repeat for r in neg_train
    )
    eff_pos_total = sum(eff_pos_by_intent.values()) + len(bitext_clean) + len(bitext_noisy)
    return {
        "raw_pos_train": len(pos_train),
        "raw_bitext_train_clean": len(bitext_clean),
        "raw_bitext_train_noisy": len(bitext_noisy),
        "raw_neg_train": len(neg_train),
        "raw_train_total": len(pos_train) + len(bitext_clean) + len(bitext_noisy) + len(neg_train),
        "effective_pos_total": eff_pos_total,
        "effective_neg_total": eff_neg_total,
        "effective_train_total": eff_pos_total + eff_neg_total,
        "target_pair_raw_domain": {
            "return_policy": int(raw_pos_by_intent.get("return_policy", 0)),
            "return_product_in_store": int(raw_pos_by_intent.get("return_product_in_store", 0)),
        },
        "target_pair_effective_domain": {
            "return_policy": int(eff_pos_by_intent.get("return_policy", 0)),
            "return_product_in_store": int(eff_pos_by_intent.get("return_product_in_store", 0)),
        },
        "target_pair_raw_total_with_bitext": {
            "return_policy": int(raw_pos_by_intent.get("return_policy", 0) + bitext_raw_by_intent.get("return_policy", 0)),
            "return_product_in_store": int(
                raw_pos_by_intent.get("return_product_in_store", 0) + bitext_raw_by_intent.get("return_product_in_store", 0)
            ),
        },
        "target_pair_effective_total_with_bitext": {
            "return_policy": int(total_eff_by_intent.get("return_policy", 0)),
            "return_product_in_store": int(total_eff_by_intent.get("return_product_in_store", 0)),
        },
    }


def _measure_historical_noisy_overlap(
    *,
    bitext_noisy: Sequence[Dict[str, Any]],
    bitext_clean: Sequence[Dict[str, Any]],
    cal_rows: Sequence[Dict[str, Any]],
    eval_rows: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Read-only disclosure of historical Fit2 exclude_noisy_test_overlap=False overlap."""
    noisy_norms = {_normalize_text(_extract_row_text(r)): r for r in bitext_noisy if _extract_row_text(r)}
    clean_norms = {_normalize_text(_extract_row_text(r)) for r in bitext_clean if _extract_row_text(r)}
    cal_norms = {_normalize_text(_extract_row_text(r)) for r in cal_rows if _extract_row_text(r)}
    eval_norms = {_normalize_text(_extract_row_text(r)) for r in eval_rows if _extract_row_text(r)}
    noisy_eval_overlap = sorted(set(noisy_norms.keys()) & eval_norms)
    noisy_cal_overlap = sorted(set(noisy_norms.keys()) & cal_norms)
    clean_eval_overlap = sorted(clean_norms & eval_norms)
    return {
        "exclude_noisy_test_overlap": False,
        "historical_bitext_train_noisy_vs_eval_norm_overlap_count": len(noisy_eval_overlap),
        "historical_bitext_train_noisy_vs_eval_sample_ids": [
            str(noisy_norms[n].get("sample_id")) for n in noisy_eval_overlap[:10]
        ],
        "historical_bitext_train_noisy_vs_cal_norm_overlap_count": len(noisy_cal_overlap),
        "historical_bitext_train_clean_vs_eval_norm_overlap_count": len(clean_eval_overlap),
        "note": (
            "Retained unmodified from Original Fit2 stage2_inputs (run-records-faithful-fit2-20261113) "
            "to avoid bundling noisy-overlap filtering into this single-factor experiment."
        ),
    }


def _collect_reference_corpus(repo_root: Path) -> Dict[str, List[Tuple[str, str]]]:
    """Load frozen eval/benchmark suites and prior training inputs for leakage auditing."""
    suites: Dict[str, List[Tuple[str, str]]] = {}
    for rel in FROZEN_PROTOCOL_HOLDOUT_PATHS:
        p = repo_root / rel
        if not p.exists():
            raise FileNotFoundError(f"Missing required frozen holdout/benchmark file: {p}")
        entries: List[Tuple[str, str]] = []
        if p.suffix.lower() == ".jsonl":
            for idx, row in enumerate(_read_jsonl(p)):
                txt = _extract_row_text(row)
                cid = str(row.get("id") or row.get("case_id") or row.get("sample_id") or idx)
                if txt:
                    entries.append((cid, txt))
        else:
            raw = json.loads(p.read_text(encoding="utf-8"))
            rows = raw if isinstance(raw, list) else raw.get("cases", [])
            for idx, row in enumerate(rows):
                txt = _extract_row_text(row)
                cid = str(row.get("id") or row.get("case_id") or row.get("sample_id") or idx)
                if txt:
                    entries.append((cid, txt))
        suites[rel] = entries
    return suites


def audit_extension_isolation(
    *,
    repo_root: Path,
    extension_rows: Sequence[Dict[str, Any]],
    baseline_train_rows: Sequence[Dict[str, Any]],
    baseline_cal_rows: Sequence[Dict[str, Any]],
    baseline_eval_rows: Sequence[Dict[str, Any]],
    max_allowed_jaccard: float = 0.55,
    max_allowed_token_f1: float = 0.65,
) -> Dict[str, Any]:
    """Fail-closed check of text, parent, group, and near-duplicate isolation."""
    ext_norms = {_normalize_text(r["text"]): r for r in extension_rows}
    if len(ext_norms) != len(extension_rows):
        raise ValueError("Duplicate normalized text inside extension rows")

    ext_ids = {str(r["sample_id"]) for r in extension_rows}
    ext_parents = {str(r["parent_sample_id"]) for r in extension_rows}
    ext_groups = {str(r["group_id"]) for r in extension_rows}

    # Include prior v5-r2 / v4p1 inputs if present so new TRAIN families remain distinct from prior archives too.
    prior_splits: Dict[str, Sequence[Dict[str, Any]]] = {
        "baseline_train": baseline_train_rows,
        "baseline_cal": baseline_cal_rows,
        "baseline_eval": baseline_eval_rows,
    }
    for extra_rel in (
        "artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2/inputs/full_train_split.jsonl",
        "artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2/inputs/full_cal_split.jsonl",
    ):
        ep = repo_root / extra_rel
        if ep.exists():
            prior_splits[extra_rel] = _read_jsonl(ep)

    split_overlap_summary: Dict[str, Dict[str, int]] = {}
    for s_name, s_rows in prior_splits.items():
        s_ids = {str(r.get("sample_id") or "") for r in s_rows}
        s_parents = {str(r.get("parent_sample_id") or r.get("sample_id") or "") for r in s_rows}
        s_groups = {str(r.get("group_id") or "") for r in s_rows}
        s_norms = {_normalize_text(_extract_row_text(r)) for r in s_rows if _extract_row_text(r)}
        ov = {
            "sample_id_overlap": len(ext_ids & s_ids),
            "parent_sample_id_overlap": len(ext_parents & s_parents),
            "group_id_overlap": len(ext_groups & s_groups),
            "normalized_text_overlap": len(set(ext_norms.keys()) & s_norms),
        }
        if any(v > 0 for v in ov.values()):
            raise ValueError(f"Isolation violation against {s_name}: {ov}")
        split_overlap_summary[s_name] = ov

    suites = _collect_reference_corpus(repo_root)
    eval_archive_suites = {
        "artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2/inputs/boundary_pos_evaluation.jsonl",
        "artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2/inputs/boundary_neg_evaluation.jsonl",
        "artifacts/models/candidates/run-records-fit2-taxonomy-audit-v5-r2/inputs/bitext_test_6690.jsonl",
        "artifacts/models/candidates/run-records-faithful-fit2-20261113/stage2_inputs/boundary_pos_evaluation.jsonl",
        "artifacts/models/candidates/run-records-faithful-fit2-20261113/stage2_inputs/boundary_neg_evaluation.jsonl",
    }
    gold_triples: List[Tuple[str, str, str]] = [
        (suite_name, cid, txt)
        for suite_name, entries in suites.items()
        if suite_name not in eval_archive_suites
        for cid, txt in entries
    ]
    extension_gate_audit = check_split_isolation_and_gold_contamination(
        train_rows=list(extension_rows),
        calibration_rows=list(baseline_cal_rows),
        eval_rows=list(baseline_eval_rows),
        gold_texts=gold_triples,
    )
    if not extension_gate_audit.get("passed"):
        raise ValueError(f"Extension gate split isolation failed: {extension_gate_audit}")

    # Near-duplicate & exact check against all frozen benchmark/holdout suites + baseline eval/cal.
    suites["baseline_cal_all"] = [(str(r.get("sample_id")), _extract_row_text(r)) for r in baseline_cal_rows]
    suites["baseline_eval_all"] = [(str(r.get("sample_id")), _extract_row_text(r)) for r in baseline_eval_rows]

    ext_tokens = []
    pseudonymize_changed_rows: List[str] = []
    for r in extension_rows:
        raw_txt = str(r["text"])
        priv_txt, _ = pseudonymize(raw_txt, {})
        if priv_txt != raw_txt:
            pseudonymize_changed_rows.append(str(r["sample_id"]))
        ext_tokens.append(
            (
                str(r["sample_id"]),
                raw_txt,
                _token_set(raw_txt),
                _normalize_text(raw_txt),
                priv_txt,
                _token_set(priv_txt),
                _normalize_text(priv_txt),
            )
        )

    suite_reports: Dict[str, Any] = {}
    overall_max_jaccard = 0.0
    overall_max_f1 = 0.0
    overall_post_privacy_max_jaccard = 0.0
    overall_post_privacy_max_f1 = 0.0

    for suite_name, entries in suites.items():
        exact_hits = 0
        post_privacy_exact_hits = 0
        max_jac = 0.0
        max_f1 = 0.0
        priv_max_jac = 0.0
        priv_max_f1 = 0.0
        top_pair: Dict[str, Any] | None = None
        for cid, ctxt in entries:
            cnorm = _normalize_text(ctxt)
            ctoks = _token_set(ctxt)
            cpriv, _ = pseudonymize(ctxt, {})
            cpriv_norm = _normalize_text(cpriv)
            cpriv_toks = _token_set(cpriv)
            for ext_id, eraw, etoks, enorm, epriv, epriv_toks, epriv_norm in ext_tokens:
                if enorm == cnorm:
                    exact_hits += 1
                if epriv_norm == cpriv_norm:
                    post_privacy_exact_hits += 1
                jac = _jaccard(etoks, ctoks) if (etoks and ctoks) else 0.0
                f1 = _token_f1(eraw, ctxt) if (etoks and ctoks) else 0.0
                pjac = _jaccard(epriv_toks, cpriv_toks) if (epriv_toks and cpriv_toks) else 0.0
                pf1 = _token_f1(epriv, cpriv) if (epriv_toks and cpriv_toks) else 0.0
                if jac > max_jac or f1 > max_f1:
                    if f1 >= max_f1:
                        max_f1 = f1
                    if jac >= max_jac:
                        max_jac = jac
                    top_pair = {
                        "extension_id": ext_id,
                        "reference_id": cid,
                        "jaccard": round(jac, 4),
                        "token_f1": round(f1, 4),
                    }
                priv_max_jac = max(priv_max_jac, pjac)
                priv_max_f1 = max(priv_max_f1, pf1)
        overall_max_jaccard = max(overall_max_jaccard, max_jac)
        overall_max_f1 = max(overall_max_f1, max_f1)
        overall_post_privacy_max_jaccard = max(overall_post_privacy_max_jaccard, priv_max_jac)
        overall_post_privacy_max_f1 = max(overall_post_privacy_max_f1, priv_max_f1)
        if (
            exact_hits > 0
            or post_privacy_exact_hits > 0
            or max_jac >= max_allowed_jaccard
            or max_f1 >= max_allowed_token_f1
            or priv_max_jac >= max_allowed_jaccard
            or priv_max_f1 >= max_allowed_token_f1
        ):
            raise ValueError(
                f"Benchmark/holdout contamination or near-duplicate detected in {suite_name}: "
                f"exact={exact_hits}, post_privacy_exact={post_privacy_exact_hits}, "
                f"max_jaccard={max_jac:.4f}, max_token_f1={max_f1:.4f}, "
                f"post_privacy_max_jaccard={priv_max_jac:.4f}, post_privacy_max_token_f1={priv_max_f1:.4f}, "
                f"top_pair={top_pair}"
            )
        suite_reports[suite_name] = {
            "reference_rows": len(entries),
            "exact_norm_overlap": exact_hits,
            "post_privacy_exact_norm_overlap": post_privacy_exact_hits,
            "max_jaccard": round(max_jac, 4),
            "max_token_f1": round(max_f1, 4),
            "post_privacy_max_jaccard": round(priv_max_jac, 4),
            "post_privacy_max_token_f1": round(priv_max_f1, 4),
            "closest_pair": top_pair,
        }

    return {
        "isolation_passed": True,
        "extension_rows_count": len(extension_rows),
        "extension_groups": sorted(ext_groups),
        "pseudonymize_changed_extension_rows": pseudonymize_changed_rows,
        "prior_split_overlaps": split_overlap_summary,
        "extension_gate_split_isolation": extension_gate_audit,
        "max_jaccard_across_all_frozen_suites": round(overall_max_jaccard, 4),
        "max_token_f1_across_all_frozen_suites": round(overall_max_f1, 4),
        "post_privacy_max_jaccard_across_all_frozen_suites": round(overall_post_privacy_max_jaccard, 4),
        "post_privacy_max_token_f1_across_all_frozen_suites": round(overall_post_privacy_max_f1, 4),
        "thresholds": {
            "max_allowed_jaccard": max_allowed_jaccard,
            "max_allowed_token_f1": max_allowed_token_f1,
        },
        "suite_reports": suite_reports,
    }


def _file_hashes(datasets_dir: Path, filenames: Iterable[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for fname in filenames:
        p = datasets_dir / fname
        if not p.exists():
            raise FileNotFoundError(f"Expected locked dataset file missing: {p}")
        out[fname] = _sha256_file(p)
    return out


def prepare_and_lock_orig_fit2_return_contrast_splits(
    *,
    worktree_root: Path,
    data_repo_root: Path,
    init_model_dir: Path,
    artifact_root: Path,
    replay_per_class: int = 160,
    noise_aug_per_class: int = 80,
    bitext_cal_per_class: int = 15,
    seed: int = 20261113,
) -> Dict[str, Any]:
    """Reproduce exact Original Fit2 splits and apply ONLY the TRAIN return-channel delta."""
    base_lock = prepare_and_lock_splits(
        worktree_root=worktree_root,
        data_repo_root=data_repo_root,
        init_model_dir=init_model_dir,
        artifact_root=artifact_root,
        replay_per_class=replay_per_class,
        noise_aug_per_class=noise_aug_per_class,
        bitext_cal_per_class=bitext_cal_per_class,
        seed=seed,
        apply_active_kb_audit=False,
        exclude_noisy_test_overlap=False,
    )
    ds_dir = artifact_root / "datasets"
    orig_stage2_dir = data_repo_root / ORIG_FIT2_STAGE2_REL
    if not orig_stage2_dir.is_dir():
        raise FileNotFoundError(f"Missing Original Fit2 stage2_inputs reference: {orig_stage2_dir}")

    baseline_file_hashes = _file_hashes(ds_dir, EXPECTED_ORIG_STAGE2_LOCKED_FILES)
    orig_ref_hashes = _file_hashes(orig_stage2_dir, EXPECTED_ORIG_STAGE2_LOCKED_FILES)
    hash_diffs_vs_orig = {
        fname: {"prepared": baseline_file_hashes[fname], "orig_fit2_stage2": orig_ref_hashes[fname]}
        for fname in EXPECTED_ORIG_STAGE2_LOCKED_FILES
        if baseline_file_hashes[fname] != orig_ref_hashes[fname]
    }
    if hash_diffs_vs_orig:
        raise ValueError(
            "Reproduced Original Fit2 baseline splits diverged from archived "
            f"run-records-faithful-fit2-20261113/stage2_inputs: {hash_diffs_vs_orig}"
        )

    pos_train = _read_jsonl(ds_dir / "boundary_pos_train.jsonl")
    neg_train = _read_jsonl(ds_dir / "boundary_neg_train.jsonl")
    bitext_clean = _read_jsonl(ds_dir / "bitext_train_clean.jsonl")
    bitext_noisy = _read_jsonl(ds_dir / "bitext_train_noisy.jsonl")
    pos_cal = _read_jsonl(ds_dir / "boundary_pos_calibration.jsonl")
    neg_cal = _read_jsonl(ds_dir / "boundary_neg_calibration.jsonl")
    bitext_cal = _read_jsonl(ds_dir / "bitext_cal.jsonl")
    pos_eval = _read_jsonl(ds_dir / "boundary_pos_evaluation.jsonl")
    neg_eval = _read_jsonl(ds_dir / "boundary_neg_evaluation.jsonl")
    bitext_test = _read_jsonl(ds_dir / "bitext_test_6690.jsonl")
    full_train_base = _read_jsonl(ds_dir / "full_train_split.jsonl")
    full_cal_base = _read_jsonl(ds_dir / "full_cal_split.jsonl")

    ext_rows = build_orig_fit2_return_contrast_rows()
    isolation = audit_extension_isolation(
        repo_root=data_repo_root,
        extension_rows=ext_rows,
        baseline_train_rows=full_train_base,
        baseline_cal_rows=full_cal_base,
        baseline_eval_rows=pos_eval + neg_eval + bitext_test,
    )
    historical_noisy_overlap = _measure_historical_noisy_overlap(
        bitext_noisy=bitext_noisy,
        bitext_clean=bitext_clean,
        cal_rows=full_cal_base,
        eval_rows=pos_eval + neg_eval + bitext_test,
    )

    new_pos_train = pos_train + ext_rows
    new_full_train = full_train_base + ext_rows
    validate_boundary_split_taxonomy(new_pos_train, neg_train, "orig_fit2_return_contrast_train")
    validate_boundary_split_taxonomy(pos_cal, neg_cal, "orig_fit2_return_contrast_cal")
    validate_boundary_split_taxonomy(pos_eval, neg_eval, "orig_fit2_return_contrast_eval")

    ext_sha = _write_jsonl(ds_dir / "orig_fit2_return_contrast_extension.jsonl", ext_rows)
    pos_train_sha = _write_jsonl(ds_dir / "boundary_pos_train.jsonl", new_pos_train)
    full_train_sha = _write_jsonl(ds_dir / "full_train_split.jsonl", new_full_train)

    new_file_hashes = _file_hashes(ds_dir, EXPECTED_ORIG_STAGE2_LOCKED_FILES)
    unchanged_files = [
        fname
        for fname in EXPECTED_ORIG_STAGE2_LOCKED_FILES
        if new_file_hashes[fname] == orig_ref_hashes[fname]
    ]
    changed_files = {
        fname: {
            "baseline_sha256": orig_ref_hashes[fname],
            "new_sha256": new_file_hashes[fname],
        }
        for fname in EXPECTED_ORIG_STAGE2_LOCKED_FILES
        if new_file_hashes[fname] != orig_ref_hashes[fname]
    }
    if set(changed_files.keys()) != {"boundary_pos_train.jsonl", "full_train_split.jsonl"}:
        raise RuntimeError(f"Expected ONLY boundary_pos_train and full_train_split to change; got {changed_files}")

    baseline_exposure = compute_effective_train_exposure(
        pos_train=pos_train,
        bitext_clean=bitext_clean,
        bitext_noisy=bitext_noisy,
        neg_train=neg_train,
    )
    new_exposure = compute_effective_train_exposure(
        pos_train=new_pos_train,
        bitext_clean=bitext_clean,
        bitext_noisy=bitext_noisy,
        neg_train=neg_train,
    )

    # Preserve canonical 7 lock keys in dataset_hashes with updated full_train_split SHA.
    updated_hashes = dict(base_lock["dataset_hashes"])
    updated_hashes["full_train_split"] = full_train_sha

    lock_manifest = dict(base_lock)
    lock_manifest["schema_version"] = "orig_fit2_return_channel_contrast_lock.v1"
    lock_manifest["extension_version"] = EXTENSION_VERSION
    lock_manifest["kb_version"] = KB_VERSION
    lock_manifest["policy_version"] = POLICY_VERSION
    lock_manifest["kb_rationale"] = KB_RATIONALE
    lock_manifest["counts"] = {
        **base_lock["counts"],
        "domain_pos_train": len(new_pos_train),
        "extension_pos_train_added": len(ext_rows),
        "full_train_split_rows": len(new_full_train),
    }
    lock_manifest["dataset_hashes"] = updated_hashes
    lock_manifest["orig_fit2_stage2_reference_hashes"] = orig_ref_hashes
    lock_manifest["new_input_file_hashes"] = {
        **new_file_hashes,
        "orig_fit2_return_contrast_extension.jsonl": ext_sha,
    }
    lock_manifest["baseline_vs_new_diff"] = {
        "changed_files": changed_files,
        "unchanged_bit_identical_files": unchanged_files,
        "extension_file": "orig_fit2_return_contrast_extension.jsonl",
        "extension_file_sha256": ext_sha,
        "added_row_ids": [r["sample_id"] for r in ext_rows],
        "added_rows_metadata": [
            {
                "sample_id": r["sample_id"],
                "group_id": r["group_id"],
                "intent": r["intent"],
                "policy_source": r["policy_source"],
                "kb_version": r["kb_version"],
                "text_sha256": r["text_sha256"],
                "source_hash": r["source_hash"],
            }
            for r in ext_rows
        ],
        "raw_and_effective_exposure_baseline": baseline_exposure,
        "raw_and_effective_exposure_new": new_exposure,
        "exposure_delta": {
            "raw_domain_return_policy_delta": 10,
            "raw_domain_return_product_in_store_delta": 8,
            "effective_domain_return_policy_delta": 40,
            "effective_domain_return_product_in_store_delta": 40,
            "effective_train_total_delta": new_exposure["effective_train_total"] - baseline_exposure["effective_train_total"],
        },
        "boundary_pos_train_sha256": pos_train_sha,
    }
    lock_manifest["isolation_audit"] = isolation
    lock_manifest["historical_baseline_noisy_overlap_disclosure"] = historical_noisy_overlap
    lock_path = ds_dir / "dataset_lock_manifest.json"
    lock_path.write_text(json.dumps(lock_manifest, indent=2) + "\n", encoding="utf-8")
    return lock_manifest
