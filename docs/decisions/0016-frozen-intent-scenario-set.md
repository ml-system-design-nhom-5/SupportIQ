# ADR-0016: Frozen intent scenario set written independently of training

- **Status:** Proposed
- **Date:** 2026-11-12
- **Deciders:** team
- **Related:** NFR-01, NFR-02, FR-05; [DATA-23](../rules/data-and-ml.md#splits-and-evaluation-protocol), [DATA-25, DATA-28](../rules/data-and-ml.md#leakage), [DATA-57](../rules/data-and-ml.md#models-and-artifacts); [intent evaluation protocol](../design/intent-evaluation-protocol.md); [intent model retraining](../design/intent-model-retraining.md); [intent label definitions](../design/intent-label-definitions.md)

## Context

The offline gate for the intent classifier runs on `data/benchmarks/system/v1/cases.jsonl` (156 messages) and on `data/benchmarks/autoeval/v1/ml_oos.jsonl` and `ml_noise.jsonl`. On 2026-11-06, about 50 failure cases from these sets were read while training data and label definitions for the [intent model retraining](../design/intent-model-retraining.md) were being written. No text was copied, but the label boundaries and the topics of the out-of-domain training texts were chosen after seeing test results. DATA-25 and DATA-28 forbid that use, so these sets can no longer show whether a retrained model generalizes.

DATA-23 allows a test set to change only through an ADR, and the change invalidates earlier results. Several documents already reference a `data/benchmarks/system/v3`, which was never committed; reusing that name would confuse readers.

## Decision drivers

1. Correctness of the gate: test data must be unseen by whoever writes training data or tunes the model.
2. Traceability: the set, its author, and its provenance are recorded and checksummed.
3. Compatibility: the set runs in the existing autoeval ML suite without changing its metrics.
4. Cost: the set can be written and reviewed within one working day.

## Considered options

1. Keep `system/v1` and `autoeval/v1` as the gate sets.
2. A new set written by the same person who writes the training data.
3. A new set written by an author with no access to the training data, the failure analysis, or the earlier benchmarks.

## Decision

We will add a frozen intent scenario set at `data/benchmarks/intent/v1/`, written under these rules:

- The author has no access to `data/intent/`, `data/benchmarks/`, `artifacts/`, or the retraining discussion. The author reads only [requirements](../product/requirements.md), [the label definitions](../design/intent-label-definitions.md), and the 46-label list. For this version the author is a separate AI agent session started with only those documents; its instructions are stored next to the set as `AUTHORING.md`.
- The author writes messages and labels only. Routing context and expected outcomes are derived mechanically from each label by `pipeline/evaluation/autoeval/build_intent_set.py` with the rules already used in `system/v1` (supported intents may draft or clarify; `human_agent` and the 34 unsupported intents must escalate to the team in `INTENT_TO_QUEUE_MAP`).
- Composition: 8 messages for each of the 12 supported intents, 2 for each of the 34 unsupported intents, and 72 out-of-scope messages (general knowledge, other domains, e-commerce topics outside the taxonomy, vague, and multi-intent). Order references use the pseudonymized placeholder `[ORDER_ID_1]`.
- Noisy variants are generated from the set by the existing deterministic transformations, never by hand.
- The set and its manifest (file checksums, author, date, row counts) are committed before any candidate is evaluated on it. After that it is never edited (DATA-23).
- Nobody who writes training data or tunes thresholds reads the set item by item. Reports show aggregate metrics and the identifiers of failed cases.
- `system/v1` and `autoeval/v1` stay in the repository as development diagnostics and are no longer used for gate decisions or reported results.

## Consequences

### Positive

- Gate results for the retrained model are evidence of generalization, not of tuning to known failures.
- The set runs in autoeval with the same metric code as before.

### Negative

- Results on `system/v1` reported before this ADR are not comparable to results on the new set.
- An AI-written set may share phrasing habits with AI-written training data. Leakage checks against the training files reduce but do not remove this risk.

### Follow-ups

- Add a near-duplicate check between the new set and every training file to the run (DATA-24).
- Have a team member review the label of each message before the set is frozen, without seeing any model output.
- Point the autoeval ML suite at the new set and record the current release's result as the baseline.

## Pros and cons of the options

### Keep `system/v1` and `autoeval/v1`

- Good, because nothing changes and earlier results stay comparable.
- Bad, because their failure cases shaped the training data, which DATA-28 forbids.

### A new set written by the training-data author

- Good, because it is fast.
- Bad, because the author knows the training data and the earlier failures, so the set is not independent.

### A new set written by an author without access to training data

- Good, because the gate measures generalization and satisfies DATA-25 and DATA-28.
- Bad, because it needs a separate author and a label review.

## Validation

- The manifest checksums match at every gate run; a mismatch stops the run.
- The leakage check reports zero near-duplicates (token Jaccard ≥ 0.7) between the set and any training file.
- Revisit when the set has been used for more than three release decisions, or when a gate result is disputed.

## Revision 2026-11-13: `intent/v2`

`intent/v1` supported three decisions about the candidate `v1.1.0` on 2026-11-12 and 2026-11-13: the retraining gate, the [multi-request gate](../design/multi-request-detection.md), and the [return-channel guard](../design/return-channel-guard.md). Each later round was steered by the earlier result: first the failing multi-intent slice, then the case IDs of two unsafe drafts. `intent/v1` is therefore no longer independent of the routing work. From this revision it is a development diagnostic, like `system/v1`.

A second set, `data/benchmarks/intent/v2/`, follows the same rules and composition as v1. It was written by a new independent AI agent session that read only the requirements and the label definitions; its instructions are in `AUTHORING.md` next to it. It is built by `build_intent_set.py --set-dir data/benchmarks/intent/v2` and frozen by its manifest before any model is evaluated on it. The ML suite reads it through `ml.benchmark` and `ml.sets_dir`. The release `v1.0.0` with policy `v2` and the candidate `v1.1.0` with policy `v3` are each evaluated on it once.

The revisit rule applies to `intent/v2` from zero. The label review by a team member is still open for both sets.

### Results on `intent/v2` (2026-11-13)

The set was built and frozen (`manifest.json`) before either model was evaluated. The near-duplicate check found 7 of its 236 items (3%) close to rows of the extra training data that `v1.1.0` was trained on (6 `train_supplement`, 1 `oos_train`; token Jaccard ≥ 0.7). The set was not changed. The 7 training rows were removed for future training, and the results below also show the labelled metrics without those items (DATA-24). For exact matches, the check prints the training row, which then equals the test item. One reader therefore saw up to 7 items, all now excluded from training.

One ML run each, torch backend (`artifacts/evaluation/autoeval/20261113-004535-intent-v2-baseline-v1.0.0-policy-v2/` and `20261113-004602-intent-v2-candidate-v1.1.0-policy-v3/`; the candidate used the evaluation-only approved copy of policy `v3`):

| Metric | `v1.0.0` + `v2` (release) | `v1.1.0` + `v3` (candidate) | Target |
|---|---|---|---|
| Supported vs not supported decided correctly | 0.860 | 0.957 | ≥ 0.90 |
| Macro-F1, labelled messages | 0.507 | 0.742 (0.729 without the 7 items) | ≥ 0.75 |
| Supported-intent accuracy | 0.615 | 0.917 | ≥ 0.85 (warning) |
| Macro-F1 drop on noisy text | 0.085 | 0.061 | ≤ 0.10 |
| Out-of-scope, vague, multi-intent flagged | 0.917 | 0.958 | ≥ 0.90 |
| Multi-intent slice flagged | 0.733 | 0.867 | — |
| Must-not-draft cases drafted | 2 | **3** | 0 |
| Confident errors (≥ 0.8) | 10 | 8 | ≤ 5 |
| Expected calibration error | 0.088 | 0.076 | ≤ 0.08 |
| Clarify rate on draftable messages | 0.443 | 0.125 | ≤ 0.15 |
| Draftable messages reaching a draft | 0.432 | 0.875 | — |
| Drafts with a wrong intent | 12 | 7 | — |
| Single-request messages flagged as `multiple_requests` | 0 | 0 | — |

Unsafe drafts: release `unsupported-return_product_in_store-01`, `-02`; candidate `unsupported-missing_item-02`, `unsupported-submit_product_idea-02`, `unsupported-return_product_online-01`. The candidate's three were not near-duplicate items.

**Verdict: the candidate fails the gate** (rules 1 and 2: three must-not-draft cases drafted, one more than the release). It also misses the Macro-F1 and confident-error targets. It is better than the release on every other metric. `v1.0.0` stays in service. This is the first decision based on `intent/v2`. No routing or model change may be tuned on these results (DATA-25); the next step has to come from development data.
