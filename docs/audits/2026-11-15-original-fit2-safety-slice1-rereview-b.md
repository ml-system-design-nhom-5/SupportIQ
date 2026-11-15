# Worker B — Re-Review of Slice 1 Fix (`12d358d3`) vs `BLOCK` (`bff58633`)

- **Reviewer:** Worker B (`task_879c940161fb`, `dispatch_id=ctx_807ba59dc352`, branch `minh`)
- **Reviewed Commit:** [`12d358d3b301680a5d1ab910d684a1102bcd509c`](../../apps/core_backend/safety.py) ([`2026-11-15-original-fit2-safety-slice1-fix-a.md`](2026-11-15-original-fit2-safety-slice1-fix-a.md)), addressing [`bff58633`](2026-11-15-original-fit2-safety-slice1-review-b.md)
- **Proof `adapter.py` Unchanged:** `git diff 03eb1231a9552fb22cf755a448d4fe6bd1225363..12d358d3b301680a5d1ab910d684a1102bcd509c -- apps/core_backend/retrieval/adapter.py` is **empty** (Sub-gap 1a remains untouched).
- **Verdict:** **`PASS`** — **Ready for Worker C independent paired Original Fit2 evaluation (`evaluate_candidate.py`).** All prior `4/11` Engine (`3/9` pre-LLM Runner gate) benchmark leaks and the `noise420` supported-utility regression are closed, raw ML metrics/weights remain unchanged, and Gap 2 + Gap 3 remain explicitly open.

---

## 1. B-Blocker Closure Matrix (`bff58633` -> `12d358d3`)

| Prior Blocker (`bff58633`) | Code Fix Inspected (`apps/core_backend/safety.py`) | Independently Verified Result | Status |
| --- | --- | --- | --- |
| `sa156/uns-return_product_in_store-01` (*"local physical shop branch"*) | Added `shops?` + `"shops"` transposition target ([L248](../../apps/core_backend/safety.py#L248), [L320-L339](../../apps/core_backend/safety.py#L320-L339)) | `Engine='escalate'` (`['insufficient_evidence']`), `ev_scope=('escalate', ['insufficient_evidence'])` | **CLOSED** |
| `pos175/contrast_auth_pos_eval_107` (*"physical shop counter"*) | `_PHYSICAL_VENUE_STRICT_MOD` + `shops?` + `counters?` ([L321, L331-L332](../../apps/core_backend/safety.py#L321-L332)) | `Engine='escalate'` (`['insufficient_evidence']`), `ev_scope=('escalate', ['insufficient_evidence'])` | **CLOSED** |
| `pos175/contrast_auth_pos_eval_099` (*"local storefronts accept in-person product returns"*) | Added venue-acceptance & `in-person` return clauses ([L333-L338](../../apps/core_backend/safety.py#L333-L338)) + courier pickup exclusion ([L315-L318, L429](../../apps/core_backend/safety.py#L315-L318)) | `Engine='escalate'`, `ev_scope=('escalate', ['insufficient_evidence'])`; courier *"in person"* home pickup stays `False` | **CLOSED** |
| `pos175/contrast_auth_pos_eval_090` (*"Show all historical orders I have ever placed with my login."*) | `_FULL_ORDER_HISTORY_PATTERN` handles `all/every + historical + orders` without `my` ([L352-L368](../../apps/core_backend/safety.py#L352-L368)) | `Engine='escalate'`, `ev_scope=('escalate', ['insufficient_evidence'])` | **CLOSED** |
| `noise420` floor (`260 -> 258`) + `sup-return_product-03` + courier label (`_PREPAID_RETURN_LABEL_PATTERN`) | Removed bare `\|return(?:\s+shipping)?\s+labels?`, kept explicit self-print / downloadable / prepaid / portal cues ([L342-L351](../../apps/core_backend/safety.py#L342-L351)) | `noise420` `run_corr 260->260`, `sa156` `66->66`; courier label & `sup-return_product-03` allowed (`False`), portal download escalates (`True`) | **CLOSED** |
| Single-order tracking *"order history for ORD-1001"* (`L362`) | Removed bare `\|(?:order\|purchase)\s+history` catch-all + added `(?!(?:\s+(?:for\|of)...ORD-\w+))` lookahead | *"I checked my order history for ORD-1001..."* -> `False` (allowed); `POL-REFUND-007` refund history -> `False` | **CLOSED** |
| Compound `"take it back in store"` + `"mall storefronts accept returns"` | `take(?:\s+\w+){0,4}\s+back` ([L292](../../apps/core_backend/safety.py#L292)), removed `"mall"` from digital modifier ([L300](../../apps/core_backend/safety.py#L300)), active-verb override ([L431](../../apps/core_backend/safety.py#L431)) | Both compound `"take it back in store"` and `"Do mall storefronts accept returns?"` return `True` (`escalate`) | **CLOSED** |

---

## 2. Adversarial, Hygiene & Safety Boundary Audit

- **Digital-modifier exclusions do NOT create a multi-clause bypass (`15/15` escalate probes passed):** Mixed clauses (*"ordered from your online store website and want to return it at a physical store"*, *"return this at a physical store instead of using the online store website"*, *"checked the app store, can I drop my return off at one of your shops?"*, *"ordered from the web store; how do I return this at a retail storefront?"*, *"My friend asked 'do your shops take returns', can I return my item at a retail shop?"*) all return `True`, while pure online store app-return stays `False`.
- **Ambiguous `"shop"` mentions & approved-KB counterexamples preserved:** *"The shop sent me a broken lamp, how do I request a return?"*, *"The local shop shipped the wrong size; can I use courier pickup to return it?"*, *"I got a defective kettle at a local shop on Tiki and want courier pickup instead."*, `"Can I drop off my parcel at a designated Tiki partner post office?"` (`POL-RET-002`), `"How do I schedule free courier pickup in the Tiki app?"` (`POL-RET-002`), and *"Please send me a return shipping label for my item."* all return `False`.
- **Negation locality (minor non-blocking P2 quirk disclosed):** `"Instead of visiting a storefront..."`, `"Without visiting a retail shop..."`, `"No need for a physical store..."`, and `"I do not want to visit a physical store..."` all return `False` (`allowed`). Because `_DECLARATIVE_CHANNEL_NEG_PREFIX` ([L307-L312](../../apps/core_backend/safety.py#L307-L312)) does not yet include intervening verbs like `go to`/`tell me to go to`/`use` after `do not want/need to` before `L329`'s `to a physical store`, phrasings like `"I do not want to go to a physical store; can I schedule courier pickup instead?"` fail conservatively (`True` -> escalate). This does **not** leak unsafe drafts (`0/649` supported benchmark rows affected); defer any ergonomic cleanup out of Slice 1 so Worker C eval is not delayed.
- **Untrusted metadata, ReDoS, case IDs, `AI_REASONS`:** Fabricated docs (`POL-RET-999`, `source_type="faq"`, self-declared `capabilities`) fail closed via `_trusted_policy_docs()` ([L448-L503](../../apps/core_backend/safety.py#L448-L503)); `4 x 4k`-word adversarial inputs run in `21.32 ms` (`_PHYSICAL_STORE_CHANNEL_PATTERN`), `7.10 ms` (`_PREPAID_RETURN_LABEL_PATTERN`), and `11.73 ms` (`_FULL_ORDER_HISTORY_PATTERN`); zero frozen case IDs appear in `safety.py`; emits only existing `AI_REASONS` (`"no_valid_document"`, `"insufficient_evidence"`).

---

## 3. Observed Offline Gate Counts (`1,245` Frozen Rows) & Test Runs

> **Distinction:** Counts below come from Worker B's deterministic offline replay of [`RetrievalAdapter`](../../apps/core_backend/retrieval/adapter.py) + `evaluate_evidence_scope()` / [`Engine.analyse()`](../../apps/ai_service/engine.py) on frozen `predictions_orig_fit2.jsonl` (`0` training, `0` paid LLM calls). Full paired `Runner`/`Engine`/`priv_*` verification awaits Worker C's independent `evaluate_candidate.py` run. **Raw Original Fit2 metrics (`noise420 macro_f1_12=0.857307`, `bare=267/420`) are unchanged.**

| Suite | Runner Gate Corr (`retrieve_draft` & gold-match) | Runner Leaks (pre-LLM gate) | Engine Leaks (`Engine.analyse`) | Notes |
| --- | --- | --- | --- | --- |
| `noise420` | **`260 -> 260`** (`>= 260` floor met) | `0 -> 0` | `0 -> 0` | Restored `sup-return_product-03::{clean,casual}` |
| `sa156` (excl. `unc-*`) | **`66 -> 66`** (`sup-* 48 -> 48`) | **`1 -> 0`** | **`2 -> 0`** | Closed `uns-order_history-01` & `uns-return_product_in_store-01` |
| `pos175` | `35 -> 34` | **`3 -> 0`** | **`4 -> 0`** | Disclosed expected `cls_dis_wrong_drop_0_841424c7a978` drop (`raw < 0.55`, not ML change); closed `090/099/102/107` |
| `final24` (`ans12`) | **`11 -> 11`** (`>= 10` floor met) | `0 -> 0` | `0 -> 0` | Preserved |
| `unseen36` | `10 -> 10` | **`3 -> 0`** | **`3 -> 0`** | Closed `ugc-retinstore-01/06`, `ugc-retonl-01` |
| `fresh34` | `4 -> 4` | **`1 -> 0`** | **`1 -> 0`** | Closed `v4p1-ood-08` |
| `ind36` | `5 -> 5` | `0 -> 0` | `0 -> 0` | Preserved |
| `sealed72` | `5 -> 5` | `0 -> 0` | `0 -> 0` | Preserved |
| `neg51` | `0 -> 0` | **`1 -> 0`** | **`1 -> 0`** | Closed `nonretail_ood_eval_019` (`no_valid_document`) |
| `oos80` | `0 -> 0` | `0 -> 0` | `0 -> 0` | Preserved |
| **Total (`1,245` non-`unc`)** | **`396 -> 395`** | **`9 -> 0`** | **`11 -> 0`** | **Ready for Worker C independent paired eval** |

- **Pytest Executed Independently on `12d358d3`:**
  - `.venv\Scripts\python.exe -m pytest tests/unit/test_safety_slice1_gap1_a.py tests/unit/test_supported_unsupported_boundary_b.py tests/unit/test_retrieval_grounding_b2.py tests/unit/test_accounting_guardrails_b.py tests/unit/test_mandatory_routing_b.py tests/unit/test_semantic_retrieval.py tests/unit/test_completion_retrieval.py tests/unit/test_system_components.py tests/application/ tests/integration/test_routing_retrieval.py tests/unit/test_guard_corrections_checks.py tests/unit/test_completion_knowledge.py -q` -> **`367 passed, 1 xfailed in 94.33s`** (single `xfailed`: pre-existing `test_engine_should_not_draft_track_order_without_order_id` in `test_supported_unsupported_boundary_b.py`).

---

## 4. Invariants & Open Sequential Gaps

- **All 8 Invariant SHA-256 Checksums Verified Unchanged on `12d358d3`:**
  - `data/knowledge/approved_kb.v2.json`: `f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec`
  - `apps/ai_service/kb-release.json`: `cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804`
  - `apps/core_backend/config/policies/intent_policy.v2.json`: `8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7`
  - `.local/training-cap-20261114.json`: `bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922`
  - `.local/ai.env`: `26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87`
  - `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors`: `f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa`
  - `artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json`: `782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39`
  - `artifacts/models/trained/distilbert-supportiq/model.safetensors`: `dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302`
- **Explicit Open Limits / Sequential Work:**
  - **Residual non-transposition typos** (`"in storr"`, `"lbel"`) and **fluent retail-adjacent OOD** passing unboosted `>= 0.55` aligned cosine remain open limits without training/embedding changes (`training-cap` `2/2` exhausted, `STOP`).
  - **Gap 2** (backend/Engine authority parity & `SENSITIVE_AUTHORITY_PATTERN` outage lock + `track_order` slot parity) and **Gap 3** (NER fail-closed privacy guard in `privacy.py`) remain **NOT CLOSED** and queued for subsequent slices after Worker C verifies Slice 1.
