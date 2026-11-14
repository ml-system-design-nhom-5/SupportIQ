/**
 * The copyable trace ID under "Details" of an error (UI-25, LOG-04), and in the developer details
 * of dev mode, where it can also link to the trace in Grafana (UI-35, ADR-0007). The feature
 * builds the link from the settings; this component only renders it as an {@link ExternalLink},
 * which opens a new tab, so the console stays where it was, and says so in its name.
 */
import { Copy } from "lucide-react";

import { cn } from "@/design-system/primitives/class-names";
import { ExternalLink } from "@/design-system/primitives/external-link";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";
import {
  type CopyOutcome,
  useCopyToClipboard,
} from "@/design-system/primitives/use-copy-to-clipboard";

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
        <ExternalLink href={traceHref} emphasis="strong">
          Open in Grafana
        </ExternalLink>
      )}
      <span role="status">{textByCopyOutcome[copyOutcome]}</span>
    </span>
  );
}
