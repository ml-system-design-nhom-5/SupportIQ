# Current integrated release: live acceptance checkpoint

The first live evaluation of integrated release `5968882` did **not** pass acceptance. Data and policies are synthetic; stakeholder decisions and claim review are performed by the coordinator AI under user delegation. This report does not imply independent instructor, other-group, or human-participant approval.

## Observed results

| Boundary | Observation | Result |
|---|---|---|
| 20 application tickets, real PostgreSQL worker and Gemini gateway | 20/20 terminal states and customer observations collected; 20/20 without automatic customer reply | No automatic send observed |
| Same 20 application tickets | p50 0.28970 s; p95 3.65561 s | Below 12-second target for this sample |
| 12 answerable product cases | 5 drafts; 7 abstentions caused by classifier uncertainty | Useful automatic draft coverage 41.7%; gold action expectations unmet |
| Three explicit escalation cases | Human-agent request escalated; unauthorized transaction drafted; policy exception abstained | 1/3 expected escalation actions correct |
| Four separate retrieval component fixtures | 2/2 expiry checks and 2/2 conflict checks; actual BGE encoder | Component evidence only |
| Six emitted drafts, AI semantic review | 17/20 propositions fully supported (85%); 4 approve, 1 edit, 1 reject | Below 90% support target |
| Eleven downstream insufficiency regressions | 9 drafts, 2 LLM-unavailable outcomes; 0 expected escalation actions | Failed; safe non-send is not correct escalation |
| Same eleven diagnostic regressions | p50 4.81643 s; p95 9.44450 s; 11/11 without automatic customer reply | Performance and oversight observations do not override action failures |

The application collector's `errors` field counts failed acceptance criteria, not exclusively technical failures. On the 20-case run, 10 cases failed at least one criterion, while all 20 were collected successfully. On the eleven-case run, two LLM failures reduced collection success to 9/11 and all eleven failed expected escalation. Unknown usage from provider timeouts remains unknown despite a later successful retry.

Artifacts:

- `artifacts/evaluation/coordinator-final-live-20261112/final-evidence-20261112-145003-c7d112/`: original collection, manifests, full drafts and source snapshots, plus additive `ai_claim_review.json`.
- `artifacts/evaluation/coordinator-downstream-live-20261112/final-evidence-20261112-145227-19be70/`: eleven-case diagnostic with explicit supplementary provenance. Cases were selected after offline failures, so this is a regression sample, not an independent holdout. The base collector manifest describes constructor configuration; `supplement_provenance.json` identifies the cases actually executed.

## Corrections and remaining work

All three workers' initial changes have been integrated. Worker B's final accounting correction is integrated as `3d01cea`; it affects evaluation and does not require gateway reload. Coordinator fresh integrated focused checks passed 135 tests before the additional application reason-code contract correction. Full integrated verification is pending at this checkpoint.

Antigravity workers A and C reached provider quota during their new follow-up tasks (terminal reset estimates approximately three hours). Their new tasks are unfinished; the previous completed integrations remain valid. Ruling: the coordinator continues the already-authorized plan directly in the root checkout, preserving worker branches and synthetic evidence; quota is not treated as completion. Runtime fixes require regression tests and a further service reload before any new live result is credited.

Root cause: routing recorded `requires_authority` but escalated only `human_agent_requested`; uncertainty could therefore take precedence over an explicit dispute or exception. Related requests for archived, unapproved, historical, internal-only, or conflicting policies passed adjacent current policy evidence to the LLM, which frequently offered current-policy information instead of an escalation. Corrections add explicit authority precedence and conservative English policy-scope review. These rules supplement retrieval and are not general semantic proof or a universal contradiction detector. Confidence thresholds and trained model scores remain unchanged.

## Verified correction checkpoint

Coordinator runtime corrections are committed as `4617bb4` and `87bea96`, including explicit manager-exception escalation, unavailable cross-border shipping evidence, semantic insufficient-evidence disposition, and prompt `grounded-v3`. The prompt now distinguishes missing customer details from missing policy facts and preserves upper-limit qualifiers. Trained model scores and thresholds are unchanged.

The first full regression run exposed a test fixture using an unconstrained `MagicMock` as a numeric relevance threshold (14 failures, 711 passed). The fixture was corrected to represent the real adapter's 0.55 configuration. The rerun passed **730 tests**, with **2 skipped and 2 deselected**, in 310.15 seconds. Affected application and pipeline tests separately passed 42 checks; final focused routing, Gemini, and usage-preservation checks passed 80 checks. These test results establish the tested boundaries, not semantic claim correctness.

After gateway reload, the eleven unchanged downstream regression cases passed **11/11 expected escalation actions and reasons**, with **11/11 no automatic customer reply**. No LLM call was needed for these routed cases. Application p50 was 0.30495 seconds and p95 0.79392 seconds; this is escalation latency, not generation latency. Artifact: `artifacts/evaluation/coordinator-downstream-live-20261112-r2/final-evidence-20261112-151454-714eba/`.

Next: finish the current 24-case rerun, exercise actual staff intent correction with separate initial/assisted outcomes, re-grade current drafts, execute the 12 paired agent-simulated tasks with real measured timestamps, then complete the FR/quality matrix. External shared-data approval remains unverified. This checkpoint is not final acceptance.


## Reviewed worker integration checkpoint

The three resumed workers delivered reviewable changes. Product changes are integrated as `2b44c2d` (C diagnostic isolation and tests), `172f053` (B sanitized provider diagnostics and A routing regressions), and `75da938` (A offline audit and report generation). Historical browser assets are preserved as `976fe43`; their original execution log is unavailable, so browser pass counts remain worker-reported and unverified. Worker branches and user presentation files are preserved.

Fresh combined verification on the integrated product commit `75da938` passed **137/137 tests in 57.34 seconds**. This is a focused integration profile, not a fresh full-repository 730-test run. The original 730-test checkpoint above remains historical. Evidence: `artifacts/evaluation/reviewed-integration-20261112/`.

The latest completed 24-case run, `coordinator-final-live-20261112-r3/final-evidence-20261112-151514-078471`, observed **20/20 no automatic replies**, **3/3 designated escalation cases correctly escalated**, and **4/4 separate retrieval fixtures passing**. Among 12 answerable cases, **1 drafted automatically, 7 abstained due to classifier uncertainty, and 4 failed provider generation**. Overall application p95 was **10.75708 seconds** with failures included; low latency does not erase those failures. The actual staff intent correction diagnostic preserved 7 original abstentions and recorded **5/7 assisted drafts, 2 provider failures, 7/7 no automatic replies and matching override audits**. This is oracle-assisted diagnostic evidence, not automatic classifier accuracy or human productivity evidence.

A's 689-row offline audit independently reconciles to 420 noise rows, 80 out-of-scope rows, 156 acceptance rows and 33 sensitive/benign rows. On the 156-case component benchmark, exact action matching is **74/156**. Within the 63 mandatory cases: **16 escalate, 46 abstain and 1 uninjected encoder fault**; **21/63** match allowed actions, **41** safely abstain where strict escalation was expected, and the uninjected fault receives no success credit. This component boundary is distinct from the designated three live escalation cases.

B's provider investigation recorded 8 top-level probes comprising **9 actual provider requests** because the final probe retried. This exceeded the coordinator's 8-request allowance by one; further probe calls were stopped. The first six observations remain preserved, and unknown earlier HTTP statuses are not inferred retrospectively. Later telemetry observed HTTP 503 separately from timeouts. The existing five-second default attempt cap remains; there is no evidence that changing this cap resolves provider availability. Token usage is recorded per attempt when available; complete cost remains unknown when failed calls have unknown usage.

**Acceptance remains OPEN / NOT PASSED.** Outstanding items include low automatic draft coverage, provider 503/timeout reliability, complete billing coverage, component action mismatches, semantic grading of current drafts, paired agent-simulated handling-time measurements, and fresh browser execution with a retained runner log. Historical baseline claim grading (17/20 supported propositions, 85%) remains a failed baseline and is not a grade of the newer drafts. Partial simulated timing observations do not constitute a completed paired study. External instructor/shared-data approval remains unverified. Runtime services must be distinguished from the tested on-disk product; no new live acceptance result is credited by these offline tests.
