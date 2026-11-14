# Backend intent adapter integration

Selected four files from Worker B `95577ea` atop root `1ecdd15`:
`apps/core_backend/intent/{schemas.py,client.py,routing.py}` and
`tests/unit/test_intent_client_rejector_routing.py`.

Optional selective decisions, raw scores, calibration and provenance metadata
are retained through HTTP `/predict` -> IntentClient -> IntentPrediction ->
decide_route. Explicit rejection prevents automatic retrieve_draft. Supplied
malformed controls fail closed; original scores remain unchanged. Existing
human requests, out-of-scope escalation, validated overrides, authority, slots
and policy approval retain their precedence. Missing optional metadata preserves
baseline behavior.

C independently reviewed this exact four-file diff and reported no blocking
findings (`msg_073754ea2e60`). C also distinguished this adapter path from the
application's in-process ModelContainer -> Engine, which already enforces vetoes.

Fresh root verification using Python 3.12, `PSYCOPG_IMPL=python` and the installed
PostgreSQL libraries: **174 passed, 1 skipped, 1 deselected** across intent client,
routing, completion HTTP/routing, authority, retrieval integration, model runtime,
inference service, evaluation gates, Gemini and backend safety closure tests.
The safety closure tests passed here, resolving the native psycopg loading issue
encountered in C's separate test environment. The skip and deselection remain
disclosed; this is a focused suite, not a claim about every repository test.

This resolves the adapter metadata blocker documented in the earlier selective
runtime integration audit and evidence matrix. It does not promote classifier
candidate `028ed76`, resolve strict mandatory-escalation mismatches, demonstrate
successful live Hydrogen generation or establish whole-system acceptance.
No provider generation requests were made for this integration.

Owned services were restarted with `stop-app.ps1` and
`start-app.ps1 -SkipInstall -SkipBuild -EnableLLM`. Both ports 8002 and 8080 returned
HTTP 200 readiness after restart. The resolved LLM setting remains
`gemini-4-hydrogen`; readiness is not evidence of successful provider generation.
