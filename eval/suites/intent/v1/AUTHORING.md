# Authoring record: intent benchmark v1 (`raw_cases.jsonl`)

## Author and date

The cases in `raw_cases.jsonl` were written by an independent AI agent session on 2026-11-12. The messages were written from general knowledge of how online-shop customers write. No existing dataset, benchmark, training row, or model output was used.

## Sources read

The author read exactly two files, and nothing else in the repository or on the web:

1. `docs/product/requirements.md`
2. `docs/design/intent-label-definitions.md`

No file under `data/`, `artifacts/`, `pipeline/`, `apps/`, or `tests/` was opened, listed, or searched, and no git command was run. The only files written are `raw_cases.jsonl` and this record.

## Composition

| Slice | Category | Rows |
|---|---|---|
| `supported` | none (8 per intent, 12 intents) | 96 |
| `unsupported` | none (2 per intent, 34 intents) | 68 |
| `out_of_scope` | `general` | 15 |
| `out_of_scope` | `other_domain` | 15 |
| `out_of_scope` | `ecommerce_not_in_taxonomy` | 15 |
| `out_of_scope` | `vague` | 12 |
| `out_of_scope` | `multi_intent` | 15 |
| **Total** | | **236** |

Rows with `has_order_reference: true`: 51 (29 supported, 18 unsupported, 4 multi-intent). That is 47 of 164 supported and unsupported rows (about 29%).

`true_intent` is `null` for every out-of-scope row except `multi_intent`, where it holds the primary request chosen by Decision D3.

## Placeholder convention

- A message that refers to a specific order uses `[ORDER_ID_1]`. No raw order number appears in any message.
- Other identifiers use the same form: `[PHONE_1]` and `[TRACKING_ID_1]` appear; `[NAME_1]` and `[EMAIL_1]` are reserved for the same use.
- `has_order_reference` is `true` exactly when the text contains `[ORDER_ID_1]`. A message that mentions the customer's order in words but has no placeholder counts as `false`.
- The label definitions (section "Order identifiers in labelled text") normalize placeholders to the type alone (`[ORDER_ID]`). This set follows the numbered form requested for this task; a consumer that expects the normalized form strips the `_1` suffix.

## Labeling judgement calls

- A question about the cost of returning by mail is labeled `return_policy`, not `return_product_online`, following D2 (a question about a channel's rules stays `return_policy`).
- Sending an item back without a named channel is treated as no channel, so such requests are `return_product`. A courier pickup from home is labeled `return_product_online` (D2).
- A refund request that also states a product defect is labeled `request_refund`, because the message asks for money back; a defect report without any request is `product_issue`.
- A message saying the customer's own refund was issued but has not reached the bank is `refund_status`, not `refund_policy`, because it concerns their own refund.
- A charge above the checkout total is labeled `payment_issue` (a payment problem), not `request_refund`.
- A conditional cancel request (cancel only if the order has not shipped) is treated as a cancel request; in a multi-intent message, D3 then makes `cancel_order` the primary intent.
- In multi-intent messages, `human_agent` is not an authority intent under D3, so it does not override an earlier request; `request_refund` does, even when a delivery problem is reported first.
- A general question about support contact hours is labeled `customer_service`, not `store_opening_hours` or `human_agent`.
- Out-of-scope e-commerce topics (gift wrapping, price matching, jobs, marketplace selling, referral and affiliate programs, data sharing, recycling, gift registries) were chosen to avoid overlap with the 46 intents; topics that a reader could map to an existing intent, such as discount codes, gift card balance, warranties, or newsletter unsubscription, were left out.
- Vague messages were written without any cue that names a component or request; a bare complaint that something does not work was avoided because it could be read as `technical_issue`.
