/**
 * The copyable trace ID under "Details" of an error (UI-25, LOG-04).
 */
import { Copy } from "lucide-react";
import { useState } from "react";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";

const textByCopyOutcome: Readonly<Record<CopyOutcome, string>> = {
  idle: "",
  copied: "Trace ID copied.",
  failed: "The trace ID could not be copied. Select it to copy it.",
};

/** What the copy button last did, announced to screen readers. */
type CopyOutcome = "idle" | "copied" | "failed";

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
  const [copyOutcome, setCopyOutcome] = useState<CopyOutcome>("idle");

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(traceId);
      setCopyOutcome("copied");
    } catch (error) {
      if (!isClipboardRefusal(error)) {
        throw error;
      }
      setCopyOutcome("failed");
    }
  };

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
          void handleCopy();
        }}
      >
        <Icon icon={Copy} />
      </button>
      <span role="status">{textByCopyOutcome[copyOutcome]}</span>
    </span>
  );
}

/**
 * Tell whether the browser refused the clipboard: a `DOMException` when it denies the write, a
 * `TypeError` on a page without the clipboard API.
 *
 * @param error - What the write threw.
 * @returns True for a refusal.
 */
function isClipboardRefusal(error: unknown): boolean {
  return error instanceof DOMException || error instanceof TypeError;
}
