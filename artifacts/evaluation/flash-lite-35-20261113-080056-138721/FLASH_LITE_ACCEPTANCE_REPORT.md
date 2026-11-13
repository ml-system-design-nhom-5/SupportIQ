# Task C Bounded Application Acceptance Report (`flash-lite-35-20261113-080056-138721`)

- **Generated At:** `2026-11-13T08:02:02.468119+00:00`
- **Git Commit:** `787aa859eb5dd435d1ac72b8c947ee1c5e8b87f3`
- **Configured Model:** `gemini-3.5-flash-lite`
- **PostgreSQL Isolation:** Temporary schema `accept_fl35_de52df8250` (dropped cleanly; root ports `8080/8002` untouched)

## 1. Live LLM Budget Accounting
- **Authorized Max HTTP Requests:** `19`
- **Actual HTTP Requests Made:** `13`
- **Rejected Before Network:** `0`
- **Transport Retries Configured:** `0`
- **Budget Enforced Within Cap:** `True`

## 2. Phase 1: Primary Automatic Real-Application Results
- **Frozen Cases Submitted (Gateway + PG):** `20` (`12` answerable + `8` active-KB safety/escalation/unsupported/OOD; plus `4` injected component boundary fixtures)
- **Answerable Cases Correct-Intent:** `7/12`
- **Answerable Automatic Correct-Intent `draft_ready`:** `4/12`
- **Answerable Wrong-Intent Drafts:** `1` (`['final-case-02']`)
- **Answerable Abstained:** `7`
- **Answerable Fallback / Unavailable Errors:** `0` (`[]`)
- **Safety Unsafe Drafts:** `0` (`[]`)
- **Customer Auto-Send Blocking (`no_auto_send`):** `True`
- **Source Verification Passed:** `20/20`
- **Error Rate (`llm_unavailable`/timeout):** `0.0`
- **End-to-End Wall Latency (ms):** all `p50=298.08` (nearest `327.05`), `p95=2139.1255` (nearest `2133.34`) | answerable `p50=471.18`, `p95=2185.4095`
- **Injected Component Fixtures (`final-case-21..24`):** `4/4` passed (`expiry=2/2`, `conflict=2/2`, encoder=`real_bge_policy_encoder`)

## 3. Phase 2: Separately Labeled Staff Intent-Override Diagnostic
- **Override Cases Attempted:** `8`
- **Override `draft_ready` & Source-Verified:** `8`
- **Fallback / Failed:** `0`
- **Combined Unique Answerable Correct-Intent Drafts (Auto + Staff Override):** `12/12` (`['final-case-01', 'final-case-02', 'final-case-03', 'final-case-04', 'final-case-05', 'final-case-06', 'final-case-07', 'final-case-08', 'final-case-09', 'final-case-10', 'final-case-11', 'final-case-12']`)

## 4. Phase 3: Long-Timeout Component Diagnostic
- **Executed:** `False` — Not needed: zero llm_timeout failures under primary 5s/10s deadlines.

## 5. Tokens & Cost Accounting (Strict Non-Fabrication)
- **Attempts Counted:** `13` (missing usage: `0`, with `thoughtsTokenCount`: `0`)
- **Observed Prompt / Candidate / Thought Tokens:** `22520` / `1545` / `0`
- **Complete Cost Known / Invoice Verified:** `False` / `False` (`cost_status=complete_tokens_conditional_list_price_not_invoice`, `complete_billed_cost_usd=None`)
- **Conditional Observed List-Price USD ($0.30/1M in, $2.50/1M out):** `$0.0106185`

## 6. Stored 10-Fold OOF Verification (Zero Retraining)
- **DistilBERT OOF Records (`artifacts\training\distilbert_cv\oof_predictions.csv`):** `37911` rows, `10` folds, `46` intents, mean fold macro-F1 `0.995268` (`std_ddof1=0.001053`), global OOF macro-F1 `0.995271`
- **Serving `training_report.json` Cross-Check:** `matches_oof_macro_f1_mean_within_1e12=True`, `matches_all_10_fold_metrics_within_1e12=True`, `train_sample_ids_sha256_match=True`
