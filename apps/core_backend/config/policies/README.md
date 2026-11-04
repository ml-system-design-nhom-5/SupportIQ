# Routing Policies and Escalation Matrix

## Overview
This directory contains deterministic intent routing policies for SupportIQ.
Routing decisions classify incoming queries using model predictions (`supportiq_distilbert`) and deterministic gates before any drafting or human assignment occurs.

## Policy Versions
- `intent_policy.v2.json`: Active routing policy specifying:
  - 46 Standard Bitext Intents (12 supported + 34 escalated)
  - Team assignments: `general_support`, `order_support`, `delivery_support`, `returns_support`, `payments_support`, `account_support`, `technical_support`, `product_support`, `feedback_support`, `sales_support`, `store_support`, `privacy_support`
  - Confidence and margin thresholds for high-risk and standard intents
  - Sensitive action intents: `cancel_order`, `request_refund`, `return_product`, `payment_issue`

## Safety & Fallback Rules
1. **Invalid Model Output / ML Failure**: Always routes to `manual_fallback` with reason `ml_unavailable` or `invalid_model_output`. Never invents fake regex confidence scores.
2. **Explicit Human Request**: When customer asks for a human agent or rule triggers, bypasses LLM and routes immediately to `general_support`.
3. **Threshold Gates**: Confidence and margin checks run BEFORE any sensitive processing. Low confidence results in `clarify` (or `escalate` if clarify attempt limit reached).
4. **Scope & Idempotency**: Order lookups verify ticket customer ownership. Repeated run IDs are served idempotently.
