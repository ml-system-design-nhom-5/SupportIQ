# Worker B — System-Safety Remediation Plan Around Active Original Fit2 (`f695b1fe`)

- **Date:** `2026-11-15`
- **Branch / Scope:** `minh` — Read-only root-cause audit & minimal system remediation plan (**0** training runs, **0** weight/calibrator/rejector/embedding/LLM edits, **0** code edits, **0** live/paid LLM calls)
- **Active Model Baseline (Preserved):** Original Fit2 (`reconstructed-fit2-supcon-20261113`, `model.safetensors` SHA-256 `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`, `calibration_manifest.json` `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39`, `T=1.0`, `calibrated=true`, `selective_rejector.enabled=false`)
- **Context:** Fit2 training cap (`2/2`) is permanently exhausted (`training_stopped=true`), and Serving (`distilbert-supportiq`, `dc7af8cf...`) remains untouched. Because Original Fit2 weights cannot change without further fine-tuning, **all remaining unsafe draft/authority remediation must come from deterministic system verification gates around Fit2**.

---

## 1. Strict Boundary: Raw ML Metrics vs. System Drafting & Authority Gates

Runtime safety guards **never improve Fit2's raw classifier metrics**. Any remediation report MUST separate these surfaces cleanly:

| Surface | Owner | Affected by Runtime System Remediation? | Original Fit2 Baseline (`f695b1fe`) |
| --- | --- | --- | --- |
| **`raw_pre`, `raw_post`, `bare` (Gate)** | `ModelContainer` / `decide_route` | **No** (weights, `T=1.0`, rejector disabled are frozen) | `noise420` `macro_f1_12=0.857307`, `bare=267/420`, `oos80=3` raw leaks, `pos175=4`, `neg51=1`, `unseen36=4`, `fresh34=1`, `sa156 mand63=9`, `bitext6690 esc34=1` (`sample_031639`) |
| **`Engine` (`/v1/analyses`, `/v1/drafts`)** | `Engine._analyse` + `RetrievalAdapter` + `safety.py` | **Yes** (live service gate before LLM call & worker storage) | `11` non-fault `retrieve_draft` leaks across the `1,245`-row eval set (`9` shared w/ Runner + `2` `order_history` leaks) + `1` `bitext6690` (`sample_031639`) |
| **`PipelineRunner` (`runner`, `priv_runner`)** | `decide_route` + `RetrievalAdapter` + `safety.py` | **Yes** (orchestration/eval gate) | `9` non-fault `retrieve_draft` leaks across the `1,245`-row eval set (`unseen36=3`, `fresh34=1`, `sa156=1`, `pos175=3`, `neg51=1`) |
| **Backend Intake / Worker / Send** | `service.py` + `jobs.py` + `privacy.py` | **Yes** (sticky `is_authority_required`, `validate_reply`, PII fail-closed) | Missed authority keywords on AI outage (`6` frozen cases), silent NER skip when `spaCy` absent |

*(Note: The `4` `unc-*` fixtures in `sa156` and `final-case-21` in `final24` are synthetic fault-injection fixtures where pipeline fault mocks are tested separately from uninjected prediction.)*

---

## 2. Highest-Impact Verified Gaps (Ordered by Production Risk)

### Gap 1 (P0) — Unbounded Retrieval Scope & Missing Channel/Capability Verification (`RetrievalAdapter` + `safety.py`)

Eliminates **`9/9` non-fault `PipelineRunner` leaks** and **`11/11` non-fault `Engine` leaks** observed across all `1,245` rows of Original Fit2 (`predictions_orig_fit2.jsonl`) while blocking unsupported channels/capabilities with **`0`** code changes to Fit2.

- **Exact Call Paths:**
  - `apps/core_backend/retrieval/adapter.py`: [`RetrievalAdapter.retrieve()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/retrieval/adapter.py#L174-L255) -> `search_policies(..., top_k_docs=3)` (`L176-L183`) + `LAMBDA_INTENT = 0.15` rerank (`L213-L227`)
  - `apps/core_backend/safety.py`: [`policy_scope_requires_review()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/safety.py#L244-L286), [`evaluate_evidence_scope()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/safety.py#L289-L313), [`has_outside_product_scope_action()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/safety.py#L167-L176)
  - Consumers: [`Engine._analyse()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/ai_service/engine.py#L134-L183) and [`PipelineRunner.run()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/orchestration/pipeline_runner.py#L131-L185)
- **Current Behavior & Two Coupled Root Failures:**
  1. **Sub-gap 1a — Unaligned top-3 truncation + optional `supported_intents` boost (`neg51/nonretail_ood_eval_019`):**
     - `RetrievalAdapter.retrieve()` searches `top_k_docs=3` globally across all `14` released docs ([kb-release.json](file:///F:/Năm%203/SD/project/SupportIQ/apps/ai_service/kb-release.json#L1-L62)) **before** checking `intent`, includes unsupported-intent docs such as `POL-ORD-003` (`supported_intents: ["change_shipping_address", "edit_order"]`), uses `supported_intents` only for `+0.15` additive reranking, and returns `status="success"` even when **zero** returned docs match `intent`.
     - **Observed proof (`neg51/nonretail_ood_eval_019`):** *"How do I check remaining international long-distance minutes on my phone plan?"* -> Fit2 predicts `delivery_time @ 0.7109`. Dense retrieval returns `POL-ORD-001` (`0.605`, `track_order`), `POL-SHIP-004` (`0.563`, `delivery_issue`), `POL-REFUND-002` (`0.5563`, `refund_*`). **Zero** retrieved docs support `delivery_time` (`POL-SHIP-001` scores only **`raw=0.5305 < 0.55`**), yet both `Engine` and `Runner` draft a reply (`0.605 >= 0.55`).
  2. **Why `supported_intents` alone FAILS (both directions):**
     - *False-drop trap on `top_k_docs=3`:* Simply asserting `intent in doc.supported_intents` on current `top_k_docs=3` results drops supported answers when unrelated docs (`POL-ORD-003`, `POL-REFUND-001`, etc.) crowd top-3 before `+0.15` boost (`unseen36/ugc-retpol-04` `10 -> 9/12`, `sa156/sup-track_order-05`, `noise420` `-4`, `pos175` `-6`). Searching **all `len(allowed_doc_version_keys)` (`14`) docs** and requiring an intent-aligned doc (`intent in pv.metadata.supported_intents`) with unboosted **`raw_score >= relevance_threshold` (`0.55`)** fixes this trap: **`0` false drops** on `final24`, `sa156`, `unseen36`, `ind36`, `sealed72`, `fresh34`, and `noise420` (`260 -> 260`), with **`1`** borderline drop in `pos175` (`cls_dis_wrong_drop_0`, `raw=0.5403`).
     - *Misclassification bypass when intent IS wrong:* On the **remaining `8/9` `Runner` leaks** (`unseen36`: `ugc-retinstore-01`, `ugc-retinstore-06`, `ugc-retonl-01`; `fresh34`: `v4p1-ood-08`; `sa156`: `uns-return_product_in_store-01`; `pos175`: `contrast_auth_pos_eval_099`, `102`, `107`) plus **`2/2` Engine-only `order_history` leaks** (`sa156/uns-order_history-01`, `pos175/contrast_auth_pos_eval_090`), Fit2 misclassifies an unsupported intent into a supported one (`return_product` / `return_policy` / `track_order`). Retrieved `POL-RET-001/002/003` and `POL-ORD-001` **genuinely declare** those predicted `supported_intents` (`raw=0.5594–0.6752`, `boosted=0.7094–0.8252`), so `supported_intents` checks pass all `10` of them!
  3. **Sub-gap 1b — Missing KB Channel/Action Capability Gate (`safety.py`):**
     - Approved KB [POL-RET-002](file:///F:/Năm%203/SD/project/SupportIQ/data/knowledge/approved_kb.v2.json#L129-L157) (`answer_capabilities: ["return_initiation", "return_instructions", "pickup_service"]`) documents **only** app courier pickup or designated Tiki partner post-office drop-off — **not** physical retail storefront/branch/counter returns (`return_product_in_store`) and **not** self-printed prepaid return shipping labels via an online portal (`return_product_online`). Likewise [POL-ORD-001](file:///F:/Năm%203/SD/project/SupportIQ/data/knowledge/approved_kb.v2.json#L275-L296) covers single-order status tracking (`track_order`), **not** full account historical order lists (`order_history`).
     - [safety.py](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/safety.py#L49-L58) already checks `_POSTAL_PICKUP_PATTERN`, `_ACCOUNT_CLOSURE_PATTERN`, `_CROSS_BORDER_PATTERN`, and `_CUSTOMS_PATTERN`, but has zero channel/capability verification against retrieved KB evidence for physical in-store return drop-offs, printable prepaid return label portals, or full purchase/order-history requests.
     - **Offline probe result (`1,245` rows):** Checking for ungrounded physical-store return channels, prepaid portal label printing, and full historical order lists (gated by evidence absence, just like `has_uncovered_cross_border_shipping`) catches **`10/10`** channel/capability leaks (`8/8` non-OOD Runner leaks + `2/2` Engine `order_history` leaks) with **`0` false positives** across all `649` supported rows.
- **Normative Basis:** [CHỦ ĐỀ 1.md](file:///F:/Năm%203/SD/project/SupportIQ/docs/CHỦ%20ĐỀ%201.md#L61-L102) (`2.2` 12-intent scope vs out-of-scope escalation, `FR-02`, `FR-03`, `FR-05`, `System reliability`), [approved_kb.v2.json](file:///F:/Năm%203/SD/project/SupportIQ/data/knowledge/approved_kb.v2.json), [intent_policy.v2.json](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/config/policies/intent_policy.v2.json).
- **Minimum Patch Owner & Dependency Order:**
  1. `apps/core_backend/retrieval/adapter.py`: set search pool `top_k_docs=len(allowed_doc_version_keys)`; expose `supported_intents` and `raw_score` on evidence items; fail-closed (`status="no_match"`, `reason_codes=["below_relevance_threshold"]` / `["no_valid_document"]`) when `intent` is non-empty (and not `"human_agent"`) and no retrieved doc satisfies both `(not pv.metadata.supported_intents or intent in pv.metadata.supported_intents)` and `raw_score >= self.relevance_threshold`. (Keep `LAMBDA_INTENT` only to rank among passing aligned docs.)
  2. `apps/core_backend/safety.py`: add KB-evidence-checked scope rules in `policy_scope_requires_review()` / `evaluate_evidence_scope()` for unsupported return channels (physical retail store/branch/shopfront counter drop-off, self-service prepaid return label portal) and full account historical order-list requests unless explicitly present in retrieved `evidence` excerpts.
  3. **Reuses existing `AI_REASONS`:** emits existing `"no_valid_document"` and `"insufficient_evidence"` -> zero `SuggestionWorker.validate_analysis()` (`jobs.py:91`) breakage.
- **Tests Required:** Supported paraphrase negatives (*"drop off package at Tiki partner post office"*, *"schedule free Tiki app courier pickup"*, *"track single order ORD-1001"*, plus all `final24 ans12` / `unseen36` supported rows), leak positives (`ugc-retinstore-01/06`, `ugc-retonl-01`, `nonretail_ood_eval_019`, `uns-order_history-01` **with `ORD-1001` supplied**), and encoder-fault preservation (`unc-*`).

---

### Gap 2 (P1) — `Engine` Slot Parity & Backend Authority / Reason-Code Contract Drift

Closes manual-fallback authority leaks during AI outages/latency and aligns `Engine` with `decide_route` + backend `AI_REASONS`.

- **Exact Call Paths:**
  - `apps/backend/tickets/service.py`: [`SENSITIVE_KEYWORDS`](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/service.py#L16) -> [`create_suggestion()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/service.py#L125-L128), [`create_ticket()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/service.py#L147-L148), [`act()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/service.py#L245-L246)
  - `apps/core_backend/safety.py`: [`SENSITIVE_AUTHORITY_PATTERN`](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/safety.py#L23-L36), [`has_authority_request()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/safety.py#L147-L164)
  - `apps/backend/tickets/jobs.py`: [`AI_REASONS`](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py#L34-L43), [`validate_analysis()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py#L87-L98), [`store()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/jobs.py#L407-L409)
  - `apps/ai_service/engine.py` (`Engine._analyse` `L65-199`, `draft` reads `order_context` only at `L216`) vs [`decide_route`](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/intent/routing.py#L309-L332) (`PERSONAL_ORDER_REQUIRED`, `missing_order_id`)
- **Current Behavior & Evidence:**
  1. **`SENSITIVE_KEYWORDS` misses real authority cases on AI fallback (`service.py:16` vs `safety.py:23`):** Across the `1,245` frozen rows, **`6`** real authority cases match `SENSITIVE_AUTHORITY_PATTERN` (`has_authority_request`) but **do not match** `SENSITIVE_KEYWORDS`: `fresh34/v4p1-esc-01` (*"make an exception"*), `fresh34/v4p1-esc-05` (*"lawyer"*), `ind36/g2-esc-02` (*"grant an exception"*), `sealed72/sh-sup-22` (*"bank dispute"*), `sealed72/sh-esc-04` (*"unauthorized charges"*), `final24/final-case-14` (*"manager exception"*). Whenever AI is unavailable, times out (`ml_timeout`), fails pseudonymization (`pseudonymization_failed`), or before worker completion, `ticket.is_authority_required` remains `False` and `staff` can `POST /replies` directly (`service.py:78, 245`).
  2. **`AI_REASONS` coupling trap (`jobs.py:34, 91`):** Any new routing `reason_code` emitted by `Engine` that is absent from `AI_REASONS` raises `ValueError("Invalid routing")` inside `validate_analysis()`, silently degrading escalation into `"unavailable"` (`ai_service_unavailable`).
  3. **`Engine` missing `order_context` / `order_id` slot gate (`test_supported_unsupported_boundary_b.py:85-94` `@pytest.mark.xfail`):** Notice `PipelineRunner` (`decide_route`) clarifies whenever `track_order` lacks `order_id` (`ind36/g2-sup-01`, `sealed72/sh-sup-01`, and `sa156/uns-order_history-01`, `pos175/contrast_auth_pos_eval_090`). Adding generic `track_order -> abstain` without distinguishing personal-order vs general `"how to track"` questions would drop `ind36/g2-sup-01` and `sealed72/sh-sup-01` on `Engine`; Gap 1b's `order_history` capability check closes both observed `order_history` Engine leaks without sacrificing general `"how do I track in the app"` `Engine` answers, while personal-status lookups (`my order` / empty `order_context`) should be synced deliberately with `decide_route` (`missing_information`).
- **Normative Basis:** `FR-04`, `FR-05`, `FR-06`, `Safety & oversight`.
- **Minimum Patch Owner & Dependency Order:** (After Gap 1) Replace duplicated `SENSITIVE_KEYWORDS` in `service.py` with `has_authority_request` from `apps/core_backend/safety.py`, import a single shared allowed-reasons set between `apps/core_backend/safety.py` and `apps/backend/tickets/jobs.py`, and add API integration tests verifying `staff` receives `403 authority-required` on `"lawyer"` / `"unauthorized charges"` / `"grant an exception"` even when AI is mocked down (`ai_service_unavailable` or `pseudonymization_failed`).

---

### Gap 3 (P2) — Silent NER Disablement in `pseudonymize()` When `spaCy` Is Missing

Prevents silent raw-PII egress (`John Smith`, unstructured addresses) to `ModelContainer` and external LLMs when `en_core_web_sm` is absent (`FR-08`).

- **Exact Call Paths:** `apps/backend/tickets/privacy.py` [`_get_spacy_nlp()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/privacy.py#L21-L31), [`pseudonymize()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/privacy.py#L75-L108) -> `apps/backend/tickets/service.py` [`create_suggestion()`](file:///F:/Năm%203/SD/project/SupportIQ/apps/backend/tickets/service.py#L103-L114).
- **Current Behavior Verified Live:** In the active `.venv`, `_get_spacy_nlp()` returns **`None`** (`False`). `pseudonymize()` silently skips NER and returns `privacy_failed=False`; probing `"Contact me at alice@example.com or 0901234567 and my John Smith in Ho Chi Minh City [EMAIL_1] [LITERAL_EMAIL_1]"` leaves `"John Smith"` and `"Ho Chi Minh City"` unmasked (only `known` DB fields, regex identifiers, Luhn cards, and `Street/District` patterns are masked, and only `len not in 1..4000` triggers `ValueError` -> `pseudonymization_failed`).
- **Minimum Patch Owner & Dependency Order:** (Independent / P2 after Gap 1–2) Add an explicit strict setting (e.g., `require_privacy_ner` enabled whenever external LLM egress is active, opt-out only in local offline unit environments) in `privacy.py` / `config.py` so missing NER fails closed to `ValueError` -> existing `pseudonymization_failed` manual fallback (`service.py:106-114`), plus normalize customer-literal `[LITERAL_*]` collisions in `PLACEHOLDER` / `restore()`. Note `ModelContainer` inference itself MUST still be tested post-`pseudonymize` (`priv_engine` / `priv_runner`).

---

## 3. Fixed Offline Measurement Plan (Original Fit2 `f695b1fe`, `0` Training, `0` Paid LLM Calls)

Every remediation slice MUST run the frozen `C` protocol script architecture ([evaluate_candidate.py](file:///F:/Năm%203/SD/project/SupportIQ/artifacts/evaluation/fit2_orig_ret_channel_fit_v1_independent_c_20261114/evaluate_candidate.py)) pinning **Original Fit2** (`f695b1fe...`) under `_MockNoCallLLM` / `_OfflineValidSpyLLM` (`0` live LLM requests):

1. **Invariant Verification Checks:**
   - Assert Original Fit2 SHA (`f695b1fe...`), calibration SHA (`782c88db...`), KB (`f8dcfbbb...`), release (`cf450a72...`), and policy (`8789ee26...`) unchanged.
   - Report **raw ML metrics explicitly as unchanged baseline** (`noise420 macro_f1_12=0.857307`, `bare=267/420`). Never claim runtime guards change classifier F1.
2. **Pre/Post System Safety Metrics (Surfaces: `engine`, `runner`, `priv_engine`, `priv_runner`):**
   - **Target `0` unsafe non-fault leaks across ALL `12` suites (`1,245` rows):** `unseen36` (`3 -> 0`), `fresh34` (`1 -> 0`), `sa156 mand63 real` (`2 Eng / 1 Run -> 0`), `pos175 esc34` (`4 Eng / 3 Run -> 0`), `neg51` (`1 -> 0`), `ind36` (`0 -> 0`), `old_sealed72` (`0 -> 0`), `oos80` (`0 -> 0`), `final24 active_unans8` (`0 -> 0`), `cand_pos122/neg39` (`0 -> 0`). *(Expected residual on `bitext6690`: `1 -> 1` on `"in stroe"` typo `sample_031639` unless principled typo normalization is explicitly added and audited.)*
   - **Supported Utility Non-Regression Floors (vs Original Fit2 baseline):**
     - `final24` Runner `ans12_correct >= 10/12` (`0` wrong)
     - `sa156` Runner `sup34_correct >= 25/34`
     - `noise420` Runner `correct >= 260/420` (probe: `260 -> 260` preserved)
     - Explicitly report any coverage tradeoff (`pos175` `cls_dis_wrong_drop_0` `raw=0.5403 < 0.55`: `35 -> 34`).
   - **Backend Closure Tests (mocked AI offline):** `SENSITIVE_AUTHORITY_PATTERN` outage authority lock (`403 authority-required` for `staff`), `admin`/`manager` approval workflow, `privacy_failed` blocking `retry_suggestion`, and zero raw-PII transport egress.

---

## 4. Recommended Minimal First Implementation Slice & Explicit Open Limits

### Recommended First Slice: **Gap 1 Only** (`RetrievalAdapter` Intent-Aligned Full-Pool Check + `safety.py` Channel/Capability Scope)

Why this single slice first:
- **Smallest surface, maximum closure:** Changes only 2 core modules (`apps/core_backend/retrieval/adapter.py` + `apps/core_backend/safety.py`, inherited automatically by both `Engine` and `PipelineRunner`) plus unit/gate tests; **zero** DB schema, worker `AI_REASONS`, model, or LLM changes.
- **Empirical impact on `1,245` frozen rows (Original Fit2 `f695b1fe`):**
  - `Runner` non-fault unsafe draft leaks: **`9 -> 0`**
  - `Engine` non-fault unsafe draft leaks: **`11 -> 0`**
  - Preserves **`100%`** of `final24 ans12` (`10/12`), `sa156 sup34` (`25/34`), `noise420` Runner (`260/420`), `unseen36` supported (`10/12`), `ind36`, `sealed72`, and `fresh34`, with **`1`** disclosed `pos175` borderline drop (`cls_dis_wrong_drop_0`, `raw=0.5403`).

### Honest Open Limits (Cannot Be Solved Cleanly Without Weight/Embedding Changes)

1. **Severe user typos masking channel keywords (`bitext6690/sample_031639`):** *"how to return an item in stroe"* (`return_product_in_store -> return_policy @ 0.97816`) passes dense `POL-RET-*` retrieval (`return_policy`) and misses exact `"in store"` patterns due to `"stroe"`. Deterministic guards cannot robustly chase arbitrary spelling corruptions without hurting recall.
2. **Fluent non-retail OOD phrasing that matches intent-aligned KB cosine `>= 0.55`:** If Fit2 misclassifies a non-retail query with `conf >= threshold` AND `bge-small-en-v1.5` assigns `raw >= 0.55` to a doc supporting that predicted intent, deterministic retrieval thresholding alone cannot separate it (`raw_pre` OOD requires weight-level boundary / selective rejector calibration).
3. **LLM / Grounding behavior:** Evaluated offline with zero live LLM calls; runtime grounding guards ([find_draft_grounding_violation](file:///F:/Năm%203/SD/project/SupportIQ/apps/core_backend/safety.py#L878-L899)) remain essential defense-in-depth alongside `FR-04` human review.
