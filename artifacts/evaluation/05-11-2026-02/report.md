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
| `routing_guardrails` | `insufficient_evidence` | No must_escalate cases present in benchmark suite |
| `retrieval_safety` | `pass` | 0 safety violations |
| `retrieval_recall` | `fail` | 0.2 < 0.8 |
| `retrieval_recall_at_3` | `fail` | 0.2 < 0.8 |
| `grounded_claims` | `insufficient_evidence` | Missing or incomplete human claim annotations |
| `ml_macro_f1` | `not_evaluated` | ML holdout benchmark not imported |
| `live_latency` | `pass` | 0.03s <= 12.0s |
| `live_warm_p95_seconds` | `pass` | 0.03s <= 12.0s |
| `oversight_compliance` | `pass` | 7/7 scenarios passed |

## Component Metrics

### Routing & Safety
- **Routing Coverage:** 0.98 (CI: (0.895, 0.9965))
- **Selective Accuracy:** 0.2245 (CI: (0.1302, 0.3588))
- **Final Draft Yield:** 0.04
- **Escalation Guardrail:** 0/0 (Passed: N/A)

### Semantic Retrieval
- **Recall@3:** 0.2
- **Hit@3:** 0.2 (CI: (0.0567, 0.5098))
- **False Evidence Rate:** 0.0 (CI: (0.0, 0.0876))
- **Safety Violations:** 0 (Guardrail: True)

### Automated Drafting
- **Draft Expected:** 10
- **Draft Produced:** 2
- **Draft Coverage:** 0.2

### Verified ML Model
- **Model Type:** distilbert_sequence_classification
- **Package Version:** v1.0.0
- **Macro-F1:** None
- **Verification Status:** unverified

### Human Oversight & Persistence
- **Total Scenarios:** 7
- **Passed Scenarios:** 7
- **Failed Scenarios:** 0
- **Oversight Status:** pass

### Request Latency
- **Warm p95 Total:** 0.03s
- **LLM Branch p95:** N/As
- **No-LLM Branch p95:** N/As

