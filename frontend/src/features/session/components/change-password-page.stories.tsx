import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";

import { ChangePasswordPage } from "@/features/session/components/change-password-page";
import { changeOwnPasswordRoute, getCurrentSessionRoute } from "@/test/backend-routes";
import { exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

/** Visibly fake passwords of the stories. */
const CURRENT_PASSWORD = "not-the-old-password";
const NEW_PASSWORD = "not-the-new-password";

/** The fields that a story fills. */
type PasswordChangeEntries = {
  readonly current: string;
  readonly new: string;
  readonly confirmation: string;
};

const validEntries: PasswordChangeEntries = {
  current: CURRENT_PASSWORD,
  new: NEW_PASSWORD,
  confirmation: NEW_PASSWORD,
};

const meta = {
  title: "Session/ChangePasswordPage",
  component: ChangePasswordPage,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof ChangePasswordPage>;

export default meta;

type Story = StoryObj<typeof meta>;

/** The user-event instance of a story. */
type StoryUser = Parameters<NonNullable<Story["play"]>>[0]["userEvent"];

/**
 * Build the decorator of a story: a customer session, and the answer to the change.
 *
 * @param answer - What `changeOwnPassword` answers.
 * @returns The decorator.
 */
function withChangeAnswer(answer: FakeAnswer) {
  return withFakeBackend((backend) => {
    backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    backend.answer(changeOwnPasswordRoute, answer);
  });
}

/**
 * Paste a value into a field, as a password manager does.
 *
 * @param user - The user-event instance of the story.
 * @param field - The input.
 * @param value - The value.
 */
async function pasteInto(user: StoryUser, field: HTMLElement, value: string): Promise<void> {
  await user.click(field);
  await user.paste(value);
}

/**
 * Fill the three password fields, and select Change password.
 *
 * @param canvasElement - The root element of the story.
 * @param user - The user-event instance of the story.
 * @param entries - The passwords to type.
 */
async function fillAndSubmit(
  canvasElement: HTMLElement,
  user: StoryUser,
  entries: PasswordChangeEntries,
): Promise<void> {
  const canvas = within(canvasElement);
  await pasteInto(user, await canvas.findByLabelText("Current password"), entries.current);
  await pasteInto(user, canvas.getByLabelText("New password"), entries.new);
  await pasteInto(user, canvas.getByLabelText("Confirm new password"), entries.confirmation);
  await user.click(canvas.getByRole("button", { name: "Change password" }));
}

export const Empty: Story = { decorators: [withChangeAnswer({ kind: "no_answer" })] };

export const FieldsEmpty: Story = {
  decorators: [withChangeAnswer({ kind: "no_answer" })],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: "Change password" }));

    await expect(await canvas.findByText("Enter your current password.")).toBeVisible();
    await expect(canvas.getByText("Enter a new password.")).toBeVisible();
    await expect(canvas.getByText("Enter the new password again.")).toBeVisible();
  },
};

export const NewPasswordTooLong: Story = {
  decorators: [withChangeAnswer({ kind: "no_answer" })],
  play: async ({ canvas, canvasElement, userEvent }) => {
    const tooLong = "a".repeat(129);

    await fillAndSubmit(canvasElement, userEvent, {
      current: CURRENT_PASSWORD,
      new: tooLong,
      confirmation: tooLong,
    });

    await expect(await canvas.findByText("Use at most 128 characters.")).toBeVisible();
  },
};

export const NewPasswordsDifferent: Story = {
  decorators: [withChangeAnswer({ kind: "no_answer" })],
  play: async ({ canvas, canvasElement, userEvent }) => {
    await fillAndSubmit(canvasElement, userEvent, { ...validEntries, confirmation: "different" });

    await expect(await canvas.findByText("The two new passwords are different.")).toBeVisible();
  },
};

export const Pending: Story = {
  decorators: [withChangeAnswer({ kind: "no_answer" })],
  play: async ({ canvas, canvasElement, userEvent }) => {
    await fillAndSubmit(canvasElement, userEvent, validEntries);

    await expect(await canvas.findByRole("button", { name: "Changing password…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await expect(canvas.getByRole("button", { name: "Cancel" })).toBeDisabled();
  },
};

export const Changed: Story = {
  decorators: [withChangeAnswer(exampleAnswer(201, "changeOwnPassword", "changed"))],
  play: async ({ canvas, canvasElement, userEvent }) => {
    await fillAndSubmit(canvasElement, userEvent, validEntries);

    await expect(await canvas.findByRole("status")).toHaveTextContent(
      "Your password was changed. Your other sessions were signed out.",
    );
    await expect(canvas.getByRole("button", { name: "Go back" })).toBeVisible();
  },
};

export const CurrentPasswordIncorrect: Story = {
  decorators: [withChangeAnswer(exampleAnswer(422, "problems", "current-password-incorrect"))],
  play: async ({ canvas, canvasElement, userEvent }) => {
    await fillAndSubmit(canvasElement, userEvent, validEntries);

    await expect(await canvas.findByText("The current password is not correct.")).toBeVisible();
    await expect(canvas.getByLabelText("Current password")).toHaveValue("");
    await expect(canvas.getByLabelText("Current password")).toHaveFocus();
  },
};

export const Refused: Story = {
  decorators: [withChangeAnswer(exampleAnswer(422, "problems", "invalid-request"))],
  play: async ({ canvas, canvasElement, userEvent }) => {
    await fillAndSubmit(canvasElement, userEvent, validEntries);

    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "The password was not changed. Check the fields and try again.",
    );
  },
};

export const OutcomeUnknown: Story = {
  decorators: [withChangeAnswer({ kind: "ingress", status: 504 })],
  play: async ({ canvas, canvasElement, userEvent }) => {
    await fillAndSubmit(canvasElement, userEvent, validEntries);

    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "The password may have been changed. Select Change password again without editing the fields to find out.",
    );
  },
};

export const TechnicalFailure: Story = {
  decorators: [withChangeAnswer(exampleAnswer(503, "problems", "not-ready"))],
  play: async ({ canvas, canvasElement, userEvent }) => {
    await fillAndSubmit(canvasElement, userEvent, validEntries);

    const banner = await canvas.findByRole("alert");
    await expect(banner).toHaveTextContent("The password was not changed.");
    await expect(banner).toHaveTextContent("Details: trace");
  },
};
