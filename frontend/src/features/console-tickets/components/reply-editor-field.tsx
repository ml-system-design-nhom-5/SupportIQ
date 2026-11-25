/**
 * The reply editor of the reply area (console UI design, Draft editing and citations): plain text,
 * with every placeholder highlighted and named in a line under it (UI-43). The console never
 * restores or removes a placeholder; Send reply stays disabled while one is in the editor.
 */
import { ReplyEditor } from "@/design-system";
import {
  hasPlaceholder,
  PLACEHOLDER_LABEL,
  splitPlaceholders,
} from "@/features/console-tickets/model/placeholders";

/** Props of {@link ReplyEditorField} and of the section around it. */
export type ReplyEditorFieldProps = {
  readonly value: string;
  readonly onChange: (value: string) => void;
  /** Lines under the editor, such as "Edited text is not checked against the sources." */
  readonly hints?: readonly string[];
};

/**
 * Render the editor, with every placeholder highlighted and its label among the hints (UI-43).
 *
 * @param props - The text, its change handler, and the hints.
 * @returns The editor, such as inside the proposal card of a manager.
 */
export function ReplyEditorField({ value, onChange, hints = [] }: ReplyEditorFieldProps) {
  return (
    <ReplyEditor
      label="Reply to the customer"
      value={value}
      onChange={onChange}
      markedParts={splitPlaceholders(value)}
      placeholder="Write the reply to the customer"
      hints={hasPlaceholder(value) ? [...hints, `${PLACEHOLDER_LABEL}.`] : hints}
    />
  );
}
