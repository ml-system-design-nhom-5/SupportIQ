import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { chooseAndConfirm, findRow, openAccounts } from "@/test/accounts-screen";
import { exampleAnswer } from "@/test/fake-backend";

/**
 * Open the confirmation of Make manager for Mai Nguyen.
 *
 * @param user - The user-event instance.
 * @returns The button that opened the dialog, and the dialog.
 */
async function openConfirmation(user: ReturnType<typeof openAccounts>["user"]) {
  const row = await findRow("Mai Nguyen");
  const opener = within(row).getByRole("button", { name: /Make manager/ });
  await user.click(opener);
  return { opener, dialog: await screen.findByRole("alertdialog") };
}

describe("AccountsPage, the focus after the confirmation (UI-30)", () => {
  it("returns the focus to the button that opened the dialog after Escape", async () => {
    const { user } = openAccounts();
    const { opener } = await openConfirmation(user);

    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(opener).toHaveFocus();
    });
  });

  it("returns the focus to the button that opened the dialog after Cancel", async () => {
    const { user } = openAccounts();
    const { opener, dialog } = await openConfirmation(user);

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    await waitFor(() => {
      expect(opener).toHaveFocus();
    });
  });

  it("moves the focus to the row when the change replaced the button", async () => {
    const { user } = openAccounts({
      list: [exampleAnswer(200, "listAdminAccounts", "first-page"), { kind: "no_answer" }],
    });

    await chooseAndConfirm(user, { name: "Mai Nguyen", label: "Make manager" });

    await waitFor(() => {
      expect(screen.getByRole("rowheader", { name: /Mai Nguyen/ })).toHaveFocus();
    });
    expect(screen.getByRole("button", { name: /Make staff: Mai Nguyen/ })).toBeVisible();
  });

  it("returns the focus to the button when the change was refused", async () => {
    const { user } = openAccounts({ role: [exampleAnswer(422, "problems", "own-account")] });
    const { opener, dialog } = await openConfirmation(user);

    await user.click(within(dialog).getByRole("button", { name: "Make manager" }));

    await screen.findByRole("alert");
    await waitFor(() => {
      expect(opener).toHaveFocus();
    });
  });
});
