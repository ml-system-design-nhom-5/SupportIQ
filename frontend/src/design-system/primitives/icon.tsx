/**
 * A decorative icon from lucide-react, sized and colored by tokens. The text next to it always
 * carries the meaning, so the icon is hidden from assistive technology (UI-11).
 */
import { cva } from "class-variance-authority";
import type { LucideIcon } from "lucide-react";

const iconVariants = cva("shrink-0", {
  variants: {
    size: { xs: "size-3", sm: "size-4", md: "size-6", lg: "size-8" },
    tone: {
      inherit: "",
      muted: "text-text-muted",
      primary: "text-primary",
      success: "text-success",
      warning: "text-warning",
      danger: "text-danger",
      info: "text-info",
      ai: "text-ai",
    },
  },
});

/** The tone of an icon: one of the color roles of UI-06. */
export type IconTone =
  "inherit" | "muted" | "primary" | "success" | "warning" | "danger" | "info" | "ai";

/** The size of an icon: 12, 16, 24, or 32 px. `xs` fits a citation marker. */
export type IconSize = "xs" | "sm" | "md" | "lg";

/** Props of {@link Icon}. */
export type IconProps = {
  /** The lucide icon component. */
  readonly icon: LucideIcon;
  readonly size?: IconSize;
  readonly tone?: IconTone;
};

/**
 * Render a decorative icon.
 *
 * @param props - The icon, its size, and its tone.
 * @returns The icon, hidden from assistive technology.
 */
export function Icon({ icon: IconComponent, size = "sm", tone = "inherit" }: IconProps) {
  return <IconComponent aria-hidden="true" className={iconVariants({ size, tone })} />;
}
