# Application verification

> **Status:** Active · **Owner:** application · **Last reviewed:** 2026-11-05

Evidence and review scope for the native Windows application. Commands are in the component READMEs. The default test suite excludes external LLM calls. The explicit live integration check below uses the configured Gemini LLM.

## Functional evidence

Backend tests exercise authentication, Origin enforcement, role isolation, source-order ownership, idempotency including concurrent requests, concurrent sends, proposal approval, escalations, warning acknowledgement, stale suggestions, sticky authority, immutable audit/messages, session revocation, manager-only reports, pseudonymization, uncalibrated-model abstention and citation/placeholder provenance.

Playwright drives the production build on Microsoft Edge at 1440, 768, 390 and 360px. The flows cover sign-in, catalog, orders, sending a support request, staff reply confirmation, customer receipt, admin confirmation dialogs, versions and manager reports. Every captured state also runs axe WCAG checks and an overflow assertion. Screenshots are local under `.impeccable/review/`.

The native startup command was exercised with the existing environment and production build: `scripts/start-app.ps1 -SkipInstall -SkipBuild`. PostgreSQL and the actual local AI gateway report ready. A real local inference request predicted `track_order` and retrieved one approved source; external drafting remained disabled.

Final recorded checks: Python `419 passed, 1 skipped, 1 deselected`; frontend `3 passed`; production build and TypeScript passed; Playwright `8 passed` across four viewport projects, including axe assertions.

## Visual critique

Direction: Framed sheet, seed 1620768504, constrained by the approved mockups. No photographs were sourced or generated; the neutral product image is required by the source design.

The dominant console block is the reply and its review context. The frame closes at both edges; desktop columns retain their roles and the phone switches between inbox and ticket. Colors identify states and provenance. Money is formatted as source VND, counts derive from recorded data, and missing measurements stay as dashes. Dialogs name the affected person or reply. The shop preserves one message and one human reply per ticket.

Inline visual judgment: hierarchy 8/10, consistency 8/10, legibility 8/10, task clarity 8/10. These are subjective review scores, not measured product-quality results. Review was performed inline, without subagents.

The browser inspector recorded zero failures for sign-in, order detail, accounts and the final console at 1440/768/390. Remaining advisories are documented: sparse sign-in and admin canvases reflect their short real content; compact 12px metadata follows the approved scale; the console evidence rail has independent content height; order identifiers retain the approved monospace treatment. Violet is an explicit design token, so `palette-purple` is allowed rather than changing its meaning.

## Release limits

The source model exposes raw scores. The application applies the existing per-intent score and margin thresholds, retaining explicit low-confidence abstention. Semantic claim entailment, unknown-name/address PII recall, load targets and production security require their separate evaluation. Storybook, CI automation, telemetry deployment and production TLS are not claimed by these checks. See [the Windows guide](application-windows.md#verification-and-limits).


## Live application integration, 2026-11-05

`python scripts/verify_ai_integration.py` exercises the customer API, persistent suggestion job, verified DistilBERT model, BGE embedding retrieval, and configured Gemini LLM against the existing approved KB. It also opens the production console in Edge, checks the actual generated draft and citations, and opens a full source document. A temporary PostgreSQL schema isolates the run and is removed afterward; existing customer requests and orders are untouched.

Recorded live result for "What is your return policy?": `return_policy`, raw score 0.9963, 3 retrieved documents, 2 draft citations, `draft_ready`; analysis 108 ms, draft 1,886 ms, LLM 1,483 ms; provider usage 1,067 input and 145 output tokens. These are observations of this single local run, not a latency benchmark. The customer response still contained no reply, proving the draft had not been sent automatically. Local evidence is `.local/integration-live.json`; the rendered console is `.impeccable/review/ai-live-console.png`.

Native startup now enables external drafting with the configured key by default. `-DisableLLM` disables provider calls. Raw scores stay labeled Raw score; no calibrator or replacement policy was invented. A uniquely mentioned order is attached only if it belongs to the requesting customer; other identifiers are pseudonymized and never authorize an order lookup.

## Transient LLM timeout recovery

A user-observed failure on TCK-1003 was `llm_timeout` after approximately 7.3 seconds; model inference and retrieval had succeeded. The gateway now retries connection/time-out failures once using the remaining LLM budget, while authentication and invalid-output errors fail immediately. The UI does not recommend reviewing a draft when its generation failed. Explicit retry of that ticket produced `draft_ready` with two citations in 1,834 ms; the production console was opened and the draft verified. No reply was sent.
