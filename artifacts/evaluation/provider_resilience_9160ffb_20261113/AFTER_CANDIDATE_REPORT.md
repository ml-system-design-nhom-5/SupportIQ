# Controlled Provider Resilience Report (after_b_candidate)

- **Generated At:** `2026-11-13T02:01:25.533238+00:00`
- **Source Commit:** `9160ffbfb8e9dd9a55174273f608032aeca5aadf`
- **Boundary:** Executed via deterministic httpx.MockTransport + ControlledSimClock with 0 external provider calls. Controlled recovery does NOT establish live provider uptime or real API availability.
- **Transient Recovery Rate:** `6/9` (`66.67%`)
- **Budget Respected All (<=10s):** `True` | **Attempt Cap Respected All (<=5s):** `True`
- **Unconditional `trust_env=False`:** `False` | **Latency Includes Retry Waits All:** `False` | **429 Quota Fail-Fast:** `True` | **Storm Max Attempts:** `2`
- **All Attempts Persisted:** `True` | **Zero Fabricated Totals:** `True` | **No-Auto-Send All:** `True`
- **Simulated Latency (s):** p50=`1.2`, p95=`9.75`, max=`10.0`

| Schedule | Expected | Status | Failure | Attempts | Sim Lat / Reported Lat (s) | Sleep (s) | Wait Incl? | Usage Status | Budget<=10s |
| :--- | :--- | :--- | :--- | ---: | :--- | :--- | :--- | :--- | :--- |
| `S01_clean_success` | `draft_ready` | `draft_ready` | `None` | 1 | 0.75s / 0.75s | `[]` | `True` | `complete` | `True` |
| `S02_single_503_then_success` | `draft_ready` | `draft_ready` | `None` | 2 | 1.55s / 1.30s | `[0.25]` | `False` | `incomplete_mixed_attempts` | `True` |
| `S03_double_503_then_success` | `draft_ready` | `llm_unavailable` | `llm_unavailable` | 2 | 0.95s / 0.70s | `[0.25]` | `False` | `unknown_no_response` | `True` |
| `S04_503_short_retry_after_then_success` | `draft_ready` | `draft_ready` | `None` | 2 | 2.10s / 1.10s | `[1.0]` | `False` | `incomplete_mixed_attempts` | `True` |
| `S05_503_retry_after_beyond_budget` | `fallback` | `llm_unavailable` | `llm_unavailable` | 1 | 0.50s / 0.50s | `[]` | `True` | `unknown_no_response` | `True` |
| `S06_429_short_retry_after_then_success` | `draft_ready` | `draft_ready` | `None` | 2 | 2.20s / 1.20s | `[1.0]` | `False` | `incomplete_mixed_attempts` | `True` |
| `S07_timeout_then_success` | `draft_ready` | `draft_ready` | `None` | 2 | 6.20s / 6.20s | `[]` | `True` | `incomplete_mixed_attempts` | `True` |
| `S08_repeated_timeouts_exhaust_budget` | `fallback` | `llm_unavailable` | `llm_timeout` | 2 | 10.00s / 10.00s | `[]` | `True` | `unknown_no_response` | `True` |
| `S09_slow_503_then_clamped_timeout` | `fallback` | `llm_unavailable` | `llm_timeout` | 2 | 9.75s / 9.50s | `[0.25]` | `False` | `unknown_no_response` | `True` |
| `S10_permanent_503_exhaustion` | `fallback` | `llm_unavailable` | `llm_unavailable` | 2 | 1.05s / 0.80s | `[0.25]` | `False` | `unknown_no_response` | `True` |
| `S11_non_retryable_400_fast_fail` | `fallback` | `llm_unavailable` | `llm_request_rejected` | 1 | 0.25s / 0.25s | `[]` | `True` | `complete` | `True` |
| `S12_connect_error_then_success` | `draft_ready` | `draft_ready` | `None` | 2 | 1.20s / 1.20s | `[]` | `True` | `incomplete_mixed_attempts` | `True` |
| `S13_remaining_budget_clamped_timeout` | `fallback` | `llm_unavailable` | `llm_unavailable` | 2 | 7.95s / 7.70s | `[0.25]` | `False` | `unknown_no_response` | `True` |
| `S14_503_malformed_retry_after_header` | `draft_ready` | `llm_unavailable` | `llm_unavailable` | 1 | 0.30s / 0.30s | `[]` | `True` | `unknown_no_response` | `True` |
| `S15_429_invalid_retry_info_typing` | `draft_ready` | `llm_unavailable` | `llm_rate_limited` | 1 | 0.30s / 0.30s | `[]` | `True` | `unknown_no_response` | `True` |
| `S16_429_valid_retry_info_json` | `draft_ready` | `draft_ready` | `None` | 2 | 2.10s / 1.10s | `[1.0]` | `False` | `incomplete_mixed_attempts` | `True` |
| `S17_429_daily_quota_exhausted_non_retryable` | `fallback` | `llm_unavailable` | `llm_rate_limited` | 1 | 0.30s / 0.30s | `[]` | `True` | `unknown_no_response` | `True` |
| `S18_fast_503_storm_max_attempts_bound` | `fallback` | `llm_unavailable` | `llm_unavailable` | 2 | 0.35s / 0.10s | `[0.25]` | `False` | `unknown_no_response` | `True` |
