import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, screen, within } from "storybook/test";

import { AccountsPage } from "@/features/admin-accounts/components/accounts-page";
import {
  getCurrentSessionRoute,
  listAdminAccountsRoute,
  resetAccountPasswordRoute,
} from "@/test/backend-routes";
import { exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";
import { refuseClipboardWrites } from "@/test/story-clipboard";

const meta = {
  title: "Admin/Accounts/Reset password",
  component: AccountsPage,
} satisfies Meta<typeof AccountsPage>;

export default meta;

type Story = StoryObj<typeof meta>;

/** The user-event instance of a story. */
type StoryUser = Parameters<NonNullable<Story["play"]>>[0]["userEvent"];

/**
 * Build the decorator of a story: the admin session, a page of accounts, and the answer to a reset.
 *
 * @param answer - What `resetAccountPassword` answers.
 * @param page - The example of `listAdminAccounts`.
 * @returns The decorator.
 */
function withResetAnswer(answer: FakeAnswer, page = "first-page") {
  return withFakeBackend((backend) => {
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "admin"));
    backend.answer(listAdminAccountsRoute, exampleAnswer(200, "listAdminAccounts", page));
    backend.answer(resetAccountPasswordRoute, answer);
  });
}

/**
 * Open the reset dialog of an account.
 *
 * @param canvasElement - The root element of the story.
 * @param user - The user-event instance of the story.
 * @param displayName - The account of the row.
 * @returns The dialog.
 */
async function openDialog(
  canvasElement: HTMLElement,
  user: StoryUser,
  displayName = "Mai Nguyen",
): Promise<HTMLElement> {
  await user.click(
    await within(canvasElement).findByRole("button", {
      name: new RegExp(`Reset password.*${displayName}`),
    }),
  );
  return screen.findByRole("dialog", { name: `Reset the password of ${displayName}?` });
}

/**
 * Open the reset dialog of Mai Nguyen and select Reset password.
 *
 * @param canvasElement - The root element of the story.
 * @param user - The user-event instance of the story.
 * @returns The dialog.
 */
async function submitReset(canvasElement: HTMLElement, user: StoryUser): Promise<HTMLElement> {
  const dialog = await openDialog(canvasElement, user);
  await user.click(within(dialog).getByRole("button", { name: "Reset password" }));
  return dialog;
}

export const Open: Story = {
  decorators: [withResetAnswer({ kind: "no_answer" })],
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await openDialog(canvasElement, userEvent);

    await expect(dialog).toHaveTextContent(
      "Mai Nguyen (staff-1) will sign in with the new password. The current password stops working at once.",
    );
    await expect(
      within(dialog).getByRole("checkbox", { name: "Sign Mai Nguyen out of every session" }),
    ).toBeChecked();
  },
};

export const OpenForDeactivatedAccount: Story = {
  decorators: [withResetAnswer({ kind: "no_answer" }, "last-page")],
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await openDialog(canvasElement, userEvent, "Minh Le");

    await expect(dialog).toHaveTextContent(
      "The account stays deactivated until an admin reactivates it.",
    );
  },
};

export const PasswordInvalid: Story = {
  decorators: [withResetAnswer({ kind: "no_answer" })],
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await openDialog(canvasElement, userEvent);
    await userEvent.click(within(dialog).getByLabelText("Password"));
    await userEvent.paste("a".repeat(129));

    await userEvent.click(within(dialog).getByRole("button", { name: "Reset password" }));

    await expect(await within(dialog).findByText("Use at most 128 characters.")).toBeVisible();
  },
};

export const NotFound: Story = {
  decorators: [withResetAnswer(exampleAnswer(404, "problems", "not-found"))],
  play: async ({ canvas, canvasElement, userEvent }) => {
    await submitReset(canvasElement, userEvent);

    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "Mai Nguyen was not found. The list was loaded again.",
    );
  },
};

export const Refused: Story = {
  decorators: [withResetAnswer(exampleAnswer(422, "problems", "admin-password-unresettable"))],
  play: async ({ canvas, canvasElement, userEvent }) => {
    await submitReset(canvasElement, userEvent);

    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "The password of Mai Nguyen was not reset. Load the list again.",
    );
  },
};

export const OutcomeUnknown: Story = {
  decorators: [withResetAnswer({ kind: "network_error" })],
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await submitReset(canvasElement, userEvent);

    await expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "The password may have been reset. Select Reset password again without editing the fields to find out.",
    );
  },
};

export const TechnicalFailure: Story = {
  decorators: [withResetAnswer(exampleAnswer(503, "problems", "not-ready"))],
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await submitReset(canvasElement, userEvent);

    const banner = await within(dialog).findByRole("alert");
    await expect(banner).toHaveTextContent("The password of Mai Nguyen was not reset.");
    await expect(banner).toHaveTextContent("Details: trace");
  },
};

export const PasswordReset: Story = {
  decorators: [withResetAnswer(exampleAnswer(201, "resetAccountPassword", "reset"))],
  play: async ({ canvas, canvasElement, userEvent }) => {
    await submitReset(canvasElement, userEvent);

    await expect(await canvas.findByRole("status")).toHaveTextContent(
      "The password of Mai Nguyen was reset. Mai Nguyen was signed out of every session.",
    );
  },
};

export const CopyFailed: Story = {
  decorators: [withResetAnswer({ kind: "no_answer" })],
  beforeEach: refuseClipboardWrites,
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await openDialog(canvasElement, userEvent);

    await userEvent.click(within(dialog).getByRole("button", { name: "Copy password" }));

    await expect(
      await within(dialog).findByText("The password could not be copied. Select it to copy it."),
    ).toBeVisible();
  },
};
