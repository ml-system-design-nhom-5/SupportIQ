import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";

import { FormField } from "@/design-system/components/form-field";
import { PasswordInput } from "@/design-system/primitives/password-input";

const PASSWORD_ID = "story-password";

/** A visibly fake value of the stories. */
const STORY_PASSWORD = "not-a-real-password";

const meta = {
  title: "Design system/Primitives/PasswordInput",
  component: PasswordInput,
  args: { id: PASSWORD_ID, autoComplete: "current-password", defaultValue: STORY_PASSWORD },
  decorators: [
    (Story, { parameters }) => (
      <FormField
        inputId={PASSWORD_ID}
        label="Password"
        error={typeof parameters["fieldError"] === "string" ? parameters["fieldError"] : undefined}
      >
        <Story />
      </FormField>
    ),
  ],
} satisfies Meta<typeof PasswordInput>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Hidden: Story = {
  play: async ({ canvas }) => {
    await expect(canvas.getByLabelText("Password")).toHaveAttribute("type", "password");
    await expect(canvas.getByRole("button", { name: "Show password" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  },
};

export const Shown: Story = {
  play: async ({ canvas, userEvent }) => {
    const input = canvas.getByLabelText("Password");
    await userEvent.click(input);

    await userEvent.click(canvas.getByRole("button", { name: "Show password" }));

    await expect(canvas.getByRole("button", { name: "Show password" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(input).toHaveAttribute("type", "text");
    await expect(input).toHaveValue(STORY_PASSWORD);
    await expect(input).toHaveFocus();
  },
};

export const WithError: Story = {
  args: { defaultValue: "", "aria-invalid": true, "aria-describedby": `${PASSWORD_ID}-error` },
  parameters: { fieldError: "The current password is not correct." },
};
