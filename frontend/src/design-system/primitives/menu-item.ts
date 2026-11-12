/**
 * The classes of an item in a Radix menu, shared by every menu of the design system (CODE-48): the
 * highlighted item gets the `background` role and the focus outline, so the keyboard position is
 * visible (UI-30).
 */

/** The classes of a menu item. */
export const MENU_ITEM_CLASSES =
  "flex cursor-default items-center gap-2 rounded-sm p-2 font-medium text-text outline-none data-disabled:opacity-45 data-highlighted:bg-background data-highlighted:outline-2 data-highlighted:-outline-offset-2 data-highlighted:outline-focus-ring";
