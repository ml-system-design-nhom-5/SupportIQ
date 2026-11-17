# Design: Intent label definitions (product semantics)

- **Status:** Draft
- **Owner:** ML engineer
- **Reviewers:** team
- **Last reviewed:** 2026-11-17
- **Related:** [requirements §3.2](../product/requirements.md#32-in-scope-intents), [intent model retraining](intent-model-retraining.md), [DATA-03](../rules/data-and-ml.md#sources-and-acceptable-use), [DATA-28](../rules/data-and-ml.md#leakage)

Defines what each supported intent means for this product, so that training rows and dev cases written for the [intent model retraining](intent-model-retraining.md) are labeled consistently. Sources: [requirements §3.2](../product/requirements.md#32-in-scope-intents), the approved KB (`data/knowledge/approved_kb.v2.json`), and the simulated order data (`data/knowledge/mock_orders.json`).

The first version was drafted on 2026-11-06 after its author had viewed failure cases from `data/benchmarks/system/v1` and `data/benchmarks/autoeval/v1`. The boundaries below may therefore reflect those test cases, which DATA-28 does not allow. Reviewers check each definition against the requirements and the KB alone, and change any boundary that only the benchmark supports.

## Why this document exists

The model is trained on Bitext, whose labels follow Bitext's own conventions. Several of them differ from
what the product means by the same intent name:

| Label | Bitext usage (observed in the training CSV) | Product meaning (from KB / requirements) |
|---|---|---|
| `track_order` | Mostly *tracking a replacement or exchange item* | Status / location / ETA of the customer's own order, incl. its shipment |
| `track_delivery` | "Where is my package / shipment" without an order | Carrier-level tracking without an order reference ([D1](#d1-track_order-and-track_delivery-stay-separate)) |
| `refund_policy` | "Where can I read your refund policy" | The refund rules: eligibility, conditions, **processing and receipt timelines** per payment method |
| `delivery_time` | "Delivery date of my order" | General delivery duration and service levels ("how long does shipping take") |

Training only on Bitext therefore teaches the model Bitext's boundaries. Rows written to the definitions
below are added to training so the model learns the product's boundaries.

## The 12 supported intents

| Intent | Use when the customer… | Typical cues | Not this intent if… |
|---|---|---|---|
| `track_order` | wants the status, location, progress or expected arrival of **their own order** (order ID, "my order", "my purchase", or a package tied to an order) | order ID, "my order", "where is", "status", "still processing", "shipped yet" | it is a general "how long does shipping take" question → `delivery_time`; it reports a problem (late beyond ETA, lost, marked delivered but missing) → `delivery_issue` |
| `cancel_order` | wants to cancel an order, or asks whether / how it can be cancelled | cancel, call off, stop the order, no longer want | they want to change items/address → `change_order`; they want money back for a delivered order → `request_refund` / `return_product` |
| `delivery_time` | asks how long delivery generally takes, delivery service levels, or delivery days/windows | how long, business days, express, same-day, weekend delivery | it is about a specific order's current status → `track_order` |
| `delivery_issue` | reports a problem with a delivery: late beyond the estimate, lost, stuck in transit, marked delivered but not received, wrong address, courier problems | never arrived, stuck, delayed, lost, marked delivered, courier | the item arrived damaged → `damaged_delivery`; an item is missing from the box → `missing_item`; a different product arrived → `wrong_item` |
| `shipping_costs` | asks about shipping fees, free-shipping thresholds, or why a fee was charged | shipping fee, delivery charge, free shipping, cost to ship | it is about how long shipping takes → `delivery_time` |
| `return_policy` | asks about the return rules: return window, conditions, non-returnable categories, who pays return shipping | can I return, how many days, conditions, non-returnable, opened item | they want to start a return for a specific item → `return_product` |
| `return_product` | wants to return a specific item / start a return, or asks for the steps to do so | send back, return this, start a return, return request | they only ask what the rules are → `return_policy`; they name a return channel (in store, online, by post, courier pickup) → [D2](#d2-a-named-return-channel-selects-the-channel-intent) |
| `refund_policy` | asks about refund rules: eligibility, conditions, **how long refunds take**, where the money goes per payment method | refund rules, how long does a refund take, credited back, business days, store credit | it is about the progress of **their own** refund → `refund_status`; they want a refund → `request_refund` |
| `request_refund` | asks to get money back for an order or item | refund me, money back, reimburse, claim a refund | they ask about the status of a refund already requested → `refund_status` |
| `refund_status` | asks about the progress of **their own** refund already requested or approved | my refund, where is my refund, not received my refund yet, still pending | the question is general ("how long do refunds take") → `refund_policy` |
| `payment_issue` | reports a payment problem: declined, charged twice, debited but order unconfirmed, payment stuck | declined, charged twice, double charge, debited, payment failed | they ask which methods are accepted → `payment_methods`; how to pay → `pay` |
| `human_agent` | wants to talk to a person / live agent | real person, human, agent, representative, call me | it is a general customer-service contact question → `customer_service` |

## Confusable neighbours outside the supported set

These stay labelled with their Bitext intent and are routed to manual handling (ESC-02):
`track_delivery`, `damaged_delivery`, `missing_item`, `wrong_item`, `change_order`, `order_history`,
`payment_methods`, `pay`, `return_product_in_store`, `return_product_online`, `exchange_product`,
`customer_service`, `store_opening_hours`, `product_information`, `availability`, `technical_issue`.

## Decisions

### D1. `track_order` and `track_delivery` stay separate

The labels are not merged. A message that refers to the customer's order (an order placeholder, "my order",
"my purchase", or a package tied to an order) is `track_order`. Carrier-level tracking with no order context,
for example a question about a courier's tracking code or website, is `track_delivery`.

### D2. A named return channel selects the channel intent

A return request that names a channel is labelled with the Bitext channel intent: in a physical store or
branch → `return_product_in_store`; online, by post, or by courier pickup → `return_product_online`. Both are
outside the 12 supported intents and go to manual handling (ESC-02). A return request without a channel is
`return_product`. A question about the rules of a channel ("is there a fee to return by post?") is still
`return_policy`.

Reasons: Bitext contains about 980 rows for each channel intent, all with an explicit channel cue, so the rule
matches the training data instead of contradicting it; and the KB documents only the in-app return process,
so channel-specific requests have no supporting document for a draft (FR-03, ESC-04).

### D3. Multi-intent messages are not training rows

Messages that ask for two or more different things ("cancel my order and refund me") are never added to
training data: a single-label example would teach the model to be confident on them. In evaluation sets each
one carries:

- `true_intent`: the primary request, chosen in this order: an intent that requires authority
  (`cancel_order`, `request_refund`, ESC-03) first, then the first request in the message;
- an expected outcome of "flagged": low confidence, clarification, or escalation, never a direct draft
  (NFR-02).

## Order identifiers in labelled text

Training and evaluation text uses the placeholder form that `ai-service` receives
([ADR-0010](../decisions/0010-pseudonymization-and-egress-control.md#placeholder-syntax)), normalized to the type
alone: `[ORDER_ID]`, `[TRACKING_ID]`, `[NAME]` (DATA-59). Raw identifiers such as `ORD-1001` never appear in
labelled data.
