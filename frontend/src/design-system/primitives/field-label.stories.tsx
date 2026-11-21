import type { Meta, StoryObj } from "@storybook/react-vite";

import { FieldLabel } from "@/design-system/primitives/field-label";
import { TextInput } from "@/design-system/primitives/text-input";

const meta = {
  title: "Design system/Primitives/FieldLabel",
  component: FieldLabel,
  args: { htmlFor: "password", children: "Password" },
  decorators: [
    (Story) => (
      <div>
        <Story />
        <TextInput id="password" type="password" />
      </div>
    ),
  ],
} satisfies Meta<typeof FieldLabel>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
