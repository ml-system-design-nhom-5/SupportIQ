# SupportIQ stateless AI gateway

This local HTTP boundary adapts the existing verified inference model, approved KB retriever, and Gemini client to `/v1/analyses`, `/v1/drafts`, `/v1/asset-versions`, and versioned KB reads. It owns no tickets, sessions, orders, database, or per-ticket state. The application backend calls it with pseudonymized text and identifier-free order fields.

Native startup runs it on `127.0.0.1:8002`, using offline model caches. Model load failures return unavailable outcomes instead of synthetic predictions. The existing classifier reports raw scores. The gateway applies the existing per-intent routing thresholds and requests intent confirmation only below those thresholds. The application preserves manual support throughout an AI failure.

External generation uses a local `GEMINI_API_KEY` by default; start with `-DisableLLM` to disable it. An HTTP transport allows only HTTPS calls to `generativelanguage.googleapis.com`; provider responses and keys are not logged. The standard test suite excludes external generation. Run `python scripts/verify_ai_integration.py` explicitly to verify the complete live application flow in an isolated schema. Model scores, policies and source IDs are never fabricated.

The gateway validates citation identity and placeholder provenance around the existing draft client. These structural checks do not establish semantic entailment; a human must still verify every claim. The existing model/retrieval calibration and grounding evaluations remain separate release gates.
