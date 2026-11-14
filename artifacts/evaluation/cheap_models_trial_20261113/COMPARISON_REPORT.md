# Cheaper drafting model trial

User requested trying cheaper models after Hydrogen failures. This new allowance
was limited to three direct generation requests, one per model, no retries.
All three used the same question and retrieved snippets from the prior gateway
trial: POL-RET-001:2.0, POL-RET-003:2.0, POL-REFUND-001:1.0. Read timeout was
30 seconds. The classifier and embedding models were not changed.

| Model | HTTP | Result | Wall seconds | Observed conditional USD |
| --- | --- | --- | ---: | ---: |
| gemini-2.5-flash-lite | 404 | model unavailable | 0.5078 | unknown |
| gemini-3.1-flash-lite | 200 | draft with three validated source IDs | 1.6634 | 0.00072075 |
| gemini-3.5-flash-lite | 200 | draft with two validated source IDs | 2.0297 | 0.00098520 |

3.1 usage: 1,509 input + 229 candidate tokens, total 1,738.
3.5 usage: 1,509 input + 213 candidate tokens, total 1,722.
Neither response supplied thoughtsTokenCount; this is not proof of zero thinking.
Conditional estimates use observed token fields and published standard paid text
rates per million tokens, verified 2026-11-13:

- 2.5 Flash-Lite: input USD 0.10 / output USD 0.40.
- 3.1 Flash-Lite: input USD 0.25 / output USD 1.50.
- 3.5 Flash-Lite: input USD 0.30 / output USD 2.50.

Source: https://aistudio.google.com/docs/pricing . Output rates include thinking.
Account tier, discounts, invoiced cost and charges on failed requests are unknown.
The raw record retains `complete_billed_cost_usd: null` for every model.

The coordinator's AI review found both successful drafts consistent with the
provided policy excerpts: 30 days for Tiki Trading and 7 days for marketplace
sellers, intact original packaging/accessories and no use/laundering, plus the
listed restricted categories. The 3.1 draft also stated the supported returned-
product inspection and personal-preference shipping-fee conditions. This is AI
review of one case per model, not an independent human study or full acceptance.

Decision: select gemini-3.1-flash-lite for the active private local environment,
then reload owned services. It was faster and cheaper in this one-case test.
This does not establish a reliability rate, p95 latency or superiority on all
support intents. No customer reply was sent. No extra generation is authorized
by this report; all three trial requests have been consumed.

Reload verified: root AiSettings resolves gemini-3.1-flash-lite from the private
local environment; backend port 8080 and AI port 8002 readiness both HTTP 200.
Tracked code defaults still select Hydrogen if no local model is specified; the
explicit local selection is 3.1 Flash-Lite. No credentials were changed.
