/**
 * Vite, Vitest, and dev-server settings of frontend.
 *
 * The dev server and `vite preview` proxy `/v1` and `/health` to `backend` or to the Prism mock,
 * so the session cookie stays on the page's origin (ADR-0009, `SameSite=Strict`). The proxy
 * target is the setting `SUPPORTIQ_BACKEND_URL` (README.md, Settings).
 */
import { storybookTest } from "@storybook/addon-vitest/vitest-plugin";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { playwright } from "@vitest/browser-playwright";
import { loadEnv, type Plugin, type ProxyOptions } from "vite";
import { defineConfig, type ViteUserConfig } from "vitest/config";

/** The Prism mock of contracts/README.md (For consumers, The mock). */
const DEFAULT_BACKEND_URL = "http://127.0.0.1:4010";

/**
 * The Content Security Policy of the built page (SEC-23): no inline script and no other origin.
 * Inline styles stay allowed, because the Radix primitives set styles on their elements.
 */
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const sharedConfig: ViteUserConfig = {
  plugins: [react(), tailwindcss(), contentSecurityPolicy()],
  // TODO(#5): the build is one chunk above 500 kB, so the first page loads every screen.
  // The Content Security Policy refuses `data:` fonts, so no asset is inlined.
  build: { assetsInlineLimit: 0 },
  resolve: {
    alias: { "@": new URL("./src", import.meta.url).pathname },
  },
  test: {
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/api/generated/**",
        "src/test/**",
        "src/**/*.stories.tsx",
        "src/**/*.test.{ts,tsx}",
        "src/app/main.tsx",
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
        plugins: [storybookTest({ configDir: ".storybook" })],
        // Bundle these before the first story runs. Otherwise Vite finds them during the run,
        // bundles again, and reloads, which fails the stories that were loading (TEST-19).
        optimizeDeps: {
          include: [
            "@radix-ui/react-alert-dialog",
            "@radix-ui/react-label",
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
 * @returns The Vite plugin.
 */
function contentSecurityPolicy(): Plugin {
  return {
    name: "supportiq-content-security-policy",
    apply: "build",
    transformIndexHtml: () => [
      {
        tag: "meta",
        attrs: { "http-equiv": "Content-Security-Policy", content: CONTENT_SECURITY_POLICY },
        injectTo: "head-prepend",
      },
    ],
  };
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
