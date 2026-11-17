/**
 * Keep a resizable console column and its preference in step (console UI design, Column
 * controls): the preference opens or collapses the panel, and a resize or collapse that the
 * person makes with the splitter goes back into the preference, in px.
 */
import { useEffect } from "react";
import { usePanelRef } from "react-resizable-panels";

/** A resizable column as the screen keeps it: its width in px and whether it is collapsed. */
export type ColumnState = {
  readonly width: number;
  readonly isCollapsed: boolean;
};

/** A resizable column and the handler of its changes. */
export type ResizableColumn = ColumnState & {
  readonly onChange: (column: ColumnState) => void;
};

/**
 * Connect a column to its panel.
 *
 * @param column - The width, whether it is collapsed, and the change handler.
 * @returns The ref of the panel, and the handler of a finished layout change of its group.
 */
export function useColumnPanel(column: ResizableColumn) {
  const panelRef = usePanelRef();
  const { width, isCollapsed } = column;
  useEffect(() => {
    const panel = panelRef.current;
    if (panel === null || panel.isCollapsed() === isCollapsed) {
      return;
    }
    if (isCollapsed) {
      panel.collapse();
      return;
    }
    panel.expand();
    panel.resize(width);
  }, [panelRef, width, isCollapsed]);
  const reportLayout = () => {
    // The library reports a finished change before React draws it, and the size in px comes from
    // the element (react-resizable-panels.js:1759), so the panel is read on the next frame.
    requestAnimationFrame(() => {
      const panel = panelRef.current;
      if (panel === null) {
        return;
      }
      const isNowCollapsed = panel.isCollapsed();
      // A collapsed panel keeps the width that it opens to again.
      const nowWidth = isNowCollapsed ? width : Math.round(panel.getSize().inPixels);
      if (isNowCollapsed !== isCollapsed || nowWidth !== width) {
        column.onChange({ width: nowWidth, isCollapsed: isNowCollapsed });
      }
    });
  };
  return { panelRef, reportLayout };
}
