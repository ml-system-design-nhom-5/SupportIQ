import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getCurrentSessionRoute, listConsoleTicketsRoute } from "@/test/backend-routes";
import { createFakeBackend, exampleAnswer } from "@/test/fake-backend";
import { renderApp } from "@/test/render-app";

/**
 * Open a path with a session of the given example.
 *
 * @param path - The app path.
 * @param sessionExample - The example of `getCurrentSession`.
 * @returns The rendered app.
 */
function openWithSession(path: string, sessionExample: string) {
  const backend = createFakeBackend();
  backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", sessionExample));
  backend.answer(listConsoleTicketsRoute, exampleAnswer(200, "listConsoleTickets", "open-queue"));
  return renderApp({ path, backend });
}

describe("ShopLayout", () => {
  it("shows Demo Shop, the navigation, and the account menu of the customer", async () => {
    openWithSession("/shop", "customer");

    const bar = await screen.findByRole("banner");
    expect(bar).toHaveTextContent("Demo Shop");
    const navigation = within(bar).getByRole("navigation", { name: "Main" });
    expect(
      within(navigation)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Products", "My orders", "Support"]);
    expect(within(bar).getByRole("button", { name: "Lan Tran · Customer" })).toBeVisible();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("shows only the brand to a session of another role (shop UI design, Permission denied)", async () => {
    openWithSession("/shop", "staff");

    const bar = await screen.findByRole("banner");
    expect(bar).toHaveTextContent("Demo Shop");
    expect(within(bar).queryByRole("navigation")).not.toBeInTheDocument();
    expect(within(bar).queryByText("Mai Nguyen")).not.toBeInTheDocument();
  });
});

describe("ConsoleLayout", () => {
  it("shows SupportIQ Console with Tickets, the account menu, and the inbox", async () => {
    openWithSession("/console", "manager");

    const bar = await screen.findByRole("banner");
    expect(bar).toHaveTextContent("SupportIQConsole");
    expect(within(bar).getByRole("link", { name: "Tickets" })).toHaveAttribute("href", "/console");
    expect(within(bar).getByRole("button", { name: "Hoa Pham · Manager" })).toBeVisible();
    expect(await screen.findByRole("complementary", { name: "Inbox" })).toBeVisible();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("shows only the brand to a session of another role", async () => {
    openWithSession("/console", "customer");

    const bar = await screen.findByRole("banner");
    expect(bar).toHaveTextContent("SupportIQConsole");
    expect(within(bar).queryByRole("navigation")).not.toBeInTheDocument();
    expect(within(bar).queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("AdminLayout", () => {
  it("shows SupportIQ Admin with Accounts and the account menu of the admin", async () => {
    openWithSession("/admin", "admin");

    const bar = await screen.findByRole("banner");
    expect(bar).toHaveTextContent("SupportIQAdmin");
    expect(within(bar).getByRole("link", { name: "Accounts" })).toHaveAttribute(
      "href",
      "/admin/accounts",
    );
    expect(within(bar).getByRole("button", { name: "Quang Vo · Admin" })).toBeVisible();
  });

  it("shows only the brand to a session of another role", async () => {
    openWithSession("/admin", "customer");

    const bar = await screen.findByRole("banner");
    expect(bar).toHaveTextContent("SupportIQAdmin");
    expect(within(bar).queryByRole("navigation")).not.toBeInTheDocument();
  });
});
