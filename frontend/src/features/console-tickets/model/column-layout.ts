/**
 * The layout of the console columns that the browser keeps for each account (console UI design,
 * Column controls; UI-15): the width in px of the inbox and of the AI sidebar, and whether each is
 * collapsed. The layout is the same on every ticket. The stored text is untrusted: text that is
 * not a layout gives the default columns, and a width outside its limits is brought within them.
 */
import { type ColumnState, consoleColumnSizes } from "@/design-system";
import { parseJson, readField } from "@/features/console-tickets/model/json-text";

/** The prefix of the key under which the browser keeps the column layout of an account. */
const PREFERENCE_KEY_PREFIX = "supportiq.console-columns.";

/** The columns that the person can resize and collapse. */
export type ColumnLayout = {
  readonly inbox: ColumnState;
  readonly aiDetails: ColumnState;
};

/** The name of a column of the layout. */
export type ColumnName = keyof ColumnLayout;

/**
 * Build the key of the column layout of one account, so that two people who share a browser keep
 * their own layout.
 *
 * @param accountId - The `account_id` of the signed-in account.
 * @returns For example `supportiq.console-columns.9a7d3e21-…`.
 */
export function buildColumnLayoutKey(accountId: string): string {
  return `${PREFERENCE_KEY_PREFIX}${accountId}`;
}

/**
 * Read a stored column layout.
 *
 * @param text - The stored text, or undefined when none is stored.
 * @returns The layout: the default of a column that the text does not hold, and every width within
 *   the limits of its column.
 */
export function parseColumnLayout(text: string | undefined): ColumnLayout {
  const stored = text === undefined ? undefined : parseJson(text);
  return {
    inbox: toColumnState(readField(stored, "inbox"), consoleColumnSizes.inbox),
    aiDetails: toColumnState(readField(stored, "aiDetails"), consoleColumnSizes.aiDetails),
  };
}

/**
 * Read a column of the layout.
 *
 * @param value - The stored column, which should hold `width` and `isCollapsed`.
 * @param sizes - The default width and the limits of the column.
 * @returns The column: the default width when the stored one is not a number, a width within the
 *   limits, and collapsed only when the stored value says so.
 */
function toColumnState(
  value: unknown,
  sizes: (typeof consoleColumnSizes)[ColumnName],
): ColumnState {
  const width = readField(value, "width");
  return {
    width:
      typeof width === "number" && Number.isFinite(width)
        ? Math.min(sizes.maxWidth, Math.max(sizes.minWidth, Math.round(width)))
        : sizes.defaultWidth,
    isCollapsed: readField(value, "isCollapsed") === true,
  };
}
