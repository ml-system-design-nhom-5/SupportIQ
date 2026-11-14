# Stage 1 Final Re-Review — Corrective Grounding Fix (`183cdf69`)

- **Reviewer:** Worker C (`task_af4763213667`)
- **Reviewed Commit:** `183cdf6935ad392e2e01e6af331d56a326dfabb9` (`fix(safety,engine): bind Engine.draft to authoritative sources and block passive/splice bypasses`)
- **Prior Reviews:** `docs/audits/2026-11-14-polite-framing-grounding-review-c.md` (`b88692ccacda54c3e7ba07162e48e11abc7c7cb9`), `docs/audits/2026-11-14-polite-framing-grounding-rereview-c.md` (`8f28fe44cdd3459cd3cf43e40e2577b59bfe65ab`)
- **Reference Note:** `docs/audits/2026-11-14-polite-framing-grounding-b.md`
- **Verdict:** **`PASS`** (Cleared to proceed to Stage 2 fixed model evaluation of `fit2-taxonomy-audit-v5-r2` on this frozen runtime)

---

## 1. Independent Verification of All Prior Findings

1. **Authoritative Source Binding in `Engine.draft()` (`apps/ai_service/engine.py:215-328`, `apps/core_backend/safety.py:923-966`):**
   - `Engine.draft()` precomputes `authoritative_sources` from `copy.deepcopy(evidence)` plus validated identifier-free `supplied_facts` (`extract_order_facts(..., allowed_fields=ORDER_CONTEXT_ALLOWED_SET, include_order_identifiers=False)`) via `build_grounded_sources()` **before** invoking `self.llm.generate()`, passing isolated `copy.deepcopy(...)` arguments.
   - `validate_snapshot_sources(..., require_snapshot=True)` checks every returned `input_snapshot["sources"]` entry against `authoritative_sources` (`source_id`, `source_type`, `document_id`, `version`, `excerpt`/`text`, `sha256`), and `find_draft_grounding_violation()`, `validate_generated_draft()`, and final `citations`/`segments` run strictly on `authoritative_sources`.
   - `tests/e2e/test_full_pipeline.py::test_normal_shipping_cost_flow` was fixed by aligning `adapter.retrieve` with `b1000000-0000-0000-0000-000000000005` rather than weakening validation.
   - **Observed probes:** `1_forged_doc`, `2_wrong_version`, `3_tampered_excerpt`, `4_arg_mutation_attack`, `5_spoof_order_facts`, `6_missing_snapshot`, `snap_extra_s3=False`, `snap_wrong_sha=False`, `snap_wrong_type=False` -> all rejected (`llm_unavailable` / `False`); `snap_reordered_ok=True`; `7_llm_ctx_scrubbed` passed only `{'order_status': 'delivered'}` (no `order_id`, `tracking_code`, `customer_phone`).

2. **Passive Present-Tense Status Guard (`apps/core_backend/safety.py:482-486, 700-729`):**
   - `_PASSIVE_COMMIT` now matches `is(?:\s+(?:now|already))?` and `_is_verified_recorded_order_status()` checks `order_status`, `refund_status`, `return_status`, and `payment_status` strictly against cited `order_facts` sources.
   - **Observed probes:** `"Your order is cancelled [S1]."`, `"Your refund is approved [S1]."`, `"Your return is approved [S1]."`, `"Your refund is refunded [S1]."`, `"Your return is processed [S1]."`, `"Your order is credited [S1]."` against `POL-RET-001` -> `engine=llm_unavailable`, `gem=ERR:llm_invalid_citations/transaction_commitment`. Mismatched `order_facts` (`order_status: delivered` / `refund_status: pending` / `return_status: requested`) -> `engine=llm_unavailable`. Verified matching `order_facts` (`order_status: cancelled`, `refund_status: approved`) and general policy plural (`"Refunds are approved after inspection [S1]."`) -> `engine=draft_ready`, `gem=ALLOWED`.

3. **Missing-Space Sentence Splits & Inline Clause Splices (`apps/core_backend/safety.py:367-379, 506-556, 732-909`):**
   - `_SENTENCE_BOUNDARY` + `_is_token_identifier_dot()` split missing-space `.Next` boundaries while preserving `1.000.000`/`18.000` decimals, `2026-11-10` dates, `e.g.`/`i.e.` abbreviations, emails, and URLs; `_has_spliced_uncited_clause()` / `_clause_lacks_source_support()` reject unsupported trailing or `,` / `:` / ` - ` / `(...)` spliced predicate claims.
   - **Observed probes:** `no_space_before_cite`, `no_space_lowercase_after`, `comma_splice_after`, `comma_splice_before`, `colon_splice`, `dash_splice`, `paren_splice`, `[S1], and express shipping is free.`, `[S1]; and we approved your return.`, `We approved your return.Products ... [S1].` -> all `engine=llm_unavailable`, `gem=ERR:llm_invalid_citations/uncited_claim`. Preserved valid `valid_decimal_vnd`, `valid_date_iso`, `valid_abbrev_eg`, `valid_url_and_policy`, `valid_general_shipping`, `valid_polite_plus_policy`, and gated polite+clarification+`[S1]` -> `engine=draft_ready`, `gem=ALLOWED`.

---

## 2. Focused 17-Suite Test Run

- **Command:** `.\.venv\Scripts\python.exe -m pytest tests/unit/test_gemini_llm.py tests/unit/test_ai_grounding.py tests/unit/test_completion_grounding.py tests/unit/test_llm_grounding_safety_review.py tests/unit/test_llm_egress_safety_review.py tests/unit/test_llm_source_privacy.py tests/unit/test_order_context_grounding.py tests/unit/test_guard_corrections_checks.py tests/unit/test_pipeline_runner_safety_b.py tests/unit/test_routing_safety_regressions.py tests/unit/test_retrieval_grounding_b2.py tests/unit/test_accounting_guardrails_b.py tests/unit/test_autoeval.py tests/application/test_ai_boundary.py tests/application/test_application.py tests/application/test_backend_safety_closure.py tests/e2e/test_full_pipeline.py -q`
- **Observed Result:** **`423 passed, 1 deselected in 105.14s (0:01:45)`**.

---

## 3. Residual Limitations

- Uncited polite framing (`_SAFE_POLITE_FRAMING`, `_POLITE_NON_CLAIM`) and clarification questions (`_SAFE_CLARIFICATION_QUESTION` when `is_clarification=True`) are restricted to closed English templates within 100 characters.
- `Engine.draft()` accepts only canonical `"policy"` and `"order_facts"` source types (`"order"`/`"order_context"` aliases fail closed), and `return_status` is not in `ORDER_CONTEXT_ALLOWED_FIELDS` so `Engine.draft()` fails closed on recorded return-approval assertions.
- General non-numeric single-clause policy statements cited with `[S1]` are governed by numeric/date checks, transaction-commitment checks, cosmetics/duplicate-charge guardrails, and multi-clause predicate-stem checks (`_has_spliced_uncited_clause`), not full semantic NLI entailment.
