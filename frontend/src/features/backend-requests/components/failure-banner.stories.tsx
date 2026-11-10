import type { Meta, StoryObj } from "@storybook/react-vite";

import { Button } from "@/design-system";
import { FailureBanner } from "@/features/backend-requests/components/failure-banner";

const meta = {
  title: "Backend requests/FailureBanner",
  component: FailureBanner,
  args: {
    lead: "Your message was not sent.",
    failure: {
      kind: "problem",
      status: 503,
      problemType: "not_ready",
      traceId: "1c80319c0af7651916cd43dd8448eb21",
    },
  },
} satisfies Meta<typeof FailureBanner>;

export default meta;

type Story = StoryObj<typeof meta>;

export const NotReady: Story = {};
export const NotFound: Story = {
  args: {
    failure: { kind: "problem", status: 404, problemType: "not_found" },
    notFoundMessage: "This order was not found.",
  },
};
export const TooLarge: Story = { args: { failure: { kind: "ingress", status: 413 } } };
export const RateLimited: Story = { args: { failure: { kind: "ingress", status: 429 } } };
export const WithAction: Story = { args: { action: <Button>Reload list</Button> } };
