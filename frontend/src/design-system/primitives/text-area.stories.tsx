import type { Meta, StoryObj } from "@storybook/react-vite";

import { FormField } from "@/design-system/components/form-field";
import { TextArea } from "@/design-system/primitives/text-area";

const meta = {
  title: "Design system/Primitives/TextArea",
  component: TextArea,
  args: { id: "message", placeholder: "Describe your question." },
  decorators: [
    (Story) => (
      <FormField inputId="message" label="Write to support about this order">
        <Story />
      </FormField>
    ),
  ],
} satisfies Meta<typeof TextArea>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Empty: Story = {};
export const Filled: Story = {
  args: { defaultValue: "Can I also return the charging cable that came with the headphones?" },
};
export const Invalid: Story = { args: { defaultValue: "x".repeat(2001), "aria-invalid": true } };
export const Disabled: Story = { args: { defaultValue: "Sending this message", disabled: true } };
