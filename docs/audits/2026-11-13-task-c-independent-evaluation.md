# Task C Independent Evaluation Report: Baseline Freeze, Controlled Provider Resilience, and Classifier Gate Readiness

- **Date (UTC):** `2026-11-13`
- **Task C Branch:** `MINHDZVODICH/supportiq-final-evidence`
- **Baseline Reference:** `54fda75` (`54fda754a528f6798f6cf2024cb1688c5936ad02`)
- **Evaluated Worker B Candidates:** `0eaadac` (initial), `9160ffb` (`9160ffbfb8e9dd9a55174273f608032aeca5aadf`, historical interim preserved), and **`ff0e147`** (`ff0e147d0181317d1550cec8df53420d8eddf771`, final)
- **Worker A Candidate Status:** **BLOCKED / ABSENT** (original verified Bitext raw/cleaned/splits absent; authorized recovery from recorded public source + exact hash; no classifier improvement claimed)
- **Boundary Declaration:** All provider resilience runs used deterministic `httpx.MockTransport` and `ControlledSimClock` with **0 live external LLM calls** and **0 root service restarts**. Controlled mock recovery does **not** prove live external provider uptime or real API quota availability.

---

## 1. Independent Baseline Freeze & Correct-Intent Recomputation

Artifacts:
- [`baseline_freeze.json`](../../artifacts/evaluation/independent_baseline_20261113/baseline_freeze.json)
- [`BASELINE_FREEZE_REPORT.md`](../../artifacts/evaluation/independent_baseline_20261113/BASELINE_FREEZE_REPORT.md)

Recomputed directly from frozen policies, knowledge base, model comparison raw predictions, and live `r3` evidence records:

| Suite / Metric | Serving (`distilbert-supportiq`) | Prior Rejected (`supportpilot-distilbert`) | Independent Finding |
| :--- | :--- | :--- | :--- |
| **Final Acceptance Answerable (N=12) — Raw Draft-Eligible** | **5/12** (`41.67%`) | **8/12** (`66.67%`) | Serving drafts cases `01, 02, 08, 09, 11` |
| **Final Acceptance Answerable (N=12) — Correct-Intent Draft-Eligible** | **4/12** (`33.33%`) | **6/12** (`50.00%`) | Serving `final-case-02` predicts `return_policy` != `return_product`; `supportpilot` also drafts `final-case-12` on wrong intent `track_order` |
| **System Acceptance `draft_expected` (N=34) — Raw Draft-Eligible** | **21/34** (`61.76%`) | **26/34** (`76.47%`) | Explicitly labeled `known_acceptance_regression_not_unseen_holdout` |
| **System Acceptance `draft_expected` (N=34) — Correct-Intent Draft-Eligible** | **17/34** (`50.00%`) | **23/34** (`67.65%`) | Serving has 4 wrong-intent drafts inside `draft_expected` |
| **Strict Mandatory Escalation (N=63) — Allowed Actions Match** | **21/63** (`33.33%`) | **20/63** (`31.75%`) | `abstain/manual_fallback != escalate`; serving has 16 `escalate`, 46 `manual_fallback`, 1 static uninjected `NOT_EXECUTED` (`unc-return_policy-04`) |
| **Strict Mandatory Escalation — Real Unsafe Draft Leaks** | **0** | **2** (`uns-return_product_in_store-01`, `uns-track_delivery-01`) | Excludes pre-existing static uninjected fault `unc-return_policy-04` |
| **ML OOD (N=80) — Safe Rate / Draft Leaks** | **80/80** (`0` leaks) | **79/80** (`['oos-multi_intent-07']`) | Raw `raw_predictions.jsonl` confirms leak is `oos-multi_intent-07` (`cancel_order`, conf `0.81853`), correcting earlier prose reference to `-09` |
| **Live R3 Run (20 HTTP + 4 Fixtures)** | **1/12** `draft_ready` (`0/12` correct-intent + `draft_ready`) | N/A | 20/20 `no_auto_send`; 5/12 pre-LLM draft routed (4/12 correct-intent), 7/12 abstained, 4/12 timed out; single `draft_ready` (`final-case-02`) had wrong predicted intent (`return_policy` != `return_product`) |

Note on worktree assets: Inside this git worktree, ignored model weight files under `artifacts/models/` are absent on disk (`MISSING` in the worktree freeze manifest); model inference checks ran explicitly against the frozen directories in the root repository (`F:\Năm 3\SD\project\SupportIQ\artifacts\models\...`).

---

## 2. Controlled Before/After Provider Resilience Evaluation (18 Schedules, 0 Live Calls)

Artifacts:
- Baseline (`05398cf` / `54fda75` parity): [`artifacts/evaluation/provider_resilience_20261113/BEFORE_BASELINE_REPORT.md`](../../artifacts/evaluation/provider_resilience_20261113/BEFORE_BASELINE_REPORT.md)
- Initial B (`0eaadac`, historical preserved): [`artifacts/evaluation/provider_resilience_0eaadac_initial_20261113/BEFORE_AFTER_COMPARISON.md`](../../artifacts/evaluation/provider_resilience_0eaadac_initial_20261113/BEFORE_AFTER_COMPARISON.md)
- Interim B (`9160ffb`, historical preserved): [`artifacts/evaluation/provider_resilience_9160ffb_20261113/BEFORE_AFTER_COMPARISON.md`](../../artifacts/evaluation/provider_resilience_9160ffb_20261113/BEFORE_AFTER_COMPARISON.md), [`AFTER_CANDIDATE_REPORT.md`](../../artifacts/evaluation/provider_resilience_9160ffb_20261113/AFTER_CANDIDATE_REPORT.md), [`after_candidate.json`](../../artifacts/evaluation/provider_resilience_9160ffb_20261113/after_candidate.json)
- **Final B (`ff0e147` vs `54fda75`):** [`BEFORE_AFTER_COMPARISON.md`](../../artifacts/evaluation/provider_resilience_ff0e147_20261113/BEFORE_AFTER_COMPARISON.md), [`AFTER_CANDIDATE_REPORT.md`](../../artifacts/evaluation/provider_resilience_ff0e147_20261113/AFTER_CANDIDATE_REPORT.md), [`after_candidate.json`](../../artifacts/evaluation/provider_resilience_ff0e147_20261113/after_candidate.json), [`candidate_edge_contracts.json`](../../artifacts/evaluation/provider_resilience_ff0e147_20261113/candidate_edge_contracts.json), [`report_hashes.json`](../../artifacts/evaluation/provider_resilience_ff0e147_20261113/report_hashes.json)

### Summary Comparison Across Revisions

| Controlled Schedule Metric (18 Deterministic Schedules) | Baseline (`54fda75`) | Initial B (`0eaadac`) | Interim B (`9160ffb`) | Final B (`ff0e147`) |
| :--- | :--- | :--- | :--- | :--- |
| **Draft-Ready Count** | `6/18` | `9/18` (7/9 transient; 2 invalid-header cases retried) | `7/18` | **`7/18`** |
| **Transient Recovery Rate (9 Recoverable Schedules)** | `4/9` (`44.44%`) | `7/9` (`77.78%`) | `6/9` (`66.67%`) | **`6/9` (`66.67%`)** |
| **10s Deadline Allocation Respected All** | `True` | `True` | `True` | **`True`** |
| **5s Per-Attempt Timeout Cap Respected All** | `True` | `True` | `True` | **`True`** |
| **Unconditional `trust_env=False`** | `False` | `True` | `False` (proxy default `True`) | **`False`** (proxy default `True`) |
| **Reported Latency Includes Retry Waits All** | `True` | `False` | `False` (9 schedules dropped waits) | **`True`** (`18/18` schedules match sim elapsed) |
| **429 Daily Quota Fail-Fast (`S17`)** | `True` | `False` (retried daily quota) | `True` (`1` att, `0.30s`) | **`True`** (`1` att, `0.30s`) |
| **Fast 503 Storm Max Attempts (`S18`)** | `2` | `2` | `2` | **`2`** (`0.35s` sim & reported) |
| **Unknown/Incomplete Usage Preserved (0 Fabricated Totals)** | `True` | `True` | `True` | **`True`** |
| **No-Auto-Send Verified All** | `True` | `True` | `True` | **`True`** |
| **Simulated Elapsed Latency (All 18 incl. Failures) p50 / p95 / max (s)** | `0.8` / `9.5` / `10.0` | `0.775` / `9.75` / `10.0` | `1.2` / `9.75` / `10.0` | **`1.2` / `9.75` / `10.0`** |

### Key Verified Findings on Final Worker B Candidate `ff0e147` (`ff0e147d0181317d1550cec8df53420d8eddf771`)

1. **Wait-Inclusive Latency & Separated Components (`latency_includes_retry_waits_all = True`):**
   - `BudgetedDraftClient.generate()`, `_raise_aggregated_error()`, and `_raise_budget_exhausted()` now expose wait-inclusive `latency_seconds` plus separated `transport_latency_seconds` and `retry_wait_seconds` on both success results and `LLMError` exceptions (`Engine.draft()` `step_latency_ms["llm"]` matches `simulated_elapsed_seconds` across all `18/18` schedules, including exhausted/failed retry schedules `S03` `0.95s`, `S09` `9.75s`, `S10` `1.05s`, `S13` `7.95s`, `S18` `0.35s`).
   - Direct unit contract checks on `ff0e147` ([`candidate_edge_contracts.json`](../../artifacts/evaluation/provider_resilience_ff0e147_20261113/candidate_edge_contracts.json)) confirm:
     - Success (`S04` `503 Retry-After: 1 -> 200`): `latency_seconds=2.1`, `transport_latency_seconds=1.1`, `retry_wait_seconds=1.0`.
     - Exhausted failure (`S10` `503 -> 503`): `LLMError.code='llm_unavailable'`, `latency_seconds=1.05`, `transport_latency_seconds=0.8`, `retry_wait_seconds=0.25`, `attempt_count=2`.
2. **Hard Quota `429 QuotaFailure` + Valid `Retry-After` Header Fail-Fast (`passed = True`):**
   - `E01_hard_quota_429_with_valid_retry_after_header`: `429 QuotaFailure` (`GenerateRequestsPerDayPerProjectPerModel`) WITH header `Retry-After: 1` fails fast in **`1` attempt**, `sleep_delays_seconds=[]`, `simulated_elapsed_seconds=0.3`, `failure_code='llm_rate_limited'`, `no_auto_send_verified=True`, `total_tokens_fabricated=False`.
3. **Typed `google.rpc.RetryInfo` & Malformed Injected `retry_after` (`passed = True`):**
   - `S16_429_valid_retry_info_json` (`@type == "type.googleapis.com/google.rpc.RetryInfo"`, `"1s"`) recovers in `2` attempts (`2.10s` sim & reported); `E02_429_untyped_retry_delay_dict` (`@type == "...BadRequest"`) fails fast in `1` attempt with `0` sleep.
   - `malformed_injected_retry_after`: `'not-a-number'`, `True`, `nan`, `-3.0`, and `90000.0` injected on `LLMError` all fail closed cleanly in `1` call with `sleep_calls=[]`, `raised_code='llm_unavailable'`, `retry_wait_seconds=0.0` (no `ValueError`/`TypeError` crash).
4. **No Lower Coverage Falsely Counted as Success:**
   - Conservative fail-closed schedules `S05` (`503 Retry-After: 15 > 10s`, `expected_if_recovered='fallback'`), `S14` (`503` malformed `Retry-After` header), and `S15` (`429` invalid `RetryInfo` typing) all resolve to `llm_unavailable` in `1` attempt and are NOT counted as `draft_ready` recoveries (`S05` fixes baseline's buggy retry-past-`Retry-After: 15`). Transient recovery denominator remains strict (`6/9 = 66.67%`).
5. **Preserved Interim History (`9160ffb`) Summary:**
   - Historical interim candidate `9160ffb` ([`provider_resilience_9160ffb_20261113/`](../../artifacts/evaluation/provider_resilience_9160ffb_20261113/)) also achieved `6/9` controlled recovery and `S17` fail-fast, **but failed `latency_includes_retry_waits_all`** (`False` across `S02, S03, S04, S06, S09, S10, S13, S16, S18`), omitted `transport_latency_seconds`/`retry_wait_seconds`, and lacked `@type` checking on `RetryInfo` and `QuotaFailure + valid Retry-After` fail-fast.

### `ff0e147` Artifact SHA-256 Checksums ([`report_hashes.json`](../../artifacts/evaluation/provider_resilience_ff0e147_20261113/report_hashes.json))

| File | SHA-256 |
| :--- | :--- |
| `before_baseline.json` | `da2ccaf3fa0d857a10d8165d2a2a365cd806ae0f5dc357357051d6ee4562aa17` |
| `BEFORE_BASELINE_REPORT.md` | `a21a36cf867822969e7f3a12e41abe721affaeca66728408832d87274f79b6c5` |
| `after_candidate.json` | `e61235be76a5993e1fbdc797bf0630214270b1432bd6461879160f23003a91b2` |
| `AFTER_CANDIDATE_REPORT.md` | `44d33e7523d2faac399aa29be4bb3b40b67278401475a72999c4df2cd5e4ea76` |
| `before_after_comparison.json` | `a316e557adfeeb399c211f9d4ac5fe6e45f0649de2bfd0aaaa1863289b615986` |
| `BEFORE_AFTER_COMPARISON.md` | `7a355b114b6e988ecad4dcd74680655bd694d644d648efaa45b04be986081658` |
| `candidate_edge_contracts.json` | `de2e05593e3799164a71d69a0fe54d3c5bf3cd317aeb5256eb3790beebf55a1f` |

---

## 3. Independent Classifier Acceptance Gate & Worker A Blocker

- **Gate Script & Smoke Verification:** [`scripts/run_classifier_acceptance_gate.py`](../../scripts/run_classifier_acceptance_gate.py) and [`pipeline/evaluation/classifier_acceptance_gate.py`](../../pipeline/evaluation/classifier_acceptance_gate.py) were verified against the prior rejected candidate (`F:\Năm 3\SD\project\SupportIQ\artifacts\models\finetuned\supportpilot-distilbert`) vs Serving (`distilbert-supportiq`), producing `Gate Decision: REJECT` ([`CLASSIFIER_GATE_REPORT.md`](../../artifacts/evaluation/classifier_gate_rejected_supportpilot_20261113/CLASSIFIER_GATE_REPORT.md)) on `34_label_regression_system_acceptance`, `mandatory_escalation_unsafe_draft_leak` (`2` leaks), `mandatory_strict_action_regression` (`20/63 < 21/63`), `missing_group_isolated_holdout`, `missing_or_unverified_provenance`, `noise_safe_routing_regression`, `oos_draft_leak` (`1/80` `oos-multi_intent-07`), and `wrong_intent_draft_regression`.
- **Missing Worker A Candidate Blocker:** As confirmed by workspace/root inspection (`F:\Năm 3\SD\project\SupportIQ\data\datasets\` contains only `.gitkeep`; `artifacts/models/` contains only serving `distilbert-supportiq`, rejected `supportpilot-distilbert`, base `distilbert-base-uncased`, and `03-11-2026-*` TF-IDF artifacts), original verified Bitext raw/cleaned/split datasets are absent. Recovery is authorized only from a recorded public source + exact hash; until an actual trained candidate + provenance manifest + verified group-isolated splits are supplied, **no classifier or automatic draft coverage improvement is claimed**.

---

## 4. Final Review Recommendation & Regression Verification

- **Worker B Provider Resilience (`ff0e147`):** **APPROVE (controlled provider resilience & accounting).** All 18 deterministic schedules and all 5 targeted edge-contract checks pass (`budget_respected_all=True`, `attempt_cap_respected_5s=True`, `latency_includes_retry_waits_all=True`, `quota_429_non_retryable_fail_fast=True`, `no_auto_send_all=True`, `zero_fabricated_totals=True`, plus root `test_provider_recovery_b.py` 156 tests passing per coordinator notice). Operational caveats retained explicitly: `trust_env=True` proxy default is intentionally preserved unless overridden, deadline allocation bounds per-attempt timeouts rather than preemptive hard OS thread kills, and **actual live external LLM availability remains unknown**.
- **Worker A Classifier / Whole-System Live Draft Coverage:** **REJECTED FIRST CANDIDATE (`4cb07f4`); SERVING ASSETS UNCHANGED** (no automatic draft-coverage promotion).
- **Task C Regression Verification (`pytest` after final edits):**
  - `pytest tests/unit/test_task_c_evaluation_gates.py tests/unit/test_live_provider_budget_guard.py tests/unit/test_candidate_comparison_accounting.py tests/unit/test_accounting_guardrails_b.py -q` (run recorded after edit).

---

## 5. Bounded Live Oracle-Intent Grounded-Provider Component Verification (`ff0e147`, 8/8 HTTP Budget)

Authorized per `9b52b31` (`Live verification authorization`) after passing the controlled 18-schedule gate. Executed with `BudgetGuardedTransport(max_requests=8)` wrapping `httpx.HTTPTransport(retries=0)` (`trust_env=False`, `follow_redirects=False`, pinned HTTPS host `generativelanguage.googleapis.com`), `5s` per-attempt timeout, `10s` deadline, and `gemini-3.1-flash-lite` (`grounded-v3`). Private root `.env` credentials were read in memory only (`0` secrets persisted).

Artifacts: [`LIVE_VERIFICATION_REPORT.md`](../../artifacts/evaluation/live_ff0e147_oracle_20261113/LIVE_VERIFICATION_REPORT.md), [`live_verification.json`](../../artifacts/evaluation/live_ff0e147_oracle_20261113/live_verification.json), [`accounting_recomputed.json`](../../artifacts/evaluation/live_ff0e147_oracle_20261113/accounting_recomputed.json), [`dry_run_preflight.json`](../../artifacts/evaluation/live_ff0e147_oracle_20261113/dry_run_preflight.json), [`report_hashes.json`](../../artifacts/evaluation/live_ff0e147_oracle_20261113/report_hashes.json)

- **Boundary Label:** **`oracle_intent_grounded_provider_component_verification`** (uses `intent_override` = expected intent on `final-case-02`, `03`, `10`, `12` with approved KB retrieval — **NOT** automatic end-to-end classifier coverage or whole-system live acceptance).
- **Budget & Transport Reconciliation:** Preflight `0/8` -> Final actual HTTP requests **`8/8`** (`rejected_before_network=0`, `transport_retries_configured=0`). Remaining live calls: `0` (run stopped cleanly at 4 top-level generations / 8 HTTP calls). `live_verification.json` remains preserved byte-identical (`548a96fd...`).
- **Per-Case & Per-Attempt Results:**
  - `final-case-02` (`return_product`, serving raw pred `return_policy` `0.7699`): Att 0 HTTP `503` (`4.6577s`, usage `None`) -> `0.25s` backoff -> Att 1 `llm_timeout` (`5.0053s`) -> `llm_unavailable` (`failure_code=llm_timeout`, wall `9.93s`, LLM rep `9.91s`, `no_auto_send=True`).
  - `final-case-03` (`refund_policy`, serving raw pred `payment_issue` `0.4416`): Att 0 `llm_timeout` (`5.1053s`) -> Att 1 `llm_timeout` (`5.0045s`) -> `llm_unavailable` (`failure_code=llm_timeout`, wall `10.15s`, LLM rep `10.11s`, `no_auto_send=True`). Note: `10.11s` reflects documented deadline-allocation semantics where OS socket read timeout completes slightly after `5.0s`.
  - `final-case-10` (`delivery_issue`, serving raw pred `delivery_issue` `0.2618`): Att 0 `llm_timeout` (`5.1047s`) -> Att 1 HTTP `200` (`1.3891s`, `1742`/`122`/`1864` tokens) -> **`draft_ready`** (wall `6.6006s`, LLM rep `6.494s`, cites `POL-SHIP-004:1.0`, preserves verified KB hotline `1900 6035`, `no_auto_send=True`).
  - `final-case-12` (`payment_issue`, serving raw pred `track_order` `0.5636`): Att 0 `llm_timeout` (`5.0171s`) -> Att 1 HTTP `200` (`1.3321s`, `1704`/`128`/`1832` tokens) -> **`draft_ready`** (wall `6.4771s`, LLM rep `6.349s`, cites `POL-PAY-001:1.0`, `no_auto_send=True`).
- **Coordinator AI Draft Review Notes (Oracle Component Boundary):**
  - `final-case-10`: **`policy_supported`** — accurately cites `POL-SHIP-004:1.0` (`24-48 hours`, courier GPS verification / delivery hub inspection, hotline `1900 6035` preserved without placeholder leak).
  - `final-case-12`: **`conditional_payment_guidance`** — grounded in `POL-PAY-001:1.0` (`15-30 minutes` payment reconciliation, auto-refund `after 1 hour` within `24-72 business hours`); `intent_override` bypassed Serving misclassification (`track_order`), so it verifies grounded-provider component recovery ONLY (`NOT` automatic classifier coverage).
- **Aggregate Live Component Outcome & Latency Method Transparency:** **`2/4` recovered drafts (`2/4` fallback)** across `8` HTTP calls / `4` cases (`6/8` attempts failed/timed out); `no_auto_send_all=True`. Sorted case wall latencies `[6.4771, 6.6006, 9.9265, 10.1452]`: **standard interpolated median p50 = `8.26355s`** (`(6.6006 + 9.9265) / 2`), vs prior nearest-rank `len//2` index `p50 = 9.9265s`, `max = 10.1452s` (`p95` collapses to `max` on `n=4` cases; descriptive only, tiny-sample caveat).
- **Corrected Token Accounting & Verified Primary Pricing ([`accounting_recomputed.json`](../../artifacts/evaluation/live_ff0e147_oracle_20261113/accounting_recomputed.json)):**
  - `cost_status=incomplete_token_coverage`, `attempts_missing_usage=6/8`, `observed_prompt=3446`, `observed_candidate=250`, `observed_total_minus_prompt=250`, `observed_reported_total=None`, `complete_cost_known=False`, `complete_cost_usd=None`, `invoice_verified=False`. Responses omit `thoughtsTokenCount` (`missing_thought_field_not_proof_of_zero=True`); zero usage invented for failed attempts.
  - **Verified primary list rates (`gemini-3.1-flash-lite` standard paid text via [`gemini-3.1-flash-lite-20261112.json`](../../artifacts/evaluation/pricing/gemini-3.1-flash-lite-20261112.json) / `ai.google.dev/gemini-api/docs/pricing`, `$0.25` input / `$1.50` output incl. thinking per 1M):** **`$0.0012365` conditional observed USD** (`$0.0008615` input + `$0.000375` output), retaining the prior unverified `$0.075/$0.30` estimate (`$0.00033345`) strictly for audit history; actual account billing tier & invoice remain unverified.
- **SHA-256 Hashes (`live_ff0e147_oracle_20261113/report_hashes.json`):** `dry_run_preflight.json` (`5a8253db8a458a413f8d20d283e38b432b0b74bf34ad49549f3412bdc8909d96`), `live_verification.json` (`548a96fd2466fcefb1c2cb74e876818bc0ec1c9967b56765761cb662121f8dad`, unmodified), `LIVE_VERIFICATION_REPORT.md` (`a3e6da967eeee98e272f023bd28898322245fb82ee462be9aeed0326e267f3de`), `accounting_recomputed.json` recorded.

---

## 6. Worker A First Candidate (`4cb07f4`) Independent Gate Evaluation -> `REJECT`

Artifacts: [`CLASSIFIER_GATE_REPORT.md`](../../artifacts/evaluation/classifier_gate_task_a_first_20261113/CLASSIFIER_GATE_REPORT.md), [`gate_report.json`](../../artifacts/evaluation/classifier_gate_task_a_first_20261113/gate_report.json)

Evaluated Worker A's recovered-Bitext first candidate (`C:/Users/PC/orca/workspaces/SupportIQ/supportiq-final-routing/artifacts/evaluation/task_a_20261113/candidate_model`, weights SHA-256 `1fc2d1b1c239709f88f1b7f1633a6446a7f5f606dac6ad820a1e6a00a9c92dcc`) against Serving `distilbert-supportiq`:
- **Split Isolation & Gold Contamination (`domain_templates.jsonl`, 216 rows vs 1,009 gold prompts):** **`PASS`** (`template_group_id` partitions cleanly disjoint; 0 exact/high-similarity gold matches).
- **Gate Decision:** **`REJECT`** (`oos_draft_leak`: **`2/80`** `['oos-multi_intent-02', 'oos-multi_intent-07']` at raw `T=1.0` vs Serving `0/80`; `34_label_regression_system_acceptance`: `0.5897`/`0.6225` vs Serving `0.6154`/`0.6471`; plus A's own `T=0.75` report records `3/80` OOD leaks and `1->3` mandatory draft leaks). Serving model `distilbert-supportiq` remains unchanged; calibration/negative-rejection followup authorized offline.

---

## 7. Worker A Follow-Up Candidate (`32e9781`) Independent Gate Evaluation -> `REJECT`

Artifacts: [`CLASSIFIER_GATE_REPORT.md`](../../artifacts/evaluation/classifier_gate_task_a_followup_20261113/CLASSIFIER_GATE_REPORT.md), [`gate_report.json`](../../artifacts/evaluation/classifier_gate_task_a_followup_20261113/gate_report.json), [`followup_supplement.json`](../../artifacts/evaluation/classifier_gate_task_a_followup_20261113/followup_supplement.json), [`report_hashes.json`](../../artifacts/evaluation/classifier_gate_task_a_followup_20261113/report_hashes.json)

Evaluated Worker A's negative-calibration followup candidate (`distilbert-supportiq-task-a-followup`, commit `32e9781`, `T=1.0`, `neg_loss_weight=0.75`, weights SHA-256 `b9e500b2997d54e62ffed9a805f84996b4633f103c2b9b7504e6fee8880aed4e`, matching `candidate_provenance_manifest.json`) without re-running heavy Bitext `6,690` inference (`classifier_gate_task_a_first_20261113/` preserved untouched):
- **Split Isolation & Gold Contamination (`PASS` on both datasets):** `domain_templates.jsonl` (`216` rows: `108` train / `36` cal / `72` eval) and `domain_negatives.jsonl` (`90` rows: `36` train / `27` cal / `27` eval, SHA `fdaae87d...`) both passed Task C split isolation & gold contamination (`0` overlaps, `0` exact/high-Jaccard matches vs `1,009` gold prompts). On held-out `domain_negatives` (`n=27`), both Serving and Follow-Up routed **`27/27 (1.0)` safe (`0` false drafts)**.
- **Safety vs Coverage Tradeoff Observed Independently:** Relative to `4cb07f4`, Follow-Up eliminated `34_label_regression_system_acceptance` (`0.6154` / `0.6520` >= Serving `0.6154` / `0.6471`), improved `ml_noise_420` (`0.7929` acc / `0.8012` F1 / `0.9548` safe routing vs Serving `0.6548`/`0.6817`/`0.9286`), eliminated `final_acceptance_24` wrong-intent answerable drafts (`0` vs Serving `1` `final-case-02`), and held-out domain eval reached `0.8056` acc / `24/72` raw / `22/72` correct-intent draftable. However, uniform-KL damping made strict-threshold answerable coverage conservative (`system_acceptance` `34` `draft_expected`: `17/34` raw / `15/34` correct-intent vs Serving `21/34` / `17/34`; `final_acceptance` `12`: `5/12`).
- **Gate Decision (`REJECT`, agreeing with Worker A `promotion_approved: false`):** Fails `oos_draft_leak` (**`1/80`** `['oos-multi_intent-02']` on `ml_oos_80` vs Serving `0/80`) plus Task C legacy top-level provenance keys (`missing_provenance_field:training_lineage,dataset_hashes,base_model,git_commit` despite valid SHA-256 matches in `candidate_provenance_manifest.json`), alongside Worker A's reported `1` unanswerable leak (`final-case-21`, pre-existing static expired-KB case) and mandatory action gap (`22/63`). **Serving model `distilbert-supportiq` remains unchanged.**

---

## 8. Worker A Selective Candidate (`028ed76`) & Worker B Runtime / Engine Verification (`23767a7`)

Artifacts:
- [`a_selective_dataset_review.json`](../../artifacts/evaluation/independent_baseline_20261113/a_selective_dataset_review.json), [`serving_selective_baseline.json`](../../artifacts/evaluation/independent_baseline_20261113/serving_selective_baseline.json)
- [`CLASSIFIER_GATE_REPORT.md`](../../artifacts/evaluation/classifier_gate_task_a_selective_20261113/CLASSIFIER_GATE_REPORT.md), [`gate_report.json`](../../artifacts/evaluation/classifier_gate_task_a_selective_20261113/gate_report.json), [`selective_supplement.json`](../../artifacts/evaluation/classifier_gate_task_a_selective_20261113/selective_supplement.json), [`report_hashes.json`](../../artifacts/evaluation/classifier_gate_task_a_selective_20261113/report_hashes.json)

### 8.1 Dataset Family Audit, Calibration-Only Selection & Provenance
- **Dataset Isolation (`task_a_selective_20261113/datasets/`):** Verified `11/11` manifest SHA-256 hashes, disjoint `template_group_id` splits across `{train, calibration, evaluation}` (`positive`: `108/36/72` across `72` groups / `12` intents; `negative`: `42/27/27` across `32` groups), `0` overlaps/exact/high-Jaccard matches against frozen gold suites and `306` prior dev templates (`negative_evaluation.jsonl` `n=27` and `positive_evaluation.jsonl` `n=72` both pass independently). Note: passing synthetic holdout isolation does not establish real user distribution equivalence or rule out subtle semantic paraphrase similarity.
- **Calibration-Only Winner (`calibration_selection.json`):** `fit1_selective_head` (`clean_positive_ce` + `cls_l2_plus_logit_geometry_v1` `776d` logistic rejector `tau=0.50`, `T=1.0857`, calibration utility `1.00205`) beat `fit2_selective_margin` (`0.97250`) strictly on calibration within `38.34s` total (`<= 1800.0s` cap).
- **Candidate Artifact Hashes (`028ed76`):** `model.safetensors` (`5eb713e430c18978dd007c8417874887ad8b1f7dda3ce6a9722ef8b61b2e1445`), `tokenizer.json` (`41b9d12a4c559e4098f30173bc0f76d092c43d7b1f873e7027da45a256f30f87`), `config.json` (`6fa1fa9cc6a94063a977b0adaf2c9c3b9296cf296d4ad9dcc6f2c52ca3bac9cb2`), `calibration_manifest.json` (`selective_calibration.v1`, `fc0d0ff98ce847b9102feb5b216b9b857ce6797d7eb3fe016181bfafbf16ffbb`). Historical Serving (`dc7af8cf...`), `4cb07f4` (`53ae375d...`), and `32e9781` (`ebdb2ef9...`) artifacts remain byte-identical.

### 8.2 Comparative Gate Metrics (`Serving` vs `028ed76 Raw` vs `028ed76 Calibrated + Rejector`)
`system_acceptance_156` and `final_acceptance_24` are labeled `known_acceptance_regression_not_unseen_holdout`; precision among draft-eligible strictly excludes wrong-intent drafts (`correct_intent_draft_eligible / raw_draft_eligible`), abstention coverage omits invented accuracy, and static uninjected fault fixtures (`unc-return_policy-04`, `final-case-21..24`) are tracked separately.

| Suite / Metric | Serving (`T=1.0`, raw) | Candidate `028ed76` Raw (`T=1.0`, no rej) | Candidate `028ed76` Cal + Rejector (`T=1.0857`, `tau=0.50`) |
| :--- | :--- | :--- | :--- |
| **Held-Out Positive (`n=72`, `sup12`)** Acc / Draft (`corr/raw`, Prec, Abst) | `0.4444` / `16/29` (`0.551724`, `0.597222`) | `0.7639` / `40/49` (`0.816327`, `0.319444`) | **`0.7639` / `37/45` (`0.822222`, `0.375`)** |
| **Held-Out Domain Negatives (`n=27`)** False Drafts | `0/27` | `1/27` (`return_product`, `0.840859`) | **`0/27`** |
| **Bitext 46 Test (`n=6,690`)** `all_46` / `other_34` Acc | `0.995366` / `0.996753` | N/A (`calibrated` argmax identical) | **`0.993274` / `0.994927`** (`F1 0.995634`) |
| **AutoEval `ml_noise_420`** Acc / Safe / ECE / Brier | `0.6548` / `0.9286` / `0.0920` / `0.1828` | `0.7905` / `0.9357` / `0.0577` / `0.1225` | **`0.7905` / `0.9524` / `0.0501` / `0.1209`** (`246/266` Prec `0.924812`) |
| **AutoEval `ml_oos_80`** False Drafts | **`0/80`** | `3/80` (`oos-multi_intent-02,07,11`) | **`3/80`** (`oos-multi_intent-02,07,11`) |
| **Regression `system_acceptance` 34 `draft_expected`** `corr/raw` (Prec, Abst) | `17/21` (`0.809524`, `0.382353`) | `25/27` (`0.925926`, `0.205882`) | **`21/23` (`0.913043`, `0.323529`)** |
| **Regression `system_acceptance` 63 Mandatory** Strict / Real Leaks / Uninjected | `21/63` / `0` / `1` (`unc-return_policy-04`) | `21/63` / `3` / `1` | `21/63` / **`1`** (`una-product_information-01`) / `1` |
| **Regression `final_acceptance` 12 Ans** `corr/raw` (Prec, Wrong) + Real Active Unans (`8`) | `4/5` (`0.80`, `['final-case-02']`) + `0` | `9/9` (`1.0`, `[]`) + `1` (`final-case-18`) | **`9/9` (`1.0`, `[]`) + `0`** (uninjected `final-case-21` separated) |

### 8.3 Runtime Parity, `23767a7` Engine Enforcement & Backend Route Blocker
- **Score Parity (`ModelContainer` vs `GateSequenceClassifier`):** Verified `0.0` `max_confidence_abs_diff` and `0.0` `max_margin_abs_diff` on Serving (`T=1.0` raw and `T=1.0857` calibrated) and on Candidate `028ed76` across `6` probes with `max_selective_score_abs_diff = 5.274e-07`, `0` rejector decision mismatches, and fail-closed rejection when `calibration_manifest_path` is omitted or tampered or `temperature <= 0`.
- **Engine Enforcement (`main` `c80a1bd` vs Worker B `23767a7` atop `65e1f47`/`ce98424`):**
  - On pre-merge `c80a1bd` `apps/ai_service/engine.py`, `verify_engine_rejection_enforcement` confirms `Engine._analyse` ignores `rejected_by_experimental_adapter=True` / `selective_accepted=False` (`engine_enforces_experimental_rejection=false`; rejector vetoes occur only in Task C's `_apply_adapter_routing_guard`).
  - On Worker B commit **`23767a7`** (`151 passed in 2.70s` in `supportiq-public-contact-fix`), independent cross-worktree verification confirms `Engine._analyse` **does** enforce `rejected_by_experimental_adapter=True` / `selective_accepted=False` -> `recommendation='abstain'` (`['low_confidence', 'out_of_scope_intent']`) with `intent.probability=0.95` unmutated, `Engine.draft` returns `status='abstained'` with `0` LLM calls, and `escalate` priority remains preserved for sensitive requests.
- **Open Backend-Route Blocker (`core_backend` Metadata Drop):** Verified via `IntentClient.classify_intent` + `IntentPrediction.model_fields` (`apps/core_backend/intent/{schemas.py,client.py}`) that the core backend intent adapter drops all `8` extra fields (`selective_accepted`, `selective_score`, `selective_threshold`, `rejected_by_experimental_adapter`, `raw_confidence`, `raw_score_kind`, `calibration_temperature`, `calibration_schema_version`). Coordinator backend follow-up `ctx_ee504bee728d` failed startup readiness and remains unfixed/unverified.

### 8.4 Final Gate Decision & Recommendations
- **Worker A Candidate `028ed76` (`supportiq-fit1_selective_head-20261113`):** **`REJECT` (HOLD SERVING BASELINE).** Candidate resolves the `32e9781` flattening regression and achieves substantial coverage/precision gains on `ml_noise_420`, `system_acceptance`, `final_acceptance`, and held-out `positive_evaluation`, while keeping `Bitext other_34 = 99.49%`; however, it still fails **`oos_draft_leak`** (`3/80`: `oos-multi_intent-02,07,11` vs Serving `0/80`) and **`mandatory_escalation_unsafe_draft_leak`** (`1/63`: `una-product_information-01` vs Serving `0/63`).
- **Worker B (`23767a7` `ModelContainer` + `Engine._analyse`):** Verified for score parity and `Engine`-path rejector enforcement; **blocked from full system promotion** alongside `028ed76` leaks until `apps/core_backend/intent/{schemas.py,client.py,routing.py}` preserves and enforces rejector metadata end-to-end.
- **Artifact SHA-256 (`classifier_gate_task_a_selective_20261113/report_hashes.json`):** `gate_report.json` (`674ad9f99659c1ac2a0e193446efa4674fa19c7499c8d4af96267b1890f257f0`), `CLASSIFIER_GATE_REPORT.md` (`6bae82d6d13702c6e8d35187c1b4f82498c2c75bf07ee1bb49f47febd5f0b8ac`), `selective_supplement.json` (`a53750be7c4ca7f365f27de19a88be102cc1a60e7f18577e1aa0faeeb4f80c11`).


