/**
 * Placeholders in AI text and in the reply editor (UI-43; ADR-0010, Placeholder syntax). A mask, a
 * pseudonym that `backend` could not restore, and a restored `LITERAL`, which is customer text in
 * the reserved format, all match the same expression, and the contract cannot tell them apart. The
 * console highlights every match with one label and keeps Send reply and Submit for approval
 * disabled while the editor holds one; `backend` refuses such a reply with `422` as the backstop
 * (SEC-38). The console never restores or removes a placeholder itself.
 */
import type { MarkedTextPart } from "@/design-system";

/** The placeholder expression of ADR-0010, as `contracts/schemas/Placeholder.yaml` writes it. */
export const PLACEHOLDER_PATTERN = String.raw`\[(NAME|EMAIL|PHONE|CARD|ADDRESS|ORDER_ID|TRACKING_ID|TRANSACTION_ID|LITERAL)(_[1-9][0-9]{0,2})?\]`;

/** The label of highlighted placeholder text (UI-43, as the project lead decided on 2026-11-12). */
export const PLACEHOLDER_LABEL = "Personal data or reserved text: replace before sending";

/**
 * Split text into its placeholders, which are marked, and the text between them.
 *
 * @param text - AI text or the text of the editor, exactly as it is.
 * @returns The parts in order; joined, they give the text back unchanged. Empty text has no part.
 */
export function splitPlaceholders(text: string): readonly MarkedTextPart[] {
  const parts: MarkedTextPart[] = [];
  let end = 0;
  for (const match of text.matchAll(new RegExp(PLACEHOLDER_PATTERN, "g"))) {
    if (match.index > end) {
      parts.push({ text: text.slice(end, match.index), isMarked: false });
    }
    parts.push({ text: match[0], isMarked: true });
    end = match.index + match[0].length;
  }
  if (end < text.length) {
    parts.push({ text: text.slice(end), isMarked: false });
  }
  return parts;
}

/**
 * Tell whether text holds a placeholder.
 *
 * @param text - AI text or the text of the editor.
 * @returns True when any part of it matches the placeholder expression.
 */
export function hasPlaceholder(text: string): boolean {
  return new RegExp(PLACEHOLDER_PATTERN).test(text);
}
