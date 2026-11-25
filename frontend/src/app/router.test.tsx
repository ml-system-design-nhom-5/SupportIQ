import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppProviders, createAppDependencies } from "@/app/composition-root";
import { RouteErrorBoundary } from "@/app/route-error-boundary";
import { appRoutes } from "@/app/router";
import { RequestFailureError } from "@/features/backend-requests";
import {
  getCurrentSessionRoute,
  getShopOrderRoute,
  listShopTicketsRoute,
} from "@/test/backend-routes";
import { createFakeBackend, exampleAnswer } from "@/test/fake-backend";
import { createFakeEventSources } from "@/test/fake-event-source";
import {
  fixedRandomBytes,
  renderApp,
  TEST_BASE_URL,
  testNow,
  testSettings,
} from "@/test/render-app";

/**
 * Render a route that throws, with the route error boundary.
 *
 * @param error - What the route throws.
 */
function renderThrowingRoute(error: unknown): void {
  const Thrower = () => {
    throw error;
  };
  const router = createMemoryRouter([
    { path: "/", element: <Thrower />, errorElement: <RouteErrorBoundary /> },
  ]);
  render(<RouterProvider router={router} />);
}

describe("appRoutes", () => {
  it("shows the not-found page for an address that no route serves", async () => {
    renderApp({ path: "/no/such/page" });

    expect(
      await screen.findByRole("heading", { level: 1, name: "This page was not found" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the start page" })).toHaveAttribute("href", "/");
  });
});

describe("a defect while data loads", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("reaches the error boundary of the route, so no screen stays in its loading state", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const dependencies = createAppDependencies({
      settings: testSettings,
      baseUrl: TEST_BASE_URL,
      fetch: () => Promise.reject(new RangeError("A defect in frontend.")),
      random: () => 0,
      clock: () => testNow,
      createIdempotencyKey: () => "00000000-0000-4000-8000-000000000000",
      randomBytes: fixedRandomBytes,
      preferenceStorage: undefined,
      openEventSource: createFakeEventSources().open,
    });

    render(
      <AppProviders dependencies={dependencies}>
        <RouterProvider router={createMemoryRouter(appRoutes, { initialEntries: ["/shop"] })} />
      </AppProviders>,
    );

    expect(
      await screen.findByRole("heading", { level: 1, name: "This page could not be shown" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/A defect in frontend/)).not.toBeInTheDocument();
  });
});

describe("a defect in a write", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("reaches the error boundary of the screen, so the failure never stays silent", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    backend.answer(getShopOrderRoute, exampleAnswer(200, "getShopOrder", "refund-under-review"));
    backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "empty"));
    const dependencies = createAppDependencies({
      settings: testSettings,
      baseUrl: TEST_BASE_URL,
      fetch: (request) =>
        request.method === "POST"
          ? Promise.reject(new RangeError("A defect in frontend."))
          : backend.fetch(request),
      random: () => 0,
      clock: () => testNow,
      createIdempotencyKey: () => "00000000-0000-4000-8000-000000000000",
      randomBytes: fixedRandomBytes,
      preferenceStorage: undefined,
      openEventSource: createFakeEventSources().open,
    });
    render(
      <AppProviders dependencies={dependencies}>
        <RouterProvider
          router={createMemoryRouter(appRoutes, { initialEntries: ["/shop/orders/ORD-20931"] })}
        />
      </AppProviders>,
    );
    const user = userEvent.setup();

    await user.type(await screen.findByRole("textbox", { name: /Write to support/ }), "Hello");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "This page could not be shown" }),
    ).toBeInTheDocument();
  });
});

describe("RouteErrorBoundary", () => {
  it("shows a plain-language state with Reload page for an unexpected error (TS-26)", () => {
    renderThrowingRoute(new TypeError("Cannot read properties of undefined (reading 'x')"));

    expect(
      screen.getByRole("heading", { level: 1, name: "This page could not be shown" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Something went wrong. Reload the page to try again.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Reload page" })).toBeEnabled();
    expect(screen.queryByText(/Cannot read properties/)).not.toBeInTheDocument();
  });

  it("describes a request failure and shows its trace ID (UI-25)", () => {
    renderThrowingRoute(
      new RequestFailureError({
        kind: "problem",
        status: 500,
        problemType: "internal_error",
        traceId: "319c0af7651916cd43dd8448eb211c80",
      }),
    );

    expect(screen.getByText("Something went wrong. Try again in a moment.")).toBeVisible();
    expect(screen.getByText("319c0af7651916cd43dd8448eb211c80")).toBeVisible();
  });
});
