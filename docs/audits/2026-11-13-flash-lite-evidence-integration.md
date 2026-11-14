# Flash-Lite application evidence integration

Selected collector source/tests and evidence from C `b472240` (including earlier
`8d9b3e0` and `765121a`). Existing Engine integration `b7ebc34` and coordinator
semantic grading `52a7da0` are preserved. No classifier weights were replaced.

Root verification: **75 passed, 1 deselected**, no new generation requests.
Independently verified all17 hashes in the four imported artifact manifests and
both report hashes referenced by the coordinator semantic grading record.

## Actual application results

The owned isolated backend/PostgreSQL/AI gateway used the serving classifier,
real BGE and Gemini3.5Flash-Lite. Twenty application cases comprise12 answerable
and8 active-KB safety cases; four additional component fixtures explicitly inject
expired/conflicting BGE evidence. This is not a browser or real-human study.

Run1 consumed5 actual generation HTTP requests; Run2 consumed13. Total18/24,
with6 remaining globally and lower-layer retries disabled. Run2 has no timeout
or unavailable result in its13 generation attempts; the sample is small and
the runs repeat frozen scenarios, so this is not an availability SLA.

Run2 automatic results:5/12 raw drafts,4/12 correct-intent drafts,1 wrong-intent
draft and7 abstentions. Eight separately labeled validated staff intent overrides
produced8 drafts. The combined12 unique correct-intent cases require staff
intervention and must not be presented as12/12 automatic classifier coverage.
All20 inspected customer tickets remained unsent. Eight safety cases had no unsafe
draft; four injected BGE boundary fixtures passed.

All20 application cases: interpolated p50=298.08ms, p95=2139.1255ms. Answerable12:
p50=471.18ms, p95=2185.4095ms. These distributions include fast abstentions;
staff override timing is separate. They do not measure full staff handling time.

Coordinator AI grading under user delegation reviewed18 captured drafts across
the two runs and found54/54 claim units supported by actually cited snapshots.
Each run's wrong-intent draft still requires intent correction before approval.
This is zero-human AI grading of a repeated small sample, not a universal claim.

## Accounting and cleanup corrections

Preserve original records and hashes. Additive verification records that all18
attempts omitted thoughtsTokenCount; it is unmeasured, not measured zero. Run2
observed22520 prompt and1545 candidate tokens give conditional standard-list
USD0.0106185; cumulative candidate-only conditional USD0.0146488. Actual billed
cost, account tier and omitted thinking remain unknown.

The corrected collector truthfully reports schema creation/drop success/failure,
including a sanitized error category and failure regression test. C's additive
read-only pg_namespace query confirms both original schemas are absent. Older
hardcoded cleanup claims remain historical and are superseded by that observation.

## Remaining acceptance limits

Stored37911-row,10-fold,46-intent OOF data independently recomputes to fold-mean
macro-F1=0.9952684306823985 and matches training_report metrics. Original CV
manifest, training git_commit and per-fold checkpoints remain missing; no new
training or invented original provenance is claimed.

Candidate c6cae7a has0/80 OOD leaks but still one real mandatory unsafe draft;
it remains rejected. Serving Engine mandatory matching is53/60 with7 safe
fallback mismatches and3 fault cases NOT_EXECUTED in that static suite. Separate
HTTP routing-stage limitations are documented in the mandatory integration audit.
No new measured productivity gain is claimed; the previous paired AI exercise
remains limited simulation evidence. Overall acceptance remains open.
