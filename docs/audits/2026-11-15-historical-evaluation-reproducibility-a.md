# Reproducible Historical Novelty Verification & UTF-8 BOM Handling Audit (Worker A)

- **Date:** 2026-11-15
- **Branch:** `minh`
- **Component Scope:** Evaluation Infrastructure & Holdout Novelty Invariants (`fit2_independent_gate_20261113`, `test_sealed_holdout_20261113`, `historical_inventory`)
- **Authority / Directive:** Coordinator Review (`msg_ae4b786e5b99`) on Audit `264249b`
- **Execution Mode:** Ponytail ULTRA (minimal complete change, fail-closed reproducibility, zero heuristic shortcuts)
- **Status:** **`RESOLVED / VERIFIED PASS`**

---

## 1. Executive Summary

Prior to this work, running `pytest tests/unit/test_fit2_independent_gate.py tests/unit/test_sealed_holdout_20261113.py` failed with 2 blocking errors:
1. `AssertionError: {'exact_overlap': ['g2-sup-01', ... 36 cases total ...]}` in `test_fit2_independent_gate.py::test_novel_vs_all_prior_and_internal`.
2. `json.decoder.JSONDecodeError: Unexpected UTF-8 BOM (decode using utf-8-sig)` in `test_sealed_holdout_20261113.py::test_sealed_holdout_counts_kb_and_zero_overlap` when reading `artifacts/evaluation/fit2_independent_gate_20261113/results/verdict_fit2-sibling-boundary-v2.json`.

### Root Cause Diagnosis
1. **Downstream Result Pollution:** The overlap detection function `historical_corpus()` in `gate.py` and `collect_historical_prompts()` in `test_sealed_holdout_20261113.py` recursively walked `artifacts/evaluation/**`. When subsequent candidate evaluation runs took place on Nov 14–15 (`original_fit2_safety_slice1_*`, `fit2_v4p1_*`, `fit2_v5r2_*`, etc.), their prediction output logs (`predictions_*.jsonl`) recorded model predictions on these exact test gates. Naive globbing read downstream evaluation prediction logs as antecedent training data.
2. **Empirical Novelty Verification:** Cross-referencing all 36 gate cases and all 72 sealed holdout cases against genuine antecedent training and benchmark corpora (`data/`) confirms **0/36** and **0/72** overlap. All 36 apparent matches were 100% downstream evaluation predictions generated post-freeze.
3. **UTF-8 BOM Crash:** `verdict_fit2-sibling-boundary-v2.json` contains a standard 3-byte UTF-8 BOM signature (`\xef\xbb\xbf`). The test called `Path.read_text(encoding="utf-8")`, which does not strip BOM bytes, causing Python's JSON parser to crash.

---

## 2. Engineering Solution Architecture

In accordance with strict reproducibility standards and Ponytail ULTRA principles:
- **No Naive Timestamp Heuristics:** We do NOT rely on filesystem `mtimes` (which change on `git checkout`, cloning, or CI machines).
- **No Wildcard Directory Exclusion:** We do NOT exclude directories by ad-hoc name patterns or git tracking status.
- **No Byte Modification on Disk:** We do NOT rewrite existing artifact files to strip BOMs.

### Architecture Components

1. **Immutable Historical As-Of Inventory (`pipeline/evaluation/historical_as_of_inventory.json`):**
   - Established strictly from Git commit `16b01eb` (Fri Nov 13 19:13:05 2026), the exact freeze point of the holdout gate.
   - Contains exact relative repository paths and SHA-256 digests for all **786 antecedent files** across `data`, `artifacts/evaluation`, `artifacts/preparation`, and `artifacts/audit`.
   - Exactly matches the frozen `manifest.json` parameters: `"overlap_corpus_files": 786` and `"overlap_corpus_prompts": 13271`.

2. **Fail-Closed Historical Inventory Loader (`pipeline/evaluation/historical_inventory.py`):**
   - `load_historical_corpus_inventory()`: Validates that all 786 antecedent files exist and their SHA-256 digests match. Raises `HistoricalCorpusIntegrityError` if any file is missing or tampered.
   - `read_json_safe()` & `read_jsonl_safe()`: Decodes JSON/JSONL using `encoding="utf-8-sig"` to transparently handle UTF-8 BOM without mutating file bytes on disk.
   - `collect_historical_corpus_prompts()` & `collect_historical_prompt_tuples()`: Extracts prompts strictly from the immutable inventory.

3. **Gate & Unit Test Refactoring:**
   - [artifacts/evaluation/fit2_independent_gate_20261113/gate.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/artifacts/evaluation/fit2_independent_gate_20261113/gate.py): `historical_corpus(roots=None)` delegates to `collect_historical_corpus_prompts(exclude_dirs=[HERE])`.
   - [tests/unit/test_fit2_independent_gate.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/tests/unit/test_fit2_independent_gate.py): Reads manifests and policies using `utf-8-sig`.
   - [tests/unit/test_sealed_holdout_20261113.py](file:///F:/N%C4%83m%203/SD/project/SupportIQ/tests/unit/test_sealed_holdout_20261113.py): `collect_historical_prompts()` delegates to `collect_historical_prompt_tuples()`, and JSON reads use `utf-8-sig`.

4. **Dedicated Regression Test Suite (`tests/unit/test_historical_corpus_reproducibility.py`):**
   Implements 4 negative/positive regression tests:
   - `test_downstream_result_export_does_not_invalidate_novelty`: Confirms exporting a downstream evaluation prediction log containing holdout prompt texts does not pollute antecedent corpus or invalidate novelty.
   - `test_prefreeze_overlap_fails_closed`: Confirms injecting a genuine pre-freeze prompt triggers exact overlap failure.
   - `test_tampered_or_missing_inventory_fails_closed`: Confirms missing inventory, missing corpus files, or tampered sha256 hashes raise `HistoricalCorpusIntegrityError`.
   - `test_utf8_bom_and_normal_utf8_semantic_equivalence`: Confirms JSON and JSONL with BOM decode to identical Python objects as UTF-8 without altering disk bytes.

---

## 3. Verification & Test Evidence

### A. Targeted & Regression Test Suite Execution
```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_fit2_independent_gate.py tests/unit/test_sealed_holdout_20261113.py tests/unit/test_historical_corpus_reproducibility.py -v
```
**Outcome:** **`8 passed in 9.62s`** (100% PASS, 0 failures, 0 warnings)
```text
tests/unit/test_fit2_independent_gate.py::test_shape_and_gold_semantics PASSED [ 12%]
tests/unit/test_fit2_independent_gate.py::test_novel_vs_all_prior_and_internal PASSED [ 25%]
tests/unit/test_fit2_independent_gate.py::test_manifest_hash_lock PASSED [ 37%]
tests/unit/test_sealed_holdout_20261113.py::test_sealed_holdout_counts_kb_and_zero_overlap PASSED [ 50%]
tests/unit/test_historical_corpus_reproducibility.py::test_downstream_result_export_does_not_invalidate_novelty PASSED [ 62%]
tests/unit/test_historical_corpus_reproducibility.py::test_prefreeze_overlap_fails_closed PASSED [ 75%]
tests/unit/test_historical_corpus_reproducibility.py::test_tampered_or_missing_inventory_fails_closed PASSED [ 87%]
tests/unit/test_historical_corpus_reproducibility.py::test_utf8_bom_and_normal_utf8_semantic_equivalence PASSED [100%]
```

### B. Core System Unit Test Suite Execution
```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_order_context_grounding.py tests/unit/test_ai_grounding.py tests/unit/test_privacy_pii.py tests/unit/test_schema_constraints.py -q
```
**Outcome:** **`79 passed in 8.48s`** (100% PASS, 0 regressions)

---

## 4. Operational Invariant Safeguards

- **Paid LLM Calls:** Zero paid API calls made; usage remains strictly capped (~22/24 consumed lifetime); training remains `2/2 STOP`.
- **Model Weights & Calibration:** Zero changes to model parameters, calibration matrices, or serving endpoints.
- **Runtime Processes:** Zero backend or AI service restarts.
- **Git Push:** Read-only worker role observed; no `git push` executed.
