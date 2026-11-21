/**
 * Checks that stories repeat.
 */
import { expect } from "storybook/test";

/**
 * Fail when the content of a story, or of any element in it, does not fit its width (UI-33).
 * Checking each element also finds text that `overflow: hidden` cuts off, and text that starts
 * before the left edge, where the page cannot scroll to it. Text that ends in an ellipsis is cut
 * off on purpose and shows it.
 *
 * @param canvasElement - The root element of the story.
 * @returns A promise that settles when the check is recorded in the story's report.
 */
export async function expectNoSidewaysOverflow(canvasElement: HTMLElement): Promise<void> {
  const canvasLeft = canvasElement.getBoundingClientRect().left;
  const overflowing = [canvasElement, ...canvasElement.querySelectorAll("*")].filter(
    (element) =>
      (element.clientWidth > 0 &&
        element.scrollWidth > element.clientWidth &&
        getComputedStyle(element).textOverflow !== "ellipsis") ||
      element.getBoundingClientRect().left < canvasLeft,
  );

  await expect(overflowing).toEqual([]);
}
