/**
 * The classes of a Radix menu, shared by every menu of the design system (CODE-48): the content
 * is a raised surface, at least the menu width, and the highlighted item gets the `background`
 * role and the focus outline, so the keyboard position is visible (UI-30). A menu adds its own
 * limits to the content, such as a maximum width or a list that scrolls.
 */

/** The classes of the content of a menu, which holds its items. */
export const MENU_CONTENT_CLASSES =
  "z-20 flex min-w-menu flex-col rounded-md border border-border bg-surface-raised p-1 text-sm shadow-md";

/** The classes of a menu item. */
export const MENU_ITEM_CLASSES =
  "flex cursor-default items-center gap-2 rounded-sm p-2 font-medium text-text outline-none data-disabled:opacity-45 data-highlighted:bg-background data-highlighted:outline-2 data-highlighted:-outline-offset-2 data-highlighted:outline-focus-ring";
