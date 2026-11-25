/**
 * A screen state in a panel: loading failed, not found, permission denied, or empty (UI-23,
 * UI-25). It says what happened and what to do next.
 */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { TraceId } from "@/design-system/components/trace-id";
import { Icon } from "@/design-system/primitives/icon";

/** Props of {@link StateMessage}. */
export type StateMessageProps = {
  readonly icon: LucideIcon;
  /** The heading level: 1 when the state replaces the whole screen. */
  readonly headingLevel: 1 | 2;
  readonly title: string;
  readonly description?: string;
  /** Buttons or links that say what to do next. */
  readonly actions?: ReactNode;
  readonly traceId?: string;
};

/**
 * Render a state message.
 *
 * @param props - The icon, the heading, the text, the actions, and the trace ID.
 * @returns The panel with the message.
 */
export function StateMessage({
  icon,
  headingLevel,
  title,
  description,
  actions,
  traceId,
}: StateMessageProps) {
  const Heading = headingLevel === 1 ? "h1" : "h2";
  return (
    <section className="flex flex-col items-center gap-2 rounded-lg border border-border bg-surface px-6 py-4 text-center shadow-sm">
      <Icon icon={icon} size="md" tone="muted" />
      <Heading className="text-base font-semibold text-text">{title}</Heading>
      {description === undefined ? null : <p className="text-text-muted">{description}</p>}
      {actions === undefined ? null : (
        <div className="flex flex-wrap justify-center gap-2">{actions}</div>
      )}
      {traceId === undefined ? null : <TraceId traceId={traceId} />}
    </section>
  );
}
