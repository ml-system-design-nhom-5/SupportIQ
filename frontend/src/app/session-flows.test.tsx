import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { chooseFromAccountMenu } from "@/test/account-menu";
import {
  createSessionRoute,
  deleteCurrentSessionRoute,
  getCurrentSessionRoute,
  listAdminAccountsRoute,
  listShopOrdersRoute,
} from "@/test/backend-routes";
import { createFakeBackend, exampleAnswer, noContentAnswer } from "@/test/fake-backend";
import { renderApp } from "@/test/render-app";

describe("a session answer of the wrong shape", () => {
  it("shows the error state with Try again, not a state for a role", async () => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, { kind: "body", status: 200, body: {} });

    renderApp({ path: "/shop", backend });

    expect(
      await screen.findByRole("heading", { name: "Your session could not be checked" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
  });
});

describe("a session that ends in the middle of a task", () => {
  it("opens sign-in once and returns to the same page afterwards", async () => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    backend.answer(
      listShopOrdersRoute,
      exampleAnswer(401, "problems", "unauthenticated"),
      exampleAnswer(200, "listShopOrders", "last-page"),
    );
    backend.answer(createSessionRoute, exampleAnswer(201, "createSession", "created"));
    const { user, router } = renderApp({ path: "/shop/orders", backend });

    await screen.findByRole("button", { name: "Sign in" });
    expect(router.state.location.pathname).toBe("/sign-in");
    expect(backend.requestsTo(listShopOrdersRoute)).toHaveLength(1);
    expect(new URLSearchParams(router.state.location.search).get("returnTo")).toBe("/shop/orders");
    await user.type(screen.getByRole("textbox", { name: "Login name" }), "customer-1");
    await user.type(screen.getByLabelText("Password"), "not-a-real-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("list", { name: "Your orders" })).toBeVisible();
    expect(router.state.location.pathname).toBe("/shop/orders");
  });
});

describe("switching accounts", () => {
  it("removes the customer's data on sign-out, so the next account never sees it", async () => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    backend.answer(listShopOrdersRoute, exampleAnswer(200, "listShopOrders", "last-page"));
    backend.answer(deleteCurrentSessionRoute, noContentAnswer);
    // createSession answers a SessionView, the schema of this getCurrentSession example.
    backend.answer(createSessionRoute, exampleAnswer(201, "getCurrentSession", "admin"));
    backend.answer(listAdminAccountsRoute, exampleAnswer(200, "listAdminAccounts", "last-page"));
    const { user, router, dependencies } = renderApp({ path: "/shop/orders", backend });
    await screen.findByRole("list", { name: "Your orders" });

    await chooseFromAccountMenu(user, "Sign out");

    await screen.findByRole("button", { name: "Sign in" });
    const keysAfterSignOut = dependencies.queryClient
      .getQueryCache()
      .getAll()
      .map((query) => query.queryKey[0]);
    expect(keysAfterSignOut).toEqual(["session"]);

    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "admin"));
    await user.type(screen.getByRole("textbox", { name: "Login name" }), "admin-1");
    await user.type(screen.getByLabelText("Password"), "not-a-real-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Accounts" })).toBeVisible();
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/admin/accounts");
    });
    expect(screen.queryByText(/ORD-/)).not.toBeInTheDocument();
    expect(screen.queryByText("Lan Tran")).not.toBeInTheDocument();
  });
});
