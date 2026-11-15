# Worker B — Independent Code Review of Slice 1 (`03eb1231`)

- **Reviewer:** Worker B (`task_4f7abe01932b`, `dispatch_id=ctx_69cbb6222371`, branch `minh`)
- **Reviewed Commit:** [`03eb1231a9552fb22cf755a448d4fe6bd1225363`](../../apps/core_backend/safety.py) (`safety(slice1): close Gap 1 retrieval intent-gating and KB capability scope`, on top of [`94a8f4fcd1373407b0e8e4156a10d1d1555ea9bb`](2026-11-15-original-fit2-safety-remediation-plan-b.md))
- **Files Reviewed (Read-Only):** [`adapter.py`](../../apps/core_backend/retrieval/adapter.py), [`safety.py`](../../apps/core_backend/safety.py), [`test_safety_slice1_gap1_a.py`](../../tests/unit/test_safety_slice1_gap1_a.py), [`2026-11-15-original-fit2-safety-slice1-a.md`](2026-11-15-original-fit2-safety-slice1-a.md)
- **Verdict:** **`BLOCK`** — **Do NOT send to Worker C paired evaluation yet.** Sub-gap 1a (`RetrievalAdapter`) is sound, but Sub-gap 1b (`safety.py`) still lets **`4/11` Engine (`3/9` Runner) non-fault baseline leaks** in the frozen `1,245`-row benchmark pass `policy_scope_requires_review` / `evaluate_evidence_scope`, drops `noise420` supported utility below the **`>= 260/420`** plan floor (`260 -> 258`), and misses `"take it back in store"`.

---

## 1. Verdict Breakdown by Component

| Component | Status | Verdict | Key Finding |
| --- | --- | --- | --- |
| **Sub-gap 1a:** [`RetrievalAdapter.retrieve()`](../../apps/core_backend/retrieval/adapter.py#L140-L285) | Checked | **PASS** | Full-pool search (`top_k_docs=len(allowed_doc_version_keys)`), fail-closed `supported_intents` & empty/unknown intent handling, unboosted `raw_score >= relevance_threshold` (`0.55`) before `LAMBDA_INTENT=0.15`. Closes `neg51/nonretail_ood_eval_019` (`1 -> 0`) with expected borderline drop `pos175/cls_dis_wrong_drop_0_841424c7a978` (`no_match`). |
| **Sub-gap 1b:** [`policy_scope_requires_review()`](../../apps/core_backend/safety.py#L311-L558) | Checked | **BLOCK** | Leaves **`4/11` Engine (`3/9` Runner)** Original Fit2 benchmark leaks unblocked (`ev_scope=None`, `Engine='draft'`), breaks the `noise420 >= 260/420` floor (`260 -> 258`) + drops `sa156/sup-return_product-03`, and fails same-clause `"take it back"`. |
| **Tests:** [`test_safety_slice1_gap1_a.py`](../../tests/unit/test_safety_slice1_gap1_a.py) | Executed | **PASS (insufficient coverage)** | `46 passed in 4.63s` (with `test_supported_unsupported_boundary_b.py`: `70 passed, 1 xfailed in 5.73s`; `test_retrieval_grounding_b2.py` + `test_accounting_guardrails_b.py`: `68 passed in 9.32s`). Missed frozen benchmark strings `uns-return_product_in_store-01`, `contrast_auth_pos_eval_090/099/107`, and `sup-return_product-03`. |
| **Boundary / `AI_REASONS` Contract** | Checked | **PASS** | Emits only existing `AI_REASONS` (`"no_valid_document"`, `"insufficient_evidence"`), preserves `unc-*` fault paths and `store_location` OOD abstention (`evidence == []`), raw classifier outputs untouched. Gaps 2 & 3 remain open for sequential slices. |

---

## 2. Reproducible Blocking Defects in `apps/core_backend/safety.py`

### Blocker 1 (P0) — `4/11` Engine (`3/9` Runner) Original Fit2 Benchmark Leaks Survive Slice 1

Running real `RetrievalAdapter` (`approved_kb.v2.json` + `kb-release.json`) and `evaluate_evidence_scope()` / `Engine` across the baseline `retrieve_draft` leak rows in [`predictions_orig_fit2.jsonl`](../../artifacts/evaluation/fit2_orig_ret_channel_fit_v1_independent_c_20261114/predictions_orig_fit2.jsonl) reproduces **4 unblocked leaks** (`Engine='draft'`, `evaluate_evidence_scope() == None`):

1. **`sa156/uns-return_product_in_store-01`** (`gold=return_product_in_store`, `pred=return_policy`, Engine=`draft`, Runner `ev_scope=None`):
   > *"Can I drop off my online return at a local physical shop branch?"*
   - **Code cause (`safety.py:315-319`):** `_PHYSICAL_STORE_CHANNEL_PATTERN` matches `stores?|storefronts?|branch(?:es)?|shopfronts?|showrooms?|outlets?|kiosks?`, omitting **`shops?`**. Neither `"physical shop"` nor `"shop branch"` matches (also misses [`test_supported_unsupported_boundary_b.py#L107`](../../tests/unit/test_supported_unsupported_boundary_b.py#L107) *"one of your shops"*, *"retail shops"*, *"Tiki shop"*, and *"mall pop-up shop"*).
2. **`pos175/contrast_auth_pos_eval_107`** (`gold=return_product_in_store`, `pred=return_policy`, Engine=`draft`, Runner `ev_scope=None`):
   > *"Does your physical shop counter accept returns from web orders?"*
   - **Code cause (`safety.py:316-317`):** Same `shops?` omission (`physical` + `shop` + `counter` fails both `physical ... counters?` and `... shopfronts? ... counter`).
3. **`pos175/contrast_auth_pos_eval_099`** (`gold=return_product_in_store`, `pred=return_policy`, Engine=`draft`, Runner `ev_scope=None`):
   > *"Do your local storefronts accept in-person product returns?"*
   - **Code cause (`safety.py:311-322`):** `"local storefronts"` has no leading `at|to|into` (`L314`), `"local"` is not in `(?:retail|physical|brick-and-mortar)` (`L316`), `"accept in-person product"` separates `storefronts` from `returns` (`L317`), and `"in-person ... returns"` is absent from physical channel phrases.
4. **`pos175/contrast_auth_pos_eval_090`** (`gold=order_history`, `pred=track_order`, Engine=`draft`, Runner baseline=`clarify` missing `order_id`, `ev_scope=None`):
   > *"Show all historical orders I have ever placed with my login."*
   - **Code cause (`safety.py:333-345`):** `_FULL_ORDER_HISTORY_PATTERN` requires `my` right after `all (?:of )?` (`L340`), or `(?:order|purchase)s?\s+(?:history|logs?|lists?|records?|summary)` (`L336`), or `every\s+(?:order|purchase)...ever placed` (`L342`). `"all historical orders I have ever placed"` puts `historical` before `orders` without `my` or `every`.

### Blocker 2 (P0) — `noise420` Supported Utility Violates Plan Floor (`260 -> 258`) + Courier/Tracking False Positives

1. **`noise420` & `sa156` drop (`safety.py:329`):** `_PREPAID_RETURN_LABEL_PATTERN` ends with bare catch-all `|return(?:\s+shipping)?\s+labels?`, flagging any mention of a return shipping label without requiring prepaid/printable/downloadable or self-service portal/email/print-my-own semantics:
   - **`sa156/sup-return_product-03`** (`gold=return_product`, `meta.expected_actions=['retrieve_draft', 'clarify']`, `must_escalate=False`): *"Please send me a return shipping label for my item."* -> `('escalate', ['insufficient_evidence'])`.
   - **`noise420/sup-return_product-03::clean`** and **`::casual`** -> both escalate (`ev_scope=('escalate', ['insufficient_evidence'])`), dropping `noise420` supported retention **`260 -> 258`** (below the remediation plan's **`>= 260/420`** floor), while typo variants `::typo#1`/`::typo#2` (`"lbel"`) pass through inconsistently!
   - **False positive on courier pickup (`courier_brought_label`):** *"Does the courier bring a return label when picking up my return?"* returns **`True` (`escalate`)** even though [`POL-RET-002`](../../data/knowledge/approved_kb.v2.json) covers courier return pickup.
2. **Single-order tracking false positive (`safety.py:337`):** Bare `|(?:order|purchase)\s+history` without full/all/past/list/export intent flags `"I checked my order history for ORD-1001 and it shows In Transit — when does ORD-1001 arrive?"` as **`True` (`escalate`)**.

### Blocker 3 (P1) — Same-Clause `"take it back"` Bypass & `"mall"` Modifier Trap

1. **`safety.py:287` (`_CHANNEL_RETURN_VERB`):** Uses `take\s+back` without optional `(?:(?:\s+\w+){0,2})` between `take` and `back` (unlike `bring(?:\s+\w+){0,2}\s+(?:back|in)` on `L286`). Compound *"I bought this shirt in store and want to take it back in store."* evaluates `last_purchase_end > last_return_end` and returns **`False` (BYPASS)**.
2. **`safety.py:295` (`_ONLINE_OR_DIGITAL_STORE_MODIFIER`):** Includes `mall|brand|flagship|seller|merchant` alongside `online|web|app|google play|apple|digital`, which would suppress non-return modifiers in e.g. *"Do mall storefronts accept returns?"* unless a return verb precedes `"mall"`. Keep `_ONLINE_OR_DIGITAL_STORE_MODIFIER` strictly to digital/app storefronts.

---

## 3. Pre-LLM Gate Impact Measured Directly on Frozen `1,245` Original Fit2 Rows

> Measurement uses real `RetrievalAdapter` + `evaluate_evidence_scope` / `policy_scope_requires_review` on baseline `retrieve_draft` rows (`0` model/calibration/KB edits, `0` paid LLM calls; **not** a substitute for Worker C's full `evaluate_candidate.py` paired run). Raw Fit2 classifier metrics (`noise420 macro_f1_12=0.857307`, `bare=267/420`) remain untouched.

| Suite | Runner Corr (`retrieve_draft` & gold-match) | Runner Leaks (pre-LLM gate) | Engine Leaks | Note |
| --- | --- | --- | --- | --- |
| `noise420` | `260 -> 258` (**below `260` floor**) | `0 -> 0` | `0 -> 0` | Drops `sup-return_product-03::{clean,casual}` (`L329`) |
| `sa156` (excl. `unc-*`) | `66 -> 65` | `1 -> 1` | `2 -> 1` | Drops `sup-return_product-03`; **leaks** `uns-return_product_in_store-01` |
| `pos175` | `35 -> 34` | `3 -> 2` | `4 -> 3` | Expected `cls_dis_wrong_drop_0` (`no_match`); **leaks** `090`, `099`, `107` |
| `final24` | `11 -> 11` | `0 -> 0` | `0 -> 0` | Preserved |
| `unseen36` | `10 -> 10` | `3 -> 0` | `3 -> 0` | Closed `ugc-retinstore-01/06`, `ugc-retonl-01` |
| `fresh34` | `4 -> 4` | `1 -> 0` | `1 -> 0` | Closed `v4p1-ood-08` |
| `ind36` | `5 -> 5` | `0 -> 0` | `0 -> 0` | Preserved |
| `sealed72` | `5 -> 5` | `0 -> 0` | `0 -> 0` | Preserved |
| `neg51` | `0 -> 0` | `1 -> 0` | `1 -> 0` | Closed `nonretail_ood_eval_019` (`no_match`) |
| `oos80` | `0 -> 0` | `0 -> 0` | `0 -> 0` | Preserved |
| **Total (`1,245` non-`unc` eval rows)** | **`396 -> 392`** | **`9 -> 3`** | **`11 -> 4`** | **Must reach `9 -> 0` Runner / `11 -> 0` Engine and `noise420 >= 260`** |

*(Residual noted consistently with Slice 1 report: `bitext6690/sample_031639` `"in stroe"` now returns `True` via `L376` adjacent-transposition normalization; Gaps 2 & 3 remain open.)*

---

## 4. Verification & Invariant SHA-256 Checksums

- **Observed Pytest Runs (after `03eb1231`):**
  - `.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py -q` -> `46 passed in 4.63s`
  - `.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py tests/unit/test_supported_unsupported_boundary_b.py -q` -> `70 passed, 1 xfailed in 5.73s`
  - `.venv\Scripts\python.exe -m pytest tests/unit/test_retrieval_grounding_b2.py tests/unit/test_accounting_guardrails_b.py -q` -> `68 passed in 9.32s`
  - *(Note: Worker A's report cited `artifacts/models/reconstructed-fit2-...` as `MISSING`; the actual Original Fit2 path is [`artifacts/models/candidates/reconstructed-fit2-supcon-20261113/`](../../artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json) and matches the plan checksums identically.)*

| Artifact | Verified SHA-256 (unchanged) |
| --- | --- |
| [`data/knowledge/approved_kb.v2.json`](../../data/knowledge/approved_kb.v2.json) | `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec` |
| [`apps/ai_service/kb-release.json`](../../apps/ai_service/kb-release.json) | `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804` |
| [`apps/core_backend/config/policies/intent_policy.v2.json`](../../apps/core_backend/config/policies/intent_policy.v2.json) | `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7` |
| `.local/training-cap-20261114.json` | `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922` |
| `.local/ai.env` | `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87` |
| [`artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors`](../../artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors) | `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa` |
| [`artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json`](../../artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json) | `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39` |
| [`artifacts/models/trained/distilbert-supportiq/model.safetensors`](../../artifacts/models/trained/distilbert-supportiq/model.safetensors) | `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302` |

---

## 5. Required Surgical Fixes in `safety.py` Before Re-Review

1. **`_PHYSICAL_STORE_CHANNEL_PATTERN` (`safety.py:311-322`):**
   - Add `shops?` alongside `stores?|storefronts?|branch(?:es)?|shopfronts?|showrooms?|outlets?|kiosks?`.
   - Cover shop-acceptance phrasings with `local` and separated objects (e.g., `(?:retail|physical|local|brick[-\s]+and[-\s]+mortar)\s+(?:stores?|storefronts?|shops?|branch(?:es)?|showrooms?|locations?|outlets?|counters?)` combined with return/drop-off/exchange/accept-return verbs anywhere in the same clause, closing `uns-return_product_in_store-01`, `contrast_auth_pos_eval_099`, `contrast_auth_pos_eval_107`, and `boundary_b-107`).
   - Restrict `_ONLINE_OR_DIGITAL_STORE_MODIFIER` (`L295`) to genuinely digital/non-physical modifiers (`online|web|app|google play|play|apple|digital`).
2. **`_CHANNEL_RETURN_VERB` (`safety.py:287`):** Allow up to 2 optional tokens in `take(?:\s+\w+){0,2}\s+back` to match *"take it back in store"*.
3. **`_FULL_ORDER_HISTORY_PATTERN` (`safety.py:333-345`):**
   - Cover `(?:all(?:\s+of)?(?:\s+my)?|every)\s+(?:past|previous|historical|older)?\s*(?:orders?|purchases?)` (even when `historical` appears without `my`), closing `contrast_auth_pos_eval_090`.
   - Drop bare `|(?:order|purchase)\s+history` (`L337`) or require full/list/export/view-history intent so single-order `"order history for ORD-1001 ... when does ORD-1001 arrive?"` is not false-escalated.
4. **`_PREPAID_RETURN_LABEL_PATTERN` (`safety.py:323-332`):** Remove bare `|return(?:\s+shipping)?\s+labels?` (`L329`) and keep explicit prepaid/printable/downloadable/self-service-portal/print-your-own cues so `ugc-retonl-01` escalates while `sa156/sup-return_product-03`, `noise420/sup-return_product-03::{clean,casual}` (`noise420 >= 260/420`), and courier-pickup label questions stay unblocked.
5. **Regression Tests:** Add all 4 surviving Original Fit2 leak strings (`uns-return_product_in_store-01`, `contrast_auth_pos_eval_090/099/107`), `boundary_b-107`, `"take it back in store"`, `sup-return_product-03`, `courier_brought_label`, and `order_history_single_track` to [`test_safety_slice1_gap1_a.py`](../../tests/unit/test_safety_slice1_gap1_a.py).
