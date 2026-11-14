# Before/After Controlled Provider Resilience Comparison

- **Before Commit:** `54fda754a528f6798f6cf2024cb1688c5936ad02`
- **After Commit (B Candidate):** `ff0e147d0181317d1550cec8df53420d8eddf771`
- **Boundary:** Executed via deterministic httpx.MockTransport + ControlledSimClock with 0 external provider calls. Controlled recovery does NOT establish live provider uptime or real API availability.

## Summary Delta

| Metric | Before | After |
| :--- | :--- | :--- |
| **Draft-Ready Count** | 6/18 | 7/18 |
| **Transient Recovery** | 4/9 (44.44%) | 6/9 (66.67%) |
| **10s Budget Respected All** | `True` | `True` |
| **5s Attempt Cap Respected All** | `True` | `True` |
| **Unconditional `trust_env=False`** | `False` | `False` |
| **Latency Includes Retry Waits All** | `True` | `True` |
| **429 Daily Quota Fail-Fast** | `True` | `True` |
| **Fast 503 Storm Max Attempts** | `2` | `2` |
| **No-Auto-Send Verified All** | `True` | `True` |
| **Simulated Latency p50 / p95 / max (s)** | 0.8 / 9.5 / 10.0 | 1.2 / 9.75 / 10.0 |

## Schedule-by-Schedule Comparison

| Schedule | Expected | Before Status (Att / Sim / Rep) | After Status (Att / Sim / Rep) | Wait Incl? | Usage Status (B -> A) | Budget OK (B / A) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `S01_clean_success` | `draft_ready` | `draft_ready` (1 / 0.75s / 0.75s) | `draft_ready` (1 / 0.75s / 0.75s) | `True` | `complete` -> `complete` | `True` / `True` |
| `S02_single_503_then_success` | `draft_ready` | `draft_ready` (2 / 1.30s / 1.30s) | `draft_ready` (2 / 1.55s / 1.55s) | `True` | `incomplete_mixed_attempts` -> `incomplete_mixed_attempts` | `True` / `True` |
| `S03_double_503_then_success` | `draft_ready` | `llm_unavailable` (2 / 0.70s / 0.70s) | `llm_unavailable` (2 / 0.95s / 0.95s) | `True` | `unknown_no_response` -> `unknown_no_response` | `True` / `True` |
| `S04_503_short_retry_after_then_success` | `draft_ready` | `draft_ready` (2 / 1.10s / 1.10s) | `draft_ready` (2 / 2.10s / 2.10s) | `True` | `incomplete_mixed_attempts` -> `incomplete_mixed_attempts` | `True` / `True` |
| `S05_503_retry_after_beyond_budget` | `fallback` | `draft_ready` (2 / 1.00s / 1.00s) | `llm_unavailable` (1 / 0.50s / 0.50s) | `True` | `incomplete_mixed_attempts` -> `unknown_no_response` | `True` / `True` |
| `S06_429_short_retry_after_then_success` | `draft_ready` | `llm_unavailable` (1 / 0.30s / 0.30s) | `draft_ready` (2 / 2.20s / 2.20s) | `True` | `unknown_no_response` -> `incomplete_mixed_attempts` | `True` / `True` |
| `S07_timeout_then_success` | `draft_ready` | `draft_ready` (2 / 6.20s / 6.20s) | `draft_ready` (2 / 6.20s / 6.20s) | `True` | `incomplete_mixed_attempts` -> `incomplete_mixed_attempts` | `True` / `True` |
| `S08_repeated_timeouts_exhaust_budget` | `fallback` | `llm_unavailable` (2 / 10.00s / 10.00s) | `llm_unavailable` (2 / 10.00s / 10.00s) | `True` | `unknown_no_response` -> `unknown_no_response` | `True` / `True` |
| `S09_slow_503_then_clamped_timeout` | `fallback` | `llm_unavailable` (2 / 9.50s / 9.50s) | `llm_unavailable` (2 / 9.75s / 9.75s) | `True` | `unknown_no_response` -> `unknown_no_response` | `True` / `True` |
| `S10_permanent_503_exhaustion` | `fallback` | `llm_unavailable` (2 / 0.80s / 0.80s) | `llm_unavailable` (2 / 1.05s / 1.05s) | `True` | `unknown_no_response` -> `unknown_no_response` | `True` / `True` |
| `S11_non_retryable_400_fast_fail` | `fallback` | `llm_unavailable` (1 / 0.25s / 0.25s) | `llm_unavailable` (1 / 0.25s / 0.25s) | `True` | `complete` -> `complete` | `True` / `True` |
| `S12_connect_error_then_success` | `draft_ready` | `draft_ready` (2 / 1.20s / 1.20s) | `draft_ready` (2 / 1.20s / 1.20s) | `True` | `incomplete_mixed_attempts` -> `incomplete_mixed_attempts` | `True` / `True` |
| `S13_remaining_budget_clamped_timeout` | `fallback` | `llm_unavailable` (2 / 7.70s / 7.70s) | `llm_unavailable` (2 / 7.95s / 7.95s) | `True` | `unknown_no_response` -> `unknown_no_response` | `True` / `True` |
| `S14_503_malformed_retry_after_header` | `draft_ready` | `llm_unavailable` (2 / 0.60s / 0.60s) | `llm_unavailable` (1 / 0.30s / 0.30s) | `True` | `unknown_no_response` -> `unknown_no_response` | `True` / `True` |
| `S15_429_invalid_retry_info_typing` | `draft_ready` | `llm_unavailable` (1 / 0.30s / 0.30s) | `llm_unavailable` (1 / 0.30s / 0.30s) | `True` | `unknown_no_response` -> `unknown_no_response` | `True` / `True` |
| `S16_429_valid_retry_info_json` | `draft_ready` | `llm_unavailable` (1 / 0.30s / 0.30s) | `draft_ready` (2 / 2.10s / 2.10s) | `True` | `unknown_no_response` -> `incomplete_mixed_attempts` | `True` / `True` |
| `S17_429_daily_quota_exhausted_non_retryable` | `fallback` | `llm_unavailable` (1 / 0.30s / 0.30s) | `llm_unavailable` (1 / 0.30s / 0.30s) | `True` | `unknown_no_response` -> `unknown_no_response` | `True` / `True` |
| `S18_fast_503_storm_max_attempts_bound` | `fallback` | `llm_unavailable` (2 / 0.10s / 0.10s) | `llm_unavailable` (2 / 0.35s / 0.35s) | `True` | `unknown_no_response` -> `unknown_no_response` | `True` / `True` |
