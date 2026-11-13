# Mandatory routing integration

Integrates Worker B production changes from `5f3493e`, additive accounting from
`71fae3b` and C's independent pre-integration review from `765121a`.

The Engine now escalates recognized intents outside the twelve supported labels,
preserves explicit outside-scope action handling, and recognizes additional common
human-support and unsupported-policy expressions. The HTTP router also respects
validated staff intent overrides at its confidence gate, matching established
Engine behavior. Existing source, authority, rejection and approval gates remain.
The language heuristics are bounded English rules, not a general semantic scope
or contradiction detector.

On the unchanged serving classifier, offline Engine exact action matches improve
from 74/156 to 114/156. Among 60 mandatory cases without simulated fault injection,
exact matches improve from 19/60 to 53/60 with zero unsafe drafts. Seven safe
fallback mismatches remain. Three uninjected fault cases remain NOT_EXECUTED;
the unadjusted static 55/63 number is not a claim of executed safety coverage.

Comparable draft_expected_34 remains 21/34 raw eligible and 17/34 correct-intent
eligible before and after. The separate draft_allowed_88 slice is 51 raw /44
correct and must not replace the 34-case denominator.

The separate HTTP IntentClient -> decide_route path retains pre-existing gaps:
12 unfaulted mandatory unsafe draft recommendations and 2/80 OOD leaks, identical
before and after. It does not perform Engine source-content checks. This change
must not be described as establishing safety for every path.

C independently reviewed ordinary valid-policy questions, recomputed both paths
and reported no blocking regression in this scope. Candidate `c6cae7a` still
fails mandatory safety even combined with these changes and is not promoted.
No live provider requests are needed or made for this integration.

Fresh root verification: **237 passed, 1 deselected** in 144.59 seconds across
mandatory routing, runtime parity, routing/override, typed HTTP intent controls,
evaluation gates, Gemini requests, application AI boundary, PostgreSQL backend
safety closure and the full pipeline test module. Python3.12 and the pure Python
psycopg implementation were used. These test modules use mocked provider calls;
this is not a new live-provider availability measurement.

Owned local services were reloaded. Ports8080/8002 both returned readiness HTTP200 with configured gemini-3.5-flash-lite. A no-generation POST to /v1/analyses for an account-closure request returned escalate, verifying the reloaded route without consuming LLM budget.
