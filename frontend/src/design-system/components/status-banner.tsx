/**
 * A banner that reports the outcome of an action or a problem on the page, with an icon and a
 * bold lead so color is not the only signal (UI-11, UI-25).
 */
import { cva } from "class-variance-authority";
import { CircleCheck, Info, type LucideIcon, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { TraceId } from "@/design-system/components/trace-id";
import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";

const bannerVariants = cva("flex items-start gap-3 rounded-md border px-4 py-3 text-text", {
  variants: {
    tone: {
      success: "border-success/35 bg-success-subtle",
      info: "border-info/35 bg-info-subtle",
      warning: "border-warning/35 bg-warning-subtle",
      danger: "border-danger/35 bg-danger-subtle",
    },
  },
});

const leadVariants = cva("font-semibold", {
  variants: {
    tone: {
      success: "text-success",
      info: "text-info",
      warning: "text-warning",
      danger: "text-danger",
    },
  },
});

const iconByTone: Readonly<Record<StatusBannerTone, LucideIcon>> = {
  success: CircleCheck,
  info: Info,
  warning: TriangleAlert,
  danger: TriangleAlert,
};

/** The tone of a banner: a color role of UI-06. */
export type StatusBannerTone = "success" | "info" | "warning" | "danger";

/** Props of {@link StatusBanner}. */
export type StatusBannerProps = {
  readonly tone: StatusBannerTone;
  /** The bold first sentence: what happened. */
  readonly lead: string;
  /** What it means or what to do next. */
  readonly children?: ReactNode;
  /** The trace ID of a failed request, when there is one. */
  readonly traceId?: string;
  /** An action, such as "Reload list". */
  readonly action?: ReactNode;
  /**
   * The element ID that a script moves the focus to, such as a success that replaces a form. The
   * banner can then hold the focus, but Tab never reaches it (UI-30).
   */
  readonly focusTargetId?: string;
};

/**
 * Render a banner. A `danger` banner is an alert; the others are status messages.
 *
 * @param props - The tone, the lead, the text, the trace ID, the action, and the focus target ID.
 * @returns The banner.
 */
export function StatusBanner({
  tone,
  lead,
  children,
  traceId,
  action,
  focusTargetId,
}: StatusBannerProps) {
  return (
    <div
      id={focusTargetId}
      tabIndex={focusTargetId === undefined ? undefined : -1}
      role={tone === "danger" ? "alert" : "status"}
      className={cn(bannerVariants({ tone }), FOCUS_RING_CLASSES)}
    >
      <Icon icon={iconByTone[tone]} tone={tone} />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="wrap-break-word">
          <span className={leadVariants({ tone })}>{lead}</span> {children}
        </p>
        {traceId === undefined ? null : <TraceId traceId={traceId} />}
      </div>
      {action === undefined ? null : <div className="shrink-0">{action}</div>}
    </div>
  );
}
