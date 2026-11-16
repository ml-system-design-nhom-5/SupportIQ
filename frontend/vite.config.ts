/**
 * Vite, Vitest, and dev-server settings of frontend.
 *
 * The dev server and `vite preview` proxy `/v1` and `/health` to `backend` or to the Prism mock,
 * so the session cookie stays on the page's origin (ADR-0009, `SameSite=Strict`). The proxy
 * target is the setting `SUPPORTIQ_BACKEND_URL` (README.md, Settings). The build writes the
 * Content Security Policy, which names the wake origin when `VITE_BACKEND_WAKE_ORIGIN` is set
 * (backend wake-up design, rule 10).
 */
import { storybookTest } from "@storybook/addon-vitest/vitest-plugin";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { playwright } from "@vitest/browser-playwright";
import { loadEnv, type Plugin, type ProxyOptions } from "vite";
import { defineConfig, type ViteUserConfig } from "vitest/config";

import { BACKEND_WAKE_ORIGIN_SETTING, parseBackendWakeOrigin } from "./src/app/build-settings.ts";
import { buildContentSecurityPolicy } from "./src/app/content-security-policy.ts";

/** The Prism mock of contracts/README.md (For consumers, The mock). */
const DEFAULT_BACKEND_URL = "http://127.0.0.1:4010";

const sharedConfig: ViteUserConfig = {
  // TODO(#5): the build is one chunk above 500 kB, so the first page loads every screen.
  // The Content Security Policy refuses `data:` fonts, so no asset is inlined.
  build: { assetsInlineLimit: 0 },
  resolve: {
    alias: { "@": new URL("./src", import.meta.url).pathname },
  },
  test: {
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}", "ingress/**/*.ts"],
      exclude: [
        "src/api/generated/**",
        "src/test/**",
        "src/**/*.stories.tsx",
        "src/**/*.test.{ts,tsx}",
        "src/app/main.tsx",
        "ingress/**/*.test.ts",
      ],
      // TEST-21: 80% branch coverage for the component, 90% for the view-model mappings.
      thresholds: {
        branches: 80,
        "src/features/*/model/**": { branches: 90 },
      },
    },
    projects: [
      {
        extends: true,
        // A unit test compares a value of frontend with its schema (src/test/contract-schemas.ts).
        server: { fs: { allow: [import.meta.dirname, "../contracts"] } },
        test: {
          name: "unit",
          environment: "jsdom",
          include: ["src/**/*.test.{ts,tsx}"],
          setupFiles: ["src/test/setup.ts"],
          // Whole-app tests type into the page; this bound only stops a stuck test.
          testTimeout: 60_000,
          // TEST-15: tests run in random order.
          sequence: { shuffle: true },
          env: { TZ: "UTC" },
        },
      },
      {
        extends: true,
        test: {
          name: "ingress",
          // The Pages Function runs on the Workers runtime (ADR-0016): the fetch API without a
          // DOM, as Node has it, so its tests need neither jsdom nor the setup of the app.
          environment: "node",
          include: ["ingress/**/*.test.ts"],
          sequence: { shuffle: true },
        },
      },
      {
        extends: true,
        plugins: [storybookTest({ configDir: ".storybook" })],
        // Bundle these before the first story runs. Otherwise Vite finds them during the run,
        // bundles again, and reloads, which fails the stories that were loading (TEST-19).
        optimizeDeps: {
          include: [
            "@radix-ui/react-alert-dialog",
            "@radix-ui/react-dialog",
            "@radix-ui/react-dropdown-menu",
            "@radix-ui/react-label",
            "@radix-ui/react-popover",
            "@radix-ui/react-tooltip",
            "@tanstack/react-query",
            "@testing-library/react",
            "@testing-library/user-event",
            "class-variance-authority",
            "clsx",
            "lucide-react",
            "openapi-fetch",
            "react-dom/client",
            "react-router",
            "storybook/test",
            "tailwind-merge",
          ],
        },
        test: {
          name: "storybook",
          sequence: { shuffle: true },
          browser: {
            enabled: true,
            headless: true,
            provider: playwright(),
            instances: [{ browser: "chromium" }],
          },
        },
      },
    ],
  },
};

export default defineConfig(({ mode }) => {
  const proxy = readBackendProxy(mode);
  return {
    ...sharedConfig,
    plugins: [react(), tailwindcss(), contentSecurityPolicy(readBackendWakeOrigin(mode))],
    // Stories and tests read the contract example files as fixtures (TEST-11).
    server: { proxy, fs: { allow: [".", "../contracts/examples"] } },
    preview: { proxy },
  };
});

/**
 * Read the proxy target, or stop with a message that names the setting (ARCH-34).
 *
 * @param value - The value of `SUPPORTIQ_BACKEND_URL`, or undefined when it is not set.
 * @returns The absolute HTTP URL of `backend` or of the mock.
 */
function parseBackendUrl(value: string | undefined): string {
  const url = value ?? DEFAULT_BACKEND_URL;
  if (!URL.canParse(url) || !/^https?:$/.test(new URL(url).protocol)) {
    throw new Error(`SUPPORTIQ_BACKEND_URL must be an absolute http or https URL, got "${url}".`);
  }
  return url;
}

/**
 * Build the proxy entries for the paths that `backend` serves.
 *
 * @param target - The proxy target.
 * @returns One entry for `/v1` and one for `/health`.
 */
function buildBackendProxy(target: string): Record<string, ProxyOptions> {
  return { "/v1": { target }, "/health": { target } };
}

/**
 * Add the Content Security Policy to the built page only, because the dev server injects an
 * inline script for React Fast Refresh.
 *
 * @param wakeOrigin - The Render origin of `backend`, or undefined when no wake request is sent.
 * @returns The Vite plugin.
 */
function contentSecurityPolicy(wakeOrigin: string | undefined): Plugin {
  const content = buildContentSecurityPolicy(wakeOrigin);
  return {
    name: "supportiq-content-security-policy",
    apply: "build",
    transformIndexHtml: () => [
      {
        tag: "meta",
        attrs: { "http-equiv": "Content-Security-Policy", content },
        injectTo: "head-prepend",
      },
    ],
  };
}

/**
 * Read the wake origin of a Vite mode with the parser that the app uses too (backend wake-up
 * design, rule 10), so an invalid value stops the build with the setting's name.
 *
 * @param mode - The Vite mode.
 * @returns The Render origin of `backend`, or undefined when the setting is not set.
 */
function readBackendWakeOrigin(mode: string): string | undefined {
  const environment = loadEnv(mode, import.meta.dirname, "VITE_");
  return parseBackendWakeOrigin(environment[BACKEND_WAKE_ORIGIN_SETTING]);
}

/**
 * Read the proxy of a Vite mode. Vite's `loadEnv` reads the shell and the `.env` files, and the
 * shell wins.
 *
 * @param mode - The Vite mode.
 * @returns The proxy entries.
 */
function readBackendProxy(mode: string): Record<string, ProxyOptions> {
  const { SUPPORTIQ_BACKEND_URL: backendUrl } = loadEnv(mode, import.meta.dirname, "SUPPORTIQ_");
  return buildBackendProxy(parseBackendUrl(backendUrl));
}
