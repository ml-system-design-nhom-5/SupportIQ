import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";

import { FailureState } from "@/features/backend-requests/components/failure-state";

const meta = {
  title: "Backend requests/FailureState",
  component: FailureState,
  args: {
    title: "Your orders could not be loaded",
    headingLevel: 1,
    isRetrying: false,
    onRetry: fn(),
    failure: {
      kind: "problem",
      status: 503,
      problemType: "not_ready",
      traceId: "1c80319c0af7651916cd43dd8448eb21",
    },
  },
} satisfies Meta<typeof FailureState>;

export default meta;

type Story = StoryObj<typeof meta>;

export const NotReady: Story = {};
export const Retrying: Story = { args: { isRetrying: true } };
export const LostConnection: Story = { args: { failure: { kind: "network" } } };
export const Timeout: Story = { args: { failure: { kind: "timeout" } } };
export const IngressGatewayTimeout: Story = { args: { failure: { kind: "ingress", status: 504 } } };
export const InSection: Story = { args: { headingLevel: 2, title: "Tickets could not be loaded" } };
