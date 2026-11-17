/**
 * The note for staff only (UI-21; console UI design, For staff only): AI text, so it carries the
 * `ai` marker (UI-13), in its own panel and never in the draft. It is never sent to the customer.
 */
import { Info } from "lucide-react";

import { Panel, PanelHeader, PanelSection, StaffNote, Tag } from "@/design-system";

/** Props of {@link StaffNotePanel}. */
type StaffNotePanelProps = {
  readonly note: string;
};

/**
 * Render the staff note.
 *
 * @param props - The note.
 * @returns The panel.
 */
export function StaffNotePanel({ note }: StaffNotePanelProps) {
  return (
    <Panel density="compact" as="section" label="For staff only" tone="ai">
      <PanelHeader
        icon={Info}
        level={2}
        title="For staff only"
        trailing={<Tag tone="ai">AI note</Tag>}
      />
      <PanelSection>
        <StaffNote>{note}</StaffNote>
      </PanelSection>
    </Panel>
  );
}
