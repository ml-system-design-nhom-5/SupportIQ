# SupportIQ

AI Customer Support Copilot for E-commerce. See [the architecture and requirements](docs/ARCHITECTURE.md).

Core backend: [design specification](docs/superpowers/specs/2026-10-27-core-backend-design.md) and [REST API contract](docs/api/core-backend.openapi.yaml).

Team delivery: [four-member backend implementation plan](docs/superpowers/plans/2026-10-27-core-backend-team-plan.md).

## Repository structure

```text
SupportIQ/
|-- apps/
|   |-- storefront/src/           # Customer storefront and support conversations
|   |-- staff-web/src/            # Agent, manager, and administrator interface
|   `-- core-backend/
|       |-- src/modules/
|       |   |-- auth/             # Authentication, RBAC, session invalidation
|       |   |-- tickets/          # Requests, conversations, approved responses
|       |   |-- commerce/         # Demo catalog, checkout, orders, shipping, refunds
|       |   |-- orchestration/    # Async pipeline, state, gates, retries, timeouts
|       |   |-- intent/           # ML inference client and confidence handling
|       |   |-- retrieval/        # Hybrid search, document validity, evidence
|       |   |-- llm/              # Grounded drafts, citations, egress queue client
|       |   |-- review/           # Approve, edit, reject; explicit response delivery
|       |   |-- escalation/       # Low confidence, missing evidence, errors, manual mode
|       |   |-- privacy/          # PII scanner, identifier resolver, token vault access
|       |   |-- feedback/         # Decisions, corrections, curation for offline improvement
|       |   |-- audit/            # Insert-only events, request IDs, versioned traces
|       |   `-- reports/          # Aggregates, latency, errors, request costs
|       `-- config/
|           |-- prompts/          # Versioned LLM prompt templates
|           `-- policies/         # Intent scope, thresholds, escalation rules
|-- services/
|   |-- ml-inference/src/         # Independently deployed non-generative classifier
|   `-- egress-proxy/config/      # External LLM host allowlist and outbound policy
|-- ml/
|   |-- training/                # Preprocessing, baselines, training, fixed splits/seeds
|   |-- evaluation/              # Cross-validation, per-class F1, confusion matrices
|   `-- releases/                # Approved manifests: model, prompt, KB, index versions
|-- data/
|   |-- datasets/                # Local downloaded datasets and generated splits (ignored)
|   |-- knowledge/               # Versioned policies/FAQ, sources, validity metadata
|   `-- business/                # Synthetic demo catalog, orders, delivery/refund seeds
|-- artifacts/
|   |-- models/                  # Generated model binaries (ignored)
|   `-- search-index/            # Generated full-text/vector indexes (ignored)
|-- db/migrations/
|   |-- app/                     # Requests, drafts, workflow and demo business records
|   |-- knowledge/               # Knowledge metadata, document versions and validity
|   |-- audit/                   # Audit/feedback persistence and insert-only permissions
|   `-- token-vault/             # Restricted token-to-PII mapping storage
|-- infra/
|   |-- compose/                 # Local stack, networks, health checks, replica settings
|   |-- edge/                    # Ingress/API gateway, TLS, core backend load balancing
|   |-- ml-balancer/             # Internal ML inference load balancing and health checks
|   |-- cache/                   # Shared cache, rate counters, TTL/memory limits
|   |-- queue/                   # Pipeline jobs and sanitized AI egress buffer
|   |-- secrets/                 # Secret injection templates; no credentials
|   |-- observability/           # Sanitized logs, metrics, dashboards
|   `-- aws/                     # Deployment and network/egress restrictions
|-- tests/
|   |-- unit/                    # Module-level behavior
|   |-- integration/             # Service, persistence, cache and queue boundaries
|   |-- e2e/                     # Customer request through staff-approved response
|   |-- security/                # RBAC, PII scans, injection, vault/egress restrictions
|   |-- performance/             # Concurrent sessions, latency, resource consumption
|   `-- evaluation/              # Retrieval, grounding, robustness, escalation scenarios
`-- docs/
    |-- ARCHITECTURE.md
    `-- images/                  # Existing architecture diagrams
```

This is a folder scaffold. Frameworks, dependency manifests, runtime configuration, migrations, and application code have not been added. Existing documents remain under `docs/`. Empty directories contain `.gitkeep` so they can be tracked when Git is initialized.

## Component boundaries

- Keep business modules in one core backend. Replicas run the same stateless application; operational state belongs in persistence and the shared cache. ML inference and the egress proxy have separate deployment directories because the architecture gives them independent scaling or access controls.
- Keep the customer storefront separate from the staff interface. Staff workflows must remain usable for manual handling when AI components fail. All responses require explicit staff approval before delivery; demo commerce operations must not be triggered by the AI pipeline.
- Only the identifier resolver may access token-vault mappings. Keep vault storage and credentials separate from application, knowledge, and audit storage. Folder placement alone does not enforce access control; enforce it in code, database permissions, and deployment networks.
- Scan and tokenize PII before AI processing, caching, logging, or external delivery. The LLM path goes through the sanitized egress buffer and allowlisted proxy. Real secrets belong in a secrets manager and are injected at runtime.
- Use one shared cache for sessions/permissions, rate counters, retrieval, optional intent results, and dashboard aggregates. Do not cache LLM drafts, vault mappings, business snapshots, or audit writes. Apply versioned keys and recheck document validity after retrieval cache hits.
- Keep raw datasets, trained binaries, and generated indexes local or in controlled artifact storage. Commit only synthetic business seeds and approved knowledge sources with versions and validity metadata. Runtime databases and vault contents do not belong in this repository.
- Feedback improvements are reviewed batches: curation, offline evaluation, then an approved release manifest. Record model, prompt, knowledge, and index versions so requests can be traced and releases rolled back.

## Intent scope

[The project brief](docs/CHỦ%20ĐỀ%201.md), section 2.2, defines 46 classifier labels for ML evaluation and 12 supported product intents. Other labels must fall back to staff handling. The core backend design lists the supported intents and routing rules.
