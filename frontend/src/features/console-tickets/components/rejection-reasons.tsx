/**
 * Why staff rejected the draft (ADR-0006; console UI design, state-rejected.png): the staff reason
 * codes as chips, at least one, and a note when the code is Other. The reasons improve the AI after
 * review; the customer never sees them.
 */
import { useId } from "react";

import { FieldLabel, PanelSection, Stack, TextInput, ToggleChipGroup } from "@/design-system";
import {
  type StaffReasonCode,
  staffReasonOptions,
} from "@/features/console-tickets/model/staff-reason-codes";

/** Props of {@link RejectionReasons}. */
type RejectionReasonsProps = {
  readonly reasonCodes: ReadonlySet<StaffReasonCode>;
  readonly note: string;
  readonly onToggle: (reasonCode: StaffReasonCode) => void;
  readonly onNoteChange: (note: string) => void;
};

/**
 * Render the reasons of the rejection.
 *
 * @param props - The chosen codes, the note, and their handlers.
 * @returns The section with the chips and, for Other, the note.
 */
export function RejectionReasons({
  reasonCodes,
  note,
  onToggle,
  onNoteChange,
}: RejectionReasonsProps) {
  const noteId = useId();
  return (
    <PanelSection>
      <ToggleChipGroup
        label="Why did you reject it?"
        options={staffReasonOptions}
        selected={reasonCodes}
        onToggle={onToggle}
      />
      {reasonCodes.has("other") ? (
        <Stack gap="1">
          <FieldLabel htmlFor={noteId}>Note for the reason Other</FieldLabel>
          <TextInput
            id={noteId}
            value={note}
            onChange={(event) => {
              onNoteChange(event.target.value);
            }}
          />
        </Stack>
      ) : null}
    </PanelSection>
  );
}
