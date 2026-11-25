import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";

import { RadioGroup } from "@/design-system/primitives/radio-group";

const meta = {
  title: "Design system/Primitives/RadioGroup",
  component: RadioGroup,
  args: {
    name: "role",
    legend: "Role",
    options: [
      { value: "staff", label: "Staff" },
      { value: "manager", label: "Manager" },
    ],
    value: "staff",
    onValueChange: fn(),
  },
} satisfies Meta<typeof RadioGroup>;

export default meta;

type Story = StoryObj<typeof meta>;

export const FirstChosen: Story = {};
export const SecondChosen: Story = { args: { value: "manager" } };
