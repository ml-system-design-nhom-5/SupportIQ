/**
 * The classes of a badge in each tone (UI-06), shared by {@link StatusBadge} and {@link Tag}, so a
 * tone looks the same on both (CODE-48).
 */
import { cva } from "class-variance-authority";

/** The badge classes of each tone. */
export const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0 text-sm font-medium whitespace-nowrap",
  {
    variants: {
      tone: {
        neutral: "border-border bg-background text-text-muted",
        info: "border-info/35 bg-info-subtle text-info",
        success: "border-success/35 bg-success-subtle text-success",
        warning: "border-warning/35 bg-warning-subtle text-warning",
        danger: "border-danger/35 bg-danger-subtle text-danger",
        ai: "border-ai/35 bg-ai-subtle text-ai",
      },
    },
  },
);
