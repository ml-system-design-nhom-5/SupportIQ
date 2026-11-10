import type { Meta, StoryObj } from "@storybook/react-vite";

import { FormField } from "@/design-system/components/form-field";
import { TextInput } from "@/design-system/primitives/text-input";

const meta = {
  title: "Design system/Components/FormField",
  component: FormField,
  args: {
    inputId: "login-name",
    label: "Login name",
    children: <TextInput id="login-name" placeholder="staff-1" />,
  },
} satisfies Meta<typeof FormField>;

export default meta;

type Story = StoryObj<typeof meta>;

export const WithTextInput: Story = {};
