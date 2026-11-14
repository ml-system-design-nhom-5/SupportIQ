# Guard review corrections

The b3f89e4 PipelineRunner patch is staged in root, not integrated or loaded.
C audit f24590b found actionable priority/clarify/false-positive issues. Both CLS
and lexical classifier feasibility experiments are negative; stop new model fits.
Base production root665c6cf; later worker-only evidence stays separate.

## B: shared guards and generation-result boundary

- Reproduce C findings with failing general tests: human+fraud manager priority,
  low-confidence/missing-order clarify, overlapping evidence-scope failures,
  negated requests, drafting a reply versus draft policy, expired product versus
  expired policy, current policy versus purchase-year context.
- Minimal shared safety module under core_backend is authorized for rules used by
  Engine and PipelineRunner; preserve imported compatibility aliases where needed.
  Remove duplicated rule drift rather than adding independent regex copies.
- Text safety is applied before either retrieve_draft or clarify can bypass it,
  preserving denied commerce ownership and all independent authority gates. Human
  routing must not strip manager authority; escalation beats ordinary abstention.
- Validate post-generation output at the PipelineRunner boundary using the actual
  GeminiDraftClient body/citations/input_snapshot contract. Reject uncited/unknown
  citations and unsupported commitments without rejecting legitimate client output
  or requiring removed/rewritten markers. Keep failed output out of stored drafts.
- Record matched source/client provenance and test successful default-client output,
  malicious/invalid injected output, score immutability and supported coverage.
- Source scope: shared safety helper, Engine, PipelineRunner, focused tests/new
  additive artifacts. Coordinate any other file before editing it. No gold edits,
  new fits, live calls, model promotion or bulk refusal to improve safety metrics.

## A: truthful typed fault propagation

- No more classifier fitting. Work on existing retriever error preservation,
  ai_service endpoint exception typing, backend AI-client/job failure propagation
  and focused fault tests; coordinate exact fields with B before Engine edits.
- Distinguish ML timeout, ML error, encoder unavailable/failed and missing evidence
  using bounded public codes. Retain detailed internals privately without logging
  credentials or exposing raw exceptions. Preserve existing safe fallback contract.
- Preserve cross-customer order intake404 and zero ticket creation. Do not weaken
  privacy or create a ticket merely to satisfy an incompatible frozen escalation
  expectation. Report this boundary mismatch explicitly.
- Existing reason aliases may coexist with canonical codes for compatibility.
  Capture original expected.actions versus must_escalate conflicts faithfully;
  no frozen fixture changes or false PASS classification.
- Own retrieval/adapter.py, ai_service/main.py, backend AI-client/job modules and
  focused tests/new artifacts. B owns Engine/shared guard/PipelineRunner.

## C: regression/review evidence

- Preserve raw f24590b fault observations, exact module/HTTP boundary and cleanup
  hashes. Provide minimal red repros for A/B; no production source edits.
- Review new shared guard priority, negation handling and legitimate generation
  compatibility independently. Check customer ownership context matches synthetic
  order ownership; keep original mismatched-context report historical/additive.
- Re-execute prior fault probes with zero provider allowance after fixes, reporting
  strict action/reason matches separately from safe fallback/privacy intake denial.
- Update diagnostic tests to assert the desired corrected behavior where appropriate,
  without altering immutable old raw outcomes. No new semantic grading or training.

All work is offline/no-provider. Global live allowance stays18/24 used with6
reserved; no worker in this plan is authorized to spend those remaining calls.
Serving classifier, approved KB, policy thresholds and required staff approval stay.
