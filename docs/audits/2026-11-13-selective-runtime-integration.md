# Selective runtime integration

Integrated selected runtime files from Worker B `23767a7` and evaluation files
from Worker C `0882810`. Candidate `028ed76` remains rejected and is not installed
as the serving model. Its training implementation and weights remain in Worker
A's workspace; this integration does not claim to integrate those assets.

The runtime validates model outputs and explicit calibration manifests, keeps
raw probabilities separate from calibrated scores and selective decisions, and
prevents automatic Engine drafts when an explicit selective veto is present.
Existing classifiers without selective metadata retain their routing behavior.

The initial combined test run exposed a stale C assertion requiring the old
Engine behavior. Integration expectations now require Engine rejection and no
additional harness veto. Assertions against immutable historical reports retain
their original expectations; report bytes and recorded hashes are unchanged.

Fresh root-workspace verification:

- Runtime parity, evaluation gates, live-call budget guard, comparison/accounting,
  grounding, AI boundary and model provenance: **151 passed, 1 deselected**.
- Real serving-model parity: **1 passed, 8 deselected**.
- No live provider requests were made by these checks.

Remaining blockers:

- Candidate gate rejects 3/80 OOD leaks and one real mandatory-escalation leak.
- Separate core-backend IntentPrediction/IntentClient/routing path drops optional
  selective metadata. This integration does not fix or validate that path.
- Orca follow-up `ctx_ee504bee728d` failed at agent readiness; inspection returned
  unverifiable liveness and `worker_identity_changed`. Its work is not counted as
  running or completed.
- Running services have not been restarted to load these source changes. These
  checks establish test behavior, not whole-system acceptance or live readiness.
