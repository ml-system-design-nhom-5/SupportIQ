import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { openAccountMenu } from "@/test/account-menu";
import { openAccounts } from "@/test/accounts-screen";
import { getCurrentSessionRoute, listShopOrdersRoute } from "@/test/backend-routes";
import { createFakeBackend, exampleAnswer } from "@/test/fake-backend";
import { createMemoryStorage } from "@/test/memory-storage";
import { renderApp, testSettings } from "@/test/render-app";

/** Settings where dev mode is available. */
const devModeSettings = { ...testSettings, isDevModeAvailable: true };

/** The key of the dev mode switch of the customer account of the session example. */
const CUSTOMER_KEY = "supportiq.dev-mode.5f0c2a8e-3b1d-4c7a-9e2f-1a6b8d4c0e31";

describe("the dev mode switch in the account menu of each area (UI-35)", () => {
  it("is never offered to a customer in the shop, even where dev mode is available", async () => {
    const backend = createFakeBackend();
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    backend.answer(listShopOrdersRoute, exampleAnswer(200, "listShopOrders", "last-page"));
    const { user } = renderApp({
      path: "/shop/orders",
      backend,
      settings: devModeSettings,
      preferenceStorage: createMemoryStorage({ [CUSTOMER_KEY]: "on" }).storage,
    });
    await screen.findByRole("list", { name: "Your orders" });

    const menu = await openAccountMenu(user);

    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((menuItem) => menuItem.textContent),
    ).toEqual(["Change password", "Sign out"]);
    expect(within(menu).queryByRole("menuitemcheckbox")).not.toBeInTheDocument();
  });

  it("is offered to an admin, as to the roles of the console", async () => {
    const { user } = openAccounts({ settings: devModeSettings });
    await within(await screen.findByRole("banner")).findByRole("link", { name: "Accounts" });

    const menu = await openAccountMenu(user);

    expect(within(menu).getByRole("menuitemcheckbox", { name: "Dev mode" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });
});
