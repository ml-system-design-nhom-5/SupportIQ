/**
 * Checks that every UI flow repeats: axe on the current screen (UI-32), and no sideways scrolling
 * (UI-33).
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

/**
 * Fail when axe finds a WCAG violation on the current screen.
 *
 * @param page - The page.
 */
export async function expectNoAccessibilityViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();

  expect(results.violations).toEqual([]);
}

/**
 * Fail when the page scrolls sideways at the current viewport width.
 *
 * @param page - The page.
 */
export async function expectNoSidewaysScrolling(page: Page): Promise<void> {
  const overflowWidth = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );

  expect(overflowWidth).toBeLessThanOrEqual(0);
}
