# SupportIQ frontend

The React/TypeScript application implements the approved shop, three-column support console, manager reports, and internal administration screens. Shared tokens and Radix dialogs/popovers preserve the visual semantics in the design documents. Fonts ship in the local bundle; no third-party font requests are made.

```powershell
cd apps/frontend
pnpm install --frozen-lockfile
pnpm dev
pnpm build
pnpm test
pnpm test:e2e
```

The development server proxies `/v1` to the backend on port 8080. Production files are served by FastAPI on the same origin. End-to-end tests require the native application to be running, use installed Microsoft Edge, and read local generated credentials without printing them. They create synthetic test tickets in the local application database. Screenshots go to `.impeccable/review/` and are excluded from Git.

Routes: `/sign-in`; `/shop`, `/shop/products/:productId`, `/shop/orders`, `/shop/orders/:orderId`, `/shop/support`; `/console`, `/console/tickets/:ticketId`, `/console/reports`; `/admin/accounts`, `/admin/versions`.

TanStack Query stores loaded data in memory only. Role/session transitions remove private query data. Editor text is retained across failed requests and polling but is not persisted to browser storage. Writes have no automatic retry; ticket creation retains the same idempotency key when the same message is retried.
