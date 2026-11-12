/**
 * Copy text to the clipboard and remember the outcome, so a screen can announce it (UI-25: the
 * copyable trace ID; account management design: Copy password).
 */
import { useState } from "react";

/** What the last copy did. */
export type CopyOutcome = "idle" | "copied" | "failed";

/** The copy function and the outcome of the last copy. */
export type ClipboardCopy = {
  readonly copyOutcome: CopyOutcome;
  /** Copies the text; a refusal of the browser becomes the `failed` outcome. */
  readonly copy: (text: string) => Promise<void>;
};

/**
 * Copy text to the clipboard.
 *
 * @returns The copy function and the outcome of the last copy.
 */
export function useCopyToClipboard(): ClipboardCopy {
  const [copyOutcome, setCopyOutcome] = useState<CopyOutcome>("idle");
  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopyOutcome("copied");
    } catch (error) {
      if (!isClipboardRefusal(error)) {
        throw error;
      }
      setCopyOutcome("failed");
    }
  };
  return { copyOutcome, copy };
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
