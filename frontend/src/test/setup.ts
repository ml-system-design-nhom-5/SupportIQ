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

beforeEach(() => {
  // TEST-16: no test reaches the network. Every request goes to the fake backend of src/test/.
  vi.stubGlobal("fetch", () => {
    throw new Error("A test called the real fetch. Use the fake backend of src/test/.");
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
