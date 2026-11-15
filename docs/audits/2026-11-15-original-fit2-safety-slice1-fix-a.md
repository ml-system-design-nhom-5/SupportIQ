# System Safety Remediation — Slice 1 Fix (Response to Worker B Review Block)

- **Worker:** A (`task_f672418f9eb1`, `dispatch_id=ctx_a12a5141322b`)
- **Parent Commit:** `bff58633f651ebc4603d18791bcd0808feffa7ce` (review on frozen Slice 1 [`03eb1231a9552fb22cf755a448d4fe6bd1225363`](../../apps/core_backend/safety.py)) on branch `minh`
- **Review Addressed:** [`2026-11-15-original-fit2-safety-slice1-review-b.md`](2026-11-15-original-fit2-safety-slice1-review-b.md)
- **Scope Modified:** [`apps/core_backend/safety.py`](../../apps/core_backend/safety.py) and [`tests/unit/test_safety_slice1_gap1_a.py`](../../tests/unit/test_safety_slice1_gap1_a.py) only (`adapter.py` Sub-gap 1a untouched; Gaps 2 & 3 remain open).

---

## 1. Root-Cause Fixes in `apps/core_backend/safety.py`

1. **Physical Retail Store / Shopfront / In-Person Return Coverage (`_PHYSICAL_STORE_CHANNEL_PATTERN`, `_CHANNEL_RETURN_VERB`, `_ONLINE_OR_DIGITAL_STORE_MODIFIER`, `_is_non_return_store_context`):**
   - Added `shops?` (`stores?|shops?|storefronts?|shopfronts?|branch(?:es)?|showrooms?|outlets?|kiosks?`), strict physical/retail/brick-and-mortar venue forms, venue-acceptance return/exchange clauses (`local storefronts accept in-person product returns`, `physical shop counter accept returns`, `mall storefronts accept returns`), and `"shops"` (`>=5` chars) to `_ADJ_TRANSPOSITION_TARGETS`.
   - Kept marketplace seller shop mentions (`"The local shop sent me a defective kettle..."`) unblocked by requiring explicit return-destination/acceptance channel syntax unless paired with strict `physical|retail|brick-and-mortar` modifiers, and protected courier `"in person"` pickup (`_COURIER_PICKUP_CONTEXT`) from false-triggering as storefront drop-off.
   - Restricted `_ONLINE_OR_DIGITAL_STORE_MODIFIER` strictly to digital storefronts (`online|web|app|google play|play|apple|digital|virtual|e-commerce`), removing `mall|brand|flagship|seller|merchant|official`.
   - Fixed same-clause `"take it back in store"` and `"bring my online order back"` by expanding `_CHANNEL_RETURN_VERB` (`take(?:\s+\w+){0,4}\s+back`, `bring(?:\s+\w+){0,4}\s+(?:back|in)`, `swap(?:ping)?`) and short-circuiting `_is_non_return_store_context()` whenever the matched channel span itself contains an active return/acceptance verb (`_CHANNEL_RETURN_VERB` or `accept|take|handle|process`).
   - Added `ask(?:s|ed)?` to `_QUOTE_ATTRIBUTION_PREFIX` for attributed third-party quote masking while continuing to enforce direct quoted customer requests.

2. **Prepaid / Self-Print Label Portal Precision (`_PREPAID_RETURN_LABEL_PATTERN`):**
   - Removed the overbroad bare `|return(?:\s+shipping)?\s+labels?` catch-all that caused false escalations on ordinary return label requests (`sa156/sup-return_product-03`, `noise420/sup-return_product-03::{clean,casual}`) and courier-pickup label questions (`"Does the courier bring a return label when picking up my return?"`).
   - Retained explicit self-service prepaid / printable / downloadable / self-print / portal / print-your-own cues (`"Where can I print my own return label at home?"`, `"portal to download a printable shipping label"`, `"prepaid return shipping label"`, etc.).

3. **Full Account Order History vs Single-Order Tracking (`_FULL_ORDER_HISTORY_PATTERN`):**
   - Covered all/every/past/previous/historical multi-order export/listing requests even when `historical` appears without `my` (e.g., `"Show all historical orders I have ever placed with my login."`, `"Export every past purchase under my login."`) using plural/all/every/record boundaries.
   - Removed bare `|(?:order|purchase)\s+history` and added single-order negative lookahead so single-order tracking referencing order history (`"I checked my order history for ORD-1001 and it shows In Transit — when does ORD-1001 arrive?"`) remains allowed alongside `'My Orders'` and covered `'refund history'`.

---

## 2. TDD & Focused Regression Verification

1. **RED Reproduction (`task-1728`):** Expanded [`tests/unit/test_safety_slice1_gap1_a.py`](../../tests/unit/test_safety_slice1_gap1_a.py) with all B review blocker cases, counterexamples, unseen English paraphrases, and mixed multi-clause/quoted controls -> **`15 failed, 52 passed in 9.25s`** on untouched `03eb1231` / `bff58633`.
2. **GREEN Verification (`task-1750`):**
   - `.\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -q` -> **`67 passed in 9.04s`**
3. **Focused Core Regression Suite (`task-1746`):**
   ```text
   .\.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py tests/unit/test_supported_unsupported_boundary_b.py tests/unit/test_retrieval_grounding_b2.py tests/unit/test_accounting_guardrails_b.py tests/unit/test_mandatory_routing_b.py tests/unit/test_semantic_retrieval.py tests/unit/test_completion_retrieval.py tests/unit/test_system_components.py tests/application/ tests/integration/test_routing_retrieval.py tests/unit/test_guard_corrections_checks.py tests/unit/test_completion_knowledge.py -q
   -> 367 passed, 1 xfailed in 87.55s
   ```
   *(The single `xfailed` is the pre-existing `@pytest.mark.xfail(strict=True)` `test_engine_should_not_draft_track_order_without_order_id` in `tests/unit/test_supported_unsupported_boundary_b.py:92`.)*

---

## 3. Invariant SHA-256 Verification (Unchanged)

| Artifact | Verified SHA-256 |
| --- | --- |
| [`data/knowledge/approved_kb.v2.json`](../../data/knowledge/approved_kb.v2.json) | `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec` |
| [`apps/ai_service/kb-release.json`](../../apps/ai_service/kb-release.json) | `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804` |
| [`apps/core_backend/config/policies/intent_policy.v2.json`](../../apps/core_backend/config/policies/intent_policy.v2.json) | `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7` |
| `.local/training-cap-20261114.json` | `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922` |
| `.local/ai.env` | `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87` |
| [`artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors`](../../artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors) | `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` |
| [`artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json`](../../artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json) | `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39` |
| [`artifacts/models/trained/distilbert-supportiq/model.safetensors`](../../artifacts/models/trained/distilbert-supportiq/model.safetensors) | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` |

Zero training runs, weight edits, calibrator/rejector edits, KB/release/policy edits, or live LLM calls were performed.

---

## 4. Remaining Limits & Next Sequential Steps

- **Residual typos:** Non-transposition spelling mutations (e.g., `"in storr"`, `"lbel"`) remain outside deterministic single-adjacent-transposition normalization to prevent English homograph false positives.
- **Pending Verification by Worker B & Worker C:** This slice closes the unit/integration reproducers in [`test_safety_slice1_gap1_a.py`](../../tests/unit/test_safety_slice1_gap1_a.py); full frozen `1,245`-row leakage (`9 -> 0` Runner / `11 -> 0` Engine) and `noise420 >= 260/420` preservation remain to be re-measured by Worker B on this frozen commit before Worker C runs paired `evaluate_candidate.py` comparison.
- **Open Sequential Slices:** Gap 2 (authority/policy gates) and Gap 3 (NER/redaction) remain pending and unbundled.
