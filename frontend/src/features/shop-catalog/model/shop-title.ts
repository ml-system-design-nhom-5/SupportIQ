/**
 * The shop name and the titles of shop pages. The project lead named the shop "Demo Shop" on
 * 2026-11-05 (shop UI design, Layout); it is defined only here.
 */

/** The brand of the shop. */
export const SHOP_NAME = "Demo Shop";

/**
 * Build the document title of a shop page (WCAG 2.4.2).
 *
 * @param pageName - The name of the page, for example "My orders".
 * @returns For example "My orders · Demo Shop".
 */
export function buildShopTitle(pageName: string): string {
  return `${pageName} · ${SHOP_NAME}`;
}
