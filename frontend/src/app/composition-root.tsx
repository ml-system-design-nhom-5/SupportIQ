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
  getRequestFailure,
  IdempotencyKeyFactoryContext,
  idempotentWriteMutationKey,
  isUnauthenticatedError,
  shouldRetryRequest,
} from "@/features/backend-requests";
import { endSession } from "@/features/session";

/** Everything the app receives from its composition root. */
export type AppDependencies = {
  readonly backendClient: BackendClient;
  readonly queryClient: QueryClient;
  readonly clock: Clock;
  readonly createIdempotencyKey: () => string;
  readonly randomBytes: RandomBytes;
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
};

/** Props of {@link AppProviders}. */
export type AppProvidersProps = {
  readonly dependencies: AppDependencies;
  readonly children: ReactNode;
};

/**
 * Create the dependencies of the app.
 *
 * @param options - The settings, the base URL, the fetch implementation, and the sources of
 *   randomness, time, and identifiers.
 * @returns The client, the query client, the clock, the key factory, and the random bytes.
 */
export function createAppDependencies(options: AppDependencyOptions): AppDependencies {
  listenToWindowFocus();
  return {
    backendClient: createBackendClient({
      baseUrl: options.baseUrl,
      requestTimeoutMs: options.settings.requestTimeoutMs,
      fetch: options.fetch,
    }),
    queryClient: createAppQueryClient(options),
    clock: options.clock,
    createIdempotencyKey: options.createIdempotencyKey,
    randomBytes: options.randomBytes,
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
            <RandomBytesContext value={dependencies.randomBytes}>{children}</RandomBytesContext>
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
 * screen opens sign-in with a return path (contracts v1 design, Common elements). Reads retry only
 * retryable failures (ERR-12). Writes are never retried, except the mutations
 * whose key starts with {@link idempotentWriteMutationKey}, which send an `Idempotency-Key`
 * (TS-29). Data loads again on window focus only where a screen asks for it (shop UI design,
 * Reloading on focus). Requests are sent even when the browser reports that it is offline, so the
 * person gets the error state of a lost connection instead of a request that waits (shop UI
 * design, States). An error that is not a request failure is a defect, which goes to the error
 * boundary of the route, so no screen stays in its loading state (TS-26).
 *
 * @param options - The settings and the random source.
 * @returns The query client.
 */
function createAppQueryClient(options: Pick<AppDependencyOptions, "settings" | "random">) {
  const isDefect = (error: unknown) => getRequestFailure(error) === undefined;
  const retry = (failureCount: number, error: unknown) =>
    shouldRetryRequest(failureCount, error, options.settings.requestRetryMaxCount);
  const retryDelay = (attemptIndex: number) =>
    computeRetryDelayMs(attemptIndex, options.settings.requestRetryBaseDelayMs, options.random());
  const endSessionOnUnauthenticated = (error: unknown) => {
    if (isUnauthenticatedError(error)) {
      endSession(queryClient, "no_valid_session");
    }
  };
  const queryClient: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: endSessionOnUnauthenticated }),
    mutationCache: new MutationCache({ onError: endSessionOnUnauthenticated }),
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
