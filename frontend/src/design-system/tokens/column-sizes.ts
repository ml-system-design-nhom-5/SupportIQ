/**
 * The sizes of the console columns in px, at every window width (console UI design, Column
 * controls; limits set by the project lead on 2026-11-15): the default widths of the layout
 * table, the limits of each resizable column, and the rail of a collapsed column. The columns
 * take their widths from here; `--container-inbox` and `--container-ai-sidebar` of tokens.css give
 * the same default widths to stories of a single component, and the ColumnWidths story of
 * tokens.stories.tsx keeps them equal.
 */
export const consoleColumnSizes = {
  inbox: { defaultWidth: 272, minWidth: 200, maxWidth: 400 },
  aiDetails: { defaultWidth: 340, minWidth: 280, maxWidth: 480 },
  middleMinWidth: 520,
  railWidth: 48,
  /** The splitter between two columns: the 8 px grip of the mockups with 4 px on each side. */
  separatorWidth: 16,
  /** The padding of the workspace columns: `p-4` on both sides, 16 px each. */
  workspacePadding: 32,
} as const;
