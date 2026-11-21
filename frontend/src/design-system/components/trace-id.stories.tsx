import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";

import { TraceId } from "@/design-system/components/trace-id";

const meta = {
  title: "Design system/Components/TraceId",
  component: TraceId,
  args: { traceId: "4bf92f3577b34da6a3ce929d0e0e4736" },
} satisfies Meta<typeof TraceId>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
/** In the developer details of dev mode, with the link to the trace in Grafana (UI-35). */
export const WithGrafanaLink: Story = {
  args: { traceHref: "http://localhost:3000/explore?trace=4bf92f3577b34da6a3ce929d0e0e4736" },
  play: async ({ canvas, args }) => {
    const link = canvas.getByRole("link", { name: "Open in Grafana (opens in a new tab)" });
    await expect(link).toHaveAttribute("href", args.traceHref);
    await expect(link).toHaveAttribute("target", "_blank");
  },
};
