/**
 * Render the whole app, or a part of it, with the real composition root, a memory router, the
 * fake backend, and a fixed clock.
 */
import { render, type RenderResult } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import type { ReactNode } from "react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";

import { type AppDependencies, AppProviders, createAppDependencies } from "@/app/composition-root";
import { appRoutes } from "@/app/router";
import type { FrontendSettings } from "@/app/settings";
import { ClockContext } from "@/design-system";
import { createFakeBackend, type FakeBackend } from "@/test/fake-backend";

/** The time that every test treats as now (TEST-14). */
export const testNow = new Date("2026-11-05T09:00:00Z");

/** The bytes that {@link fixedRandomBytes} repeats: the symbols t, e, s, and t. */
const fixedBytes = [26, 14, 25, 26] as const;

/**
 * The random source of every test and story (TEST-14): the bytes 26, 14, 25, and 26, repeated, so
 * the suggested password is always {@link FIXED_SUGGESTED_PASSWORD}.
 *
 * @param count - How many bytes to return.
 * @returns The bytes 26, 14, 25, and 26, repeated until there are count of them.
 */
export function fixedRandomBytes(count: number): Uint8Array {
  const repeats = Math.ceil(count / fixedBytes.length);
  return Uint8Array.from(
    Array.from({ length: repeats }, () => fixedBytes)
      .flat()
      .slice(0, count),
  );
}

/** The suggested password that {@link fixedRandomBytes} gives. */
export const FIXED_SUGGESTED_PASSWORD = "test-test-test";

/** The origin of the app in tests. */
export const TEST_BASE_URL = "http://localhost:3000";

/** Settings without automatic retries, so a failure shows at once. Retry tests set their own. */
export const testSettings: FrontendSettings = {
  requestTimeoutMs: 10_000,
  requestRetryMaxCount: 0,
  requestRetryBaseDelayMs: 1,
};

/** What a rendering helper returns. */
export type RenderedApp = RenderResult & {
  readonly user: UserEvent;
  readonly backend: FakeBackend;
  readonly dependencies: AppDependencies;
};

/** Options of {@link renderApp} and {@link renderWithDependencies}. */
export type RenderAppOptions = {
  /** The app path to open. */
  readonly path: string;
  /** The fake backend; a new one by default. */
  readonly backend?: FakeBackend;
  readonly settings?: FrontendSettings;
};

/**
 * Create the dependencies of a test, with the fake backend and the fixed clock.
 *
 * @param backend - The fake backend.
 * @param settings - The settings.
 * @returns The dependencies.
 */
export function createTestDependencies(
  backend: FakeBackend,
  settings: FrontendSettings = testSettings,
): AppDependencies {
  let keyCount = 0;
  return createAppDependencies({
    settings,
    baseUrl: TEST_BASE_URL,
    fetch: backend.fetch,
    random: () => 0,
    clock: () => testNow,
    randomBytes: fixedRandomBytes,
    createIdempotencyKey: () => {
      keyCount += 1;
      return `00000000-0000-4000-8000-${String(keyCount).padStart(12, "0")}`;
    },
  });
}

/**
 * Render the whole app at a path, with every route.
 *
 * @param options - The path, the fake backend, and the settings.
 * @returns The render result, a user-event instance, the backend, and the dependencies.
 */
export function renderApp(options: RenderAppOptions): RenderedApp & {
  readonly router: ReturnType<typeof createMemoryRouter>;
} {
  const backend = options.backend ?? createFakeBackend();
  const dependencies = createTestDependencies(backend, options.settings);
  const router = createMemoryRouter(appRoutes, { initialEntries: [options.path] });
  const user = userEvent.setup();
  const result = render(
    <AppProviders dependencies={dependencies}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...result, user, backend, dependencies, router };
}

/**
 * Render one component with the app's dependencies and a memory router at a path.
 *
 * @param ui - The component.
 * @param options - The path, the fake backend, and the settings.
 * @returns The render result, a user-event instance, the backend, and the dependencies.
 */
export function renderWithDependencies(ui: ReactNode, options: RenderAppOptions): RenderedApp {
  const backend = options.backend ?? createFakeBackend();
  const dependencies = createTestDependencies(backend, options.settings);
  const user = userEvent.setup();
  const result = render(
    <AppProviders dependencies={dependencies}>
      <MemoryRouter initialEntries={[options.path]}>{ui}</MemoryRouter>
    </AppProviders>,
  );
  return { ...result, user, backend, dependencies };
}

/**
 * Render a presentational component with a router and the fixed clock.
 *
 * @param ui - The component.
 * @returns The render result and a user-event instance.
 */
export function renderUi(ui: ReactNode): RenderResult & { readonly user: UserEvent } {
  const user = userEvent.setup();
  const result = render(
    <MemoryRouter>
      <ClockContext value={() => testNow}>{ui}</ClockContext>
    </MemoryRouter>,
  );
  return { ...result, user };
}
