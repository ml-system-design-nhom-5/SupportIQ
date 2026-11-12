---
name: SupportIQ
description: Human-reviewed commerce support with visible evidence
colors:
  background: "#f4f4f5"
  surface: "#ffffff"
  text: "#18181b"
  muted: "#52525b"
  primary: "#1d4ed8"
  border: "#e4e4e7"
  border-strong: "#71717a"
  success: "#15803d"
  warning: "#b45309"
  danger: "#b91c1c"
  info: "#0369a1"
  ai: "#6d28d9"
typography:
  title:
    fontFamily: "Inter Variable, sans-serif"
    fontSize: "24px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Inter Variable, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  identifier:
    fontFamily: "JetBrains Mono Variable, monospace"
    fontSize: "0.9em"
    fontWeight: 400
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
spacing:
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

The approved [console design](docs/design/console-ui.md) is the visual authority. Staff inspect a message, its intent, a reply and its evidence in a stable workspace. The shop and admin reuse that system. Source code: `apps/frontend/src/styles.css` and `components/ui.tsx`.

## Colors

Surfaces are neutral. Blue identifies primary actions; semantic green, amber and red identify status. Violet identifies AI-authored material, as explicitly required by the approved design. Order records stay neutral and distinct from AI. Status includes an icon and a text label.

## Typography

Inter is self-hosted and used for interface text. JetBrains Mono is limited to identifiers and versions. Console text is 14px, shop text 16px, metadata 12px; titles are 24px, with a compact 16px ticket title. Raw model scores are explicitly labeled and never presented as calibrated confidence.

## Layout

The desktop console uses a 272px inbox, flexible review column and 320px evidence column (340px above 1600px). Columns scroll independently; the reply action bar stays at the bottom of its panel. Below 1000px evidence stacks under review. Below 768px the inbox and selected ticket become separate views with a back link. The shop caps content at 960px with 32px desktop and 16px phone gutters. Navigation moves into a second row on phones.

## Elevation & Depth

Working panels are flat with quiet borders. Shadows belong only to floating dialogs and popovers: `0 12px 32px rgb(24 24 27 / .16)` and `0 4px 12px rgb(24 24 27 / .08)`.

## Shapes

Small tags use 4px corners, controls 6px, panels 8px. Product images use the approved neutral box treatment because the source data has no photographs. Avatar circles identify people only.

## Components

Buttons have primary, secondary, ghost and danger variants and visible disabled, hover and keyboard-focus states. Fields have persistent labels. Radix dialogs provide focus trapping and escape behavior. The reply area places warnings next to the send action. Citation markers open source information; order citations open the order records. Animations are limited to control feedback, loading and dialog appearance, with a reduced-motion override.

## Do's and Don'ts

- Do preserve the message → intent → reply sequence and evidence sidebar.
- Do keep unsent confidential text in memory only.
- Do use the semantic status component instead of defining screen-specific colors.
- Don't add simulated confidence, report totals, policies, testimonials or product photography.
- Don't present an unsent draft in the customer area.
