# Final acceptance supplement (v1)

Eleven cases of the system v2 acceptance cases, kept on `main` as a diagnostic regression set for unanswerable questions. Everything below comes from `manifest.json` or was checked during the join.

## What the manifest records

- **Benchmark ID**: `supportiq-downstream-unanswerable-regression-11`, version `1.0.0`, created `2026-11-12T13:56:38.789962+00:00`.
- **Status**: `approved_by_coordinator_for_local_evaluation`. The approval authority is `delegated_ai_stakeholder_coordinator`, and the approval scope is local diagnostic regression evaluation only, with no instructor, human participant, or cross-group approval.
- **Selection**: the eleven cases that reached a draft recommendation in one model run on `main`. The manifest calls this a diagnostic selection after component inference, not an independent held-out test.
- **Execution status**: `not_executed_pending_integrated_gateway_reload`.
- **Cases**: 11 in `cases.jsonl`. The join checked that their IDs are the `case_ids` of the manifest, in the same order, and that each case equals the case with the same ID in `eval/suites/system/v2/acceptance/cases.jsonl`.

## Frozen files

The files keep every byte. They are not edited after results have been seen ([DATA-23](../../../../docs/rules/data-and-ml.md#splits-and-evaluation-protocol)), and they never enter training, tuning, or prompts ([DATA-25](../../../../docs/rules/data-and-ml.md#leakage)).

## Paths in the manifest

`manifest.json` is not edited, so its paths are the paths on `main` before the join ([ADR-0021, Large files and data](../../../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#large-files-and-data), statement 4).

| Path in the manifest | Current path |
|---|---|
| None: `cases_sha256` pins the case file | `eval/suites/final_acceptance_supplement/v1/cases.jsonl` |
| `data/benchmarks/system/v2/acceptance/cases.jsonl` | `eval/suites/system/v2/acceptance/cases.jsonl` |
| `artifacts/evaluation/final-routing-20261112-v3/raw_predictions.jsonl` | Not in the tree, because the join does not keep `artifacts/` ([ADR-0021, Large files and data](../../../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#large-files-and-data), statement 2). It stays in the history: `git show 19ece5d:artifacts/evaluation/final-routing-20261112-v3/raw_predictions.jsonl` |

## Pinned hashes

Each pinned SHA-256 is a lowercase hash of raw bytes.

- `cases_sha256` matches `cases.jsonl` at its current path.
- `original_suite_sha256` matches `eval/suites/system/v2/acceptance/cases.jsonl`, which has CRLF line ends.
- `selection_evidence_sha256` matches the selection evidence in the history at `19ece5d`.
