# Serving (`dc7af8cf`) vs Locked Fit2 (`f695b1fe`) Live Flash-Lite 3.5 Comparison

- **Budget:** `18/24` prior + `3` used now = `21/24` (`rejected_before_network=0`, `max_attempts=1`, `retries=0`).
- **Owner & Policy Scope:** `demo-customer`, identical case `as_of`, active KB + real BGE, `CUDA_VISIBLE_DEVICES=""`, C candidate **REJECT** stands (3 answerable cases only; no universal claim).
- **Tokens / Thoughts:** prompt `5249`, candidate `404`, thoughts `None` (`omitted_all_attempts`, `complete_cost_known=False`).

| Arm | Case | Expected | Predicted (Conf) | Rec / Terminal | Attempts | Intent OK | Source OK | Latency (ms) |
| --- | --- | --- | --- | --- | ---: | --- | --- | ---: |
| `serving_dc7af8cf` | `final-case-02` | `return_product` | `return_policy` (0.7699) | `draft` / `draft_ready` | 1 | False | True | 2463.22 |
| `serving_dc7af8cf` | `final-case-03` | `refund_policy` | `payment_issue` (0.4416) | `abstain` / `abstained` | 0 | False | True | 210.6 |
| `serving_dc7af8cf` | `final-case-10` | `delivery_issue` | `delivery_issue` (0.2618) | `abstain` / `abstained` | 0 | True | True | 215.72 |
| `fit2_f695b1fe` | `final-case-02` | `return_product` | `return_product` (0.1319) | `abstain` / `abstained` | 0 | True | True | 17.68 |
| `fit2_f695b1fe` | `final-case-03` | `refund_policy` | `refund_policy` (0.9052) | `draft` / `draft_ready` | 1 | True | True | 1502.22 |
| `fit2_f695b1fe` | `final-case-10` | `delivery_issue` | `delivery_issue` (0.8911) | `draft` / `draft_ready` | 1 | True | True | 1997.29 |
