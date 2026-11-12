import type { Meta, StoryObj } from "@storybook/react-vite";

import { IntentChoice } from "@/design-system/components/intent-choice";
import { IntentStrip } from "@/design-system/components/intent-strip";

const meta = {
  title: "Design system/Components/IntentStrip",
  component: IntentStrip,
  args: {
    intentName: "Refund status",
    candidates: [
      { name: "Request refund", probability: 0.05 },
      { name: "Return product", probability: 0.02 },
    ],
  },
} satisfies Meta<typeof IntentStrip>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Predicted: Story = { args: { confidence: { band: "high", probability: 0.91 } } };
export const MediumConfidence: Story = {
  args: { confidence: { band: "medium", probability: 0.62 } },
};
export const ChosenByStaff: Story = {
  args: { intentName: "Request refund", candidates: [] },
};
export const ChooseAnIntent: Story = {
  render: () => (
    <IntentChoice
      candidates={[
        { name: "Cancel order", probability: 0.41, band: "low" },
        { name: "Change order", probability: 0.33 },
        { name: "Track order", probability: 0.11 },
      ]}
    />
  ),
};
