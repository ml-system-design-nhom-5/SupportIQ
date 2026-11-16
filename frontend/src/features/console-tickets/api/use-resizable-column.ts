/**
 * Read and change one console column of the signed-in account (console UI design, Column
 * controls; UI-15). The browser keeps the layout, so it stays the same across tickets and reloads.
 */
import { use, useSyncExternalStore } from "react";

import type { ResizableColumn } from "@/design-system";
import {
  buildColumnLayoutKey,
  type ColumnName,
  parseColumnLayout,
} from "@/features/console-tickets/model/column-layout";
import {
  type PreferenceStore,
  PreferenceStoreContext,
  useSignedInAccountId,
} from "@/features/session";

/**
 * Read a column.
 *
 * @param name - The column: the inbox or the AI sidebar.
 * @returns The width of the column, whether it is collapsed, and the handler that keeps a change.
 * @throws Error when no composition root provides the preference store.
 */
export function useResizableColumn(name: ColumnName): ResizableColumn {
  const store = usePreferenceStore();
  const accountId = useSignedInAccountId();
  const key = accountId === undefined ? undefined : buildColumnLayoutKey(accountId);
  const readText = () => (key === undefined ? undefined : store.read(key));
  const layout = parseColumnLayout(useSyncExternalStore(store.subscribe, readText));
  return {
    ...layout[name],
    onChange: (column) => {
      if (key !== undefined) {
        // The layout is read again, so a change of the other column in the same moment stays.
        store.write(key, JSON.stringify({ ...parseColumnLayout(readText()), [name]: column }));
      }
    },
  };
}

/**
 * Read the preference store.
 *
 * @returns The store that the composition root provides.
 * @throws Error when there is none.
 */
function usePreferenceStore(): PreferenceStore {
  const store = use(PreferenceStoreContext);
  if (store === null) {
    throw new Error("useResizableColumn needs PreferenceStoreContext.");
  }
  return store;
}
