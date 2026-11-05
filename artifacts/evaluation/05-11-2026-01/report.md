# SupportIQ System Evaluation Report

- **Execution State:** `completed`
- **Evidence Kind:** `simulated`
- **Mandatory Acceptance Gates Passed:** `False`
- **Summary Reason:** Simulated mock runs cannot satisfy live acceptance criteria.

> [!WARNING]
> **Simulated Mock Run:** This run was executed using offline simulated mocks. Simulated evidence cannot certify live production acceptance criteria.

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
| `routing_guardrails` | `fail` | Escalated 20/63 |
| `retrieval_safety` | `pass` | 0 safety violations |
| `retrieval_recall` | `fail` | 0.0 < 0.8 |
| `retrieval_recall_at_3` | `fail` | 0.0 < 0.8 |
| `grounded_claims` | `insufficient_evidence` | Missing or incomplete human claim annotations |
| `ml_macro_f1` | `not_evaluated` | ML holdout benchmark not imported |
| `live_latency` | `pass` | 0.0362s <= 12.0s |
| `live_warm_p95_seconds` | `pass` | 0.0362s <= 12.0s |
| `oversight_compliance` | `fail` | 1 oversight scenarios failed |

## Component Metrics

### Routing & Safety
- **Routing Coverage:** 0.6154 (CI: (0.5371, 0.6881))
- **Selective Accuracy:** 0.3646 (CI: (0.2752, 0.4643))
- **Final Draft Yield:** 0.0
- **Escalation Guardrail:** 20/63 (Passed: False)

### Semantic Retrieval
- **Recall@3:** 0.0
- **Hit@3:** 0.0 (CI: (0.0, 0.1015))
- **False Evidence Rate:** 0.0 (CI: (0.0, 0.0305))
- **Safety Violations:** 0 (Guardrail: True)

### Automated Drafting
- **Draft Expected:** 34
- **Draft Produced:** 0
- **Draft Coverage:** 0.0

