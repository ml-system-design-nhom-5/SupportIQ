import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, screen, within } from "storybook/test";

import { AccountsPage } from "@/features/admin-accounts/components/accounts-page";
import {
  createAdminAccountRoute,
  getCurrentSessionRoute,
  listAdminAccountsRoute,
} from "@/test/backend-routes";
import { exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { FIXED_SUGGESTED_PASSWORD } from "@/test/render-app";
import { withFakeBackend } from "@/test/story-backend";
import { acceptClipboardWrites, refuseClipboardWrites } from "@/test/story-clipboard";

const meta = {
  title: "Admin/Accounts/Create account",
  component: AccountsPage,
} satisfies Meta<typeof AccountsPage>;

export default meta;

type Story = StoryObj<typeof meta>;

/** The user-event instance of a story. */
type StoryUser = Parameters<NonNullable<Story["play"]>>[0]["userEvent"];

/**
 * Build the decorator of a story: the admin session, the accounts, and the answer to a creation.
 *
 * @param answer - What `createAdminAccount` answers.
 * @returns The decorator.
 */
function withCreateAnswer(answer: FakeAnswer) {
  return withFakeBackend((backend) => {
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "admin"));
    backend.answer(listAdminAccountsRoute, exampleAnswer(200, "listAdminAccounts", "first-page"));
    backend.answer(createAdminAccountRoute, answer);
  });
}

/**
 * Open the create dialog.
 *
 * @param canvasElement - The root element of the story.
 * @param user - The user-event instance of the story.
 * @returns The dialog.
 */
async function openDialog(canvasElement: HTMLElement, user: StoryUser): Promise<HTMLElement> {
  await user.click(await within(canvasElement).findByRole("button", { name: "Create account" }));
  return screen.findByRole("dialog", { name: "Create an account" });
}

/**
 * Type a display name in the open dialog and select Create account.
 *
 * @param dialog - The create dialog.
 * @param user - The user-event instance of the story.
 * @param displayName - The display name to type.
 */
async function typeNameAndSubmit(
  dialog: HTMLElement,
  user: StoryUser,
  displayName: string,
): Promise<void> {
  await user.type(within(dialog).getByRole("textbox", { name: "Display name" }), displayName);
  await user.click(within(dialog).getByRole("button", { name: "Create account" }));
}

/**
 * Open the dialog, leave the number empty for the next free number, type a display name, and
 * select Create account.
 *
 * @param canvasElement - The root element of the story.
 * @param user - The user-event instance of the story.
 * @param displayName - The display name to type.
 * @returns The dialog.
 */
async function submitCreation(
  canvasElement: HTMLElement,
  user: StoryUser,
  displayName = "Lan Do",
): Promise<HTMLElement> {
  const dialog = await openDialog(canvasElement, user);
  await typeNameAndSubmit(dialog, user, displayName);
  return dialog;
}

/**
 * Open the dialog, type a number and a display name, and select Create account.
 *
 * @param canvasElement - The root element of the story.
 * @param user - The user-event instance of the story.
 * @param loginNumber - The number to type.
 * @returns The dialog.
 */
async function submitCreationWithNumber(
  canvasElement: HTMLElement,
  user: StoryUser,
  loginNumber: string,
): Promise<HTMLElement> {
  const dialog = await openDialog(canvasElement, user);
  await user.type(within(dialog).getByRole("textbox", { name: "Login name" }), loginNumber);
  await typeNameAndSubmit(dialog, user, "Lan Do");
  return dialog;
}

export const Open: Story = {
  decorators: [withCreateAnswer({ kind: "no_answer" })],
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await openDialog(canvasElement, userEvent);

    await expect(within(dialog).getByLabelText("Password")).toHaveValue(FIXED_SUGGESTED_PASSWORD);
    await expect(within(dialog).getByRole("radio", { name: "Staff" })).toBeChecked();
  },
};

export const NumberInvalid: Story = {
  decorators: [withCreateAnswer({ kind: "no_answer" })],
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await submitCreationWithNumber(canvasElement, userEvent, "0");

    await expect(
      await within(dialog).findByText("Enter a whole number from 1 to 9999, or leave it empty."),
    ).toBeVisible();
  },
};

export const DisplayNameInvalid: Story = {
  decorators: [withCreateAnswer({ kind: "no_answer" })],
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await submitCreation(canvasElement, userEvent, " Lan Do");

    await expect(
      await within(dialog).findByText("Remove the spaces at the start and the end."),
    ).toBeVisible();
  },
};

export const PasswordInvalid: Story = {
  decorators: [withCreateAnswer({ kind: "no_answer" })],
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await openDialog(canvasElement, userEvent);
    await userEvent.clear(within(dialog).getByLabelText("Password"));

    await userEvent.click(within(dialog).getByRole("button", { name: "Create account" }));

    await expect(await within(dialog).findByText("Enter a password.")).toBeVisible();
  },
};

export const LoginNameTaken: Story = {
  decorators: [withCreateAnswer(exampleAnswer(409, "problems", "login-name-taken"))],
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await submitCreationWithNumber(canvasElement, userEvent, "4");

    await expect(
      await within(dialog).findByText(
        "staff-4 is already in use. Enter another number, or leave the field empty.",
      ),
    ).toBeVisible();
  },
};

export const Refused: Story = {
  decorators: [withCreateAnswer(exampleAnswer(422, "problems", "invalid-request"))],
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await submitCreation(canvasElement, userEvent);

    await expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "The account was not created. Check the fields and try again.",
    );
  },
};

export const OutcomeUnknown: Story = {
  decorators: [withCreateAnswer({ kind: "ingress", status: 504 })],
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await submitCreation(canvasElement, userEvent);

    await expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "The account may have been created. Select Create account again without editing the fields to find out.",
    );
  },
};

export const TechnicalFailure: Story = {
  decorators: [withCreateAnswer(exampleAnswer(500, "problems", "internal-error"))],
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await submitCreation(canvasElement, userEvent);

    const banner = await within(dialog).findByRole("alert");
    await expect(banner).toHaveTextContent("The account was not created.");
    await expect(banner).toHaveTextContent("Details: trace");
  },
};

export const PermissionDenied: Story = {
  decorators: [withCreateAnswer(exampleAnswer(403, "problems", "forbidden-role"))],
  play: async ({ canvas, canvasElement, userEvent }) => {
    await submitCreation(canvasElement, userEvent);

    await expect(
      await canvas.findByRole("heading", { name: "The admin area is for admin accounts" }),
    ).toBeVisible();
  },
};

export const AccountCreated: Story = {
  decorators: [withCreateAnswer(exampleAnswer(201, "createAdminAccount", "created"))],
  play: async ({ canvas, canvasElement, userEvent }) => {
    await submitCreation(canvasElement, userEvent);

    await expect(await canvas.findByRole("status")).toHaveTextContent(
      "Account created: Lan Do, login name staff-5.",
    );
    await expect(canvas.getByRole("button", { name: "Create account" })).toHaveFocus();
  },
};

export const PasswordCopied: Story = {
  decorators: [withCreateAnswer({ kind: "no_answer" })],
  beforeEach: acceptClipboardWrites,
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await openDialog(canvasElement, userEvent);

    await userEvent.click(within(dialog).getByRole("button", { name: "Copy password" }));

    await expect(await within(dialog).findByText("Password copied.")).toBeVisible();
  },
};

export const CopyFailed: Story = {
  decorators: [withCreateAnswer({ kind: "no_answer" })],
  beforeEach: refuseClipboardWrites,
  play: async ({ canvasElement, userEvent }) => {
    const dialog = await openDialog(canvasElement, userEvent);

    await userEvent.click(within(dialog).getByRole("button", { name: "Copy password" }));

    await expect(
      await within(dialog).findByText("The password could not be copied. Select it to copy it."),
    ).toBeVisible();
  },
};
