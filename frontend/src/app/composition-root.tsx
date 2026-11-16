/**
 * The composition root of frontend (ARCH-21): it creates the `backend` client, the query client,
 * and the clock once, and provides them to the app. `main.tsx` passes the real browser
 * dependencies; tests pass a fake fetch, a fixed clock, and fixed random bytes.
 */
import {
  focusManager,
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import type { ReactNode } from "react";

import { type BackendClient, BackendClientContext, createBackendClient } from "@/api/client";
import type { FrontendSettings } from "@/app/settings";
import { type Clock, ClockContext } from "@/design-system";
import { type RandomBytes, RandomBytesContext } from "@/features/admin-accounts";
import {
  computeRetryDelayMs,
  createBackendWaker,
  getRequestFailure,
  IdempotencyKeyFactoryContext,
  idempotentWriteMutationKey,
  isRetryableFailure,
  isUnauthenticatedError,
  shouldRetryRequest,
  type WakeBackend,
} from "@/features/backend-requests";
import {
  createDevModePreferences,
  createPreferenceStore,
  DevModeContext,
  type DevModeSetup,
  endSession,
  type FrontendDetails,
  type PreferenceStorage,
  type PreferenceStore,
  PreferenceStoreContext,
} from "@/features/session";

/** Everything the app receives from its composition root. */
export type AppDependencies = {
  readonly backendClient: BackendClient;
  readonly queryClient: QueryClient;
  readonly clock: Clock;
  readonly createIdempotencyKey: () => string;
  readonly randomBytes: RandomBytes;
  readonly devMode: DevModeSetup;
  /** The display preferences of the screens, such as the widths of the console columns. */
  readonly preferenceStore: PreferenceStore;
};

/** What the composition root needs from its caller. */
export type AppDependencyOptions = {
  readonly settings: FrontendSettings;
  /** The origin of `backend`: the page's origin in the browser. */
  readonly baseUrl: string;
  readonly fetch: (request: Request) => Promise<Response>;
  /** The random source of the retry jitter, a number in [0, 1). */
  readonly random: () => number;
  readonly clock: Clock;
  /** Creates the `Idempotency-Key` of one user action (ARCH-31). */
  readonly createIdempotencyKey: () => string;
  /** The random source of suggested passwords: `crypto.getRandomValues` in the browser. */
  readonly randomBytes: RandomBytes;
  /**
   * Where display preferences such as dev mode are kept: `localStorage` in the browser, or
   * undefined when the browser refuses storage (UI-35).
   */
  readonly preferenceStorage: PreferenceStorage | undefined;
};

/** Props of {@link AppProviders}. */
export type AppProvidersProps = {
  readonly dependencies: AppDependencies;
  readonly children: ReactNode;
};

/**
 * Create the dependencies of the app.
 *
 * @param options - The settings, the base URL, the fetch implementation, the sources of
 *   randomness, time, and identifiers, and the preference storage.
 * @returns The client, the query client, the clock, the key factory, the random bytes, dev mode,
 *   and the preference store.
 */
export function createAppDependencies(options: AppDependencyOptions): AppDependencies {
  listenToWindowFocus();
  const { isDevModeAvailable, grafanaTraceUrl } = options.settings;
  const wakeBackend = createBackendWaker({
    origin: options.settings.backendWakeOrigin,
    timeoutMs: options.settings.backendWakeTimeoutMs,
    fetch: options.fetch,
  });
  // Backend wake-up design, rule 4: one wake request when the app starts, and one after each
  // retryable failure of a request (createAppQueryClient).
  void wakeBackend();
  return {
    backendClient: createBackendClient({
      baseUrl: options.baseUrl,
      requestTimeoutMs: options.settings.requestTimeoutMs,
      fetch: options.fetch,
    }),
    queryClient: createAppQueryClient(options, wakeBackend),
    clock: options.clock,
    createIdempotencyKey: options.createIdempotencyKey,
    randomBytes: options.randomBytes,
    devMode: {
      isAvailable: isDevModeAvailable,
      ...(grafanaTraceUrl === undefined ? {} : { grafanaTraceUrl }),
      preferences: createDevModePreferences(options.preferenceStorage),
      frontendDetails: buildFrontendDetails(options.settings),
    },
    preferenceStore: createPreferenceStore(options.preferenceStorage),
  };
}

/**
 * Describe frontend for the developer details of the admin area (admin UI design).
 *
 * @param settings - The settings.
 * @returns The build version, every `VITE_` setting, and the dashboards whose link is set.
 */
function buildFrontendDetails(settings: FrontendSettings): FrontendDetails {
  const { frontendBuildVersion } = settings;
  const dashboards = [
    { title: "System overview", href: settings.grafanaSystemOverviewUrl },
    { title: "AI pipeline", href: settings.grafanaAiPipelineUrl },
  ].flatMap(({ title, href }) => (href === undefined ? [] : [{ title, href }]));
  return {
    ...(frontendBuildVersion === undefined ? {} : { buildVersion: frontendBuildVersion }),
    settings: settings.viteSettings,
    dashboards,
  };
}

/**
 * Provide the dependencies to the app.
 *
 * @param props - The dependencies and the app.
 * @returns The providers around the app.
 */
export function AppProviders({ dependencies, children }: AppProvidersProps) {
  return (
    <QueryClientProvider client={dependencies.queryClient}>
      <BackendClientContext value={dependencies.backendClient}>
        <ClockContext value={dependencies.clock}>
          <IdempotencyKeyFactoryContext value={dependencies.createIdempotencyKey}>
            <RandomBytesContext value={dependencies.randomBytes}>
              <DevModeContext value={dependencies.devMode}>
                <PreferenceStoreContext value={dependencies.preferenceStore}>
                  {children}
                </PreferenceStoreContext>
              </DevModeContext>
            </RandomBytesContext>
          </IdempotencyKeyFactoryContext>
        </ClockContext>
      </BackendClientContext>
    </QueryClientProvider>
  );
}

/**
 * Create the query client with the request policy of frontend.
 *
 * A `401` from any request ends the session: the cached data of the account is removed, and the
 * screen opens sign-in with a return path (contracts v1 design, Common elements). A retryable
 * failure of any request sends a wake request, because `backend` may have stopped. Reads retry only
 * retryable failures (ERR-12). Writes are never retried, except the mutations
 * whose key starts with {@link idempotentWriteMutationKey}, which send an `Idempotency-Key`
 * (TS-29). Data loads again on window focus only where a screen asks for it (shop UI design,
 * Reloading on focus). Requests are sent even when the browser reports that it is offline, so the
 * person gets the error state of a lost connection instead of a request that waits (shop UI
 * design, States). An error that is not a request failure is a defect, which goes to the error
 * boundary of the route, so no screen stays in its loading state (TS-26).
 *
 * @param options - The settings and the random source.
 * @param wakeBackend - Sends a wake request, unless none is set up or one is in flight.
 * @returns The query client.
 */
function createAppQueryClient(
  options: Pick<AppDependencyOptions, "settings" | "random">,
  wakeBackend: WakeBackend,
) {
  const isDefect = (error: unknown) => getRequestFailure(error) === undefined;
  const retry = (failureCount: number, error: unknown) =>
    shouldRetryRequest(failureCount, error, options.settings.requestRetryMaxCount);
  const retryDelay = (attemptIndex: number) =>
    computeRetryDelayMs(attemptIndex, options.settings.requestRetryBaseDelayMs, options.random());
  const handleFailure = (error: unknown) => {
    if (isUnauthenticatedError(error)) {
      endSession(queryClient, "no_valid_session");
    }
    const failure = getRequestFailure(error);
    if (failure !== undefined && isRetryableFailure(failure)) {
      void wakeBackend();
    }
  };
  const queryClient: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: handleFailure }),
    mutationCache: new MutationCache({ onError: handleFailure }),
    defaultOptions: {
      queries: {
        retry,
        retryDelay,
        refetchOnWindowFocus: false,
        networkMode: "always",
        throwOnError: isDefect,
      },
      mutations: { retry: false, networkMode: "always" },
    },
  });
  queryClient.setMutationDefaults(idempotentWriteMutationKey, {
    retry,
    retryDelay,
    throwOnError: isDefect,
  });
  return queryClient;
}

/**
 * Tell TanStack Query when the window regains focus. Its default listens only for the tab
 * becoming visible, which misses a person who comes back from another window while the tab stayed
 * visible (shop UI design, Alternatives considered).
 *
 * TanStack Query also holds a retry for as long as it counts the window as unfocused, which would
 * send a write later without a new action and without a limit (ERR-13). So it always counts the
 * window as focused, and this listener only reports each return to the window.
 */
function listenToWindowFocus(): void {
  focusManager.setFocused(true);
  focusManager.setEventListener((notifyReturnToWindow) => {
    const handleFocusChange = () => {
      if (document.visibilityState !== "hidden") {
        notifyReturnToWindow();
      }
    };
    window.addEventListener("focus", handleFocusChange);
    document.addEventListener("visibilitychange", handleFocusChange);
    return () => {
      window.removeEventListener("focus", handleFocusChange);
      document.removeEventListener("visibilitychange", handleFocusChange);
    };
  });
}
