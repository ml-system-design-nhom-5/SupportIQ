import type { Meta, StoryObj } from "@storybook/react-vite";

import { AccountLabel } from "@/design-system/components/account-label";

const meta = {
  title: "Design system/Components/AccountLabel",
  component: AccountLabel,
  args: { displayName: "Mai Nguyen" },
} satisfies Meta<typeof AccountLabel>;

export default meta;

type Story = StoryObj<typeof meta>;

export const WithRole: Story = { args: { roleLabel: "Staff" } };
export const WithoutRole: Story = { args: { displayName: "Linh Tran" } };
export const LongNonAsciiName: Story = {
  args: { displayName: "Nguyễn Thị Phương Thảo Trần Lê Hoàng", roleLabel: "Manager" },
};
