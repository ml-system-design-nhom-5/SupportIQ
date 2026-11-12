/**
 * The copyable trace ID under "Details" of an error (UI-25, LOG-04).
 */
import { Copy } from "lucide-react";

import { cn } from "@/design-system/primitives/class-names";
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
};

/**
 * Render "Details: trace <id>" with a copy button.
 *
 * @param props - The trace ID.
 * @returns The details line.
 */
export function TraceId({ traceId }: TraceIdProps) {
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
      <span role="status">{textByCopyOutcome[copyOutcome]}</span>
    </span>
  );
}
