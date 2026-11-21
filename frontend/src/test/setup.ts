/**
 * Setup of the unit and component tests (Vitest with jsdom).
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

/**
 * How long `findBy` and `waitFor` wait. They return as soon as the condition holds, so this bound
 * only keeps a whole-app test from failing on a loaded machine (TEST-19).
 */
const ASYNC_WAIT_LIMIT_MS = 15_000;

configure({ asyncUtilTimeout: ASYNC_WAIT_LIMIT_MS });

/** How far off the screen the splitters of the console columns sit in jsdom. */
const OFF_SCREEN_PX = 10_000;

/**
 * jsdom has no `ResizeObserver`, which the resizable console columns use (react-resizable-panels).
 * jsdom lays nothing out, so no size ever changes and the stub reports nothing.
 */
class ResizeObserverStub {
  readonly observe = () => undefined;
  readonly unobserve = () => undefined;
  readonly disconnect = () => undefined;
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
  // jsdom puts every element in a 0 × 0 box at the top left, where user-event presses too, so
  // react-resizable-panels would take every press for a drag of a splitter and prevent it. Here
  // the splitters sit off the screen; the stories and the UI flow tests drag them in a browser.
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function boxInJsdom(
    this: HTMLElement,
  ) {
    return this.hasAttribute("data-separator")
      ? new DOMRect(-OFF_SCREEN_PX, -OFF_SCREEN_PX, 0, 0)
      : new DOMRect();
  });
  // TEST-16: no test reaches the network. Every request goes to the fake backend of src/test/.
  vi.stubGlobal("fetch", () => {
    throw new Error("A test called the real fetch. Use the fake backend of src/test/.");
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
