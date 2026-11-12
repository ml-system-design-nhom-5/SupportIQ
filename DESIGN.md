---
name: SupportIQ
description: Human-reviewed commerce support with visible evidence
direction: achromatic-ledger
seed: 1338469755
colors:
  background: "#f8fafc"
  surface: "#ffffff"
  text: "#0f172a"
  muted: "#475569"
  primary: "#1d4ed8"
  primary-hover: "#1e40af"
  primary-subtle: "#eff6ff"
  border: "#e2e8f0"
  border-strong: "#64748b"
  success: "#15803d"
  success-subtle: "#f0fdf4"
  warning: "#b45309"
  warning-subtle: "#fffbeb"
  danger: "#b91c1c"
  danger-subtle: "#fef2f2"
  info: "#0369a1"
  info-subtle: "#f0f9ff"
  ai: "#3b2d54"
  ai-subtle: "#f6f3f9"
  ai-border: "#e2daeb"
typography:
  title:
    fontFamily: "Inter Variable, sans-serif"
    fontSize: "28px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Inter Variable, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  meta:
    fontFamily: "Inter Variable, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
  identifier:
    fontFamily: "JetBrains Mono Variable, monospace"
    fontSize: "0.9em"
    fontWeight: 400
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
    height: "34px"
---

# SupportIQ design system

## Overview

The approved [console design](docs/design/console-ui.md) is the visual authority. Staff inspect a message, its intent, a reply and its evidence in a stable, distraction-free workspace. The shop and admin reuse that system. Source code: `apps/frontend/src/styles.css` and `components/ui.tsx`.

Selected direction: **Achromatic Ledger** (seed: `1338469755`). A crisp, functional light theme with high contrast, calm surfaces, and clear visual hierarchy.

## Colors

Surfaces are neutral and quiet (`#f8fafc` background, `#ffffff` card surfaces, `#e2e8f0` structural borders). Blue (`#1d4ed8`) identifies interactive primary actions and navigation highlights; semantic green, amber and red identify operational statuses.

AI-authored material uses a restrained slate plum (`--ai: #3b2d54`, `--ai-subtle: #f6f3f9`, `--ai-border: #e2daeb`) replacing former decorative high-saturation violet panels. Explicit AI markers (sparkle icon, "AI draft" heading, citation badges, source numbers, intent confidence pill) clearly distinguish machine suggestions from human operator input and official order records.

## Typography

Inter Variable is self-hosted and used for all interface prose. JetBrains Mono is strictly limited to ticket identifiers, trace IDs, and version strings.
- Headings: 28px hero/page titles (24px on phone), 20px section headers, 16px card headers.
- Body: 14px default, 1.5 line-height.
- Metadata: 13px floor for secondary information and timestamps (ensuring legible sub-scale contrast).
- Raw model scores are explicitly labeled and never presented as calibrated confidence.

## Layout & Responsive Breakpoints

- **Desktop (1440px+)**: 272px inbox pane, flexible review column, 320px evidence sidebar (340px above 1600px). Columns scroll independently; the reply action bar stays anchored at the bottom of its panel. Sign-in features a balanced two-column layout with product guarantees on the left and credentials on the right.
- **Tablet (768px)**: Evidence pane stacks below review column with full source list visibility; inbox remains accessible. Sign-in stacks gracefully.
- **Mobile & Small Phone (390px / 360px)**: The inbox and selected ticket workspace become dedicated separate views with a back button. Touch targets meet 44px minimum bounds. Navigation flows into an accessible header row. Zero horizontal scroll overflow across all viewports.

## Elevation & Depth

Panels are flat with subtle 1px border contrast (`#e2e8f0`) and no decorative card drop-shadows. Shadows are strictly reserved for modal overlays and popovers (`0 12px 32px rgb(15 23 42 / .12)`), marked with `/* taste-skill-ignore */` for linting compliance.

## Components & Accessibility

- **Action State Clarity**: Primary actions (e.g., `Send reply`, `Submit for approval`) are always visible in their expected DOM positions. When AI analysis is in progress, buttons are cleanly disabled with informative contextual helper copy ("The AI is still working on this ticket.") rather than disappearing.
- **Citations & Sources**: Citation markers render as crisp bordered chips with hover focus rings; clicking opens source details or order context.
- **Forms & Inputs**: Explicit persistent `<label>` elements for every field; visible focus rings with 2px offset; error notices announce errors to screen readers (`role="alert"`).
- **Compliance**: Zero WCAG 2.2 AA violations in axe-core audits across desktop, tablet, mobile, and small-phone viewports.

## Do's and Don'ts

- Do preserve the message → intent → reply sequence and evidence sidebar.
- Do keep unsent confidential text in memory only.
- Do use the semantic status component instead of defining screen-specific colors.
- Don't add decorative AI gradients or saturation that distract from customer messages.
- Don't add simulated confidence, report totals, policies, testimonials or product photography.
- Don't present an unsent draft in the customer area.
