# SupportIQ System Evaluation Benchmark Suite v2 (Acceptance)

- **Suite ID:** `supportiq-system-acceptance-v2`
- **Split:** `acceptance`
- **Status:** `draft` (held as draft until formal human sign-off as required by spec)
- **Total Cases:** 156
- **Purpose:** Full blinded acceptance benchmark across all 46 intent labels and 12 product scopes with strict quota enforcement.
- **Slice Quotas:**
  - `supported`: 60
  - `unsupported`: 34
  - `answerable`: 24
  - `unanswerable`: 18
  - `uncertainty_and_faults`: 20
- **Contract Rules:** Enforces strict separation between `must_escalate` and `safe_manual_handling`. Zero logical contradictions between `must_escalate` and `draft_expected`.

## Paths in the manifest

`suite_manifest.json` is not edited, so its paths are the paths on `main` before the join ([ADR-0021, Large files and data](../../../../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#large-files-and-data), statement 4). Each pinned SHA-256 is the uppercase hash of the raw bytes, CRLF line ends included, and still matches the file at its current path:

| Path in the manifest | Current path |
|---|---|
| `cases.jsonl` | `eval/suites/system/v2/acceptance/cases.jsonl` |
| `coverage_matrix.csv` | `eval/suites/system/v2/acceptance/coverage_matrix.csv` |
| `data/knowledge/approved_kb.v1.json` | `eval/suites/system/inputs/approved_kb.v1.json` |
| `data/knowledge/mock_orders.json` | `eval/suites/system/inputs/mock_orders.json` |
| `apps/core_backend/config/policies/intent_policy.v2.json` | `eval/suites/system/inputs/intent_policy.v2.json` |
