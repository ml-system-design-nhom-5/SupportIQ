# Intent scenario set (v1)

The frozen intent scenario set that `main` added on 2026-11-12 under [ADR-0026](../../../../docs/decisions/0026-frozen-intent-scenario-set.md). Everything below comes from `manifest.json`, `AUTHORING.md`, and ADR-0026, or was checked during the update of the join with `main` on 2026-11-17.

## What the manifest records

- **Version**: `intent-v1`, seed 42, written by an independent author (`AUTHORING.md`).
- **Files and rows**: `raw_cases.jsonl` 236, `cases.jsonl` 164, `ml_oos.jsonl` 72, `ml_noise.jsonl` 480.
- **Status**: since the revision of 2026-11-13 of ADR-0026, `intent/v1` is a development diagnostic, because three decisions about the candidate `v1.1.0` were based on it. [`intent/v2`](../v2/README.md) took its place.

No code of this repository reads this set yet: the ML suite of the autoeval that read it was not kept ([eval README, State after the join](../../../README.md#state-after-the-join)).

## Frozen files

The files keep every byte. They are not edited after results have been seen ([DATA-23](../../../../docs/rules/data-and-ml.md#splits-and-evaluation-protocol)), and they never enter training, tuning, or prompts ([DATA-25](../../../../docs/rules/data-and-ml.md#leakage)).

## Paths in the manifest

`manifest.json` is not edited, so it names the ADR by its number and path on `main`.

| Path in the manifest or `AUTHORING.md` | Current path |
|---|---|
| `docs/decisions/0016-frozen-intent-scenario-set.md` | `docs/decisions/0026-frozen-intent-scenario-set.md` |
| `data/benchmarks/intent/v1/` | `eval/suites/intent/v1/` |

## Pinned hashes

Each pinned SHA-256 is a lowercase hash of raw bytes. On 2026-11-17 all five files matched their pins, and the four data files matched their row counts.
