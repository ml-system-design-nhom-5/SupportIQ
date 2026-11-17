/**
 * A chip that shows a value and does nothing, such as an escalation reason in the panel of an
 * escalated ticket (console UI design, state-escalated.png). It looks like a chip of
 * {@link ToggleChipGroup} that is off, but it is plain text, not a control.
 */

/**
 * The classes of a chip that is off, shared with the chips of {@link ToggleChipGroup} (CODE-48). A
 * chip that is on overrides the colors with later classes.
 */
export const CHIP_CLASSES =
  "inline-flex h-6 items-center rounded-sm border border-border bg-background px-2 text-sm whitespace-nowrap text-text";

/** Props of {@link Chip}. */
export type ChipProps = {
  readonly children: string;
};

/**
 * Render a chip.
 *
 * @param props - The text.
 * @returns The chip.
 */
export function Chip({ children }: ChipProps) {
  return <span className={CHIP_CLASSES}>{children}</span>;
}
