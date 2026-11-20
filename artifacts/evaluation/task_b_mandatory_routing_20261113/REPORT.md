# Task B General Mandatory Routing Diagnostic (2026-11-13)

- Workspace commit: `0772d09`
- Serving model: `F:/Năm 3/SD/project/SupportIQ/artifacts/models/trained/distilbert-supportiq`
- Offline guarantee: zero live LLM requests (`_SpyOfflineLLM.calls == 0`), uninjected fault cases separated as `NOT_EXECUTED`.

## Before vs After (Serving `distilbert-supportiq`)

| Metric | Engine Before | Engine After | HTTP `/predict -> IntentClient -> decide_route` After |
| --- | ---: | ---: | ---: |
| Acceptance 156 exact match | 74 / 156 | 114 / 156 | 116 / 156 |
| Mandatory N=63 (all incl. uninjected faults) | 21 / 63 | 55 / 63 | 39 / 63 |
| Mandatory unfaulted (N=60) | 19 / 60 | 53 / 60 | 37 / 60 |
| Unfaulted mandatory unsafe `retrieve_draft` leaks | 0 | 0 | 12 |
| `draft_expected` (N=88) raw / correct intent | 51 / 44 | 51 / 44 | 39 / 33 |
| `ml_oos` (N=80) unsafe `retrieve_draft` leaks | 0 | 0 | 2 |

## Uninjected Fault Cases (`NOT_EXECUTED`)

- `unc-track_order-03` (`fault=ml_timeout`): `NOT_EXECUTED` (never marked PASS under static evaluation).
- `unc-return_policy-04` (`fault=encoder_failure`): `NOT_EXECUTED` (never marked PASS under static evaluation).
- `unc-track_order-05` (`fault=commerce_unauthorized`): `NOT_EXECUTED` (never marked PASS under static evaluation).
- `final-case-21` (`injected_expired_fixture`, uninjected in static JSON): `NOT_EXECUTED`.

## Remaining Unfaulted Mandatory Misses on Serving Model

- `uns-return_product_in_store-01`: true=`return_product_in_store` pred=`return_policy` (p=0.506) -> Engine=`manual_fallback` ['low_confidence', 'out_of_scope_intent'], HTTP+decide_route=`clarify`
- `uns-technical_issue-01`: true=`technical_issue` pred=`payment_issue` (p=0.262) -> Engine=`manual_fallback` ['low_confidence', 'out_of_scope_intent', 'requires_authority', 'no_valid_document'], HTTP+decide_route=`clarify`
- `uns-track_delivery-01`: true=`track_delivery` pred=`shipping_costs` (p=0.365) -> Engine=`manual_fallback` ['low_confidence', 'out_of_scope_intent'], HTTP+decide_route=`clarify`
- `uns-wrong_item-01`: true=`wrong_item` pred=`return_product` (p=0.340) -> Engine=`manual_fallback` ['low_confidence', 'out_of_scope_intent', 'requires_authority'], HTTP+decide_route=`clarify`
- `una-product_information-01`: true=`product_information` pred=`delivery_time` (p=0.180) -> Engine=`manual_fallback` ['low_confidence', 'out_of_scope_intent'], HTTP+decide_route=`clarify`
- `una-refund_policy-01`: true=`refund_policy` pred=`payment_issue` (p=0.628) -> Engine=`manual_fallback` ['low_confidence', 'requires_authority'], HTTP+decide_route=`clarify`
- `una-sales_period-01`: true=`sales_period` pred=`return_policy` (p=0.123) -> Engine=`manual_fallback` ['low_confidence', 'out_of_scope_intent'], HTTP+decide_route=`clarify`
