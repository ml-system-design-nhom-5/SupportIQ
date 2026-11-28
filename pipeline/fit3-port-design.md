# Design for the Fit3 pipeline port

- **Status:** Draft
- **Reviewers:** ML pipeline and evaluation component owners
- **Related:** [NFR-01 and NFR-02](../docs/product/requirements.md), [WF-01 and WF-02](../docs/rules/workflow.md)

## Summary

Port Fit3 training and offline evaluation from the legacy layout to main's
pipeline. Keep all repository changes inside the pipeline directory. Use the
published Fit3 v19 bundle as the reference for checking the port.

## Design

- Reuse the pipeline preparation and Transformer evaluation modules. Load
  the verified local bundle through the existing Transformer adapter.
- Keep the shared Wave 31 and 32 encoder trainer in the training layer.
  Preserve each wave's preset, sampling, loss, seed and calibration semantics.
  Make frozen inputs explicit, including model bundles and the train, dev and
  calibration cache. Replace inherited helpers with pipeline-owned functions
  only where the main pipeline lacks equivalents.
- Evaluate classifier quality with the existing pipeline metrics on the same
  frozen cases. Run routing, retrieval or drafting comparisons only through
  existing evaluation contracts. Report unavailable evidence explicitly.
- Preserve all existing main entry points, schemas and model selection.
  The published checkpoint remains experimental pending independent validation.

## Failure handling

| Condition | Behavior | Verification |
| --- | --- | --- |
| Missing or mismatched artifact | Fail before inference or training | Missing bundle and tamper tests |
| Invalid split, labels or incomplete case alignment | Fail before emitting aggregate metrics | Split and paired-ID tests |
| Service evaluation unavailable | Report classifier results and identify the unavailable comparison | Offline evaluation test |

## Acceptance criteria

1. Every implementation PR changes files only under the pipeline directory.
   The port runs offline without importing the removed apps package.
2. Verify release bundle hashes and 46 labels. Replay v19 on the original
   written benchmark and compare predictions, Macro-F1 and accuracy. Report
   any difference and identify the dataset and artifact hashes.
3. Rerun the Wave 31 and 32 presets with the original verified inputs. Compare
   weights, logits, development and calibration results against v19 to v21.
   Explicitly report any missing inputs and any differences.
4. Run the existing main pipeline tests and add pipeline-local regression
   tests for the new entry points.

## Alternatives and rollout

Copying the legacy tree would restore imports from the removed apps package.
Publishing only the frozen bundle gives inference access without training
reproducibility. Review this design first, then land artifact and evaluation
support and the shared training port in separate scoped pull requests.
