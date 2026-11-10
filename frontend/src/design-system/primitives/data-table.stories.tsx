import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";

import { DataTable } from "@/design-system/primitives/data-table";

const meta = {
  title: "Design system/Primitives/DataTable",
  component: DataTable<Column>,
  args: {
    caption: "Internal accounts",
    columns: [
      { key: "account", label: "Account" },
      { key: "role", label: "Role" },
      { key: "actions", label: "Actions", align: "end" },
    ],
    rows: [
      { id: "1", cells: { account: "An Tran (you)", role: "Admin", actions: "None" } },
      { id: "2", cells: { account: "Hoa Pham", role: "Manager", actions: "Make staff" } },
    ],
  },
} satisfies Meta<typeof DataTable<Column>>;

export default meta;

type Column = "account" | "role" | "actions";

type Story = StoryObj<typeof meta>;

export const TwoRows: Story = {};

export const NoRows: Story = { args: { rows: [] } };

export const LongUnbrokenName: Story = {
  args: {
    rows: [
      { id: "1", cells: { account: "N".repeat(160), role: "Staff", actions: "Make manager" } },
    ],
    columns: [
      { key: "account", label: "Account", isRowHeader: true },
      { key: "role", label: "Role" },
      { key: "actions", label: "Actions", align: "end" },
    ],
  },
  play: async ({ canvasElement }) => {
    const table = within(canvasElement).getByRole("table");

    await expect(table.offsetWidth).toBeLessThanOrEqual(canvasElement.clientWidth);
  },
};

export const WithRowHeader: Story = {
  args: {
    columns: [
      { key: "account", label: "Account", isRowHeader: true },
      { key: "role", label: "Role" },
      { key: "actions", label: "Actions", align: "end" },
    ],
  },
};
