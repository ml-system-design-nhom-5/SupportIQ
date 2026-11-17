# Intent scenario set (v2)

The second frozen intent scenario set, which `main` added on 2026-11-13 in the revision of [ADR-0026](../../../../docs/decisions/0026-frozen-intent-scenario-set.md). Everything below comes from `manifest.json`, `AUTHORING.md`, and ADR-0026, or was checked during the update of the join with `main` on 2026-11-17.

## What the manifest records

- **Version**: `intent-v2`, seed 42, written by a new independent author (`AUTHORING.md`).
- **Files and rows**: `raw_cases.jsonl` 236, `cases.jsonl` 164, `ml_oos.jsonl` 72, `ml_noise.jsonl` 480.
- **Use on `main`**: the release `v1.0.0` with policy `v2` and the candidate `v1.1.0` with policy `v3` were each evaluated on it once (ADR-0026, Revision 2026-11-13), and the candidate `v1.2.0` with policy `v4` after that ([intent model v1.2](../../../../docs/design/intent-model-v1.2.md)). The gate on this set keeps a threshold of 0 for must-not-draft cases forwarded to drafting ([intent evaluation protocol, Unsafe drafts](../../../../docs/design/intent-evaluation-protocol.md#unsafe-drafts-the-gate-stays-at-0)).

No code of this repository reads this set yet: the ML suite of the autoeval that read it was not kept ([eval README, State after the join](../../../README.md#state-after-the-join)).

## Frozen files

The files keep every byte. They are not edited after results have been seen ([DATA-23](../../../../docs/rules/data-and-ml.md#splits-and-evaluation-protocol)), and they never enter training, tuning, or prompts ([DATA-25](../../../../docs/rules/data-and-ml.md#leakage)).

## Paths in the manifest

`manifest.json` is not edited, so it names the ADR by its number and path on `main`.

| Path in the manifest or `AUTHORING.md` | Current path |
|---|---|
| `docs/decisions/0016-frozen-intent-scenario-set.md` | `docs/decisions/0026-frozen-intent-scenario-set.md` |
| `data/benchmarks/intent/v2/` | `eval/suites/intent/v2/` |

## Pinned hashes

Each pinned SHA-256 is a lowercase hash of raw bytes. On 2026-11-17 all five files matched their pins, and the four data files matched their row counts.
