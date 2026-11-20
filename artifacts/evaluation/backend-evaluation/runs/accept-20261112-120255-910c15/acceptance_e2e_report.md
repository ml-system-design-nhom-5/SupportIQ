# SupportIQ — End-to-End Application Acceptance Report (MOCK CHECKS ONLY)

- **Run ID:** `accept-20261112-120255-910c15`
- **Timestamp:** `2026-11-12T12:02:55.578304+00:00`
- **Git HEAD:** `f67a018a67f31460bdf9812cbb2815e1491f9660`
- **Mode:** `mock`
- **Runner Checks Status:** **PASSED (MOCK CHECKS ONLY)**
- **Global Production Accepted:** `False` *(Cannot be certified by runner alone)*

> [!WARNING]
> **MOCK SIMULATION NOTICE:** Latency figures (e.g. p95) reflect mock loopback transport latency and synthetic delays, NOT actual LLM provider execution evidence. This run does NOT constitute live or production certification.

> [!IMPORTANT]
> **Application Acceptance Invariants:**
> 1. **100% Human Oversight:** Unreviewed AI drafts never reach the customer (`customer_reply is None`).
> 2. **Performance Target:** End-to-end p95 latency must be <= 12.0s under declared test conditions.
> 3. **Truthful Pricing:** Cost in USD is reported only when verified primary pricing is provided; missing pricing remains `unavailable`, never 0.0.

## 1. Acceptance Gates & Quality Checks

| Gate | Observed Value | Requirement | Status |
|---|---|---|:---:|
| **Human Oversight (No Auto-Send)** | 0 violations | 0 violations (`customer_reply is None`) | **PASS** |
| **p95 Latency** | `0.185s` | <= 12.000s | **PASS** |
| **Technical Errors** | `0` | 0 errors | **PASS** |
| **Timeouts** | `0` | 0 timeouts | **PASS** |
| **Failed Background Jobs** | `0` | 0 failures | **PASS** |

## 2. Latency Analysis (Cold vs Warm Conditions)

- **Overall p50 Latency:** `0.159s`
- **Overall p95 Latency:** `0.185s`
- **Min / Max Latency:** `0.102s` / `0.185s`

| Condition | Cases (n) | Latency (p50 / p95) | Description |
|---|---:|---|---|
| **Cold Start** | 1 | `0.155s` (first call) | Initial submission: application connection and DB pool cold start (NOT model cold start) |
| **Warm Runs** | 4 | p50: `0.160s`, p95: `0.185s` | Subsequent tickets on warmed worker thread |

## 3. Token Usage and Pricing Coverage

- **Prompt / Input Tokens:** `640`
- **Candidate / Output Tokens:** `210`
- **Thinking Tokens:** `0` (complete coverage)
- **Total Completion Tokens:** `210`
- **Total Tokens:** `850`
- **Cost Status:** `mock_simulation_cost_estimate`
- **Estimated Cost (USD):** `0.000475`
- **Lower Bound Cost (USD):** `0.000475`
- **Pricing Note:** MOCK TRANSPORT FIXTURE ONLY: Tokens and cost reflect mock simulated responses, NOT live LLM provider usage or real invoiced charges.

## 4. Case Execution Summary

| # | Condition | Ticket ID | Message | Wall Latency (ms) | Draft Status | Auto-Send Safe | Success |
|---|:---:|---|---|---:|:---:|:---:|:---:|
| 0 | `cold` | `TCK-1001` | What is your return policy?... | 154.73 | `draft_ready` | YES | **PASS** |
| 1 | `warm` | `TCK-1002` | Can I return an item I bought ... | 184.54 | `draft_ready` | YES | **PASS** |
| 2 | `warm` | `TCK-1003` | How long do I have to make a r... | 102.33 | `draft_ready` | YES | **PASS** |
| 3 | `warm` | `TCK-1004` | Do you offer refunds for retur... | 160.04 | `draft_ready` | YES | **PASS** |
| 4 | `warm` | `TCK-1005` | What are the return shipping c... | 158.94 | `draft_ready` | YES | **PASS** |

## 5. Verification Commands for Integration

```powershell
# 1. Environment preflight check
$env:PSYCOPG_IMPL = 'python'
$env:PATH = 'F:\PostgreSQL\bin;' + $env:PATH
& 'F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe' -m scripts.run_application_acceptance --mode mock

# 2. Live bounded verification (when coordinator authorizes)
# & 'F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe' -m scripts.run_application_acceptance --mode live
```
