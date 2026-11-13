# SupportIQ System Evaluation Benchmark Suite (v1)

The whole-system evaluation benchmark of SupportIQ, version v1. It measures intent classification, the safe routing gate, the retrieval of policy evidence (Semantic Retrieval), and the human control mechanism (Human Oversight).

---

## 1. Structure and provenance

- **Suite ID**: `supportiq-system-acceptance-v1`
- **Split**: `acceptance`
- **Current status**: `draft` (the set must finish independent testing by an evaluator before it moves to `approved` for live acceptance).
- **Point in time (`as_of`)**: `2026-11-05T00:00:00Z`
- **Case file (`cases.jsonl`)**: holds exactly 156 unique test cases, with no duplicate ID, structured as typed JSON Lines.
- **Coverage matrix (`coverage_matrix.csv`)**: counts the test cases of each business slice (primary slice) and checks them against the quotas.

---

## 2. Quotas of the 156 test cases (primary slices quota)

As section 5 of the system specification requires, the 156 test cases are split into 5 disjoint slices:

| Primary slice (`primary_slice`) | Quota | Actual count | What it tests |
|---|---|---|---|
| **`supported`** | 60 | 60 | The 12 core product intents (5 cases per intent): classification and the start of the suggestion flow. Only `human_agent` must be escalated (`must_escalate=True`). |
| **`unsupported`** | 34 | 34 | 34 detailed out-of-scope intents (1 case per intent): Gate 5 routes to the right specialist queue and generates no indiscriminate draft. |
| **`answerable`** | 24 | 24 | Policy questions with valid supporting documents in `data/knowledge/approved_kb.v1.json` (return, refund, and cancellation policies): Recall@3 and drafts grounded in the right evidence. |
| **`unanswerable`** | 18 | 18 | Questions without policy evidence (not covered by the KB, expired documents, unapproved or revoked documents, ACL access limits, conflicting policies): safety (fail-closed) and no fabricated draft. |
| **`uncertainty_and_faults`** | 20 | 20 | Robustness and controlled error handling: heavily misspelled questions, ambiguous multi-intent questions, out-of-domain questions (OOD null intent), prompt injection attacks, simulated timeouts and failures of the ML model, the encoder, or the LLM, and order permission violations. |
| **Total** | **156** | **156** | **Matches the design quotas exactly (100%)** |

---

## 3. Integrity checks (integrity and checksums)

Every input file that `suite_manifest.json` references is checked strictly by its SHA-256 hash before and after a run:

- If a file is changed or missing during an evaluation cycle, the system refuses to produce the acceptance report and raises a provenance violation warning.
- A path that leaves the repository (`..` or a symlink outside it) is never used.

---

## 4. Default KB coverage (KB coverage note)

- The approved knowledge base `data/knowledge/approved_kb.v1.json` currently holds only 3 officially approved core policies (Return Policy, Refund Policy, Cancellation Policy).
- The default KB **has not been shown to cover every one of the 12 product intents**.
- The system reports `kb_coverage_gap` explicitly and never invents gold document IDs for intents that have no validly approved evidence document.

---

## 5. Paths in the manifest

`suite_manifest.json` is not edited, so its paths, and the paths in this README, are the paths on `main` before the join ([ADR-0017, Large files and data](../../../../docs/decisions/0017-repository-layout-and-ai-ml-migration.md#large-files-and-data), statement 4). Each pinned SHA-256 is the uppercase hash of the raw bytes, CRLF line ends included, and still matches the file at its current path:

| Path in the manifest | Current path |
|---|---|
| `cases.jsonl` | `eval/suites/system/v1/cases.jsonl` |
| `coverage_matrix.csv` | `eval/suites/system/v1/coverage_matrix.csv` |
| `data/knowledge/approved_kb.v1.json` | `eval/suites/system/inputs/approved_kb.v1.json` |
| `data/knowledge/mock_orders.json` | `eval/suites/system/inputs/mock_orders.json` |
| `apps/core_backend/config/policies/intent_policy.v2.json` | `eval/suites/system/inputs/intent_policy.v2.json` |
