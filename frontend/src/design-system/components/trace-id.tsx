/**
 * The copyable trace ID under "Details" of an error (UI-25, LOG-04), and in the developer details
 * of dev mode, where it can also link to the trace in Grafana (UI-35, ADR-0007). The feature
 * builds the link from the settings; this component only renders it. The link opens a new tab, so
 * the console stays where it was, and its name says so.
 */
import { Copy, ExternalLink } from "lucide-react";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";
import {
  type CopyOutcome,
  useCopyToClipboard,
} from "@/design-system/primitives/use-copy-to-clipboard";
import { VisuallyHidden } from "@/design-system/primitives/visually-hidden";

const textByCopyOutcome: Readonly<Record<CopyOutcome, string>> = {
  idle: "",
  copied: "Trace ID copied.",
  failed: "The trace ID could not be copied. Select it to copy it.",
};

/** Props of {@link TraceId}. */
export type TraceIdProps = {
  /** The 32-character W3C trace ID from the Problem Details body. */
  readonly traceId: string;
  /** The ready link to this trace in Grafana; without it, there is no link. */
  readonly traceHref?: string;
};

/**
 * Render "Details: trace <id>" with a copy button, and the Grafana link when there is one.
 *
 * @param props - The trace ID and the link to the trace.
 * @returns The details line.
 */
export function TraceId({ traceId, traceHref }: TraceIdProps) {
  const { copyOutcome, copy } = useCopyToClipboard();
  return (
    <span className="inline-flex flex-wrap items-center gap-2 text-xs text-text-muted">
      <span>
        Details: trace <span className="font-mono select-all">{traceId}</span>
      </span>
      <button
        type="button"
        aria-label="Copy trace ID"
        className={cn("rounded-sm p-1 text-text-muted hover:text-text", FOCUS_RING_CLASSES)}
        onClick={() => {
          void copy(traceId);
        }}
      >
        <Icon icon={Copy} />
      </button>
      {traceHref === undefined ? null : (
        <a
          href={traceHref}
          target="_blank"
          rel="noreferrer"
          className={cn(
            "inline-flex items-center gap-1 rounded-sm font-medium text-primary hover:underline",
            FOCUS_RING_CLASSES,
          )}
        >
          Open in Grafana <VisuallyHidden>(opens in a new tab)</VisuallyHidden>
          <Icon icon={ExternalLink} size="xs" />
        </a>
      )}
      <span role="status">{textByCopyOutcome[copyOutcome]}</span>
    </span>
  );
}
