# Independent safety checks after negative CLS experiment

Base: root `a1c70e9`. Topic specification and previous closure plan remain in
force. User delegated stakeholder decisions and requested three Orca workers.
The centroid/density experiment at A `5244c34` is negative: do not implement
selective_calibration.v2 from those results or promote c6cae7a.

## A: independent lexical evidence (offline feasibility only)

- Reuse existing traditional-model/feature code. Locate and verify old trusted
  bundles first; if absent, label any refit as a new experiment, not original assets.
- Predeclare at most two base CPU fits (linear SVM and logistic regression), with
  all calibration and analysis within20 minutes. No transformer fits or live calls.
- Use verified Bitext train-only rows and allowed domain train data, with held-out
  calibration rows excluded from feature fitting. Never train on frozen benchmark
  text, labels or fresh probe evaluation rows. SVM margins are not probabilities.
- Select a conservative independent-disagreement/veto recipe on calibration only;
  keep primary probabilities immutable. Compare standalone lexical predictions and
  consensus/veto behavior on serving and locked c6cae7a. Do not force a specific
  known failing case to pass or lower product thresholds.
- Lock recipe before reporting new family-disjoint probes and known regressions.
  All previously inspected holdouts are now development. Report eligibility
  precision/correct coverage,46/34-label quality, OOD/multi-intent leaks and strict
  actions under integrated B semantics. Require zero unsafe regression and coverage
  at least serving on comparable slices before proposing runtime work.
- Deliver raw predictions, exact lineage/hashes, reusable offline code/tests and
  minimal proposed integration contract if feasible. No production edits or swap.

## B: verify actual legacy HTTP pipeline safety

- Trace the12 mandatory and2 OOD intent-stage recommendations through the complete
  HTTP IntentClient -> decide_route -> PipelineRunner path, with actual pinned
  serving predictions, approved retrieval and synthetic commerce context.
- Use a no-network spy LLM to detect whether a prohibited path reaches generation;
  never declare a route safe merely because a stub refuses all requests.
- Separate initial route from terminal outcome, required source/authority checks
  and actual LLM eligibility. If downstream guards already resolve the apparent
  gaps, document that instead of changing behavior unnecessarily.
- If a real unsafe complete-pipeline path is reproduced, add a general regression
  and minimal shared guard, preserving supported coverage, overrides, authority,
  slots and approval. No case-specific regex, gold edits or threshold weakening.
- Own PipelineRunner and its focused tests/new diagnostic artifacts. Coordinate
  any Engine/routing change before editing it. No model training or provider calls.

## C: execute previously uninjected fault boundaries

- Independently execute ml_timeout, encoder_failure and commerce_unauthorized
  cases previously marked NOT_EXECUTED, using owned isolated synthetic runtime.
  Explicitly inject the error or exercise real unauthorized synthetic ownership;
  ordinary inference on a fault-labeled question is not fault injection.
- Preserve frozen expected actions and distinguish strict mismatch from safe
  fallback. Record HTTP outcome, reason, pending/sent state, authority checks and
  whether generation was attempted. Zero provider calls; guard allowance0.
- Own collectors/tests and new fault evidence only. No production changes; report
  concrete failure reproductions to B/coordinator. Capturing a negative result is
  successful completion of this diagnostic, not a claim of product correctness.
- Independently review A/B new evidence when available and report actual gaps.

The live allowance remains18/24 used and6 reserved globally; no worker in this
plan is authorized to consume those remaining calls. No secrets, raw historical
evidence rewrites, serving model swaps, user-data mutations or invented humans.
