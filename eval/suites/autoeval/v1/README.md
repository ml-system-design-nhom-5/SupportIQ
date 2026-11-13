# autoeval v1 – fixed dataset

| File | Content | Source |
|---|---|---|
| `ml_noise.jsonl` | 84 supported or answerable sentences × (original, spoken style, 3 misspelled variants) = 420 sentences | generated from `data/benchmarks/system/v1/cases.jsonl`, seed 42 |
| `ml_oos.jsonl` | 80 out-of-scope, ambiguous, or multi-intent sentences, expected to be flagged or handed over for handling | written by hand |
| `llm_cases.jsonl` | 66 cases for the LLM: answerable, unanswerable, order lookup, prompt injection; with their source documents | generated from the benchmark and KB v2 |
| `manifest.json` | SHA-256 of the files above and of the benchmark, the KB, and the mock orders | `build-data` |

Do not edit `ml_noise.jsonl` or `llm_cases.jsonl` by hand. On `main`, after a change to `ml_oos.jsonl`, the benchmark, the KB, or the mock orders, `python -m pipeline.evaluation.autoeval build-data` rebuilt the data, and the manifest was committed with it.

## After the join

The autoeval and its `build-data` command do not run after the join, because the autoeval suites import modules that the join deleted ([ADR-0017, CI](../../../../docs/decisions/0017-repository-layout-and-ai-ml-migration.md#ci), statement 6). How the autoeval worked on `main` is described in `eval/README.md`.

## Paths in the manifest

`manifest.json` is not edited, so its paths, and the paths in this README, are the paths on `main` before the join ([ADR-0017, Large files and data](../../../../docs/decisions/0017-repository-layout-and-ai-ml-migration.md#large-files-and-data), statement 4). Its SHA-256 values are lowercase hashes of the content with CRLF line ends replaced by LF (`sha256_text_file` in `eval/src/supportiq_eval/autoeval/datasets.py`), so they differ from the raw-byte hashes of the system suites. Each still matches the file at its current path:

| Path in the manifest | Current path |
|---|---|
| `data/benchmarks/system/v1/cases.jsonl` | `eval/suites/system/v1/cases.jsonl` |
| `data/knowledge/approved_kb.v2.json` | `data/raw/kb/v2/approved_kb.v2.json` |
| `data/knowledge/mock_orders.json` | `eval/suites/system/inputs/mock_orders.json` |
| `data/benchmarks/autoeval/v1/ml_noise.jsonl` | `eval/suites/autoeval/v1/ml_noise.jsonl` |
| `data/benchmarks/autoeval/v1/ml_oos.jsonl` | `eval/suites/autoeval/v1/ml_oos.jsonl` |
| `data/benchmarks/autoeval/v1/llm_cases.jsonl` | `eval/suites/autoeval/v1/llm_cases.jsonl` |
