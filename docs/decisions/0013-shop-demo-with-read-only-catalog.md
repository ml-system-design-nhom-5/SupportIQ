# ADR-0013: Shop demo with a read-only catalog

- **Status:** Accepted
- **Date:** 2026-11-05
- **Deciders:** Team
- **Related:** Supersedes [ADR-0002](0002-shop-demo-scope.md). [Requirements](../product/requirements.md) (FR-11, §2), [ADR-0001](0001-system-architecture.md), [ADR-0009](0009-demo-accounts-and-cookie-sessions.md), [ADR-0012](0012-roles-v1.md), [UI rules](../rules/ui.md#shop), [Design: contracts v1](../design/contracts-v1.md)

## Context

- [ADR-0002](0002-shop-demo-scope.md) fixed a minimal shop: a customer signs in, sees "My orders", contacts support about an order, and sees the reply after staff send it. It excluded a product catalog, a cart, and a checkout.
- FR-11 (Should) in the team's specification asks for a simple e-commerce website without AI, where payment and delivery exist only as a demonstration. The specification's architecture figure labels the storefront "demo checkout".
- The requirements keep a complete sales, payment, or delivery system and every transaction out of scope (§2). The repository guardrails stop any task that touches transactions ([AGENTS.md](../../AGENTS.md#guardrails), guardrail 6).
- The contracts v1 design guarantees that no operation changes orders, shipments, or refunds, and a contract test enforces it.
- Without products, the shop does not look like a shop, and an order's line items show only names.
- Seeded orders can hold any state that a scenario needs, such as a delayed shipment or a refund in progress. An order created in a demo checkout would have no such history.
- On 2026-10-28 the team chose a read-only catalog without a cart, checkout, or payment.

## Decision drivers

1. **Scope and safety:** no operation creates, changes, or cancels orders, payments, or refunds.
2. **Demonstration:** the shop is recognizably an e-commerce site during demos and user tests.
3. **Effort:** UI work stays focused on the staff console, which the requirements evaluate.

## Considered options

1. Keep ADR-0002 as it is.
2. Add a read-only product catalog to the ADR-0002 scope.
3. Add a catalog, a cart, and a demo checkout that creates simulated orders.

## Decision

We adopt option 2. The statements below are normative. The shop at `/shop` in `frontend` is limited to this list:

| Included | Excluded |
|---|---|
| Sign in to a seeded customer account ([ADR-0009](0009-demo-accounts-and-cookie-sessions.md)); no sign-up | Sign-up, profile editing, real accounts |
| A read-only product catalog: a paginated product list and a product detail page | Cart, checkout, payment, inventory management, wishlists, reviews, ratings, search, filters, recommendations |
| "My orders": order, shipment, and refund status; each order line links to its catalog product | Creating, changing, or cancelling orders; any action that changes an order, a shipment, a refund, or money |
| A "Contact support" form attached to one of the customer's orders, which creates a ticket | Support questions not attached to an order |
| The reply, once staff have sent it | Any AI output, before or after the reply |
| A neutral product image from the design system, the same for every product | Product photos |

1. Products are simulated data owned by `backend`, produced by the same deterministic, versioned seed script as orders ([DATA-04](../rules/data-and-ml.md#sources-and-acceptable-use)), and read through the `CommerceGateway` port. A product has a `product_id`, a name, a description, a category, and a price (`Money`).
2. The catalog is read-only. No operation creates, changes, or deletes a product, an order, a shipment, or a refund. The contract test that fails on any write to commerce resources covers products too.
3. The catalog is available only to signed-in customers, like the rest of `/v1/shop/` ([SEC-14](../rules/security-and-privacy.md#authentication-and-authorization)).
4. Tickets still come from two sources: the shop form, and the bulk import from the shared scenario test set.
5. The shop uses the design system and adds no component outside it ([UI-38](../rules/ui.md#shop)).
6. When this ADR is accepted, ADR-0002 is marked **Superseded by ADR-0013**.

## Consequences

### Positive

- The shop looks like an e-commerce site, and order lines link to real catalog entries.
- No write path is added, so the "no transaction" guarantee and its contract test stay intact.
- FR-11 is met without building a sales system.

### Negative

- Two more read operations in the `backend` contract, and two more screens.
- The specification's "demo payment and delivery" is not built. The next revision of the specification records this ([requirements appendix](../product/requirements.md#appendix-clarifications-of-the-submitted-specification), row 12).
- The scope-creep risk of ADR-0002 remains.

### Follow-ups

- Contracts v1 design: the `Product` entity, product links on order lines, and the operations `listShopProducts` and `getShopProduct`.
- Seed script: the product catalog.

## Pros and cons of the options

### Keep ADR-0002

- Good, because it is the least work.
- Bad, because the shop does not look like a shop, and FR-11's "simple e-commerce website" is only partly met.

### Read-only catalog

- Good, because it adds realism without any write path.
- Bad, because of the costs listed under Negative.

### Catalog, cart, and demo checkout

- Good, because it matches the specification's wording and makes the demo look complete.
- Bad, because creating orders is a transaction that the requirements and guardrail 6 put out of scope. It also breaks the guarantee that no operation writes commerce data, its new orders have no history for the evaluation scenarios, and it takes effort from evaluated work.

## Validation

- Reviews reject shop features outside the table.
- The contract test lists every `backend` operation and fails on any write to products, orders, shipments, or refunds.
- A guardrail test proves that a customer never sees AI output ([TEST-26](../rules/testing.md#guardrail-tests)).
