import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { openAccounts, openCreateDialog, openResetDialog } from "@/test/accounts-screen";
import { createAdminAccountRoute, listAdminAccountsRoute } from "@/test/backend-routes";
import { exampleAnswer } from "@/test/fake-backend";
import { expectNotCached } from "@/test/query-caches";
import { FIXED_SUGGESTED_PASSWORD } from "@/test/render-app";

const DISPLAY_NAME = "Lan Do";

/** A `staff` account of the list example. */
const RESET_ACCOUNT_NAME = "Mai Nguyen";

describe("Create account, an unknown outcome (account management design, Errors and guardrails)", () => {
  it("says that the account may have been created, loads the list again, and sends the same fields with the same key", async () => {
    const { user, backend } = openAccounts({
      create: [{ kind: "network_error" }, exampleAnswer(201, "createAdminAccount", "created")],
    });
    const dialog = await openCreateDialog(user, DISPLAY_NAME);

    await user.click(within(dialog).getByRole("button", { name: "Create account" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "The account may have been created. Select Create account again without editing the fields to find out.",
    );
    await waitFor(() => {
      expect(backend.requestsTo(listAdminAccountsRoute)).toHaveLength(2);
    });
    await user.click(within(dialog).getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Account created: Lan Do, login name staff-5.",
    );
    const [firstAttempt, secondAttempt] = backend.requestsTo(createAdminAccountRoute);
    expect(secondAttempt?.headers.get("Idempotency-Key")).toBe(
      firstAttempt?.headers.get("Idempotency-Key"),
    );
    expect(secondAttempt?.body).toEqual({
      role: "staff",
      display_name: DISPLAY_NAME,
      password: FIXED_SUGGESTED_PASSWORD,
    });
  });
});

describe("Create account, the password (admin UI design, Errors and guardrails)", () => {
  it("keeps no password in the query or mutation cache after the dialog closes", async () => {
    const { user, dependencies } = openAccounts();
    const dialog = await openCreateDialog(user, DISPLAY_NAME);

    await user.click(within(dialog).getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expectNotCached(dependencies.queryClient, FIXED_SUGGESTED_PASSWORD);
  });
});

describe("Reset password, the password (account management design, Shared behavior)", () => {
  it("keeps no password in the query or mutation cache after the dialog closes", async () => {
    const { user, dependencies } = openAccounts();
    const dialog = await openResetDialog(user, RESET_ACCOUNT_NAME);

    await user.click(within(dialog).getByRole("button", { name: "Reset password" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expectNotCached(dependencies.queryClient, FIXED_SUGGESTED_PASSWORD);
  });
});
