/**
 * The decorators and parameters of every story: the design tokens and fonts, the app's
 * dependencies, a router for links unless the story brings its own, a fixed clock, so relative
 * times do not change between runs, and fixed random bytes, so suggested passwords do not either
 * (TEST-14). Stories never reach a backend: a request that a
 * story sends fails as a lost connection.
 */
import "@/design-system/tokens/tokens.css";

import type { Preview } from "@storybook/react-vite";
import { MemoryRouter } from "react-router";
import { configure } from "storybook/test";

import { AppProviders, createAppDependencies } from "@/app/composition-root";
import { fixedRandomBytes } from "@/test/render-app";

/** The time that every story treats as now. */
const storyNow = new Date("2026-11-05T09:00:00Z");

/**
 * How long `findBy` and `waitFor` wait in a story. They return as soon as the condition holds, so
 * this bound only keeps a story from failing on a loaded machine (TEST-19).
 */
configure({ asyncUtilTimeout: 15_000 });

const preview: Preview = {
  parameters: {
    // UI-32: an axe violation fails the story test.
    a11y: { test: "error" },
    layout: "padded",
  },
  decorators: [
    (Story, { parameters }) => (
      <AppProviders
        dependencies={createAppDependencies({
          settings: {
            requestTimeoutMs: 10_000,
            requestRetryMaxCount: 0,
            requestRetryBaseDelayMs: 1,
            isDevModeAvailable: false,
            backendWakeTimeoutMs: 90_000,
            viteSettings: [],
          },
          baseUrl: window.location.origin,
          fetch: () => Promise.reject(new TypeError("Stories have no backend.")),
          random: () => 0,
          createIdempotencyKey: () => "00000000-0000-4000-8000-000000000000",
          randomBytes: fixedRandomBytes,
          clock: () => storyNow,
          preferenceStorage: undefined,
        })}
      >
        {parameters["hasOwnRouter"] === true ? (
          <Story />
        ) : (
          <MemoryRouter>
            <Story />
          </MemoryRouter>
        )}
      </AppProviders>
    ),
  ],
};

export default preview;
