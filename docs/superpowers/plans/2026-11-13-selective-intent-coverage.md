# Selective intent coverage follow-up

Authority: user requests further improvement; prior delegation of stakeholder decisions and three Orca workers remains active. Base main ff3474e. Serving weights and policy thresholds remain unchanged until independent acceptance.

Problem: first domain candidate improves correct-intent draft eligibility but creates unsafe OOD routes. Uniform-KL follow-up reduces those leaks while reducing correct-intent coverage on the 34-case suite below baseline. Known frozen suites have already been inspected and are regression checks, not unbiased holdouts.

Design decision: separate intent recognition from selective rejection instead of repeatedly flattening every supported-intent prediction. Compare at most two predeclared offline candidates, using calibration data only for selection. Preserve original 46-label data replay. A writes experiment/model artifacts, B verifies runtime calibration semantics, C independently tests the candidate gate. No live requests in this round: prior authorized 8/8 budget is exhausted.

## A — Selective candidate experiment

- [ ] Merge main while preserving previous experiments. Verify original data and all previous artifact hashes.
- [ ] Before training, record two alternatives and selection objective: calibrated intent plus separately learned in-scope/rejection head, versus selective distillation/regularization preserving positive confidence. Choose the smallest option supported by calibration; do not add case-specific routing rules.
- [ ] Author new diverse positive/ambiguous/unsupported template families from taxonomy and policy, without benchmark seeds. Split by template family before generation; train/calibration/new evaluation groups disjoint. Prior experimental holdouts are now development data, never label them fresh independent evidence. Audit duplicates and semantic-family overlap; token similarity alone is insufficient proof.
- [ ] Run at most two bounded fits, total training cap 30 minutes, existing dependencies and GPU only. Preserve 46-label replay and original 34-intent holdout. Select using calibration only, lock candidate before frozen regression evaluation. Keep raw calibrated probabilities and rejection decision separate in artifacts; no invented accuracy from abstentions.
- [ ] Deliver actual weights, tokenizer/config hashes, temperature/rejector parameters and split/data provenance. Evaluate correct-intent draft eligibility, strict action contracts, fault cases, OOD and unanswerable leaks; no serving promotion without independent review. No gold-conditioned keyword rules or changes to thresholds/KB/provider.

## B — Runtime and evaluator score consistency

- [ ] Merge main. Inspect ModelContainer in apps/ml_inference/app.py and A's experiment adapters before edits. Compare their tokenization, label mapping, temperature, score_kind, confidence/margin and verification metadata.
- [ ] Reproduce any concrete offline/runtime discrepancy with controlled logits and a tiny local model fixture; add regression tests first. Fix only demonstrated discrepancies without changing default serving predictions. Preserve historical manifests and approved weights.
- [ ] If optional calibration metadata support is needed, agree the precise minimal interface with A first: explicit verified artifact identity, finite positive temperature, 46-label bijection, raw vs calibrated score provenance and fail-closed behavior for missing/conflicting hashes or incompatible schema. No silent application of experiment-only rejectors to serving.
- [ ] Verify default serving prediction parity and safe handling of unsupported/rejected candidates. Deliver focused code/tests if a real gap exists, or a precise no-change finding. No new model architecture, provider/runtime retry edits or serving asset swaps.

## C — Independent acceptance and evidence

- [ ] Merge main. Freeze baseline and previously rejected candidate results without reinterpreting known regression as new holdout.
- [ ] Review A's data lineage, template-family isolation and calibration-only selection before evaluating a new artifact. Coordinate directly with A/B and report blockers promptly.
- [ ] Gate actual candidate identity using raw and calibrated/runtime score paths, strict mandatory actions, source mismatch, 34-label retention and OOD/unanswerable cases. Explicitly separate uninjected fault fixtures from real leaks; neither counts as passing fault coverage.
- [ ] Independently recompute correct-intent draft-eligible denominators, precision among eligible cases and abstention coverage. Run controlled tests for any gate changes and retain raw outputs and rejected candidates. No full-system or human productivity claim from offline improvement.

## Integration gate

Coordinator reviews source and independent checks, integrates reversible verified changes, and promotes no model that adds unsafe OOD/unanswerable drafts or loses coverage while claiming improvement. Lowering safety thresholds, editing gold, extending the expired provider budget and per-case benchmark patches are prohibited. No root service restart until a reviewed runtime change is ready for explicit local verification.
