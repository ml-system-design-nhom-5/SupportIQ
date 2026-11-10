/**
 * Turn the pages of a cursor-paginated list into one list (CON-14).
 */

/**
 * Join the items of every loaded page, in page order, keeping each item once.
 *
 * `backend` returns each item at most once while a client follows `next_cursor`. An item that
 * frontend added to the first page after a write, before the list was loaded again, can also
 * arrive from `backend`; the first occurrence wins.
 *
 * @param pages - The items of each page, first page first.
 * @param getId - Returns the stable identifier of an item.
 * @returns The items of all pages, without duplicates.
 */
export function collectPageItems<Item>(
  pages: readonly (readonly Item[])[],
  getId: (item: Item) => string,
): readonly Item[] {
  const items: Item[] = [];
  const seenIds = new Set<string>();
  for (const item of pages.flat()) {
    const id = getId(item);
    if (!seenIds.has(id)) {
      seenIds.add(id);
      items.push(item);
    }
  }
  return items;
}
