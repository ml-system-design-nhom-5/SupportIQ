import type { Meta, StoryObj } from "@storybook/react-vite";

import { AppErrorBoundary } from "@/app/app-error-boundary";

const meta = {
  title: "App/AppErrorBoundary",
  component: AppErrorBoundary,
  parameters: { layout: "fullscreen" },
  args: { children: <DefectiveApp /> },
} satisfies Meta<typeof AppErrorBoundary>;

export default meta;

type Story = StoryObj<typeof meta>;

export const AppCouldNotStart: Story = {};

/**
 * Fail while rendering, as a defect does.
 *
 * @throws Error always.
 */
function DefectiveApp(): never {
  throw new Error("A defect that this story causes on purpose.");
}
