# SupportIQ — Backend acceptance and usable light interface

## Intent and authority

Continue the Topic 1 implementation against `docs/CHỦ ĐỀ 1.md`. The user authorizes implementation, delegates stakeholder decisions and AI grading/agent studies, and explicitly requests three Antigravity backend workers plus one frontend worker. No additional approval gate is needed for routine design choices within this scope. Earlier results and gaps are in `docs/audits/2026-11-12-topic-1-integration.md`.

## Approach

Improve the existing FastAPI/PostgreSQL application and React UI. A rewrite would discard verified ownership, audit and approval behavior; documentation alone cannot resolve runtime/evaluation gaps. Keep APIs compatible wherever possible. Preserve synthetic data, manual send, sticky manager authority and fail-closed model provenance.

Backend priorities: safety and actual egress protection; retrieval/grounding with versioned evidence; reproducible acceptance that measures the application rather than fixed summaries. A local approved app-specific gold set must be locked before execution and kept distinct from externally shared acceptance. Coordinator may approve local policy/gold as delegated stakeholder, but cannot claim approval by another group or instructor.

Frontend is Operate mode: bright neutral surfaces, dark readable text, one restrained blue action accent, semantic status colors used sparingly, persistent field labels and obvious next action. Preserve English product copy and real API data. Existing message/intent/draft/evidence composition and self-hosted type are retained where useful. Impeccable and design-taste-frontend app-screen workflow govern before/after inspection and accessibility. No decorative gradients, animations, invented counts or new marketing pages.

## Acceptance

- FR-01–08 mapped to executable tests, persisted application evidence or an explicit unresolved gap.
- ML baseline and chosen model: 46 labels, fixed splits, 10-fold Macro-F1 >= .85; per-class/confusion and provenance distinguish historical predictions from new inference.
- Retrieval: Recall@3 >= .80 on independently locked answerable gold for the evaluated KB; report uncertainty, expired/conflict/OOD slices separately.
- LLM: >=90% supported claims on source snapshots with explicit AI judge provenance. No citation-existence surrogate for semantic grading.
- Oversight: no automatic customer send/transactions; mandatory authority scenarios enforced, including after staff intent override and asynchronous retries.
- Reliability: safe manual fallback for uncertainty/no-source/API failure; no hidden plaintext egress in tested synthetic PII scenarios.
- Performance: measured application end-to-end p50/p95, errors and token/cost coverage; p95 <=12s under declared conditions. Missing pricing remains unavailable, never zero.
- Product evidence: paired manual/assisted agent trials and approve/edit/reject counts are simulations; no fabricated human results.
- UI: working keyboard/phone layouts, clear empty/loading/error states and accessible review actions; build, relevant unit tests, browser/axe and visual inspection at 1440/768/390 (360 where existing coverage requires).

## Boundaries and risks

No production deployment, push, policy bypass, real customer data or destructive DB reset. Worker branches stay isolated; root running services are coordinator-owned. Provider failures must be recorded and retried sensibly. A local run cannot certify shared cross-group versions or human-only methodology. Performance and claim samples state denominators and scope. Do not weaken gates or alter historical gold to achieve a target.
