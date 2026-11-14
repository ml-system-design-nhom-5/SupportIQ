# SupportIQ — End-to-End Application Acceptance Report

- **Run ID:** `accept-20261112-111205`
- **Timestamp:** `2026-11-12T11:12:05.333085+00:00`
- **Mode:** `mock`
- **Overall Acceptance Status:** **PASSED**

> [!IMPORTANT]
> **Application Acceptance Invariants:**
> 1. **100% Human Oversight:** Unreviewed AI drafts never reach the customer (`customer_reply is None`).
> 2. **Performance Target:** End-to-end p95 latency must be <= 12.0s under declared test conditions.
> 3. **Truthful Pricing:** Cost in USD is reported only when verified primary pricing is provided; missing pricing remains `unavailable`, never 0.0.

## 1. Acceptance Gates & Quality Checks

| Gate | Observed Value | Requirement | Status |
|---|---|---|:---:|
| **Human Oversight (No Auto-Send)** | 0 violations | 0 violations (`customer_reply is None`) | **PASS** |
| **p95 Latency** | `0.560s` | <= 12.000s | **PASS** |
| **Technical Errors** | `0` | 0 errors | **PASS** |
| **Timeouts** | `0` | 0 timeouts | **PASS** |
| **Failed Background Jobs** | `0` | 0 failures | **PASS** |

## 2. Latency Analysis (Cold vs Warm Conditions)

- **Overall p50 Latency:** `0.351s`
- **Overall p95 Latency:** `0.560s`
- **Min / Max Latency:** `0.323s` / `0.560s`

| Condition | Cases (n) | Latency (p50 / p95) | Description |
|---|---:|---|---|
| **Cold Start** | 1 | `0.560s` (first call) | Initial submission on fresh session / connection pool pickup |
| **Warm Runs** | 3 | p50: `0.331s`, p95: `0.371s` | Subsequent tickets on warmed worker thread |

## 3. Token Usage and Pricing Coverage

- **Prompt / Input Tokens:** `512`
- **Candidate Tokens:** `168`
- **Thinking Tokens:** `0` (omitted/untracked)
- **Total Output Tokens:** `168`
- **Total Tokens:** `680`
- **Cost Status:** `verified_list_price_estimate`
- **Estimated Cost (USD):** `0.00038`
- **Pricing Note:** List-price estimate for gemini-3.1-flash-lite (standard_paid) based on primary source https://aistudio.google.com/docs/pricing#gemini-3.1-flash-lite verified on 2026-11-12. Calculated with thinking tokens omitted/untracked in source records (no assumed zero). Not an invoiced account-tier charge.

## 4. Case Execution Summary

| # | Condition | Ticket ID | Message | Wall Latency (ms) | Draft Status | Auto-Send Safe | Success |
|---|:---:|---|---|---:|:---:|:---:|:---:|
| 0 | `cold` | `TCK-1001` | What is your return policy?... | 559.68 | `draft_ready` | YES | **PASS** |
| 1 | `warm` | `TCK-1002` | Can I return an item I bought ... | 330.73 | `draft_ready` | YES | **PASS** |
| 2 | `warm` | `TCK-1003` | How long do I have to make a r... | 370.72 | `draft_ready` | YES | **PASS** |
| 3 | `warm` | `TCK-1004` | Do you offer refunds for retur... | 322.53 | `draft_ready` | YES | **PASS** |

## 5. Verification Commands for Integration

```powershell
# 1. Environment preflight check
$env:PSYCOPG_IMPL = 'python'
$env:PATH = 'F:\PostgreSQL\bin;' + $env:PATH
& 'F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe' -m scripts.run_application_acceptance --mode mock

# 2. Live bounded verification (when coordinator authorizes)
# & 'F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe' -m scripts.run_application_acceptance --mode live
```
