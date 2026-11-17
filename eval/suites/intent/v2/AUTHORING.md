# Intent benchmark v2: authoring record

- **Author:** independent AI agent session
- **Date:** 2026-11-13
- **File:** `raw_cases.jsonl` (236 rows, one JSON object per line, UTF-8)

## Sources read

Exactly two files were read:

1. `docs/product/requirements.md`
2. `docs/design/intent-label-definitions.md`

Nothing else was opened, listed, or searched: no other file in the repository, no existing dataset or benchmark, no training data, no model output, no git history, and no web page. Every message was written from general knowledge of how online-shop customers write.

## Composition

| Slice | Group | Rows per group | Groups | Rows |
|---|---|---|---|---|
| `supported` | each of the 12 supported intents | 8 | 12 | 96 |
| `unsupported` | each of the 34 unsupported intents | 2 | 34 | 68 |
| `out_of_scope` | `general` | 15 | 1 | 15 |
| `out_of_scope` | `other_domain` | 15 | 1 | 15 |
| `out_of_scope` | `ecommerce_not_in_taxonomy` | 15 | 1 | 15 |
| `out_of_scope` | `vague` | 12 | 1 | 12 |
| `out_of_scope` | `multi_intent` | 15 | 1 | 15 |
| **Total** | | | | **236** |

`true_intent` is the label for `supported` and `unsupported` rows, `null` for `out_of_scope` rows, except `multi_intent`, where it is the primary request chosen by decision D3.

## Order references

Rows with `has_order_reference: true`: **46** in total.

- `supported`: 23 of 96
- `unsupported`: 20 of 68 (43 of 164 labelled rows, about 26%)
- `out_of_scope` (`multi_intent` only): 3

`has_order_reference` is true exactly when the text contains `[ORDER_ID_1]`.

## Placeholder convention

Identifiers never appear in raw form. A specific order is written as `[ORDER_ID_1]`; other identifiers use `[TRACKING_ID_1]`, `[PHONE_1]`, `[NAME_1]`, and `[EMAIL_1]`. The indexed form follows the authoring brief for this set. The label definitions document describes training text normalized to the type alone (`[ORDER_ID]`); any consumer that needs that form can strip the `_1` suffix mechanically.

## Style

Lengths range from 3 to 23 words. Tone varies (polite, angry, terse, chatty) and so does structure (questions, statements, imperatives, two-sentence messages). About one row in six is written informally (lowercase start, missing punctuation, abbreviations). No deliberate typos were added; noisy variants are generated later by code.

## Labeling judgement calls

Decisions from the label definitions applied:

- **D1.** Status, location, or arrival questions that refer to the customer's own order or purchase, or a package tied to an order, are `track_order`, including questions about a specific order's arrival date. Questions that carry only a carrier tracking code and no order context are `track_delivery`.
- **D2.** `return_product` rows never name a channel. Rows that name a store or branch are `return_product_in_store`; rows that name post or courier pickup are `return_product_online`. Questions about the rules of returning (including who pays return postage) stay `return_policy`.
- **D3.** In `multi_intent` rows, `cancel_order` or `request_refund` is chosen first when present; otherwise the first request in the message. Some multi-intent rows pair a supported intent with an unsupported one, so the primary label can be either kind.

Boundaries the definitions describe, used deliberately to make supported rows hard:

- General delivery-duration questions are `delivery_time`; a specific order's progress or expected date is `track_order`; lateness beyond an estimate, loss, stuck parcels, wrong-house drop-offs, and failed or repeatedly rescheduled delivery attempts are `delivery_issue`.
- A question about why a delivery fee was charged is `shipping_costs`, not `payment_issue`. A question whether shipping is refunded is `refund_policy`.
- General refund timing questions (including timing after a cancellation) are `refund_policy`; questions about the customer's own refund already approved or issued are `refund_status`, including a case where the bank shows nothing yet.
- A refund request whose reason is a faulty product, a late delivery, or a product not as described is `request_refund`, because the request is money back. A report of a fault with no request is `product_issue`.
- Asking whether an order can still be cancelled is `cancel_order`, not `track_order`.
- A stuck payment page and a rejected gift card at payment are `payment_issue` (a payment problem), not `technical_issue` or `payment_methods`.
- Asking for a live agent about a specific order is `human_agent`; asking how to reach support in general is `customer_service`.

Judgement calls where the definitions are silent (plain meaning of the label name):

- Adding an item to an existing order is `add_product`, and removing an item from an existing order is `remove_product`, rather than `change_order`; `change_order` is used for changing an address or a size before shipping.
- Swapping a delivered item for another size or colour is `exchange_product`; an exchange that names a shop is `exchange_product_in_store`.
- A damaged box with a broken product is `damaged_delivery`, not `delivery_issue`.
- Forgotten passwords are `recover_password`; changing profile details (email, username, phone) is `change_account`; a correction request that invokes data protection rights, or corrects a misspelled name in the shop's records, is `request_right_to_rectification`.
- Feedback about the service is `submit_feedback`; a review or rating of a purchased product is `submit_product_feedback`; a suggestion for a new product variant is `submit_product_idea`.
- Restocking on the website is `availability_online`; general back-in-stock questions are `availability`; stock at a branch is `availability_in_store`.
- Paying an unpaid order is `pay`; accepted methods and instalments are `payment_methods`.
- `ecommerce_not_in_taxonomy` covers gift wrapping and message cards, loyalty points, jobs, marketplace selling, affiliate and influencer programmes, bulk business purchasing, packaging and carbon offsetting, assembly services, gift registries, donations, referral schemes, and press contacts. Topics a reader could map to a label (discounts, gift cards, warranties, newsletters, product sourcing) were avoided.
- `other_domain` includes some deliberately confusable messages (cancelling a hotel booking, a mortgage payment, an electricity bill, a home internet fault) whose domain is clearly not the shop.
- `vague` rows contain greetings, acknowledgements, and references to an unstated earlier issue, with no identifiable request.
