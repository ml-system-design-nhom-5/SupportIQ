# Independent intent dev set v1: authoring notes

- **File:** `cases.synthetic-dev-only.jsonl` (297 rows, JSON Lines, UTF-8)
- **Author:** an independent AI agent session
- **Date:** 2026-11-14
- **Purpose:** development (validation) data for tuning, for example thresholds and model choices. **This is not a test set** and must not be reported as held-out test performance.

## Sources and independence

The author read exactly two files:

1. `docs/product/requirements.md`
2. `docs/design/intent-label-definitions.md`

Nothing else in the repository was opened, listed or searched: no training data, benchmarks, scenario sets, model artifacts, pipeline code, tests, other design documents or decision records. No git history and no web sources were used. All messages were written from general knowledge of how online-shop customers write. They are synthetic and contain no real personal data.

Caveat inherited from the source: the label definitions document states that its first version was drafted after its author viewed benchmark failure cases, so some of its boundaries may reflect those cases. This set labels by the document as it stands; if reviewers change a boundary, the affected rows should be relabelled.

## Composition

| Kind | Group / category | Per label or category | Rows |
|---|---|---|---|
| `labelled` | Supported intents (12) | 10 each | 120 |
| `labelled` | Unsupported: `return_product_in_store`, `return_product_online`, `track_delivery`, `missing_item`, `product_issue`, `wrong_item`, `order_history`, `product_information`, `close_account` (9) | 8 each | 72 |
| `labelled` | Other unsupported intents (25) | 2 each | 50 |
| `oos` | `general` | | 6 |
| `oos` | `other_domain` | | 6 |
| `oos` | `ecommerce_not_in_taxonomy` | | 8 |
| `oos` | `vague` | | 10 |
| `multi` | `multi_intent` | | 25 |
| **Total** | | | **297** |

Order references (`has_order_reference: true`): 59 of the 242 labelled rows (37 supported, 22 unsupported), about a quarter; 64 in the whole file, including 5 multi-intent rows. No out-of-scope row references an order.

Other properties: lengths range from 3 to 38 words; about one row in six is informal (lowercase, missing punctuation, abbreviations); many labelled rows are a single request written as two sentences or joined with "and"/"but", typically a request followed by its reason or context.

## Row format

```
{"id": "<kind>-<intent or category>-<NN>", "kind": "labelled"|"oos"|"multi", "true_intent": "<label>" or null,
 "category": "<category>" (oos and multi only), "has_order_reference": true|false, "text": "<message>"}
```

Multi-intent rows use the id prefix `multi-multi_intent-`.

## Placeholder convention

Identifiers never appear raw. A message about a specific order uses `[ORDER_ID_1]`; other identifiers use `[TRACKING_ID_1]`, `[PHONE_1]`, `[NAME_1]` and `[EMAIL_1]`. `has_order_reference` is true exactly when the text contains `[ORDER_ID_1]`.

Note: the label definitions document describes the normalized training form without the index (`[ORDER_ID]`, `[TRACKING_ID]`, `[NAME]`). This set follows the indexed form it was commissioned with; strip the `_1` suffix if a consumer expects the normalized form.

## Labelling judgement calls

Labels follow the label definitions document, including D1, D2 and D3. Where it is silent, the plain meaning of the label name was used. The calls below are described in general terms.

- **Order status vs carrier tracking (D1).** A tracking code or package counts as `track_order` when the message ties it to the customer's own order. A tracking code, courier website or parcel with no order context, including a parcel someone else ordered, is `track_delivery`. No `track_delivery` row contains an order placeholder.
- **Order status vs general delivery time.** A question about when the customer's own, already placed order will arrive is `track_order`, even without an ID. A hypothetical or general question ("if I order today", "how long does it take") is `delivery_time`.
- **Delivery problems.** A parcel that is late beyond its estimate, stuck, lost, misdelivered, marked delivered but not received, or affected by courier behaviour is `delivery_issue`. A parcel that arrived but lacks one or more items is `missing_item`; a parcel that arrived damaged is `damaged_delivery`; a different product or size is `wrong_item`.
- **Return channel (D2).** A return request that names a physical store or branch is `return_product_in_store`; one that names online, the website, post, mail, a return label or courier pickup is `return_product_online`. A generic phrase such as "send back" was not treated as naming a channel and stays `return_product`. A question about the rules of a channel stays `return_policy`.
- **Rules vs action for returns and refunds.** Asking whether something is eligible or allowed, even about a specific order, is `return_policy` or `refund_policy`; asking to start a return or to get money back is `return_product` or `request_refund`. Questions about where refunds go and whether fees are refunded are `refund_policy`.
- **Defect report vs refund request.** A message that only reports a fault is `product_issue`. When the customer asks for money back, the label is `request_refund`, even when the fault or a late delivery is given as the reason. A request to refund a price difference or a delivery fee is also `request_refund`.
- **Refund status vs refund request.** A refund the customer says was already requested, approved or issued is `refund_status`. Asking to claim a refund for an item already sent back, with no sign that a refund was requested, is `request_refund`.
- **Payment problems vs payment questions.** Declines, double charges, debits without confirmation and stuck payments are `payment_issue`; accepted methods are `payment_methods`; how to pay or paying an outstanding amount is `pay`.
- **Human agent vs customer service.** Asking to talk to, be called by or be transferred to a person is `human_agent`, including with an order reference. Asking for contact channels (phone number, support contact) is `customer_service`.
- **Account vs order wording.** Cancelling or deleting an account is `close_account` even when the word "cancel" is used. Updating a saved profile address or email is `change_account`; changing a specific order's address or size is `change_order`. A formal request to correct inaccurate personal data, or a misspelled name in records, is `request_right_to_rectification`.
- **Basket vs order.** `add_product` and `remove_product` were read as adding to or removing from the basket or cart.
- **Exchange vs return.** Swapping for another size or model is `exchange_product`; naming a store or branch for the swap makes it `exchange_product_in_store`.
- **Order history.** Viewing past orders or recalling what an earlier order contained is `order_history`.
- **Out of scope.** `ecommerce_not_in_taxonomy` covers shop topics no label covers (for example discounts, loyalty, gift wrapping, price matching, selling on the marketplace, jobs, bulk pricing). `vague` covers messages with no identifiable request.
- **Multi-intent primary (D3).** `true_intent` is the request that requires authority (`cancel_order` or `request_refund`) when one is present; when both are present, the one that appears first. Otherwise it is the first request in the text, in reading order. `human_agent` was not treated as an authority intent, because the requirements state that a `human_agent` request does not require authority. Asking whether an order can still be cancelled counts as a `cancel_order` request. Every multi-intent row is expected to be flagged (low confidence, clarification or escalation), never drafted directly.

## Validation

A short Python script checked: JSON parsing, field sets per kind, unique ids and unique texts (case-insensitive), labels against the 46-label list, exact counts per kind, intent and category, placeholder whitelist, the order-reference flag against the text, absence of long raw numbers, and word counts. All checks passed.
