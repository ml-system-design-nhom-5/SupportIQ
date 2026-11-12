/**
 * The warnings of a suggestion (UI-18; console UI design, placement rule 1): at the top of the
 * reply area, next to the action they block. Each warning names the condition and says what to
 * check.
 */
import { TriangleAlert } from "lucide-react";

import { formatCount } from "@/design-system/format/number";
import { Icon } from "@/design-system/primitives/icon";

/** One warning. */
export type WarningListItem = {
  readonly warningId: string;
  /** The condition, for example "Missing information". */
  readonly title: string;
  /** What staff check, in plain language. */
  readonly description: string;
};

/** Props of {@link WarningList}. */
export type WarningListProps = {
  /** The warnings, at least one. */
  readonly warnings: readonly WarningListItem[];
};

/**
 * Render the warnings.
 *
 * @param props - The warnings.
 * @returns The count and the list.
 */
export function WarningList({ warnings }: WarningListProps) {
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
          </li>
        ))}
      </ul>
    </div>
  );
}
