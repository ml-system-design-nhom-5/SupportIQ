# SupportIQ System Evaluation Report

- **Execution State:** `completed`
- **Certification Status:** `simulated_mock_rejected`
- **Evidence Kind:** `simulated`
- **Mandatory Acceptance Gates Passed:** `False`
- **Summary Reason:** Simulated mock runs cannot satisfy live acceptance criteria.

> [!WARNING]
> **Simulated Mock Run:** This run was executed using offline simulated mocks. Simulated evidence cannot certify live production acceptance criteria.

## Summary Counts

- **Total Cases:** 5
- **Executed Cases:** 5
- **Completed OK:** 5
- **Timeouts:** 0
- **Errors:** 0
- **Missing Results:** 0

## Gate Evaluation

| Gate | Status | Details |
|---|---|---|
| `routing_guardrails` | `fail` | Escalated 0/3 |
| `retrieval_safety` | `pass` | 0 safety violations |
| `retrieval_recall` | `fail` | 0.5 < 0.8 |
| `retrieval_recall_at_3` | `fail` | 0.5 < 0.8 |
| `grounded_claims` | `insufficient_evidence` | Missing or incomplete human claim annotations |
| `ml_macro_f1` | `not_evaluated` | ML holdout benchmark not imported |
| `live_latency` | `pass` | 0.0325s <= 12.0s |
| `live_warm_p95_seconds` | `pass` | 0.0325s <= 12.0s |
| `oversight_compliance` | `pass` | 7/7 scenarios passed |

## Component Metrics

### Routing & Safety
- **Routing Coverage:** 0.4 (CI: (0.1176, 0.7693))
- **Selective Accuracy:** 0.5 (CI: (0.0945, 0.9055))
- **Final Draft Yield:** 0.2
- **Escalation Guardrail:** 0/3 (Passed: False)

### Semantic Retrieval
- **Recall@3:** 0.5
- **Hit@3:** 0.5 (CI: (0.0945, 0.9055))
- **False Evidence Rate:** 0.0 (CI: (0.0, 0.5615))
- **Safety Violations:** 0 (Guardrail: True)

### Automated Drafting
- **Draft Expected:** 2
- **Draft Produced:** 1
- **Draft Coverage:** 0.5

### Verified ML Model
- **Model Type:** N/A
- **Package Version:** N/A
- **Macro-F1:** None
- **Verification Status:** N/A

### Human Oversight & Persistence
- **Total Scenarios:** 7
- **Passed Scenarios:** 7
- **Failed Scenarios:** 0
- **Oversight Status:** pass

### Request Latency
- **Warm p95 Total:** 0.0325s
- **LLM Branch p95:** N/As
- **No-LLM Branch p95:** N/As

