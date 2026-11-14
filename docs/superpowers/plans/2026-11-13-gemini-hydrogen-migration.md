# Gemini 4 Hydrogen migration

User explicitly requested resuming Worker B and switching the drafting LLM to
Gemini 4 Hydrogen. Coordinator chooses the existing Gemini Developer API and
`thinkingLevel=low` for short grounded drafts. No classifier or embedding swap.

The current key successfully resolves `models/gemini-4-hydrogen` with HTTP 200
and advertises `generateContent`. This metadata request does not establish
generation success, billing balance, or whole-system acceptance.

1. Worker B completes the existing backend metadata task in intent adapters.
2. Worker A implements model-specific Hydrogen request compatibility, updates
   active defaults/examples, preserves older explicit model compatibility, and
   verifies mock request/response and grounding regressions. No live calls.
3. Coordinator reviews and integrates the change, sets only GEMINI_MODEL in the
   private root .env, and verifies at most ONE new direct generateContent
   request (no retries) with nonpersonal grounded policy input. This is a new
   migration verification allowance; the previous 8-call allowance stays spent.
   Record status, latency and observed usage without secrets or assumed costs.
4. Reload owned local services if available and verify reported model/config;
   otherwise report precisely what was configured and tested.

Preserve citation/answerability checks, bounded retry defaults and human approval.
Do not broaden timeout or automatically fall back to another paid model. Preserve
historical benchmarks, evidence and pricing records; Hydrogen is not priced using
the previous model's rate card.

Primary references checked 2026-11-13:
- https://blog.google/innovation-and-ai/technology/developers-tools/build-with-gemini-4-hydrogen/
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-4-hydrogen

Hydrogen supports low/medium/high/xhigh thinking; the current minimal setting is
incompatible. No new SDK, continuation mechanism or large-output feature is needed
for the existing short single-turn drafting contract.
