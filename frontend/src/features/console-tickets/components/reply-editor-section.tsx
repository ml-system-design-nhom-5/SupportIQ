/**
 * The reply editor in its own section of a reply panel (console UI design, Draft editing and
 * citations), for the panels whose editor sits under their other sections.
 */
import { PanelSection } from "@/design-system";
import {
  ReplyEditorField,
  type ReplyEditorFieldProps,
} from "@/features/console-tickets/components/reply-editor-field";

/**
 * Render the editor in its own section of the panel.
 *
 * @param props - The text, its change handler, and the hints.
 * @returns The section with the editor.
 */
export function ReplyEditorSection(props: ReplyEditorFieldProps) {
  return (
    <PanelSection>
      <ReplyEditorField {...props} />
    </PanelSection>
  );
}
