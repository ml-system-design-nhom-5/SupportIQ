import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getCurrentSessionRoute } from "@/test/backend-routes";
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
  return renderApp({ path, backend });
}

describe("ShopLayout", () => {
  it("shows Demo Shop, the navigation, the customer's name, and Sign out", async () => {
    openWithSession("/shop", "customer");

    const bar = await screen.findByRole("banner");
    expect(bar).toHaveTextContent("Demo Shop");
    const navigation = within(bar).getByRole("navigation", { name: "Main" });
    expect(
      within(navigation)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Products", "My orders", "Support"]);
    expect(within(bar).getByText("Lan Tran")).toBeVisible();
    expect(within(bar).getByRole("button", { name: "Sign out" })).toBeVisible();
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
  it("shows the console app shell with the account, its role, and Sign out, and no ticket feature", async () => {
    openWithSession("/console", "manager");

    const bar = await screen.findByRole("banner");
    expect(bar).toHaveTextContent("SupportIQConsole");
    expect(within(bar).getByText("Hoa Pham")).toBeVisible();
    expect(within(bar).getByText("· Manager")).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 1, name: "The ticket inbox is not available yet" }),
    ).toBeVisible();
  });
});

describe("AdminLayout", () => {
  it("shows SupportIQ Admin with Accounts, the admin's name and role, and Sign out", async () => {
    openWithSession("/admin", "admin");

    const bar = await screen.findByRole("banner");
    expect(bar).toHaveTextContent("SupportIQAdmin");
    expect(within(bar).getByRole("link", { name: "Accounts" })).toHaveAttribute(
      "href",
      "/admin/accounts",
    );
    expect(within(bar).getByText("Quang Vo")).toBeVisible();
    expect(within(bar).getByText("· Admin")).toBeVisible();
  });

  it("shows only the brand to a session of another role", async () => {
    openWithSession("/admin", "customer");

    const bar = await screen.findByRole("banner");
    expect(bar).toHaveTextContent("SupportIQAdmin");
    expect(within(bar).queryByRole("navigation")).not.toBeInTheDocument();
  });
});
