import { act, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  createSessionRoute,
  getCurrentSessionRoute,
  listShopOrdersRoute,
} from "@/test/backend-routes";
import { createFakeBackend, exampleAnswer } from "@/test/fake-backend";
import { renderApp } from "@/test/render-app";

/**
 * Type the credentials and choose Sign in.
 *
 * @param user - The user-event instance of the test.
 */
async function submitCredentials(user: ReturnType<typeof renderApp>["user"]) {
  await user.type(screen.getByRole("textbox", { name: "Login name" }), "customer-1");
  await user.type(screen.getByLabelText("Password"), "not-a-real-password");
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("SignInPage", () => {
  it("shows the shared sign-in form without calling backend, so it can never loop", async () => {
    const { backend, user } = renderApp({ path: "/sign-in" });

    expect(screen.getByRole("heading", { level: 1, name: "SupportIQ Console" })).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Login name" })).toHaveAttribute(
      "placeholder",
      "staff-1",
    );
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    // Typing waits for the browser's task queue, so a request that the page started has been sent.
    await user.type(screen.getByRole("textbox", { name: "Login name" }), "c");
    expect(backend.requests).toHaveLength(0);
  });

  it("signs a customer in and opens the shop with the customer's name", async () => {
    const backend = createFakeBackend();
    backend.answer(createSessionRoute, exampleAnswer(201, "createSession", "created"));
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    const { user, router } = renderApp({ path: "/sign-in", backend });

    await submitCredentials(user);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/shop");
    });
    expect(await screen.findByText("Lan Tran")).toBeVisible();
  });

  it("sends the credentials once, without an Idempotency-Key (TS-29)", async () => {
    const backend = createFakeBackend();
    backend.answer(createSessionRoute, exampleAnswer(201, "createSession", "created"));
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    const { user } = renderApp({ path: "/sign-in", backend });

    await submitCredentials(user);

    await waitFor(() => {
      expect(backend.requestsTo(createSessionRoute)).toHaveLength(1);
    });
    const [request] = backend.requestsTo(createSessionRoute);
    expect(request?.body).toEqual({ login_name: "customer-1", password: "not-a-real-password" });
    expect(request?.headers.has("Idempotency-Key")).toBe(false);
  });

  it("returns to the page of the return path after sign-in", async () => {
    const backend = createFakeBackend();
    backend.answer(createSessionRoute, exampleAnswer(201, "createSession", "created"));
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    const { user, router } = renderApp({
      path: "/sign-in?returnTo=%2Fshop%2Forders%2FORD-20931",
      backend,
    });

    await submitCredentials(user);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/shop/orders/ORD-20931");
    });
  });

  it("shows one message for a refused sign-in and keeps what was typed (ADR-0009)", async () => {
    const backend = createFakeBackend();
    backend.answer(createSessionRoute, exampleAnswer(401, "problems", "invalid-credentials"));
    const { user, router } = renderApp({ path: "/sign-in", backend });

    await submitCredentials(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The login name or the password is not correct.",
    );
    expect(screen.getByRole("textbox", { name: "Login name" })).toHaveValue("customer-1");
    expect(screen.getByRole("textbox", { name: "Login name" })).toBeInvalid();
    expect(screen.getByLabelText("Password")).toHaveValue("not-a-real-password");
    expect(router.state.location.pathname).toBe("/sign-in");
  });
});

describe("SignInPage, starting a session", () => {
  it("keeps no sign-in attempt in memory, because each one holds the password", async () => {
    const backend = createFakeBackend();
    backend.answer(
      createSessionRoute,
      exampleAnswer(401, "problems", "invalid-credentials"),
      exampleAnswer(201, "createSession", "created"),
    );
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    const { dependencies, router, user } = renderApp({ path: "/sign-in", backend });

    await submitCredentials(user);
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/shop");
    });
    expect(dependencies.queryClient.getMutationCache().getAll()).toEqual([]);
  });

  it("removes the data of the account that was signed in before", async () => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    backend.answer(listShopOrdersRoute, exampleAnswer(200, "listShopOrders", "first-page"));
    backend.answer(createSessionRoute, exampleAnswer(201, "createSession", "created"));
    const { dependencies, router, user } = renderApp({ path: "/shop/orders", backend });
    await screen.findByRole("heading", { level: 1, name: "My orders" });
    await screen.findByRole("link", { name: /ORD-20990/ });

    // The browser's Back button opens sign-in like this: nothing ends the previous session.
    await act(() => router.navigate("/sign-in"));
    await submitCredentials(user);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/shop");
    });
    expect(dependencies.queryClient.getQueryData(["shop-orders", "orders"])).toBeUndefined();
  });
});

describe("SignInPage, failures and double submission", () => {
  it("explains a technical failure with its trace ID and never retries it (TS-29)", async () => {
    const backend = createFakeBackend();
    backend.answer(createSessionRoute, exampleAnswer(503, "problems", "not-ready"));
    const { user } = renderApp({
      path: "/sign-in",
      backend,
      settings: { requestTimeoutMs: 10_000, requestRetryMaxCount: 2, requestRetryBaseDelayMs: 1 },
    });

    await submitCredentials(user);

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("You were not signed in.");
    expect(banner).toHaveTextContent("The service is not available right now.");
    expect(screen.getByText("1c80319c0af7651916cd43dd8448eb21")).toBeVisible();
    expect(backend.requestsTo(createSessionRoute)).toHaveLength(1);
    expect(screen.getByRole("textbox", { name: "Login name" })).toHaveValue("customer-1");
  });

  it("explains an ingress failure that is not Problem Details", async () => {
    const backend = createFakeBackend();
    backend.answer(createSessionRoute, { kind: "ingress", status: 429 });
    const { user } = renderApp({ path: "/sign-in", backend });

    await submitCredentials(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many requests were sent. Wait a moment, then try again.",
    );
  });

  it("sends one request when Sign in is double-clicked", async () => {
    const backend = createFakeBackend();
    backend.answer(createSessionRoute, { kind: "no_answer" });
    const { user } = renderApp({ path: "/sign-in", backend });
    await user.type(screen.getByRole("textbox", { name: "Login name" }), "customer-1");
    await user.type(screen.getByLabelText("Password"), "secret");

    await user.dblClick(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("button", { name: "Signing in…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(backend.requestsTo(createSessionRoute)).toHaveLength(1);
  });

  it("does not send the form while a field is empty", async () => {
    const { user, backend } = renderApp({ path: "/sign-in" });

    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(backend.requests).toHaveLength(0);
  });
});
