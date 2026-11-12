import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";

import { Checkbox } from "@/design-system/primitives/checkbox";

const meta = {
  title: "Design system/Primitives/Checkbox",
  component: Checkbox,
  args: {
    id: "sign-out-elsewhere",
    label: "Sign out of my other sessions",
    hint: "This browser stays signed in.",
    isChecked: true,
    onCheckedChange: fn(),
  },
} satisfies Meta<typeof Checkbox>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Checked: Story = {};
export const Unchecked: Story = { args: { isChecked: false } };
