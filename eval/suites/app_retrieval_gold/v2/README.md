# Application retrieval gold cases (v2)

The retrieval cases that `main` used to measure the retrieval of the application against KB v2. Everything below comes from `app_retrieval_gold_manifest.json` or was checked during the join.

## What the manifest records

- **Benchmark ID**: `supportiq-app-retrieval-gold-v2`, version `2.1.0`, created `2026-11-12T11:40:00Z`, target release `current-policies-v1`.
- **Status**: `approved`, given by an AI coordinator under delegated authority for local retrieval evaluation only. The manifest records no other approval.
- **Cases**: 46 in `app_retrieval_gold_v2.json`, 33 answerable and 13 unanswerable:

| Slice | Cases |
|---|---|
| `supported_12_product_answerable` | 31 |
| `optional_out_of_product` | 2 |
| `human_agent_escalation` | 3 |
| `expired_temporal_rejection` | 3 |
| `conflicting_policies` | 2 |
| `out_of_domain` | 5 |

## Frozen files

The files keep every byte. They are not edited after results have been seen ([DATA-23](../../../../docs/rules/data-and-ml.md#splits-and-evaluation-protocol)), and they never enter training, tuning, or prompts ([DATA-25](../../../../docs/rules/data-and-ml.md#leakage)).

## Paths in the manifest

`app_retrieval_gold_manifest.json` is not edited, so its paths are the paths on `main` before the join ([ADR-0021, Large files and data](../../../../docs/decisions/0021-repository-layout-and-ai-ml-migration.md#large-files-and-data), statement 4).

| Path in the manifest | Current path |
|---|---|
| `data/benchmarks/app_retrieval_gold_v2.json` | `eval/suites/app_retrieval_gold/v2/app_retrieval_gold_v2.json` |
| `data/knowledge/approved_kb.v2.json` | `data/raw/kb/v2/approved_kb.v2.json` |
| `apps/ai_service/kb-release.json` | `data/raw/kb/v2/kb-release.json` |

## Pinned hashes

Each pinned SHA-256 is a lowercase hash of raw bytes.

- `sha256` matches `app_retrieval_gold_v2.json` at its current path.
- `provenance.kb_source_sha256` and `provenance.kb_release_sha256` are the hashes of the two KB files with every line end written as CRLF. The repository stores both files with LF line ends, the same bytes as on `main`, so their raw-byte hashes differ from these pins. Writing every LF as CRLF gives the pinned values.
