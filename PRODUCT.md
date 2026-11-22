# SupportIQ

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React, TypeScript, Vite, Radix primitives, Tailwind CSS, TanStack Query and React Router; FastAPI, SQLAlchemy and PostgreSQL, as specified in ADR-0003. The user requires native Windows execution without Docker.

## Users

Customers browse a read-only catalog, inspect their orders and request support. Staff review intent, evidence and drafts before replying. Managers handle authority-required tickets and reports. Administrators manage internal accounts and inspect deployed versions.

## Product Purpose

SupportIQ assists e-commerce support staff. A person reviews and sends every reply. AI never performs a transaction.

## Operating Context

Implement the approved console, shop, admin and backend-foundation designs from `origin/chore/fe-be-supportiq-ecom` at `48caf66`. UI text is English. Shop works from 360px; console is primarily a desktop workspace. Data is synthetic. The user selected `data/knowledge/mock_orders.json` as the order source.

## Capabilities and Constraints

Four server-enforced roles; customer ownership checks; read-only commerce; one message and one reply per ticket; sticky manager authority; warning acknowledgement; no unresolved personal-data placeholders in sent replies. AI failures preserve manual support. Confidential text stays out of browser persistence and logs. Existing ML and evaluation code remains intact.

## Brand Commitments

SupportIQ, the approved light-theme tokens, Inter and JetBrains Mono, and the three-column console in `docs/design/console-ui.md` are the visual authority.

## Evidence on Hand

Approved screen mockups are in `docs/design/assets/`. Existing policies are in `data/knowledge/`. Orders and catalog entries derive from `mock_orders.json`. No mockup policies or report figures are treated as actual evidence.

## Product Principles

- Intent precedes draft review.
- Order records remain distinguishable from AI text.
- Only explicit human action sends a reply.
- Reports reflect stored events, including honest zeros and unavailable measurements.

## Accessibility & Inclusion

WCAG 2.2 AA, visible keyboard focus, named controls, status icons with text, reduced motion, and a usable 360px shop.
