/**
 * The warnings of a suggestion (UI-18; console UI design, placement rule 1): at the top of the
 * reply area, next to the action they block. Each warning names the condition and says what to
 * check. With the acknowledgement props, each warning also gets the checkbox "I have checked
 * this"; the caller keeps Send reply disabled until every warning is acknowledged.
 */
import { TriangleAlert } from "lucide-react";

import { formatCount } from "@/design-system/format/number";
import { CHECKBOX_INPUT_CLASSES } from "@/design-system/primitives/checkbox";
import { Icon } from "@/design-system/primitives/icon";
import { VisuallyHidden } from "@/design-system/primitives/visually-hidden";

/** One warning. */
export type WarningListItem = {
  readonly warningId: string;
  /** The condition, for example "Missing information". */
  readonly title: string;
  /** What staff check, in plain language. */
  readonly description: string;
};

/** The acknowledgement of the warnings: both props, or neither, which shows no checkbox. */
type WarningAcknowledgementProps =
  | {
      /** The IDs of the warnings that staff acknowledged. */
      readonly acknowledgedIds: ReadonlySet<string>;
      /** Called when staff check or uncheck the checkbox of a warning. */
      readonly onAcknowledgedChange: (warningId: string, isAcknowledged: boolean) => void;
    }
  | { readonly acknowledgedIds?: never; readonly onAcknowledgedChange?: never };

/** Props of {@link WarningList}. */
export type WarningListProps = {
  /** The warnings, at least one. */
  readonly warnings: readonly WarningListItem[];
} & WarningAcknowledgementProps;

/**
 * Render the warnings.
 *
 * @param props - The warnings and, optionally, their acknowledgement.
 * @returns The count and the list.
 */
export function WarningList({ warnings, acknowledgedIds, onAcknowledgedChange }: WarningListProps) {
  const count = warnings.length;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm font-medium text-text-muted">
        {formatCount(count)} {count === 1 ? "warning" : "warnings"} to check before sending
      </p>
      <ul className="flex flex-col gap-2">
        {warnings.map((warning) => (
          <li
            key={warning.warningId}
            className="flex items-start gap-3 rounded-md border border-warning/35 bg-warning-subtle px-4 py-3 text-sm text-text"
          >
            <Icon icon={TriangleAlert} tone="warning" />
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <p className="font-semibold">{warning.title}</p>
              <p>{warning.description}</p>
            </div>
            {acknowledgedIds === undefined ? null : (
              <label className="flex shrink-0 items-center gap-2">
                <input
                  type="checkbox"
                  checked={acknowledgedIds.has(warning.warningId)}
                  className={CHECKBOX_INPUT_CLASSES}
                  onChange={(event) => {
                    onAcknowledgedChange(warning.warningId, event.target.checked);
                  }}
                />
                {/* The hidden end keeps the name of each checkbox unique, and the name starts with
                    the visible text (WCAG 2.5.3). */}
                I have checked this <VisuallyHidden>warning: {warning.title}</VisuallyHidden>
              </label>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
