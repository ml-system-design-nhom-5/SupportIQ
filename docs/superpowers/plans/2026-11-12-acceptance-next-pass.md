# Acceptance follow-up plan

> For Orca workers: execute only your assigned task in your existing workspace. Use the applicable debugging, testing and review skills. No helper agents are requested.

Goal: close observed acceptance gaps without changing frozen gold, lowering safety thresholds or claiming external approval.

Authority: the user delegated all stakeholder decisions to the coordinator and requested three Antigravity workers through acceptance. The approach below is a coordinator decision under that delegation.

Context: product integration through f885e2a passed 137 focused checks. AI grading found 21/22 supported verification units across one automatic and five oracle-assisted drafts; the remaining draft has an unresolved public-hotline placeholder. Twelve paired AI tasks show essentially equal mean times (8.974584 seconds manual, 8.970244 assisted), with six manual fallbacks. Provider failures and automatic draft coverage remain unresolved.

Approach: preserve current serving weights, 5-second attempt cap and 10-second allocated deadline. Compare existing trained classifiers offline before choosing model changes. Fix the reproduced public-policy contact redaction defect with regression tests. Obtain fresh browser evidence against an isolated application with a controlled AI gateway; distinguish UI verification from real-provider reliability. Raising timeouts has not been shown to resolve HTTP 503, and global removal of PII redaction would break the privacy requirement.

## A: Diagnose intent coverage and compare trained candidates

Owns: additive diagnostic scripts/artifacts and a candidate recommendation; no serving model or routing changes.

- [ ] Merge reviewed main into the routing workspace, preserving local changes.
- [ ] Reproduce the seven uncertain answerable cases with actual trained model identity, scores and route reasons.
- [ ] Locate already trained baseline models and verify their model/label provenance before using them.
- [ ] Compare valid existing candidates on unchanged noise, OOD and product suites with identical policy boundaries; distinguish accuracy from draftability and abstention.
- [ ] Report whether there is an evidence-supported candidate or whether new domain training is needed. Do not train on gold questions or rewrite serving artifacts.
- [ ] Deliver reproducible commands, exact denominators, raw measurements and a small next-step proposal. No live provider calls.

## B: Preserve verified public support contacts without exposing private data

Owns: apps/core_backend/llm/gemini.py and focused tests; coordinate before changing unrelated privacy modules.

- [ ] Reproduce policy hotline 1900 6035 becoming [PHONE_OR_NUMBER] through redact_contacts/build_grounded_sources and a controlled generated draft.
- [ ] Add a failing regression for the trusted public-policy contact and negative cases for customer phone, email, identifiers and forged or untrusted source content.
- [ ] Implement the smallest origin-aware correction. Do not disable private contact scrubbing or universally whitelist numbers in customer text.
- [ ] Preserve source hashes/citations, reason codes, billing metadata, no automatic sending and the existing timeout policy.
- [ ] Run relevant grounding/privacy/retry tests and report the exact red-green evidence. No live provider calls; prior probe allowance is exhausted.

## C: Obtain fresh browser execution evidence

Owns: isolated verification helpers and artifacts; existing frontend E2E spec only if a real test defect is found.

- [ ] Merge reviewed main and read impeccable/design-taste-frontend before reviewing UI or proposing visual changes.
- [ ] Use an isolated PostgreSQL schema and a controlled local AI gateway with the actual backend/frontend; choose separate ports and temporary synthetic credentials. Never restart root services.
- [ ] Run existing E2E scenarios across desktop 1440x900, tablet 768x1024, mobile 390x844 and small-phone 360x800.
- [ ] Retain machine-generated reporter output, actual command, versions, execution times, source commits, screenshots and hashes in a unique directory. Report all failures.
- [ ] Verify accessibility/overflow and explicit manual reply flow. Label the AI gateway as mock; do not credit this as real ML/LLM acceptance.
- [ ] Clean only owned processes/schema and scrub private configuration from evidence. No live provider calls.

## Coordinator gate

Review worker evidence and independent tests before integration. Retain current semantic/paired AI results unchanged. Service reload and any further live acceptance require separate recorded execution; no 503 repair or full acceptance may be inferred from mock/offline results.