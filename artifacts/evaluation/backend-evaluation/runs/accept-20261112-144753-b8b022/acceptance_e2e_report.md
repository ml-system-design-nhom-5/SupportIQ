# SupportIQ — End-to-End Application Acceptance Report (MOCK CHECKS ONLY)

- **Run ID:** `accept-20261112-144753-b8b022`
- **Timestamp:** `2026-11-12T14:47:53.849656+00:00`
- **Git HEAD:** `2b46fba0e35c645ec007736e55a096ae2ff9e464`
- **Mode:** `mock`
- **Boundary Kind:** `in_process_asgi_testclient`
- **Runner Checks Status:** **PASSED (MOCK CHECKS ONLY)**
- **Global Production Accepted:** `False` *(Cannot be certified by runner alone)*

> [!WARNING]
> **MOCK SIMULATION NOTICE:** Latency figures (e.g. p95) reflect mock loopback transport latency and synthetic delays, NOT actual LLM provider execution evidence. This run does NOT constitute live or production certification.

> [!IMPORTANT]
> **Application Acceptance Invariants:**
> 1. **100% Human Oversight:** Unreviewed AI drafts never reach the customer (`customer_reply is None` on verified HTTP 200 response).
> 2. **Performance Target:** End-to-end p95 latency must be <= 12.0s under declared test conditions with complete latency measurement coverage.
> 3. **Truthful Pricing:** Cost in USD is reported only when verified primary pricing is provided and model matches exactly; missing pricing remains `unavailable`, never 0.0.

## 1. Acceptance Gates & Quality Checks

| Gate | Observed Value | Requirement | Status |
|---|---|---|:---:|
| **Human Oversight (No Auto-Send)** | 0 violations | 0 violations (`customer_reply is None` on verified HTTP 200) | **PASS** |
| **p95 Latency** | `0.327s` | <= 12.000s | **PASS** |
| **Latency Measurement Coverage** | 100% Complete | All cases must report valid finite latency | **PASS** |
| **Technical Errors** | `0` | 0 errors | **PASS** |
| **Timeouts** | `0` | 0 timeouts | **PASS** |
| **Failed Background Jobs** | `0` | 0 failures | **PASS** |

## 2. Latency Analysis & Strata (Draft-Producing vs Abstention, Cold vs Warm)

- **Overall p50 Latency:** `0.255s`
- **Overall p95 Latency:** `0.327s`
- **Overall Mean Latency:** `0.251s`
- **Overall Error Rate:** `0.0%`
- **Min / Max Latency:** `0.183s` / `0.327s`

| Stratum / Condition | Cases (n) | p50 | p95 | Mean | Error Rate | Description |
|---|---:|---:|---:|---:|---:|---|
| **Draft-Producing** | 5 | `0.255s` | `0.327s` | `0.251s` | 0.0% | Tickets reaching draft generation (e.g. draft_ready, clarification) |
| **Abstention / Escalate** | 0 | `None` | `None` | `None` | 0.0% | Tickets abstaining or escalating before LLM generation (e.g. abstained, escalation_recommended) |
| **All Submitted Tickets** | 5 | `0.255s` | `0.327s` | `0.251s` | 0.0% | All submitted tickets across all conditions and outcomes |
| **Cold Start** | 1 | `0.265s` | `0.265s` | `0.265s` | 0.0% | Initial submission: application connection and DB pool cold start (NOT model cold start) |
| **Warm Runs** | 4 | `0.255s` | `0.327s` | `0.247s` | 0.0% | Subsequent tickets on warmed worker thread |

## 3. Token Usage and Pricing Coverage

- **Prompt / Input Tokens:** `640`
- **Candidate / Output Tokens:** `210`
- **Provider-Reported Total Tokens:** `850`
- **Thought Tokens:** `0` (complete coverage)
- **Total Completion Tokens (Billable Output):** `210`
- **Total Tokens:** `850`
- **Cost Status:** `mock_simulation_cost_estimate`
- **Estimated Cost (USD):** `0.000475`
- **Lower Bound Cost (USD):** `0.000475`
- **Pricing Note:** MOCK TRANSPORT FIXTURE ONLY: Tokens and cost reflect mock simulated responses, NOT live LLM provider usage or real invoiced charges.

## 4. Case Execution Summary

| # | Condition | Ticket ID | Message | Wall Latency (ms) | Draft Status | Auto-Send Safe | Success |
|---|:---:|---|---|---:|:---:|:---:|:---:|
| 0 | `cold` | `TCK-1001` | What is your return policy?... | 265.37 | `draft_ready` | YES | **PASS** |
| 1 | `warm` | `TCK-1002` | Can I return an item I bought ... | 327.19 | `draft_ready` | YES | **PASS** |
| 2 | `warm` | `TCK-1003` | How long do I have to make a r... | 254.84 | `draft_ready` | YES | **PASS** |
| 3 | `warm` | `TCK-1004` | Do you offer refunds for retur... | 224.84 | `draft_ready` | YES | **PASS** |
| 4 | `warm` | `TCK-1005` | What are the return shipping c... | 182.68 | `draft_ready` | YES | **PASS** |

## 5. Deployed Provenance Hashes & Live Service Versions

> [!NOTE]
> Local asset hashes represent local deployment expectations. Observed service versions reflect runtime responses from the service under test.

| Asset / Property | Kind | Identifier / Value | Hash (SHA-256) |
|---|:---:|---|---|
| **Deployed Knowledge Base** | Local Asset | `data/knowledge/approved_kb.v2.json` | `AAA924C4B48DCD53A14269045B278B66F6E5E8AE9D1B614CD59B757102B78594` |
| **Gateway Release Manifest** | Local Asset | `apps/ai_service/kb-release.json` | `33CF05B50C25384FBB208CD0C0C5CAE71991D29A0F754CB1B20A1D6D7285CDAA` |
| **Routing Policy** | Local Asset | `apps/core_backend/config/policies/intent_policy.v2.json` | `8789EE26ACDAC2E105FEA90942A1129553CA98DB4B182FCC4D74880B1F537BE7` |
| **Runner Configuration** | Local Config | *(safe without secrets)* | `6DD15B083B09279FDBF40A7BB4CB9662954A14EC97E8C84FEA06780A23D92330` |
| **Raw Execution Records** | Run Output | `raw_records.json` | `74D2BDCEF15FDDC43EDA7DF793B7C78B0F6D8905DB7BFB50ACF64807EB673336` |

### Observed Live Service Metadata

- **Observed Release ID(s):** `['rel-v2']`
- **Observed Model Version(s):** `['v1.0.0']`
- **Observed KB Version(s):** `['v2.0']`
- **Observed Prompt Version(s):** `['v2.0']`
- **Observed LLM Model(s):** `['mock-eval-llm']`
- **Observed Provider(s):** `['google_ai_studio']`

## 6. Verification Commands for Integration

```powershell
# 1. Environment preflight check
$env:PSYCOPG_IMPL = 'python'
$env:PATH = 'F:\PostgreSQL\bin;' + $env:PATH
& 'F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe' -m scripts.run_application_acceptance --mode mock

# 2. Live bounded verification (when coordinator authorizes)
# & 'F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe' -m scripts.run_application_acceptance --mode live
```
