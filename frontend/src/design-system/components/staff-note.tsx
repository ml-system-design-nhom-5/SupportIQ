/**
 * A note that the AI wrote for staff only (UI-21; console UI design, For staff only): never part
 * of the draft and never sent to the customer. The panel around it carries the `ai` marker
 * (UI-13). Text is rendered as text (SEC-22).
 */

/** Props of {@link StaffNote}. */
export type StaffNoteProps = {
  readonly children: string;
};

/**
 * Render the note.
 *
 * @param props - The text of the note.
 * @returns The note, with a bar in the `info` role.
 */
export function StaffNote({ children }: StaffNoteProps) {
  return (
    <p className="border-l-4 border-info pl-3 text-sm wrap-break-word whitespace-pre-wrap text-text">
      {children}
    </p>
  );
}
