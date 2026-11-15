# System Safety Remediation — Slice 1 (Gap 1: Retrieval & Evidence Capability Scope)

- **Worker:** A (`task_5c258330c0d7`, `dispatch_id=ctx_f0d6cc001f31`)
- **Base Commit:** `94a8f4fcd1373407b0e8e4156a10d1d1555ea9bb` on branch `minh`
- **Plan Reference:** [`2026-11-15-original-fit2-safety-remediation-plan-b.md`](2026-11-15-original-fit2-safety-remediation-plan-b.md)
- **Scope Implemented:** **Gap 1 only** (`Sub-gap 1a` + `Sub-gap 1b`). Gap 2 and Gap 3 remain open for sequential slices.

---

## 1. Changes Implemented

### Sub-gap 1a — RetrievalAdapter Pool, Intent Scoping, and Unboosted Threshold ([`apps/core_backend/retrieval/adapter.py`](../../apps/core_backend/retrieval/adapter.py))
- **Full-pool search prior to intent filtering:** `retrieve()` now searches across `top_k_docs=len(allowed_doc_version_keys)` with `token_budget=max(1500, 1500 * len(allowed_doc_version_keys))` so rank-4+ intent-aligned docs cannot be crowded out by top-3 or token-budget truncation before intent gating.
- **Fail-closed metadata & intent validation:**
  - `__init__` quarantines malformed `supported_intents` / `answer_capabilities` (`None`, non-sequence, non-string, or blank string) under `"invalid_approval_metadata"`.
  - `retrieve()` normalizes `clean_intent`, preserves `human_agent` -> `"human_agent_escalation"`, fails closed (`"no_match"`) on empty/whitespace/non-string or unknown intents, and requires non-empty `supported_intents` containing `clean_intent` (never treating missing/`[]` `supported_intents` as a universal allow).
- **Unboosted threshold gating & consistent outputs:** Additive `LAMBDA_INTENT = 0.15` reranking is applied *only* to intent-aligned, eligible, authorized docs whose unboosted `raw_score >= self.relevance_threshold` (0.55 default). Unrelated docs are never attached, and empty passing sets return `"no_match"` with `["no_match", "below_relevance_threshold"]`.

### Sub-gap 1b — KB-Evidence-Checked Capability & Channel Scope ([`apps/core_backend/safety.py`](../../apps/core_backend/safety.py))
- Extended `policy_scope_requires_review()` (automatically enforced by both `Engine._analyse()` and `PipelineRunner.run()` -> `evaluate_evidence_scope()` using `"insufficient_evidence"` inside existing `AI_REASONS`) for three capability/channel families when non-empty evidence would otherwise be served:
  1. **Physical retail storefront returns/exchanges/drop-offs** (distinct from partner post offices and courier pickup), with clause-local guards preserving `"bought/purchased in store"` (including rightmost purchase-vs-return verb ordering so `"bought online and want to return in store"` still escalates), `"store credit"`, digital/online stores, and declarative negated alternatives.
  2. **Self-service prepaid/printable/downloadable return/shipping label portals**, while allowing app return initiation and courier pickup.
  3. **Full account order/purchase history exports/lists** (even when an `order_id` like `ORD-1001` is also present), while preserving `'My Orders'`, single-order tracking, and covered `'refund history'` (`POL-REFUND-007`).
- **Trusted KB authority binding:** `_trusted_policy_docs()` and `_trusted_docs_cover_capability()` verify coverage strictly against approved active docs in `eligible_versions` matched by `source_type == "policy"` + `(doc_id, version)`, never trusting unverified citation/LLM labels or self-declared evidence `capabilities`.
- **OOD abstention preservation:** `_has_uncovered_channel_or_capability()` returns `False` when `evidence` is empty, preserving `"abstained"` (`out_of_scope_intent` + `no_valid_document`) on OOD queries such as `app-gold-ood-03` (`store_location`).
- **Principled text normalization:** NFKC/quote/dash/whitespace normalization plus algorithmic single adjacent-letter transposition normalization restricted to unambiguous `>=5`-character channel keywords (handles e.g. `"in stroe"` without a brittle phrase dictionary).
- **Quote attribution handling:** Attributed or counterfactual quotes (e.g., `Support said "bring it to a store"...`) are blanked before channel matching, while direct quoted customer requests (`Can I 'return in store'?`) remain checked.

---

## 2. Verification Summary

- **TDD Tests Added:** [`tests/unit/test_safety_slice1_gap1_a.py`](../../tests/unit/test_safety_slice1_gap1_a.py) (46 test cases covering Gap 1a crowdout/threshold/metadata/intent-edge invariants and Gap 1b `Engine` + `PipelineRunner` escalations, supported counterexamples, untrusted citation rejection, multi-clause queries, mixed purchase+return syntax, and documented non-transposition residual).
- **Targeted Gap 1 + Core Retrieval/Safety/Application/Integration Run (`pytest`):**
  ```text
  .\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py tests/unit/test_semantic_retrieval.py tests/unit/test_completion_retrieval.py tests/unit/test_mandatory_routing_b.py tests/unit/test_retrieval_grounding_b2.py tests/unit/test_system_components.py tests/application/ tests/integration/test_routing_retrieval.py tests/unit/test_guard_corrections_checks.py tests/unit/test_completion_knowledge.py -q
  -> 274 passed in 106.29s
  ```
- **Full Repository Bare `pytest -q`:**
  ```text
  .\.venv\Scripts\python.exe -m pytest -q
  -> 1302 passed, 2 skipped, 5 deselected, 1 xfailed, 2 failed in 787.11s
  ```
  - The 2 failures are pre-existing workspace artifact-scan checks unrelated to `adapter.py` or `safety.py`:
    - `tests/unit/test_fit2_independent_gate.py::test_novel_vs_all_prior_and_internal` (scans untracked files in `artifacts/evaluation/`)
    - `tests/unit/test_sealed_holdout_20261113.py::test_sealed_holdout_counts_kb_and_zero_overlap` (UTF-8 BOM in untracked `artifacts/evaluation/` JSON)
- **Invariant Checksums (Unchanged):**
  - `data/knowledge/approved_kb.v2.json`: `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec`
  - `apps/ai_service/kb-release.json`: `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804`
  - `apps/core_backend/config/policies/intent_policy.v2.json`: `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7`
  - `.local/training-cap-20261114.json`: `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922`
  - `artifacts/models/reconstructed-fit2-supcon-20261113/{model.safetensors,calibration_manifest.json}`: `MISSING` in this checkout.
  - Zero training runs, weight edits, calibrator/rejector edits, KB/release/policy edits, or live LLM calls performed.

---

## 3. Residual Limits & Open Slices

- **Non-transposition typos remain residual:** Deletion/substitution typos (e.g., `"in storr"`, `"in stor"`) are intentionally *not* heuristic-patched to avoid English word collisions (explicitly verified in `test_gap1b_non_transposition_typo_residual_documented_behavior`).
- **Pre-retrieval `track_order` slot clarification:** Slotless personal `track_order` queries without an `order_id` slot still route to `"clarify"` (`missing_order_id`) in `PipelineRunner` before reaching retrieval/`evaluate_evidence_scope`; `Engine` reaches `policy_scope_requires_review` and escalates regardless.
- **Open Sequential Work:** **Gap 2** and **Gap 3** from the remediation plan remain unimplemented; do not claim raw classifier metric changes or full acceptance from Slice 1 alone.
