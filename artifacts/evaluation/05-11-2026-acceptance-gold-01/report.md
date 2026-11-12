# SupportIQ System Evaluation Report

- **Execution State:** `completed`
- **Certification Status:** `pending_human_acceptance`
- **Evidence Kind:** `live`
- **Mandatory Acceptance Gates Passed:** `False`
- **Summary Reason:** Mandatory gates not satisfied: routing_guardrails (fail), retrieval_recall_at_3 (fail), grounded_claims (insufficient_evidence), oversight_compliance (fail)

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
| `routing_guardrails` | `fail` | Escalated 41/63 |
| `retrieval_safety` | `pass` | 0 safety violations |
| `retrieval_recall` | `fail` | 0.3824 < 0.8 |
| `retrieval_recall_at_3` | `fail` | 0.3824 < 0.8 |
| `grounded_claims` | `insufficient_evidence` | Missing or incomplete human claim annotations |
| `ml_macro_f1` | `pass` | 0.9952684306823985 >= 0.85 |
| `live_latency` | `pass` | 1.1247s <= 12.0s |
| `live_warm_p95_seconds` | `pass` | 1.1247s <= 12.0s |
| `oversight_compliance` | `fail` | 4 oversight scenarios failed |

## Component Metrics

### Routing & Safety
- **Routing Coverage:** 0.2821 (CI: (0.2173, 0.3572))
- **Selective Accuracy:** 0.75 (CI: (0.6056, 0.8543))
- **Final Draft Yield:** 0.1282
- **Escalation Guardrail:** 41/63 (Passed: False)

### Semantic Retrieval
- **Recall@3:** 0.3824
- **Hit@3:** 0.3824 (CI: (0.239, 0.5496))
- **False Evidence Rate:** 0.2049 (CI: (0.1428, 0.285))
- **Safety Violations:** 0 (Guardrail: True)

### Automated Drafting
- **Draft Expected:** 34
- **Draft Produced:** 7
- **Draft Coverage:** 0.2059

### Verified ML Model
- **Model Type:** supportiq_distilbert
- **Package Version:** v1.0.0
- **Macro-F1:** 0.9952684306823985
- **Verification Status:** verified

### Human Oversight & Persistence
- **Total Scenarios:** 7
- **Passed Scenarios:** 3
- **Failed Scenarios:** 4
- **Oversight Status:** fail

### Request Latency
- **Warm p95 Total:** 1.1247s
- **LLM Branch p95:** N/As
- **No-LLM Branch p95:** N/As

