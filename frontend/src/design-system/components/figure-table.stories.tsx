import type { Meta, StoryObj } from "@storybook/react-vite";
import { Gauge, Inbox } from "lucide-react";
import { expect, within } from "storybook/test";

import { FigureTable } from "@/design-system/components/figure-table";

const meta = {
  title: "Design system/Components/FigureTable",
  component: FigureTable,
  args: {
    icon: Gauge,
    title: "Speed",
    rows: [
      { id: "latency-p50", label: "End-to-end latency p50", value: "3.6 s", target: "At most 4 s" },
      {
        id: "latency-p95",
        label: "End-to-end latency p95",
        value: "No data",
        target: "At most 12 s",
      },
      { id: "latency-count", label: "Tickets measured", value: "1 ticket", target: "No target" },
    ],
    emptyText: "No figures for this period.",
  },
} satisfies Meta<typeof FigureTable>;

export default meta;

type Story = StoryObj<typeof meta>;

export const WithTargets: Story = {};

export const WithoutFigures: Story = {
  args: {
    icon: Inbox,
    title: "AI outcomes",
    rows: [],
    emptyText: "No suggestions were completed in this period.",
  },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).queryByRole("table")).not.toBeInTheDocument();
  },
};

export const NarrowerThanAReportPanel: Story = {
  args: {
    rows: [
      {
        id: "handling-assisted",
        label: "Handling time p50, assisted",
        value: "17 min 30 s",
        target: "At least 20% shorter than manual",
      },
      {
        id: "ai-error-rate",
        label: "AI error rate",
        value: "25% · 1 of 4 suggestions",
        target: "No target",
      },
    ],
  },
  decorators: [
    (Story) => (
      // Narrower than a report panel, a third of the console at 1280 px (console UI design).
      <div className="w-ai-sidebar">
        <Story />
      </div>
    ),
  ],
  play: async ({ canvasElement }) => {
    const table = within(canvasElement).getByRole("table", { name: "Speed" });

    await expect(table.scrollWidth).toBeLessThanOrEqual(table.clientWidth);
  },
};
