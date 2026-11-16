# Frontend

This folder holds the SupportIQ web app: sign-in, the own password change at `/change-password`, the demo shop for customers at `/shop`, the Accounts and Versions screens of the admin area at `/admin`, and the ticket inbox and the ticket workspace of the console at `/console`, where staff correct the intent, try the AI again, edit, reject, and send replies, submit replies for approval, and escalate tickets, and where managers send or edit the proposals, handle escalated tickets, and read the reports at `/console/reports`. Where dev mode is available, staff and managers can switch on the developer details of the ticket workspace, and admins those of the Accounts and Versions screens. It is a React single-page app that talks to `backend` only through the [backend contract](../contracts/README.md) with a generated client, and it runs against the Prism mock until `backend` is ready. In the demo deployment, Cloudflare Pages serves the build, and the Pages Function of this folder is the ingress of `/v1` and `/health` ([Deploy on Cloudflare Pages](#deploy-on-cloudflare-pages)). What each screen does is defined in the [shop UI design](../docs/design/shop-ui.md), the [admin UI design](../docs/design/admin-ui.md), the [console UI design](../docs/design/console-ui.md), and the [account management design](../docs/design/account-management.md); the rules are in [typescript.md](../docs/rules/typescript.md) and [ui.md](../docs/rules/ui.md).

## Set up

From a fresh clone:

1. Install the Node.js version in [`../.nvmrc`](../.nvmrc), for example with `nvm install` in the repository root.
2. Enable the pnpm version pinned in `packageManager`. Node.js 24 includes Corepack:

   ```bash
   corepack enable pnpm
   ```

3. Install the contract tools, which provide the mock, in `contracts/`:

   ```bash
   pnpm install --frozen-lockfile
   ```

4. Install the frontend tools, and the browser for the tests, in this folder:

   ```bash
   pnpm install --frozen-lockfile
   pnpm exec playwright install chromium
   ```

## Run

Run the app against the mock, in this folder:

```bash
pnpm run dev:mock
```

This starts the Prism mock on port 4010 and the Vite dev server at <http://localhost:5173>. Stopping the command stops both. No `.env` file is needed ([Settings](#settings)).

The dev server proxies `/v1` and `/health`, so the session cookie stays on one site. The mock accepts any sign-in that matches the contract, and it always answers with the customer of the examples, so a browser reaches the shop but not the admin area or the console. It stores nothing: a sent message does not appear in the next list. The [UI flow tests](#test) choose other outcomes with the `Prefer` header, and Storybook shows every screen of the admin area and of the console.

## Test

Run every test, in this folder:

```bash
pnpm test
```

| Layer | Runs with | Covers |
|---|---|---|
| Unit and component tests | `pnpm run test:unit` | Mappings, formatters, error messages, query keys, every screen state, and the session flows, in shuffled order, against the example files of `contracts/examples/`, and the Pages Function in Node with a fake `backend`. Coverage is enforced: at least 80% overall and 90% in `model/`, without generated code |
| Stories with axe | `pnpm run test:stories` | Every variant and state of the design system and of the feature screens, in Chromium, and the widths that the splitters of the console columns give, which jsdom cannot lay out. An axe violation fails the story |
| UI flow tests against the mock | `pnpm run test:e2e` | The production build against Prism at 1280 px, and the shop flows also at 360 px, with axe on each screen, and where the keyboard focus lands after a button waits for `backend` or a dialog closes. Playwright starts the mock and the preview server itself |

## Commands

Run every command in this folder.

| Command | What it does |
|---|---|
| `pnpm run dev:mock` | Runs the mock and the dev server |
| `pnpm run dev` | Runs the dev server alone, against `SUPPORTIQ_BACKEND_URL` |
| `pnpm run build` | Writes the production build to `dist/` |
| `pnpm run preview` | Serves `dist/` |
| `pnpm run storybook` | Serves the design system catalog at <http://localhost:6006> |
| `pnpm run build-storybook` | Writes the catalog to `storybook-static/` |
| `pnpm run generate:api` | Generates `src/api/generated/backend.ts` from the contract |
| `pnpm run check` | Runs Prettier, ESLint with zero warnings, the compiler, dependency-cruiser, and the check that the generated client matches the contract |
| `pnpm run format` | Formats every file |

CI runs these in [`frontend.yml`](../.github/workflows/frontend.yml).

## Settings

Every setting has a safe default. [`.env.example`](.env.example) lists them.

| Setting | Default | Meaning |
|---|---|---|
| `SUPPORTIQ_BACKEND_URL` | `http://127.0.0.1:4010` | Where the dev and preview servers proxy `/v1` and `/health`, from the shell or a `.env` file. It never reaches the page |
| `VITE_REQUEST_TIMEOUT_MS` | `10000` | How long the app waits for each `backend` response, in ms |
| `VITE_REQUEST_RETRY_MAX_COUNT` | `2` | How many times a retryable request is sent again |
| `VITE_REQUEST_RETRY_BASE_DELAY_MS` | `500` | The first retry delay in ms, doubled for each later attempt, with jitter |
| `VITE_DEV_MODE` | `on` with the dev server, `off` in a production build | Whether dev mode is available: `on` or `off` ([UI-35](../docs/rules/ui.md#developer-views)). Keep it `off` in the demo deployment |
| `VITE_GRAFANA_TRACE_URL` | Not set | The link to a trace in Grafana, with `{trace_id}` once where the trace ID goes: https, or http on `localhost`, `127.0.0.1`, or `[::1]`. Not set: the developer details show the trace ID without a link |
| `VITE_FRONTEND_BUILD_VERSION` | `local` with the dev server, not set in a production build | The build version of `frontend`, which the developer details of the admin area show. A production build without it shows "Not set", never a wrong version |
| `VITE_GRAFANA_SYSTEM_OVERVIEW_URL` | Not set | The link to the Grafana dashboard System overview ([LOG-27](../docs/rules/logging-and-observability.md#dashboards)), without `{trace_id}`: https, or http on `localhost`, `127.0.0.1`, or `[::1]`. Not set: no link |
| `VITE_GRAFANA_AI_PIPELINE_URL` | Not set | The link to the Grafana dashboard AI pipeline, checked as `VITE_GRAFANA_SYSTEM_OVERVIEW_URL`. Not set: no link |
| `VITE_BACKEND_WAKE_ORIGIN` | Not set | The Render origin of `backend`, such as `https://<service>.onrender.com`: an http or https origin without a path. The app sends the wake request of the [backend wake-up design](../docs/design/backend-wake-up.md) to it when it starts and after a retryable request failure, and the build adds it to `connect-src` of the Content Security Policy. Not set: no wake request, and `connect-src` stays `'self'` |
| `VITE_BACKEND_WAKE_TIMEOUT_MS` | `90000` | How long a wake request may wait, in ms: Render's start time of about one minute plus 30 s |

`VITE_` settings are built into the page, so they never hold a secret. An invalid value stops the app at startup with the name of the setting; an invalid `VITE_BACKEND_WAKE_ORIGIN` stops the build too, because both read it with one parser. In dev mode, the developer details of the admin area list every `VITE_` setting with the value in use.

## Layout

| Path | Content |
|---|---|
| `src/api/` | The generated client and the code that creates it. Nothing outside `api/` folders calls it |
| `src/app/` | The composition root, the settings, the router, the area layouts, and the error boundaries |
| `src/design-system/` | Tokens, formatters, primitives, and domain components, each with its stories ([ADR-0008](../docs/decisions/0008-ui-design-system.md)). It imports no feature |
| `src/features/` | One folder per feature: `session`, `shop-catalog`, `shop-orders`, `shop-support`, `admin-accounts`, `admin-versions`, `console-tickets`, `console-reports`, and the shared `backend-requests`. Other code imports a feature only through its `index.ts` |
| `src/features/*/api/` | Query and mutation hooks, with one query key factory per feature, and `contract-types.ts`, the only file that `model/` may import from here |
| `src/features/*/model/` | View models, mappings, and rules, without React or the client. Unknown enum values map to a safe default |
| `src/features/*/components/` | The screens and their parts, with tests and stories |
| `src/test/` | Test helpers: the fake `backend` that answers with example files, and the render helpers |
| `e2e/` | The UI flow tests and their helpers |
| `scripts/` | The command that starts the mock with the dev server, and the check of the generated client |
| `ingress/` | The Pages Function: the ingress of the demo deployment, with its tests. It imports nothing, neither `src/` nor a package |
| `functions/` | The routes of the Pages Function, `v1/` and `health/`, which re-export the ingress. Pages requires the file name `[[path]].ts` |
| `public/` | `_routes.json`, which Vite copies to the root of the build |

`.dependency-cruiser.cjs` enforces these boundaries, and `eslint.config.js` rejects any class that does not come from a token.

## Routes

| Path | Screen | For |
|---|---|---|
| `/sign-in` | Sign in, with an optional `returnTo` | Everyone |
| `/` | Opens the area of the signed-in role, or sign-in | Everyone |
| `/change-password` | Change password, opened from the account menu | Every signed-in role |
| `/shop` | Products | `customer` |
| `/shop/products/{product_id}` | Product | `customer` |
| `/shop/orders` | My orders | `customer` |
| `/shop/orders/{order_id}` | Order, with its tickets and the message box | `customer` |
| `/shop/support` | Support | `customer` |
| `/console` | The inbox and the prompt to select a ticket. `?status=` chooses the queue: managers have Open, Awaiting approval, Escalated, and Closed; staff have Open | `staff`, `manager` |
| `/console/tickets/{ticket_id}` | The ticket workspace next to the inbox, which keeps `?status=`. Opening it records the view, then loads the ticket | `staff`, `manager` |
| `/console/reports` | Reports, for one period | `manager` |
| `/admin` | Opens Accounts | `admin` |
| `/admin/accounts` | Accounts, with the dialogs Create account and Reset password | `admin` |
| `/admin/versions` | Versions in use: the build of `backend` and the versions that `ai-service` serves | `admin` |

`backend` decides every permission. The app shows the permission-denied state when `backend` answers `403`.

## Deploy on Cloudflare Pages

[ADR-0016](../docs/decisions/0016-hosting-on-free-tiers.md#frontend-and-the-ingress-on-cloudflare-pages) defines the deployment. The Pages project builds this folder with `pnpm run build` and publishes `dist/`. The Pages Function in `functions/` is the ingress of `/v1/*` and `/health/*`, and its code is in `ingress/`:

- It forwards each request to `backend` with the method, path, query, body, and headers unchanged, and returns the answer of `backend` unchanged, every `Set-Cookie` included, without a CORS header.
- It never retries. It answers `502` when `backend` cannot be reached, `504` when `backend` sends no response headers within the timeout, and `413` for a body over 64 KiB, before it forwards anything. These answers have an empty body. The timeout bounds only the wait for the headers, so a body that streams after them is never cut.
- It logs nothing about a request.
- When the client cancels its request, such as a stream that the browser closes, the Function cancels the request to `backend` too (ADR-0022, statement 8).

`_routes.json` sends exactly `/v1/*` and `/health/*` to the Function, so static files never invoke it. The route folders of `functions/` match the same two patterns, so a build without `_routes.json` routes the same; a unit test checks both.

The settings of the Pages project:

| Setting | Read by | Default | Meaning |
|---|---|---|---|
| `SUPPORTIQ_BACKEND_URL` | The Function, at each request | None: the Function stops without it | The origin of `backend`, such as `https://<service>.onrender.com`: an https origin without a path |
| `SUPPORTIQ_BACKEND_TIMEOUT_MS` | The Function, at each request | `10000` | How long the Function waits for the response headers of `backend`, in ms: the caller's timeout of the backend contract |
| `VITE_BACKEND_WAKE_ORIGIN` | The build | Not set | The same Render origin, for the wake request ([Settings](#settings)) |
| `VITE_FRONTEND_BUILD_VERSION` | The build | Not set | Set by the build command from `CF_PAGES_COMMIT_SHA`, the commit SHA that Cloudflare Pages gives every build, because Vite passes only `VITE_` variables to the page ([admin UI design](../docs/design/admin-ui.md)). The build command is deployment configuration, kept in `deploy/` |

A missing or invalid setting of the Function stops it with the setting's name, and nothing is forwarded. The Pages project fails closed when the daily Functions limit is used up, so a `/v1` request never receives a static file in place of an answer of `backend` (statement 8).

At the first deploy, also check what the unit tests cannot: that `backend` receives the `Host` of its own URL, and that the Function does not buffer a response that streams.

## Dependencies

`package.json` pins every version exactly, and the lockfile pins the rest. React, Vite, React Router, TanStack Query, Tailwind CSS, Radix, Storybook, Vitest, Testing Library, Playwright, dependency-cruiser, ESLint, typescript-eslint, Prettier, openapi-typescript, and openapi-fetch are named by [ADR-0003](../docs/decisions/0003-tech-stack.md) or [ADR-0008](../docs/decisions/0008-ui-design-system.md).

### Runtime

| Name | Version | License | Why |
|---|---|---|---|
| `@fontsource-variable/inter` | 5.3.0 | OFL-1.1 | The bundled Inter font of the type scale, so no request leaves for a font host |
| `@fontsource-variable/jetbrains-mono` | 5.3.0 | OFL-1.1 | The bundled JetBrains Mono font for IDs, for the same reason |
| `@radix-ui/react-alert-dialog` | 1.2.1 | MIT | The accessible confirmation dialog |
| `@radix-ui/react-dialog` | 1.3.1 | MIT | The accessible form dialog of Create account and Reset password. AlertDialog has the `alertdialog` role, meant for confirmations, not for forms |
| `@radix-ui/react-dropdown-menu` | 2.2.1 | MIT | The account menu: an accessible menu button with keyboard navigation and focus return (UI-31) |
| `@radix-ui/react-label` | 2.1.17 | MIT | The accessible form label |
| `@radix-ui/react-popover` | 1.3.1 | MIT | The popover of the order chip in the console (console UI design, Order chip). This version uses the same `@radix-ui/react-popper` 1.4.0 as Tooltip and DropdownMenu |
| `@radix-ui/react-tooltip` | 1.4.1 | MIT | The accessible tooltip |
| `@tanstack/react-query` | 5.105.3 | MIT | Server state: cache, paging, retries, and invalidation |
| `class-variance-authority` | 0.7.1 | Apache-2.0 | Variant classes of primitives, as in shadcn/ui |
| `clsx` | 2.1.1 | MIT | Joins conditional classes, as in shadcn/ui |
| `lucide-react` | 1.67.0 | ISC | The icon set of the designs |
| `openapi-fetch` | 0.17.0 | MIT | The typed client over the generated types |
| `react`, `react-dom` | 19.3.1 | MIT | The UI library |
| `react-resizable-panels` | 4.16.0 | MIT | The splitters of the console columns, with the keyboard and ARIA of the window splitter pattern, sizes in px, and collapsing (console UI design, Column controls). It is the library of the Resizable component of shadcn/ui ([ADR-0008](../docs/decisions/0008-ui-design-system.md)); the project lead approved it on 2026-11-15. It has no dependencies |
| `react-router` | 8.5.1 | MIT | Routes and error boundaries |
| `tailwind-merge` | 3.7.0 | MIT | Resolves conflicting classes, as in shadcn/ui |

### Development

| Name | Version | License | Why |
|---|---|---|---|
| `@axe-core/playwright` | 4.14.0 | MPL-2.0 | Runs axe on each screen of the UI flow tests (UI-32) |
| `@eslint/js` | 9.39.5 | MIT | The base ESLint rules |
| `@playwright/test`, `playwright` | 1.61.1 | Apache-2.0 | UI flow tests, and the browser of the stories |
| `@storybook/addon-a11y` | 10.6.5 | MIT | Fails a story on an axe violation |
| `@storybook/addon-vitest` | 10.6.5 | MIT | Runs the stories as tests |
| `@storybook/react-vite`, `storybook` | 10.6.5 | MIT | The design system catalog |
| `@tailwindcss/vite`, `tailwindcss` | 4.3.4 | MIT | Tokens and utility classes |
| `@testing-library/dom` | 10.4.2 | MIT | Queries by role and text |
| `@testing-library/jest-dom` | 7.0.1 | MIT | DOM assertions |
| `@testing-library/react` | 16.3.3 | MIT | Renders components in tests |
| `@testing-library/user-event` | 14.6.8 | MIT | Acts as a person: clicks and typing |
| `@types/node` | 24.19.2 | MIT | Types of the scripts and configuration files |
| `@types/react`, `@types/react-dom` | 19.3.0 | MIT | Types of React |
| `@vitejs/plugin-react` | 6.2.1 | MIT | React in Vite |
| `@vitest/browser`, `@vitest/browser-playwright` | 5.1.0 | MIT | Runs the stories in Chromium |
| `@vitest/coverage-v8` | 5.1.0 | MIT | Coverage and its thresholds |
| `dependency-cruiser` | 18.7.2 | MIT | Feature and layer boundaries |
| `eslint` | 9.39.5 | MIT | Linting. Version 9 because the plugins of TS-02 do not all support version 10 yet |
| `eslint-plugin-better-tailwindcss` | 4.10.0 | MIT | Rejects classes that do not come from a token (UI-05, ADR-0008) |
| `eslint-plugin-jsx-a11y` | 6.10.2 | MIT | Accessibility lint rules of TS-02 |
| `eslint-plugin-react` | 7.37.5 | MIT | React lint rules of TS-02 |
| `eslint-plugin-react-hooks` | 7.1.1 | MIT | Hooks lint rules of TS-02 |
| `eslint-plugin-simple-import-sort` | 14.0.0 | MIT | Import ordering of TS-02 |
| `fast-check` | 4.10.2 | MIT | Property-based tests of pure logic with invariants, named by TEST-13 |
| `globals` | 17.14.0 | MIT | Global names of browsers and Node.js for ESLint |
| `jsdom` | 30.1.3 | MIT | The DOM of the component tests |
| `openapi-typescript` | 7.13.0 | MIT | Generates types from the contract |
| `prettier` | 3.9.10 | MIT | Formatting |
| `typescript` | 6.0.3 | Apache-2.0 | The language. `openapi-typescript` declares a peer range of `^5.x`; generation works, and the generated client check runs in CI |
| `typescript-eslint` | 8.72.1 | MIT | Type-aware lint rules of TS-02 |
| `vite` | 8.3.5 | MIT | Dev server and build |
| `vitest` | 5.1.0 | MIT | Test runner |

The project lead approved OFL-1.1 and MPL-2.0 on 2026-11-07, the two Radix packages of the account management design on 2026-11-11, and the Radix popover of the console UI design on 2026-11-12 ([WF-30](../docs/rules/workflow.md#dependencies)). `pnpm licenses list` shows the licenses of transitive packages, and the pull request that adds a dependency lists any license outside MIT, BSD, Apache-2.0, and ISC.

## Known limits

- Playwright stays on 1.61.1 so that the browser tests of `frontend` run on macOS 13. Which development platforms these tests support is not recorded yet. Tracked in [#6](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/6).
- `pnpm audit` reports two moderate advisories in `glob` and `minimatch`, through the docgen of `@storybook/react-vite`. They are development tools, and CI fails only on high or critical advisories ([WF-31](../docs/rules/workflow.md#dependencies)).
- The build is one bundle, so Vite warns that a chunk is larger than 500 kB. Tracked in [#5](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/5).
- The keyboard focus falls to the page in five cases. Show more on the last page removes its button: Shift+Tab reaches the last new item, and Tab goes to the top of the page. The reload after an unknown outcome can replace the button that holds the focus. The reload after a change or a password reset of an account that is gone (`404`) removes its row, the focused button included. Reload list in a refused banner removes the banner with its button. In these two cases, Tab then moves on to the buttons of the list in Chromium. The permission-denied screen replaces the whole screen, buttons included. In the console, the actions that replace the button with the focus move it on: Reject draft to Draft rejected, an intent correction to Other intent, Try AI again to the generating draft, Send reply to Reply sent, Submit for approval to Reply for approval, and Escalate ticket to the escalation. Tracked in [#7](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/7).
- A link from Support to a ticket that is not on the first page of its order opens the order page at the top. An order would need more than 20 tickets for this to happen.
- The console polls without push updates: the inbox every 30 s once its queue loaded, and the workspace every 2 s while a part of the suggestion is `pending` (`src/features/console-tickets/model/polling.ts`). Neither polls again after a first load that failed; Try again loads it. The lead approved polling on 2026-11-12, which answers the polling question of the [console UI design](../docs/design/console-ui.md#open-questions). The lead decided on 2026-11-13: no polling under 30 s; the workspace moves to server-sent events. Until the contract has them, the workspace keeps its 2 s interval while a part of the suggestion is `pending`.
- The manual-handling panel shows a neutral stand-in line for the manual-process instructions until the team provides the text ([console UI design, Open questions](../docs/design/console-ui.md#open-questions)).
- The Pages Function enforces the body limit of the ingress but no per-client rate limit yet, an open question of [ADR-0016](../docs/decisions/0016-hosting-on-free-tiers.md#open-questions) (statement 10). Until it is enforced, the sign-in throttle of `backend` limits password guessing per login name.
- There is no Dockerfile yet ([ARCH-10](../docs/rules/architecture.md#component-boundaries)). The project lead accepted this as debt on 2026-11-07. Since 2026-11-12, Cloudflare Pages builds `frontend` without a container ([ADR-0016](../docs/decisions/0016-hosting-on-free-tiers.md)), so no deployment uses the image. The debt ends when `frontend` gets a Dockerfile or ARCH-10 stops requiring one for a component that its platform builds without a container ([WF-23](../docs/rules/workflow.md#technical-debt)). Tracked in [#4](https://github.com/ml-system-design-nhom-5/SupportIQ/issues/4).
