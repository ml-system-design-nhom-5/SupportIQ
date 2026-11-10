import type { Meta, StoryObj } from "@storybook/react-vite";

import { FormField } from "@/design-system/components/form-field";
import { TextInput } from "@/design-system/primitives/text-input";

const meta = {
  title: "Design system/Primitives/TextInput",
  component: TextInput,
  args: { id: "login-name", placeholder: "staff-1" },
  decorators: [
    (Story) => (
      <FormField inputId="login-name" label="Login name">
        <Story />
      </FormField>
    ),
  ],
} satisfies Meta<typeof TextInput>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Empty: Story = {};
export const Filled: Story = { args: { defaultValue: "staff-1" } };
export const Invalid: Story = { args: { defaultValue: "staff-1", "aria-invalid": true } };
export const Disabled: Story = { args: { defaultValue: "staff-1", disabled: true } };
export const Password: Story = { args: { type: "password", defaultValue: "not-a-password" } };
