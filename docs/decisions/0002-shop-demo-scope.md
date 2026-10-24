# ADR-0002: Minimal shop demo scope

- **Status:** Accepted
- **Date:** 2026-10-23
- **Deciders:** Team
- **Related:** [Requirements §2](../product/requirements.md#2-scope), [ADR-0001](0001-system-architecture.md), [UI rules](../rules/ui.md)

## Context

- The requirements put a complete sales, payment, or delivery system out of scope and ask only for simulated business data.
- The team wants an e-commerce surface to demonstrate the full loop: a customer submits a request, staff handle it with SupportIQ, and the customer sees the approved reply. The loop also makes FR-04 visible: nothing reaches the customer without a staff action.
- Without a written boundary, a shop grows features that no requirement evaluates.

## Decision drivers

1. Stay inside the required scope.
2. Make the guardrails demonstrable end to end.
3. Spend UI effort on the staff console, which the requirements evaluate.

## Considered options

1. No shop: tickets come only from imported data.
2. A minimal shop demo with a locked feature list.
3. A basic e-commerce application with catalog, cart, and checkout.

## Decision

We will build a minimal shop demo at `/shop` in `frontend`, limited to this list:

| Included | Excluded |
|---|---|
| Choose a simulated customer (persona switch, no real sign-up) | Product catalog, cart, checkout |
| "My orders": order, shipment, and refund status | Payment; creating, changing, or cancelling real orders |
| "Contact support" form attached to an order, which creates a ticket | Real accounts, real personal or transaction data |
| See a reply after staff approve and send it | Any action that changes an order or money |

- The shop and the console read the same simulated data, owned by `backend`.
- Tickets come from two sources: the shop form, and bulk import from the shared scenario test set for evaluation.
- The shop has no transactional action. Only staff can send a reply, from `/console`.

## Consequences

### Positive

- The full loop can be demonstrated, and the staff-approval guardrail is visible.
- Shop and console show consistent data.

### Negative

- One more UI area to build and maintain.
- A permanent risk of scope creep.

### Follow-ups

- Any feature outside the table requires a new ADR.

## Pros and cons of the options

### No shop

- Good, because it is the least work.
- Bad, because the customer side of the loop and FR-04 are harder to demonstrate.

### Minimal shop demo

- Good, because it adds demo value at small cost.
- Bad, because it needs discipline to stay minimal.

### Basic e-commerce application

- Good, because it looks realistic.
- Bad, because it is out of scope, its effort is not evaluated, and it takes time from evaluated work.

## Validation

- Reviews reject shop features outside the table.
- A guardrail test proves a customer never sees a draft before staff send a reply ([TEST-26](../rules/testing.md#guardrail-tests)).
