import type { Meta, StoryObj } from "@storybook/react-vite";

import { FrontendDetailsView } from "@/features/session/components/frontend-details-view";

const meta = {
  title: "Session/FrontendDetailsView",
  component: FrontendDetailsView,
  args: {
    details: {
      buildVersion: "cc489d3",
      settings: [
        { name: "VITE_REQUEST_TIMEOUT_MS", value: "10000" },
        { name: "VITE_DEV_MODE", value: "true" },
        { name: "VITE_GRAFANA_TRACE_URL" },
      ],
      dashboards: [
        { title: "System overview", href: "http://localhost:3000/d/system-overview" },
        { title: "AI pipeline", href: "http://localhost:3000/d/ai-pipeline" },
      ],
    },
  },
} satisfies Meta<typeof FrontendDetailsView>;

export default meta;

type Story = StoryObj<typeof meta>;

export const WithDashboards: Story = {};

/** A production build that was given no build version, without Grafana. */
export const NothingSet: Story = {
  args: {
    details: { settings: [{ name: "VITE_GRAFANA_TRACE_URL" }], dashboards: [] },
  },
};
