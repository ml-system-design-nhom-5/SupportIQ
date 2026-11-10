import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";

import { SignInForm } from "@/features/session/components/sign-in-form";

const meta = {
  title: "Session/SignInForm",
  component: SignInForm,
  parameters: { layout: "fullscreen" },
  args: { isPending: false, onSubmit: fn() },
} satisfies Meta<typeof SignInForm>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Empty: Story = {};
export const Signing: Story = { args: { isPending: true } };
export const RefusedCredentials: Story = { args: { failure: { kind: "invalid_credentials" } } };
export const TechnicalFailure: Story = {
  args: {
    failure: {
      kind: "request_failure",
      failure: {
        kind: "problem",
        status: 503,
        problemType: "not_ready",
        traceId: "1c80319c0af7651916cd43dd8448eb21",
      },
    },
  },
};
export const LostConnection: Story = {
  args: { failure: { kind: "request_failure", failure: { kind: "network" } } },
};
