import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { findRow, openAccounts } from "@/test/accounts-screen";
import { listAdminAccountsRoute } from "@/test/backend-routes";
import {
  countExampleItems,
  MAX_PAGE_LIMIT,
  readExampleItemPageWith,
  readFullPageOfExampleItem,
} from "@/test/contract-examples";
import { exampleAnswer } from "@/test/fake-backend";

describe("AccountsPage, the list", () => {
  it("shows the largest page and keeps it when the page after it arrives", async () => {
    const fullPage = readFullPageOfExampleItem(
      { folder: "listAdminAccounts", name: "first-page", index: 0 },
      "account_id",
    );
    const { user } = openAccounts({
      list: [
        { kind: "body", status: 200, body: fullPage },
        exampleAnswer(200, "listAdminAccounts", "last-page"),
      ],
    });
    expect(await screen.findAllByRole("rowheader")).toHaveLength(MAX_PAGE_LIMIT);

    await user.click(screen.getByRole("button", { name: "Show more accounts" }));

    expect(await screen.findByRole("rowheader", { name: /Minh Le/ })).toBeVisible();
    expect(screen.getAllByRole("rowheader")).toHaveLength(
      MAX_PAGE_LIMIT + countExampleItems("listAdminAccounts", "last-page"),
    );
  });

  it("opens from /admin and shows the accounts with role and status only (SEC-41)", async () => {
    const { router } = openAccounts({
      path: "/admin",
      list: [exampleAnswer(200, "listAdminAccounts", "last-page")],
    });

    const row = await findRow("Minh Le");

    expect(router.state.location.pathname).toBe("/admin/accounts");
    expect(screen.getByRole("heading", { level: 1, name: "Accounts" })).toBeVisible();
    expect(
      screen.getByText("Internal accounts only. Customer accounts are never listed."),
    ).toBeVisible();
    expect(within(row).getByText("Staff")).toBeVisible();
    expect(within(row).getByText("Deactivated")).toBeVisible();
    expect(screen.queryByText("0b2d4f6a-8c1e-4a3b-9d5f-7e9a1c3e5b18")).not.toBeInTheDocument();
  });

  it("offers the actions of each row by role and status", async () => {
    openAccounts({ list: [exampleAnswer(200, "listAdminAccounts", "last-page")] });

    const staff = await findRow("Minh Le");

    expect(within(staff).getByRole("button", { name: /Make manager/ })).toBeEnabled();
    expect(within(staff).getByRole("button", { name: /Reactivate/ })).toBeEnabled();
  });

  it("offers no action on the caller's own row and says why", async () => {
    openAccounts({ list: [exampleAnswer(200, "listAdminAccounts", "last-page")] });

    const own = await findRow("Quang Vo");

    expect(own).toHaveTextContent("Quang Vo (you)");
    expect(within(own).getByText("You cannot change your own account")).toBeVisible();
    expect(within(own).queryByRole("button")).not.toBeInTheDocument();
  });

  it("offers only the status change on another admin's row and says why", async () => {
    openAccounts({
      list: [
        {
          kind: "body",
          status: 200,
          body: readExampleItemPageWith(
            { folder: "listAdminAccounts", name: "last-page", index: 1 },
            { account_id: "another-admin", display_name: "An Tran" },
          ),
        },
      ],
    });

    const admin = await findRow("An Tran");

    expect(within(admin).getByText("The admin role cannot be changed")).toBeVisible();
    expect(within(admin).getAllByRole("button")).toHaveLength(1);
    expect(within(admin).getByRole("button", { name: /Deactivate/ })).toBeEnabled();
  });

  it("shows a safe label for a role that this version does not know (CON-22)", async () => {
    openAccounts({
      list: [
        {
          kind: "body",
          status: 200,
          body: readExampleItemPageWith(
            { folder: "listAdminAccounts", name: "first-page", index: 1 },
            { role: "auditor" },
          ),
        },
      ],
    });

    const row = await findRow("Mai Nguyen");

    expect(within(row).getByText("Unknown role")).toBeVisible();
    expect(within(row).queryByRole("button", { name: /Make/ })).not.toBeInTheDocument();
  });

  it("follows next_cursor with Show more accounts and stops (CON-14)", async () => {
    const { user, backend } = openAccounts({
      list: [
        exampleAnswer(200, "listAdminAccounts", "first-page"),
        exampleAnswer(200, "listAdminAccounts", "last-page"),
      ],
    });
    await findRow("Hoa Pham");

    await user.click(screen.getByRole("button", { name: "Show more accounts" }));

    await findRow("Quang Vo");
    expect(screen.getAllByRole("rowheader")).toHaveLength(4);
    expect(
      backend
        .requestsTo(listAdminAccountsRoute)
        .map((request) => request.searchParams.get("cursor")),
    ).toEqual([null, "eyJhIjoyfQ"]);
    expect(screen.queryByRole("button", { name: "Show more accounts" })).not.toBeInTheDocument();
  });
});

describe("AccountsPage, loading the list", () => {
  it("shows skeleton rows while the list loads (UI-24)", async () => {
    openAccounts({ list: [{ kind: "no_answer" }] });

    expect(await screen.findByText("Loading the accounts…")).toBeInTheDocument();
  });

  it("shows the load error with Try again and the trace ID", async () => {
    const { user } = openAccounts({
      list: [
        exampleAnswer(503, "problems", "not-ready"),
        exampleAnswer(200, "listAdminAccounts", "last-page"),
      ],
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "The accounts could not be loaded" }),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await findRow("Minh Le")).toBeVisible();
  });

  it("shows the permission-denied state with Sign out for another role (403)", async () => {
    openAccounts({ list: [exampleAnswer(403, "problems", "forbidden-role")] });

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "The admin area is for admin accounts",
      }),
    ).toBeVisible();
    expect(
      within(screen.getByRole("main")).getByRole("button", { name: "Sign out" }),
    ).toBeVisible();
  });

  it("keeps the accounts shown when the next page fails", async () => {
    const { user } = openAccounts({
      list: [exampleAnswer(200, "listAdminAccounts", "first-page"), { kind: "network_error" }],
    });
    await findRow("Hoa Pham");

    await user.click(screen.getByRole("button", { name: "Show more accounts" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "More accounts could not be loaded.",
    );
    expect(await findRow("Hoa Pham")).toBeVisible();
  });
});
