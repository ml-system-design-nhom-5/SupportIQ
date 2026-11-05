# SupportIQ System Evaluation Report

- **Execution State:** `completed`
- **Certification Status:** `simulated_mock_rejected`
- **Evidence Kind:** `simulated`
- **Mandatory Acceptance Gates Passed:** `False`
- **Summary Reason:** Simulated mock runs cannot satisfy live acceptance criteria.

> [!WARNING]
> **Simulated Mock Run:** This run was executed using offline simulated mocks. Simulated evidence cannot certify live production acceptance criteria.

## Summary Counts

- **Total Cases:** 50
- **Executed Cases:** 50
- **Completed OK:** 50
- **Timeouts:** 0
- **Errors:** 0
- **Missing Results:** 0

## Gate Evaluation

| Gate | Status | Details |
|---|---|---|
| `routing_guardrails` | `fail` | Escalated 6/18 |
| `retrieval_safety` | `pass` | 0 safety violations |
| `retrieval_recall` | `fail` | 0.1429 < 0.8 |
| `retrieval_recall_at_3` | `fail` | 0.1429 < 0.8 |
| `grounded_claims` | `insufficient_evidence` | Missing or incomplete human claim annotations |
| `ml_macro_f1` | `pass` | 0.9952684306823985 >= 0.85 |
| `live_latency` | `pass` | 0.0546s <= 12.0s |
| `live_warm_p95_seconds` | `pass` | 0.0546s <= 12.0s |
| `oversight_compliance` | `pass` | 7/7 scenarios passed |

## Component Metrics

### Routing & Safety
- **Routing Coverage:** 0.62 (CI: (0.4815, 0.7414))
- **Selective Accuracy:** 0.4194 (CI: (0.2642, 0.5923))
- **Final Draft Yield:** 0.06
- **Escalation Guardrail:** 6/18 (Passed: False)

### Semantic Retrieval
- **Recall@3:** 0.1429
- **Hit@3:** 0.1429 (CI: (0.0401, 0.3994))
- **False Evidence Rate:** 0.0 (CI: (0.0, 0.0964))
- **Safety Violations:** 0 (Guardrail: True)

### Automated Drafting
- **Draft Expected:** 14
- **Draft Produced:** 3
- **Draft Coverage:** 0.2143

### Verified ML Model
- **Model Type:** supportiq_distilbert
- **Package Version:** v1.0.0
- **Macro-F1:** 0.9952684306823985
- **Verification Status:** verified

### Human Oversight & Persistence
- **Total Scenarios:** 7
- **Passed Scenarios:** 7
- **Failed Scenarios:** 0
- **Oversight Status:** pass

### Request Latency
- **Warm p95 Total:** 0.0546s
- **LLM Branch p95:** N/As
- **No-LLM Branch p95:** N/As

