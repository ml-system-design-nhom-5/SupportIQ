import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";

import { cn } from "@/design-system/primitives/class-names";
import { consoleColumnSizes } from "@/design-system/tokens/column-sizes";

/** Each color role of UI-06, its Tailwind class, and its value in tokens.css. */
const colorRoles = [
  { role: "background", swatch: "bg-background", value: "#F4F4F5" },
  { role: "surface", swatch: "bg-surface", value: "#FFFFFF" },
  { role: "surface-raised", swatch: "bg-surface-raised", value: "#FFFFFF" },
  { role: "border", swatch: "bg-border", value: "#E4E4E7" },
  { role: "border-strong", swatch: "bg-border-strong", value: "#71717A" },
  { role: "text", swatch: "bg-text", value: "#18181B" },
  { role: "text-muted", swatch: "bg-text-muted", value: "#52525B" },
  { role: "text-inverse", swatch: "bg-text-inverse", value: "#FFFFFF" },
  { role: "primary", swatch: "bg-primary", value: "#1D4ED8" },
  { role: "primary-foreground", swatch: "bg-primary-foreground", value: "#FFFFFF" },
  { role: "focus-ring", swatch: "bg-focus-ring", value: "#2563EB" },
  { role: "success", swatch: "bg-success", value: "#15803D" },
  { role: "warning", swatch: "bg-warning", value: "#B45309" },
  { role: "danger", swatch: "bg-danger", value: "#B91C1C" },
  { role: "info", swatch: "bg-info", value: "#0369A1" },
  { role: "ai", swatch: "bg-ai", value: "#6D28D9" },
  { role: "success-subtle", swatch: "bg-success-subtle", value: "#F0FDF4" },
  { role: "warning-subtle", swatch: "bg-warning-subtle", value: "#FFFBEB" },
  { role: "danger-subtle", swatch: "bg-danger-subtle", value: "#FEF2F2" },
  { role: "info-subtle", swatch: "bg-info-subtle", value: "#F0F9FF" },
  { role: "ai-subtle", swatch: "bg-ai-subtle", value: "#F5F3FF" },
] as const;

/** The type scale of UI-08. */
const typeScale = [
  { name: "3xl, 30 px", sample: "text-3xl" },
  { name: "2xl, 24 px", sample: "text-2xl" },
  { name: "xl, 20 px", sample: "text-xl" },
  { name: "lg, 18 px", sample: "text-lg" },
  { name: "base, 16 px: shop body", sample: "text-base" },
  { name: "sm, 14 px: console body", sample: "text-sm" },
  { name: "xs, 12 px: labels", sample: "text-xs" },
] as const;

const meta = {
  title: "Design system/Tokens",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

export const Colors: Story = { render: () => <ColorRoles /> };

export const Typography: Story = { render: () => <TypeScale /> };

/**
 * The default column widths of tokens.css, which stories of a single component use, are those of
 * column-sizes.ts, which the resizable columns use.
 */
export const ColumnWidths: Story = {
  render: () => <ColumnWidthSamples />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    await expect(canvas.getByText("Inbox").getBoundingClientRect().width).toBe(
      consoleColumnSizes.inbox.defaultWidth,
    );
    await expect(canvas.getByText("AI sidebar").getBoundingClientRect().width).toBe(
      consoleColumnSizes.aiDetails.defaultWidth,
    );
  },
};

/**
 * Render the color roles.
 *
 * @returns The swatches with their role names and values.
 */
function ColorRoles() {
  return (
    <ul aria-label="Color roles" className="grid grid-cols-3 gap-3">
      {colorRoles.map((color) => (
        <li
          key={color.role}
          className="flex items-center gap-3 rounded-md border border-border p-3"
        >
          <span
            aria-hidden="true"
            className={cn("size-8 rounded-sm border border-border", color.swatch)}
          />
          <span className="flex flex-col text-sm">
            <span className="font-medium">{color.role}</span>
            <span className="font-mono text-xs text-text-muted">{color.value}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Render the type scale.
 *
 * @returns One line in each size.
 */
function TypeScale() {
  return (
    <ul aria-label="Type scale" className="flex flex-col gap-2">
      {typeScale.map((size) => (
        <li key={size.name} className={size.sample}>
          {size.name}
        </li>
      ))}
      <li className="font-mono text-xs">TCK-1042 · ORD-20931 · JetBrains Mono</li>
    </ul>
  );
}

/**
 * Render a bar at each default column width.
 *
 * @returns The bars, named after their columns.
 */
function ColumnWidthSamples() {
  return (
    <div className="flex flex-col gap-2 text-sm">
      <p className="w-inbox bg-ai-subtle">Inbox</p>
      <p className="w-ai-sidebar bg-ai-subtle">AI sidebar</p>
    </div>
  );
}
