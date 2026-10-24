# TypeScript rules

> **Status:** Active · **Owner:** frontend · **Last reviewed:** 2026-10-23

TypeScript and React rules for `frontend`. They build on [code.md](code.md) and [ui.md](ui.md); where several apply, all must hold.

## Toolchain

**TS-01.** The Node.js LTS version is pinned in `.nvmrc` and `engines`. `pnpm` manages dependencies, and `pnpm-lock.yaml` is committed.

**TS-02.** The following tools run in pre-commit and CI with zero warnings:

| Tool | Purpose | Required configuration |
|---|---|---|
| `tsc --noEmit` | Type checking | Compiler options below |
| ESLint | Linting | `typescript-eslint` `strict-type-checked` and `stylistic-type-checked`, `react`, `react-hooks`, `jsx-a11y`, import ordering, Tailwind class rules |
| Prettier | Formatting | `printWidth: 100`, defaults otherwise |
| Vitest and Testing Library | Unit and component tests | Shuffled order, coverage thresholds ([testing.md](testing.md#coverage)) |
| dependency-cruiser | Feature and layer boundaries | Rules matching the project layout below |
| Storybook with axe | Component catalog and accessibility checks | Every design-system component ([ADR-0008](../decisions/0008-ui-design-system.md)) |

**TS-03.** `tsconfig.json` enables at least:

| Option | Value |
|---|---|
| `strict` | `true` |
| `noUncheckedIndexedAccess` | `true` |
| `exactOptionalPropertyTypes` | `true` |
| `noImplicitOverride` | `true` |
| `noImplicitReturns` | `true` |
| `noFallthroughCasesInSwitch` | `true` |
| `noUnusedLocals` | `true` |
| `noUnusedParameters` | `true` |
| `noPropertyAccessFromIndexSignature` | `true` |
| `verbatimModuleSyntax` | `true` |
| `forceConsistentCasingInFileNames` | `true` |

**TS-04.** ESLint complexity limits match [CODE-11](code.md#functions): `complexity: 8`, `max-depth: 3`, `max-params: 3` (use an options object beyond that), `max-lines-per-function: 40` for non-component functions, `max-lines: 300` per file.

## Project layout

**TS-05.** `frontend/src/` follows this structure:

```text
frontend/src/
├── app/                 # routes, providers, layout shells, error boundaries
├── design-system/       # tokens, primitives, domain components (ADR-0008)
│   ├── tokens/
│   ├── primitives/
│   └── components/
├── features/
│   └── <feature>/       # for example console-inbox, ticket-workspace, shop-orders
│       ├── api/         # query and mutation hooks over the generated client
│       ├── components/  # feature components
│       ├── model/       # view models and pure mapping functions
│       └── index.ts     # public API of the feature
├── api/
│   ├── generated/       # client and types generated from contracts/backend.openapi.yaml
│   └── client.ts        # the one configured client instance
└── test/                # test utilities, builders, mock handlers
```

**TS-06.** Import rules, enforced by dependency-cruiser:

- `features/<a>` imports `features/<b>` only through `features/<b>/index.ts`.
- `design-system/` imports nothing from `features/`, `app/`, or `api/`.
- Only `features/*/api/` imports from `api/`.
- `app/` composes features and never contains business presentation logic.

**TS-07.** File names are `kebab-case` (`ticket-list.tsx`). A file exports one component, named in `PascalCase` after the file. Path aliases (`@/features/...`) replace deep relative imports (`../../..`).

## Naming

**TS-08.** `camelCase` for variables, functions, and hooks. `PascalCase` for types and components. `UPPER_SNAKE_CASE` only for module-level primitive constants. Hooks start with `use`. Event props are `onX`; their handlers are `handleX`. Boolean props and variables start with `is`, `has`, `can`, or `should`.

**TS-09.** Components never consume generated contract types directly. Each feature's `model/` maps contract types to `camelCase`, read-only view models. This isolates the UI from contract changes and keeps one naming style in UI code.

## Types

**TS-10.** `any` is forbidden; use `unknown` and narrow it. Non-null assertions (`!`) are forbidden. `as` casts are forbidden except `as const` and at a validated boundary with a comment. `@ts-ignore` is forbidden; `@ts-expect-error` requires a reason and an issue link.

**TS-11.** Use `type` aliases for object shapes and unions. `interface` is not used in application code.

**TS-12.** Variants are discriminated unions on a literal field (`kind` or `status`). Every `switch` over a union ends with an exhaustiveness check (`assertNever(value)`).

**TS-13.** Props and view models are `readonly`. Arrays in view models are `readonly T[]`.

**TS-14.** TypeScript `enum` is forbidden. Closed sets are string literal unions, generated from the contract or declared once in `model/`.

**TS-15.** Unknown enum values from the backend are mapped to a safe default in `model/` ([CON-22](contracts.md#evolution)). Components never see an unmapped value.

## React

**TS-16.** Only function components. Class components are forbidden, except error boundaries in `app/`.

**TS-17.** Component limits: a component SHOULD stay under 80 lines and MUST stay under 150 lines including JSX. More than seven props means the component must be split or composed with children.

**TS-18.** Components are either containers or presentational. Containers live in features, read data through hooks, and pass props down. Presentational components (all of `design-system/` and most of `features/*/components/`) receive only props and never fetch data.

**TS-19.** Server state lives only in TanStack Query. Copying server data into local state is forbidden. Each feature builds its query keys with one key factory.

**TS-20.** Local UI state uses `useState` or `useReducer`. A global client-state library requires an ADR. React context is used only for cross-cutting concerns such as the session and the theme.

**TS-21.** Derive, don't duplicate: values computable from props or state are computed during render. State that mirrors other state is forbidden.

**TS-22.** `useEffect` is only for synchronizing with external systems. It is never used for data fetching, derived state, or responding to user events.

**TS-23.** The rules of hooks and exhaustive dependencies are enforced. Suppressing `react-hooks` rules is forbidden.

**TS-24.** List keys come from stable data IDs, never from array indexes.

**TS-25.** Inline styles, `dangerouslySetInnerHTML`, and arbitrary Tailwind values (`p-[13px]`) are forbidden. Styling uses design-system components and token-backed classes only ([ui.md](ui.md#tokens)).

**TS-26.** Every route has an error boundary and a loading state. Problem Details errors are converted to user messages by one shared function; components never display raw error bodies.

## API access

**TS-27.** The API client and its types are generated from `contracts/backend.openapi.yaml` and never written by hand. CI fails if the generated code is out of date.

**TS-28.** Only `features/*/api/` calls the client. Components never call `fetch` or the client directly.

**TS-29.** Write mutations send an `Idempotency-Key` created once per user action. Automatic retries reuse the same key. Sending a reply is never retried automatically.

## Documentation

**TS-30.** Exported functions, hooks, and components have TSDoc comments: a summary, parameters or props, and the return value.

## Dependencies

**TS-31.** Runtime and development dependencies are separated in `package.json`. Every dependency is justified in the PR that adds it ([WF-27](workflow.md#dependencies)).
