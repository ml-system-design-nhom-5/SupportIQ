# Intent data written to product semantics

All files here are **`synthetic-dev-only`** ([DATA-03](../../docs/rules/data-and-ml.md#sources-and-acceptable-use)):
never policy, never reported as test results. Checksums and row counts are in [`manifest.json`](manifest.json).

| Path | Role | Rows |
|---|---|---|
| `train_supplement/v1/rows.synthetic-dev-only.psv` | Extra **training** rows labelled to [the label definitions](../../docs/design/intent-label-definitions.md) | 500 |
| `oos_train/v1/rows.synthetic-dev-only.psv` | Out-of-domain texts for **outlier exposure** (trained towards a uniform distribution, no 47th label) | 94 |
| `dev/v1/cases.synthetic-dev-only.psv` | **Validation**: temperature calibration and τ/δ tuning ([DATA-34](../../docs/rules/data-and-ml.md#models-and-artifacts), DATA-58) | 181 |
| `dev/v1/oos.synthetic-dev-only.psv` | **Validation**: out-of-domain low-confidence rate | 39 |
| `dev_multi/v1/cases.synthetic-dev-only.psv` | **Validation**: tuning of the multi-request routing gate ([design](../../docs/design/multi-request-detection.md)); 40 `multi` messages and 40 `single` requests that contain a conjunction or two sentences | 80 |
| `train_supplement/v2/rows.synthetic-dev-only.psv` | **Training** for v1.2.0 rounds 1–4: v1 plus 168 rows for unsupported intents confused with draftable ones ([design](../../docs/design/intent-model-v1.2.md)) | 668 |
| `train_supplement/v3/rows.synthetic-dev-only.psv` | **Training** for v1.2.0 round 5: v2 plus 48 rows for patterns found in dev errors | 716 |
| `dev_independent/v1/cases.synthetic-dev-only.jsonl` | **Validation** for v1.2.0, written by an independent agent session (see its `AUTHORING.md`); 55 rows near benchmarks or training rows removed | 242 |

Format: pipe-separated, header `intent|text` (`category|text` for the out-of-domain files, categories `general`,
`other_domain`, `ecommerce_not_in_taxonomy`, `vague`; `kind|text` for `dev_multi`, kinds `multi` and `single`).
`dev_multi` was written on 2026-11-13 with AI assistance and without reading `data/benchmarks/intent/v1`.

`dev_escalation/v1/cases.synthetic-dev-only.psv` (header `intent|text`, 52 rows) is **validation only** for the
[return-channel guard](../../docs/design/return-channel-guard.md): `product_issue` and channel returns (D2) next to
the supported intents they are confused with. It was written on 2026-11-13 with AI assistance for the intents named
by two failed gate case IDs, without reading their texts (DATA-28). Two near-duplicate rows were removed. IDs are assigned by line order, so edit by appending or by
bumping the version directory, and regenerate the manifest with
`python -m pipeline.preparation.intent_extra --write-manifest`.

- Order and tracking references use normalized placeholders (`[ORDER_ID]`, `[TRACKING_ID]`), the form the
  classifier sees in service ([DATA-59](../../docs/rules/data-and-ml.md#models-and-artifacts)). The loader rejects raw
  identifiers.
- The rows were authored with AI assistance on 2026-11-06, after failure cases of `data/benchmarks/system/v1` and
  `data/benchmarks/autoeval/v1` had been read. Those sets are therefore diagnostics only
  ([ADR-0016](../../docs/decisions/0016-frozen-intent-scenario-set.md)).
- 23 rows that were near-duplicates of the frozen set `data/benchmarks/intent/v1` were removed, not rewritten, so the
  frozen set did not shape any remaining row (DATA-24, DATA-25). On 2026-11-13, 7 more rows (6 training, 1
  out-of-domain training) were removed as near-duplicates of `data/benchmarks/intent/v2`; the candidate `v1.1.0` was
  trained before that and still contains them.
- `python -m pipeline.preparation.intent_extra` validates the files, verifies the manifest, and fails on any
  near-duplicate (token Jaccard ≥ 0.7) with `data/benchmarks/` or between files; it prints only the location of a
  benchmark hit, never its text. `tests/unit/test_intent_extra.py` enforces the same.
