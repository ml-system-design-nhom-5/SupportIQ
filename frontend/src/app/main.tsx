/**
 * The entry point of frontend: parse the settings, create the dependencies, and render the app.
 */
import "@/design-system/tokens/tokens.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";

import { AppErrorBoundary } from "@/app/app-error-boundary";
import { AppProviders, createAppDependencies } from "@/app/composition-root";
import { appRoutes } from "@/app/router";
import { parseFrontendSettings } from "@/app/settings";
import { systemClock } from "@/design-system";

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("index.html has no element with the id root.");
}

const dependencies = createAppDependencies({
  settings: parseFrontendSettings(import.meta.env),
  baseUrl: window.location.origin,
  fetch: (request) => fetch(request),
  random: Math.random,
  createIdempotencyKey: () => crypto.randomUUID(),
  randomBytes: (count) => crypto.getRandomValues(new Uint8Array(count)),
  clock: systemClock,
});

createRoot(rootElement).render(
  <StrictMode>
    <AppErrorBoundary>
      <AppProviders dependencies={dependencies}>
        <RouterProvider router={createBrowserRouter(appRoutes)} />
      </AppProviders>
    </AppErrorBoundary>
  </StrictMode>,
);
