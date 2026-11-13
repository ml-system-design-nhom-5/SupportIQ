/**
 * The reply editor of the reply area (console UI design, Draft editing and citations): plain text,
 * with every placeholder highlighted and named in a line under it (UI-43). The console never
 * restores or removes a placeholder; Send reply stays disabled while one is in the editor.
 */
import { PanelSection, ReplyEditor } from "@/design-system";
import {
  hasPlaceholder,
  PLACEHOLDER_LABEL,
  splitPlaceholders,
} from "@/features/console-tickets/model/placeholders";

/** Props of {@link ReplyEditorSection}. */
type ReplyEditorSectionProps = {
  readonly value: string;
  readonly onChange: (value: string) => void;
  /** Lines under the editor, such as "Edited text is not checked against the sources." */
  readonly hints?: readonly string[];
};

/**
 * Render the editor.
 *
 * @param props - The text, its handler, and the lines under the editor.
 * @returns The section with the editor.
 */
export function ReplyEditorSection({ value, onChange, hints = [] }: ReplyEditorSectionProps) {
  return (
    <PanelSection>
      <ReplyEditor
        label="Reply to the customer"
        value={value}
        onChange={onChange}
        markedParts={splitPlaceholders(value)}
        placeholder="Write the reply to the customer"
        hints={hasPlaceholder(value) ? [...hints, `${PLACEHOLDER_LABEL}.`] : hints}
      />
    </PanelSection>
  );
}
