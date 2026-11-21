/**
 * Storybook configuration: the catalog of every design-system and feature component, in every
 * variant and state (UI-04, UI-36). The a11y addon runs axe on every story, and the Vitest addon
 * turns each story into a test that fails on any axe violation (UI-32).
 */
import { defineMain } from "@storybook/react-vite/node";

export default defineMain({
  framework: "@storybook/react-vite",
  stories: ["../src/**/*.stories.tsx"],
  addons: ["@storybook/addon-a11y", "@storybook/addon-vitest"],
  core: { disableTelemetry: true },
});
