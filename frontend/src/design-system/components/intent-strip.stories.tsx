import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, screen } from "storybook/test";

import { IntentChoice } from "@/design-system/components/intent-choice";
import { IntentStrip } from "@/design-system/components/intent-strip";

/** A correction from the strip, with a few intents in Other intent. */
const correction = {
  otherIntents: [
    { value: "cancel_order", name: "Cancel order" },
    { value: "request_refund", name: "Request refund" },
    { value: "return_product", name: "Return product" },
    { value: "track_order", name: "Track order" },
  ],
  isSending: false,
  onUseIntent: fn(),
};

/** A predicted intent whose next candidates staff can use, and Other intent. */
const correctableArgs = {
  confidence: { band: "high", probability: 0.91 },
  candidates: [
    { name: "Request refund", probability: 0.05, value: "request_refund" },
    { name: "Return product", probability: 0.02, value: "return_product" },
  ],
  correction,
} as const;

/** The candidates of a low-confidence abstention, each with a value that staff can use. */
const choiceCandidates = [
  { name: "Cancel order", probability: 0.41, band: "low", value: "cancel_order" },
  { name: "Change order", probability: 0.33, value: "change_order" },
  { name: "Track order", probability: 0.11, value: "track_order" },
] as const;

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
} satisfies Meta<typeof IntentStrip<string>>;

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
export const Correctable: Story = { args: correctableArgs };
export const CorrectableWithUnknownCandidate: Story = {
  args: {
    confidence: { band: "medium", probability: 0.62 },
    candidates: [
      { name: "Request refund", probability: 0.2, value: "request_refund" },
      { name: "Unspecified intent", probability: 0.1 },
    ],
    correction,
  },
};
export const ChosenByStaffCorrectable: Story = {
  args: { intentName: "Request refund", candidates: [], correction },
};
export const CorrectionSending: Story = {
  args: { ...correctableArgs, correction: { ...correction, isSending: true } },
};
export const OtherIntentOpen: Story = {
  args: correctableArgs,
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(canvas.getByRole("button", { name: "Other intent" }));

    await expect(await screen.findByRole("menuitem", { name: "Cancel order" })).toBeVisible();
  },
};
export const ChooseAnIntentWithUse: Story = {
  render: () => <IntentChoice candidates={choiceCandidates} correction={correction} />,
};
export const ChooseAnIntentSending: Story = {
  render: () => (
    <IntentChoice candidates={choiceCandidates} correction={{ ...correction, isSending: true }} />
  ),
};
export const ChooseAnIntentOtherIntentOpen: Story = {
  render: () => <IntentChoice candidates={choiceCandidates} correction={correction} />,
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(canvas.getByRole("button", { name: "Other intent" }));

    await expect(await screen.findByRole("menuitem", { name: "Return product" })).toBeVisible();
  },
};
