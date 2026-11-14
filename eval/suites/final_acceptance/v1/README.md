# Final acceptance cases (v1)

The final acceptance cases of `main`, with paired agent tasks and injected robustness fixtures. Everything below comes from `suite_manifest.json` or was checked during the join.

## What the manifest records

- **Benchmark ID**: `supportiq-final-acceptance-24`, version `1.1.0`, created `2026-11-12T13:20:00Z`.
- **Status**: `approved_by_coordinator_for_local_evaluation`. The approval authority is `delegated_ai_stakeholder_coordinator`, and the approval scope is local evaluation only, with no instructor or cross-group approval.
- **Cases**: 24 in `cases.jsonl`. Under `fixture_boundaries`, 20 are active-KB cases and 4 are injected synthetic cases, whose fixture documents are in `injected_robustness_fixtures.json`:

| Slice | Cases |
|---|---|
| `product_12_answerable` | 12 |
| `sensitive_escalation` | 2 |
| `human_agent_escalation` | 1 |
| `unsupported_no_source` | 2 |
| `out_of_domain` | 3 |
| `expired_injected_boundary` | 2 |
| `conflict_injected_boundary` | 2 |

- **Paired agent tasks**: `paired_agent_tasks.json`.

## Frozen files

The files keep every byte, CRLF line ends included. They are not edited after results have been seen ([DATA-23](../../../../docs/rules/data-and-ml.md#splits-and-evaluation-protocol)), and they never enter training, tuning, or prompts ([DATA-25](../../../../docs/rules/data-and-ml.md#leakage)).

## Paths in the manifest

`suite_manifest.json` is not edited, so its paths are the paths on `main` before the join ([ADR-0021, Large files and data](../../../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#large-files-and-data), statement 4).

| Path in the manifest | Current path |
|---|---|
| `data/benchmarks/final_acceptance/cases.jsonl` | `eval/suites/final_acceptance/v1/cases.jsonl` |
| `data/benchmarks/final_acceptance/paired_agent_tasks.json` | `eval/suites/final_acceptance/v1/paired_agent_tasks.json` |
| `data/benchmarks/final_acceptance/injected_robustness_fixtures.json` | `eval/suites/final_acceptance/v1/injected_robustness_fixtures.json` |
| `data/knowledge/approved_kb.v2.json` | `data/raw/kb/v2/approved_kb.v2.json` |
| `apps/ai_service/kb-release.json` | `data/raw/kb/v2/kb-release.json` |

## Pinned hashes

Each pinned SHA-256 is a lowercase hash of raw bytes.

- `provenance.cases_sha256`, `provenance.paired_tasks_sha256`, and `provenance.injected_fixtures_sha256` match the files at their current paths. `injected_robustness_fixtures.json` has CRLF line ends.
- Under `provenance.kb_reconciliation`, the two `deployed_root_serving_gateway` hashes are the hashes of the KB files with every line end written as CRLF. The two `worker_local_worktree` hashes match the KB files as the repository stores them, with LF line ends, the same bytes as on `main`.
- The join did not check `combined_kb_version_hash`.
