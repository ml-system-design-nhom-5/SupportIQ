# SupportIQ — End-to-End Application Acceptance Report (Bounded Live Run)

- **Run ID:** `accept-20261112-123928-2802bd`
- **Timestamp:** `2026-11-12T12:39:28.179297+00:00`
- **Git HEAD:** `55f4eb157a32d0a16c7ea84120d25b31fa86bd59`
- **Mode:** `live`
- **Boundary Kind:** `in_process_asgi_testclient`
- **Runner Checks Status:** **PASSED**
- **Global Production Accepted:** `False` *(Cannot be certified by runner alone)*

> [!IMPORTANT]
> **Application Acceptance Invariants:**
> 1. **100% Human Oversight:** Unreviewed AI drafts never reach the customer (`customer_reply is None` on verified HTTP 200 response).
> 2. **Performance Target:** End-to-end p95 latency must be <= 12.0s under declared test conditions with complete latency measurement coverage.
> 3. **Truthful Pricing:** Cost in USD is reported only when verified primary pricing is provided and model matches exactly; missing pricing remains `unavailable`, never 0.0.

## 1. Acceptance Gates & Quality Checks

| Gate | Observed Value | Requirement | Status |
|---|---|---|:---:|
| **Human Oversight (No Auto-Send)** | 0 violations | 0 violations (`customer_reply is None` on verified HTTP 200) | **PASS** |
| **p95 Latency** | `3.568s` | <= 12.000s | **PASS** |
| **Latency Measurement Coverage** | 100% Complete | All cases must report valid finite latency | **PASS** |
| **Technical Errors** | `0` | 0 errors | **PASS** |
| **Timeouts** | `0` | 0 timeouts | **PASS** |
| **Failed Background Jobs** | `0` | 0 failures | **PASS** |

## 2. Latency Analysis (Cold vs Warm Conditions)

- **Overall p50 Latency:** `0.176s`
- **Overall p95 Latency:** `3.568s`
- **Min / Max Latency:** `0.127s` / `3.568s`

| Condition | Cases (n) | Latency (p50 / p95) | Description |
|---|---:|---|---|
| **Cold Start** | 1 | `2.499s` (first call) | Initial submission: application connection and DB pool cold start (NOT model cold start) |
| **Warm Runs** | 4 | p50: `0.176s`, p95: `3.568s` | Subsequent tickets on warmed worker thread |

## 3. Token Usage and Pricing Coverage

- **Prompt / Input Tokens:** `2988`
- **Candidate / Output Tokens:** `281`
- **Thought Tokens:** `Unknown (observed partial: 0)` (omitted/untracked)
- **Total Completion Tokens:** `Unknown (missing thought tokens)`
- **Total Tokens:** `Unknown (observed partial: 3269)`
- **Cost Status:** `partial_lower_bound_missing_thinking`
- **Estimated Cost (USD):** `UNAVAILABLE`
- **Lower Bound Cost (USD):** `0.0011685`
- **Pricing Note:** One or more billable attempts lacked thought_tokens/thinking_tokens. Complete cost_usd is strictly null (None); lower_bound_cost_usd reflects lower bound excluding thinking tokens.

## 4. Case Execution Summary

| # | Condition | Ticket ID | Message | Wall Latency (ms) | Draft Status | Auto-Send Safe | Success |
|---|:---:|---|---|---:|:---:|:---:|:---:|
| 0 | `cold` | `TCK-1001` | What is your return policy?... | 2499.21 | `draft_ready` | YES | **PASS** |
| 1 | `warm` | `TCK-1002` | Can I return an item I bought ... | 175.56 | `abstained` | YES | **PASS** |
| 2 | `warm` | `TCK-1003` | How long do I have to make a r... | 126.88 | `abstained` | YES | **PASS** |
| 3 | `warm` | `TCK-1004` | Do you offer refunds for retur... | 128.32 | `abstained` | YES | **PASS** |
| 4 | `warm` | `TCK-1005` | What are the return shipping c... | 3567.72 | `draft_ready` | YES | **PASS** |

## 5. Verification Commands for Integration

```powershell
# 1. Environment preflight check
$env:PSYCOPG_IMPL = 'python'
$env:PATH = 'F:\PostgreSQL\bin;' + $env:PATH
& 'F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe' -m scripts.run_application_acceptance --mode mock

# 2. Live bounded verification (when coordinator authorizes)
# & 'F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe' -m scripts.run_application_acceptance --mode live
```
