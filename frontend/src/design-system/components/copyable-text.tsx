/**
 * A text that the person can read and copy but not change, such as a reply that could not be sent
 * (console UI design, Flow, step 6). It is rendered as text (SEC-22), and Copy text announces its
 * outcome, as the trace ID does (UI-25).
 */
import { Copy } from "lucide-react";

import { Button } from "@/design-system/primitives/button";
import { Text } from "@/design-system/primitives/text";
import {
  type CopyOutcome,
  useCopyToClipboard,
} from "@/design-system/primitives/use-copy-to-clipboard";

const textByCopyOutcome: Readonly<Record<CopyOutcome, string>> = {
  idle: "",
  copied: "Text copied.",
  failed: "The text could not be copied. Select it to copy it.",
};

/** Props of {@link CopyableText}. */
export type CopyableTextProps = {
  /** The name of the region, such as "Your unsent text". */
  readonly label: string;
  readonly children: string;
};

/**
 * Render the text with Copy text.
 *
 * @param props - The name of the region and the text.
 * @returns The region.
 */
export function CopyableText({ label, children }: CopyableTextProps) {
  const { copyOutcome, copy } = useCopyToClipboard();
  return (
    <section
      aria-label={label}
      className="flex flex-col items-start gap-2 rounded-md border border-border bg-background p-3"
    >
      <Text overflow="preserve">{children}</Text>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          leadingIcon={Copy}
          onClick={() => {
            void copy(children);
          }}
        >
          Copy text
        </Button>
        <span role="status" className="text-xs text-text-muted">
          {textByCopyOutcome[copyOutcome]}
        </span>
      </div>
    </section>
  );
}
