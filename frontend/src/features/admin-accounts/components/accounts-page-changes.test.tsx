import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { chooseAndConfirm, findRow, openAccounts } from "@/test/accounts-screen";
import {
  changeAccountRoleRoute,
  changeAccountStatusRoute,
  listAdminAccountsRoute,
} from "@/test/backend-routes";
import { readExampleWith } from "@/test/contract-examples";
import { exampleAnswer } from "@/test/fake-backend";
import { testSettings } from "@/test/render-app";

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

describe("AccountsPage, changes", () => {
  it("names the account and the change in the dialog, and Cancel changes nothing (UI-45)", async () => {
    const { user, backend } = openAccounts();
    const row = await findRow("Mai Nguyen");

    await user.click(within(row).getByRole("button", { name: /Make manager/ }));

    const dialog = await screen.findByRole("alertdialog", { name: "Make Mai Nguyen a manager?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    });
    expect(backend.requestsTo(changeAccountRoleRoute)).toHaveLength(0);
  });

  it("changes a role after the confirmation, shows it, and loads the list again", async () => {
    const { user, backend } = openAccounts({
      list: [exampleAnswer(200, "listAdminAccounts", "first-page"), { kind: "no_answer" }],
    });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });

    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    });
    const row = await findRow("Mai Nguyen");
    expect(within(row).getByText("Manager")).toBeVisible();
    const [request] = backend.requestsTo(changeAccountRoleRoute);
    expect(request?.path).toBe(
      "/v1/admin/accounts/9a7d3e21-6c4b-4f8e-b1a2-3c5d7e9f0a12/role-changes",
    );
    expect(request?.body).toEqual({ role: "manager" });
    expect(request?.headers.get("Idempotency-Key")).toMatch(uuidPattern);
    await waitFor(() => {
      expect(backend.requestsTo(listAdminAccountsRoute)).toHaveLength(2);
    });
  });

  it("deactivates an account with the status operation", async () => {
    const { user, backend } = openAccounts();

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Deactivate" });

    await waitFor(() => {
      expect(backend.requestsTo(changeAccountStatusRoute)).toHaveLength(1);
    });
    expect(backend.requestsTo(changeAccountStatusRoute)[0]?.body).toEqual({ is_active: false });
  });

  it("reactivates an account with the status operation", async () => {
    const { user, backend } = openAccounts({
      list: [exampleAnswer(200, "listAdminAccounts", "last-page")],
      status: [exampleAnswer(201, "changeAccountStatus", "reactivated")],
    });

    await chooseAndConfirm(user, { name: "Minh Le", label: "Reactivate" });

    await waitFor(() => {
      expect(backend.requestsTo(changeAccountStatusRoute)).toHaveLength(1);
    });
    expect(backend.requestsTo(changeAccountStatusRoute)[0]?.body).toEqual({ is_active: true });
  });

  it("makes a manager staff with the role operation", async () => {
    const { user, backend } = openAccounts({
      role: [exampleAnswer(201, "changeAccountRole", "made-staff")],
    });

    await chooseAndConfirm(user, { name: "Hoa Pham", label: "Make staff" });

    await waitFor(() => {
      expect(backend.requestsTo(changeAccountRoleRoute)).toHaveLength(1);
    });
    expect(backend.requestsTo(changeAccountRoleRoute)[0]?.body).toEqual({ role: "staff" });
  });

  it("disables the dialog while the change is sent, so a double click sends it once", async () => {
    const { user, backend } = openAccounts({ role: [{ kind: "no_answer" }] });
    const row = await findRow("Mai Nguyen");
    await user.click(within(row).getByRole("button", { name: /Make manager/ }));
    const dialog = await screen.findByRole("alertdialog");

    await user.dblClick(within(dialog).getByRole("button", { name: "Make manager" }));

    expect(await within(dialog).findByRole("button", { name: "Making manager…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(backend.requestsTo(changeAccountRoleRoute)).toHaveLength(1);
  });

  it("retries a change automatically with the same key (TS-29)", async () => {
    const { user, backend } = openAccounts({
      role: [
        exampleAnswer(503, "problems", "not-ready"),
        exampleAnswer(201, "changeAccountRole", "made-manager"),
      ],
      settings: { ...testSettings, requestRetryMaxCount: 2 },
    });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });

    await waitFor(() => {
      expect(backend.requestsTo(changeAccountRoleRoute)).toHaveLength(2);
    });
    const keys = backend
      .requestsTo(changeAccountRoleRoute)
      .map((request) => request.headers.get("Idempotency-Key"));
    expect(keys[0]).toBe(keys[1]);
  });
});

describe("AccountsPage, refused and failed changes", () => {
  it("shows the last-manager banner with the account and the trace ID", async () => {
    const { user } = openAccounts({
      status: [exampleAnswer(422, "problems", "last-active-manager")],
    });

    await chooseAndConfirm(user, { name: "Hoa Pham", label: "Deactivate" });

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent(
      "Hoa Pham was not deactivated. This change would leave no active manager. Make another account a manager first.",
    );
    expect(within(banner).getByText("eb211c80319c0af7651916cd43dd8448")).toBeVisible();
    expect(within(banner).queryByRole("button", { name: "Reload list" })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    });
  });

  it.each([
    ["own-account", exampleAnswer(422, "problems", "own-account")],
    ["no violated rule", exampleAnswer(422, "problems", "invalid-request")],
    [
      "an unknown violated rule",
      {
        kind: "body",
        status: 422,
        body: readExampleWith("problems", "own-account", { violated_rule: "a_later_rule" }),
      } as const,
    ],
  ])("asks to reload the list for %s, and Reload list clears the banner", async (_case, answer) => {
    const { user, backend } = openAccounts({ role: [answer] });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent(
      "Mai Nguyen was not made a manager. The list may be out of date. Reload the list, then try again.",
    );
    await user.click(within(banner).getByRole("button", { name: "Reload list" }));

    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
    expect(backend.requestsTo(listAdminAccountsRoute)).toHaveLength(2);
  });

  it("says that the account was not found and loads the list again (404)", async () => {
    const { user, backend } = openAccounts({ role: [exampleAnswer(404, "problems", "not-found")] });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });

    expect(await screen.findByRole("alert")).toHaveTextContent("This account was not found.");
    await waitFor(() => {
      expect(backend.requestsTo(listAdminAccountsRoute)).toHaveLength(2);
    });
  });

  it("shows the permission-denied state when the caller is no longer an admin (403)", async () => {
    const { user } = openAccounts({ role: [exampleAnswer(403, "problems", "forbidden-role")] });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "The admin area is for admin accounts",
      }),
    ).toBeVisible();
  });

  it("opens sign-in with a return path when the session ended (401)", async () => {
    const { user, router } = openAccounts({
      role: [exampleAnswer(401, "problems", "unauthenticated")],
    });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sign-in");
    });
    expect(new URLSearchParams(router.state.location.search).get("returnTo")).toBe(
      "/admin/accounts",
    );
  });

  it("does not load the list again after a technical failure with a known outcome", async () => {
    const { user, backend } = openAccounts({ role: [exampleAnswer(503, "problems", "not-ready")] });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mai Nguyen was not made a manager.",
    );
    expect(backend.requestsTo(listAdminAccountsRoute)).toHaveLength(1);
  });

  it("explains a technical failure with the trace ID, and keeps the list", async () => {
    const { user } = openAccounts({ role: [exampleAnswer(500, "problems", "internal-error")] });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent(
      "Mai Nguyen was not made a manager. Something went wrong. Try again in a moment.",
    );
    expect(within(banner).getByText("319c0af7651916cd43dd8448eb211c80")).toBeVisible();
    expect(await findRow("Mai Nguyen")).toBeVisible();
  });
});
