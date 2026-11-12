import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";

import { FormField } from "@/design-system/components/form-field";
import { FormDialog } from "@/design-system/primitives/form-dialog";
import { TextInput } from "@/design-system/primitives/text-input";

const meta = {
  title: "Design system/Primitives/FormDialog",
  component: FormDialog,
  args: {
    text: { title: "Create an account", submitLabel: "Create account" },
    returnFocus: { opener: document.body, fallbackId: "opener" },
    isPending: false,
    onSubmit: fn(),
    onCancel: fn(),
    children: (
      <FormField inputId="display-name" label="Display name">
        <TextInput id="display-name" />
      </FormField>
    ),
  },
} satisfies Meta<typeof FormDialog>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const WithDescriptionAndDanger: Story = {
  args: {
    text: {
      title: "Reset the password of Minh Le?",
      description:
        "Minh Le (staff-2) will sign in with the new password. The current password stops working at once.",
      submitLabel: "Reset password",
    },
    tone: "danger",
  },
};
export const Pending: Story = { args: { isPending: true } };
