# UI rules

> **Status:** Active · **Owner:** frontend · **Last reviewed:** 2026-10-24

A strict design system and interaction rules, so every screen looks and behaves the same, staff can work quickly and safely, and developers can build and review UI with confidence. The console exists to help staff check the AI, not to make them trust it blindly. Design-system structure: [ADR-0008](../decisions/0008-ui-design-system.md). Shop scope: [ADR-0002](../decisions/0002-shop-demo-scope.md).

## Principles

1. **Clarity over decoration.** Every element helps staff decide.
2. **Consistency everywhere.** The same thing looks and behaves the same on every screen.
3. **Transparent AI.** AI content is always marked, sourced, and correctable.
4. **Staff in control.** Nothing irreversible happens without a deliberate staff action.
5. **Accessible by default.** WCAG 2.2 AA is the floor.

## Design system structure

```mermaid
flowchart TB
    T["Design tokens<br/>color, typography, spacing, radius, elevation, motion"] -->|"used by"| P["Primitives<br/>shadcn/ui on Radix: Button, Input, Dialog, Tooltip"]
    P -->|"used by"| D["Domain components<br/>CitationMarker, ConfidenceBadge, IntentPicker,<br/>DraftEditor, StaffNotePanel, StatusBanner, ReasonCodeChips"]
    D -->|"used by"| S["Feature screens<br/>/console, /shop"]
```

**UI-01.** The design system lives in `frontend/src/design-system/` with `tokens/`, `primitives/`, and `components/` ([TS-05](typescript.md#project-layout)).

**UI-02.** Feature screens are composed only of design-system components, including layout primitives (stack, grid, panel). Feature code does not style raw HTML elements.

**UI-03.** A new visual pattern is added to the design system first, with stories, and only then used in a feature.

**UI-04.** Every design-system component has Storybook stories for every variant and every state, and passes automated accessibility checks.

## Tokens

**UI-05.** All visual values come from tokens. Feature code MUST NOT contain color literals (hex, `rgb`, `hsl`), pixel values, arbitrary Tailwind values (`p-[13px]`), or inline styles. Lint rules enforce this.

**UI-06.** Color tokens are semantic roles. Components never use raw palette names.

| Token role | Use |
|---|---|
| `background`, `surface`, `surface-raised` | Page background and panels |
| `border`, `border-strong` | Dividers and input borders |
| `text`, `text-muted`, `text-inverse` | Text |
| `primary`, `primary-foreground` | The single main action of a view |
| `focus-ring` | Keyboard focus |
| `success` | Grounded, approved, sent |
| `warning` | Needs attention: low confidence, stale source, missing information |
| `danger` | Blocked, failed, irreversible actions |
| `info` | Neutral system information |
| `ai` | Marks AI-generated content |

**UI-07.** Spacing uses a 4 px grid with these steps only: 0, 4, 8, 12, 16, 24, 32, 48, 64 px.

**UI-08.** Typography uses one sans-serif family for UI text and one monospace family for IDs and versions, both chosen at scaffold. Sizes: 12, 14, 16, 18, 20, 24, 30 px. Weights: 400, 500, 600. Console body text is 14 px; shop body text is 16 px.

**UI-09.** Radius has three steps (small, medium, large). Elevation has three levels. Motion uses two durations (100 ms and 200 ms) with one easing curve and respects `prefers-reduced-motion`.

**UI-10.** The light theme is required. A dark theme MAY be added later, only by overriding tokens.

## Visual semantics

**UI-11.** Color is never the only signal. Status is always shown with an icon and a text label as well.

**UI-12.** Each ticket and suggestion status has exactly one presentation (token, icon, label), defined once in the design system and used everywhere. Screens never define their own status colors.

**UI-13.** AI-generated content always carries the `ai` marker and a label ("AI draft", "AI suggestion"). Text written by staff never carries it.

**UI-14.** Confidence is shown as the band label and percentage provided by `backend`. The UI never computes bands or applies thresholds.

## Console interaction

**UI-15.** The console uses one fixed workspace layout, defined in the console design doc. Panels and actions never move between tickets.

**UI-16.** The main actions are always visible, in the same place: Edit, Reject draft, Escalate, and Send reply. When authority is required, staff see Submit for approval instead of Send reply. Actions that `backend` does not list in `allowed_actions` are disabled, with the reason shown. There is no automatic send.

**UI-17.** Irreversible actions (Send reply, Submit for approval, Reject draft, Escalate) never have single-key shortcuts. Their shortcuts use a modifier (`Ctrl` or `Cmd` with `Enter`), and Send reply shows a confirmation step.

**UI-18.** When a suggestion has warnings (low confidence, signal disagreement, stale or conflicting sources, sensitive ticket), Send reply stays disabled until staff acknowledge each warning.

**UI-19.** Tickets where authority is required (FR-06) show a persistent banner: the AI output is supporting information, and the decision belongs to a supervisor. Supervisors see the staff proposal next to the AI draft and send it as proposed or edited.

**UI-20.** Each draft segment shows inline citation markers. Hovering or focusing a marker shows the document title, version, effective dates, and snippet; activating it opens the full document version.

**UI-21.** Staff notes appear in a separate panel labeled "For staff only", never inside the draft editor.

**UI-22.** Intent correction takes one interaction from the AI panel. After a correction, the draft area shows that a new draft is being generated and marks the previous draft as outdated.

## States

**UI-23.** Every screen and every data-bound component implements all of its states: loading, empty, error, partial (analysis shown, draft pending), abstained, escalation recommended, manual handling, and permission denied. Each state has a story.

**UI-24.** Loading uses skeletons in the affected area only. The whole screen never blocks. The analysis appears as soon as it arrives.

**UI-25.** Error states say what happened and what to do next, in plain language. They never show stack traces, raw codes, or internal names, but offer a copyable trace ID under "Details".

**UI-26.** The manual-handling state shows the manual-process instructions and keeps every non-AI tool working.

## Content

**UI-27.** UI text uses [glossary](../glossary.md) terms and sentence case. Buttons are verbs that name the result ("Send reply", "Escalate ticket"), never "OK" or "Submit".

**UI-28.** Staff-facing text contains no ML jargon. "Confidence" is allowed; "logit", "embedding", "rerank weight" are not.

**UI-29.** Times show a relative value ("5 min ago") with the absolute local time on hover. Numbers, money, and dates use shared formatters only.

## Accessibility

**UI-30.** WCAG 2.2 AA: text contrast at least 4.5:1, UI component contrast at least 3:1, visible focus on every interactive element, full keyboard operation, a label on every input, and no information conveyed by color or position alone.

**UI-31.** Interactive widgets use the Radix-based primitives. Custom dialogs, menus, or comboboxes built from generic elements are forbidden.

**UI-32.** Automated accessibility checks (axe) run on every story and on end-to-end flows. Violations fail CI.

## Layout and performance

**UI-33.** The console targets desktop widths of 1280 px and above. The shop supports widths from 360 px.

**UI-34.** Every interaction gives visible feedback within 100 ms.

## Developer views

**UI-35.** When the developer-details setting is enabled (off by default in demo mode), the ticket workspace shows a collapsible "Developer details" panel: trace ID with a link to the trace in Grafana ([ADR-0007](../decisions/0007-observability-stack.md)), model, KB, and prompt versions, latency per step, and raw statuses and reason codes.

**UI-36.** Storybook is the catalog of every design-system component and the place to review UI changes in isolation. A UI PR links the affected stories.

**UI-37.** Tests select elements by role and accessible name. `data-testid` is allowed only when no accessible selector exists.

## Shop

**UI-38.** The shop uses the same design system and adds no components outside it. Its scope is fixed by ADR-0002.

## Boundaries

**UI-39.** The UI reads and writes data only through the `backend` contract. It contains no business logic and no AI logic.

**UI-40.** The UI never decides permissions. It reflects what `backend` allows ([SEC-20](security-and-privacy.md#authentication-and-authorization)).

## UI review checklist

- [ ] Only design-system components and tokens are used; no literals or arbitrary values.
- [ ] Every state is implemented and has a story.
- [ ] AI content is marked; citations work; staff notes are separate.
- [ ] Irreversible actions need a deliberate action; warnings must be acknowledged.
- [ ] Keyboard and screen reader work; axe passes.
- [ ] Text uses glossary terms and contains no jargon.
