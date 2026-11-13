# Draft coverage and provider reliability implementation plan

Authority: coordinator decisions under the user's explicit stakeholder delegation and request for three Orca workers. Base: main 5a777bb. This is a local implementation and evaluation round, not approval to deploy a candidate.

Goal: increase useful draft coverage while preserving strict routing, source grounding, privacy, manual approval and the twelve-second application latency requirement.

Design: improve the classifier using independently authored, policy-derived domain data plus verified original 46-label training data; preserve the serving model until independent checks pass. Separately improve transient-provider handling within the existing ten-second allocated budget and five-second attempt cap. Measure classifier draft eligibility, actual provider completion and supported generated content separately.

Alternatives: promoting the existing supportpilot checkpoint is rejected because it introduced routing leaks. Lowering thresholds or raising timeouts without evidence is rejected. A new staged candidate and targeted transport fixes allow independent rejection of either change.

Global constraints: frozen gold/KB unchanged; no gold questions as training/paraphrase seeds; no invented human study, fresh CV or provider success. No dependency/provider/model/tier changes, secrets in artifacts, root service restart or external provider calls by workers. The previous live-call allowance is exhausted. Coordinator will separately record any subsequent live verification budget before execution; offline success alone cannot establish provider availability.

## A — Stage an improved trained classifier

Own pipeline/training additions, new domain-data generator and candidate outputs; no provider or runtime-engine changes.

- [ ] Merge main, inventory verified original training data and available compute, retain weight/data hashes and full 46-label mappings.
- [ ] Create independently authored domain templates from approved policy terminology, never benchmark prompts. Generate distinct train/calibration/evaluation template groups before paraphrasing; record leakage/similarity checks without tuning on acceptance outcomes. Retain 34-label replay and evaluate all 46 labels.
- [ ] Implement a reproducible, bounded candidate-training experiment using existing dependencies and verified data. Prefer a small established classifier or limited fine-tuning supported by existing pipeline; cap one training attempt at 30 minutes, record budget and failures. Do not invent missing data or download dependencies. Missing required lineage/data is a concrete blocker to report, not permission to use gold.
- [ ] Test split isolation, label retention and artifact identity; execute candidate comparison against serving on independent held-out data, noise/OOD, and frozen acceptance as a known regression suite. Separate correct-intent coverage from raw draft eligibility, strict mandatory-action matches and uninjected faults.
- [ ] Deliver actual candidate weights/provenance or precise blocker, raw results and measured recommendation. Never overwrite serving weights or lower thresholds. No external LLM calls.

## B — Improve bounded provider recovery

Own apps/ai_service/drafting.py, transport portions of apps/core_backend/llm/gemini.py and focused retry tests. Preserve the integrated hotline/provenance fix.

- [ ] Merge main and reproduce current failure behavior with controlled HTTP transport and clocks. Review current official provider/httpx documentation if API behavior is needed; distinguish documented guarantees from observed behavior.
- [ ] Add failing tests for transient 503 then success, permanent failure, Retry-After beyond remaining budget, timeouts, exhausted budget and per-attempt usage completeness. Inspect production caller lifecycle and HTTP connection reuse.
- [ ] Implement only evidence-supported recovery improvements: bounded backoff/Retry-After handling if appropriate, exact retryable classifications, stable connection reuse and deadline-aware request allocation. Retain default five-second attempt cap, ten-second budget, no automatic financial actions and explicit safe fallback. Do not claim blocking transport hard cancellation unless actually implemented and tested without orphaned work.
- [ ] Run relevant accounting/privacy/grounding/retry checks; report controlled completion rate and latency including every failure. No live provider calls and no serving model/provider changes.

## C — Independent evaluation and integration gate

Own additive evaluation helpers/tests/artifacts and this round's evidence documentation; do not edit A training or B runtime files.

- [ ] Merge main; freeze source/version/hash identities and independently recompute current draft eligibility, correct-intent eligibility, strict mandatory actions and abstention denominators from raw artifacts.
- [ ] Build a controlled before/after provider resilience evaluation using realistic 503/timeouts/success schedules. Persist every attempt, no-response usage, total latency, fallback and no-auto-send; use same schedules for both versions. Obtain B's candidate commit when ready rather than modifying B's code.
- [ ] Prepare candidate classifier comparison gate consuming A's actual artifact identity. Reject missing lineage, train/calibration/eval template overlap, 34-label regression or new unsafe draft eligibility; never label a known acceptance regression set a new independent holdout.
- [ ] Add meaningful metric/harness regression tests. Deliver reproducible artifacts and unresolved gaps; do not claim live LLM reliability from controlled transports.

## Coordinator gate

Review independently and integrate selectively. Run focused integration tests and build as appropriate. Strict mandatory-action compliance, correct supported answers and latency with failures included take precedence over draft count. Live provider acceptance, if run, requires a separately recorded bounded request budget and actual per-attempt reconciliation. No full acceptance claim from mock or training results alone.
