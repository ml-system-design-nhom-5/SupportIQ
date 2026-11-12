# SupportIQ System Evaluation Report

- **Execution State:** `completed`
- **Certification Status:** `simulated_mock_rejected`
- **Evidence Kind:** `simulated`
- **Mandatory Acceptance Gates Passed:** `False`
- **Summary Reason:** Simulated mock runs cannot satisfy live acceptance criteria.

> [!WARNING]
> **Simulated Mock Run:** This run was executed using offline simulated mocks. Simulated evidence cannot certify live production acceptance criteria.

## Summary Counts

- **Total Cases:** 156
- **Executed Cases:** 156
- **Completed OK:** 152
- **Timeouts:** 2
- **Errors:** 2
- **Missing Results:** 0

## Gate Evaluation

| Gate | Status | Details |
|---|---|---|
| `routing_guardrails` | `fail` | Escalated 18/63 |
| `retrieval_safety` | `pass` | 0 safety violations |
| `retrieval_recall` | `fail` | 0.4118 < 0.8 |
| `retrieval_recall_at_3` | `fail` | 0.4118 < 0.8 |
| `grounded_claims` | `insufficient_evidence` | Missing or incomplete human claim annotations |
| `ml_macro_f1` | `not_evaluated` | ML holdout benchmark not imported |
| `live_latency` | `pass` | 0.0557s <= 12.0s |
| `live_warm_p95_seconds` | `pass` | 0.0557s <= 12.0s |
| `oversight_compliance` | `pass` | 7/7 scenarios passed |

## Component Metrics

### Routing & Safety
- **Routing Coverage:** 0.6154 (CI: (0.5371, 0.6881))
- **Selective Accuracy:** 0.3438 (CI: (0.2564, 0.4431))
- **Final Draft Yield:** 0.1026
- **Escalation Guardrail:** 18/63 (Passed: False)

### Semantic Retrieval
- **Recall@3:** 0.4118
- **Hit@3:** 0.4118 (CI: (0.2637, 0.5778))
- **False Evidence Rate:** 0.0164 (CI: (0.0045, 0.0578))
- **Safety Violations:** 0 (Guardrail: True)

### Automated Drafting
- **Draft Expected:** 34
- **Draft Produced:** 14
- **Draft Coverage:** 0.4118

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
- **Warm p95 Total:** 0.0557s
- **LLM Branch p95:** N/As
- **No-LLM Branch p95:** N/As

