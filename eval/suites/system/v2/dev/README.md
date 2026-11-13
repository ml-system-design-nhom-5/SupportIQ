# SupportIQ System Evaluation Benchmark Suite v2 (Dev)

- **Suite ID:** `supportiq-system-dev-v2`
- **Split:** `dev`
- **Status:** `candidate`
- **Total Cases:** 50
- **Purpose:** Development and diagnostic regression suite addressing failure inventory patterns discovered in v1 (misclassified models, confidence thresholds on outside-scope/human-agent intents, unverified gold citations, and fault injections).
- **Lineage:** Subsampled from v1 failure inventory and core product intents with rectified outcome contracts.

## Paths in the manifest

`suite_manifest.json` is not edited, so its paths are the paths on `main` before the join ([ADR-0017, Large files and data](../../../../../docs/decisions/0017-repository-layout-and-ai-ml-migration.md#large-files-and-data), statement 4). Each pinned SHA-256 is the uppercase hash of the raw bytes, CRLF line ends included, and still matches the file at its current path:

| Path in the manifest | Current path |
|---|---|
| `cases.jsonl` | `eval/suites/system/v2/dev/cases.jsonl` |
| `coverage_matrix.csv` | `eval/suites/system/v2/dev/coverage_matrix.csv` |
| `data/knowledge/approved_kb.v1.json` | `eval/suites/system/inputs/approved_kb.v1.json` |
| `data/knowledge/mock_orders.json` | `eval/suites/system/inputs/mock_orders.json` |
| `apps/core_backend/config/policies/intent_policy.v2.json` | `eval/suites/system/inputs/intent_policy.v2.json` |
