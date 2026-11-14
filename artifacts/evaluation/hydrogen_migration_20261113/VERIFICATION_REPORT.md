# Gemini 4 Hydrogen migration verification

Selected model: `gemini-4-hydrogen`, thinking level `low`. Active defaults and
the private root `.env` now select Hydrogen. Credentials were not changed.
Explicit Gemini 2.5 and Gemini 3 request compatibility remains covered by tests.

Root verification: **89 tests passed** across Gemini requests, provider recovery,
grounding, application AI boundary, and live-call budget guards.

Exactly **one** newly authorized direct `generateContent` request was attempted
with approved `POL-RET-001:2.0` policy content and no customer data. No retries or
other generation requests were made. It failed closed with `llm_timeout` after
**5.2668 seconds**, with no HTTP response or token usage observed. The raw record
is `live_verification.json`. Complete cost is unknown, not zero. The earlier
eight-request verification budget remains exhausted and is separate from this
one-request migration allowance, which is now also exhausted.

Owned local application services were restarted through `stop-app.ps1` and
`start-app.ps1 -SkipInstall -SkipBuild -EnableLLM`. Post-start checks confirmed
the resolved model setting is `gemini-4-hydrogen`, backend readiness on port
8080 is HTTP 200, and AI readiness on port 8002 is HTTP 200 with verified trained
classifier, retrieval ready, and LLM configured/enabled. Readiness does not
establish provider generation success; no additional generation was triggered.

The model configuration switch is complete. Successful live Hydrogen drafting,
comparative reliability and full-system acceptance remain unverified. The
classifier and embedding models were not changed or promoted.
