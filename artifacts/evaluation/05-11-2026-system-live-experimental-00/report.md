# SupportIQ System Evaluation Report

- **Execution State:** `completed`
- **Evidence Kind:** `live_experimental`
- **Mandatory Acceptance Gates Passed:** `False`
- **Summary Reason:** Experimental live runs cannot certify acceptance with an unapproved suite.

> Live experimental run: real dependencies with an unapproved benchmark suite. Results are exploratory and cannot certify acceptance.

## Summary Counts

- **Total Cases:** 156
- **Executed Cases:** 156
- **Completed OK:** 154
- **Timeouts:** 2
- **Errors:** 0
- **Missing Results:** 0

## Gate Evaluation

| Gate | Status | Details |
|---|---|---|
| `routing_guardrails` | `fail` | Escalated 31/63 |
| `retrieval_safety` | `pass` | 0 safety violations |
| `retrieval_recall` | `fail` | 0.6176 < 0.8 |
| `retrieval_recall_at_3` | `fail` | 0.6176 < 0.8 |
| `grounded_claims` | `insufficient_evidence` | Missing or incomplete human claim annotations |
| `ml_macro_f1` | `not_evaluated` | ML holdout benchmark not imported |
| `live_latency` | `fail` | 17.3999s > 12.0s |
| `live_warm_p95_seconds` | `fail` | 17.3999s > 12.0s |
| `oversight_compliance` | `fail` | 1 oversight scenarios failed |

## Component Metrics

### Routing & Safety
- **Routing Coverage:** 0.4231 (CI: (0.3483, 0.5015))
- **Selective Accuracy:** 0.8182 (CI: (0.7085, 0.8928))
- **Final Draft Yield:** 0.0833
- **Escalation Guardrail:** 31/63 (Passed: False)

### Semantic Retrieval
- **Recall@3:** 0.6176
- **Hit@3:** 0.6176 (CI: (0.4504, 0.761))
- **False Evidence Rate:** 0.2951 (CI: (0.2214, 0.3813))
- **Safety Violations:** 0 (Guardrail: True)

### Automated Drafting
- **Draft Expected:** 34
- **Draft Produced:** 6
- **Draft Coverage:** 0.1765

