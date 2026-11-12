import type { Meta, StoryObj } from "@storybook/react-vite";

import { StatusBadge } from "@/design-system/components/status-badge";
import {
  authorityRequiredPresentation,
  presentationByAccountStatus,
  presentationByAiStatus,
  presentationByConsoleTicketStatus,
  presentationByDocumentValidity,
  presentationByHandlingMode,
  presentationByInternalRole,
  presentationByOrderStatus,
  presentationByRefundStatus,
  presentationByShipmentStatus,
  presentationByShopTicketStatus,
  type StatusPresentation,
} from "@/design-system/components/status-presentations";

const meta = {
  title: "Design system/Components/StatusBadge",
  component: StatusBadge,
  args: { presentation: presentationByOrderStatus.delivered },
} satisfies Meta<typeof StatusBadge>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Single: Story = {};

export const OrderStatuses: Story = { render: () => renderAll(presentationByOrderStatus) };

export const ShipmentStatuses: Story = { render: () => renderAll(presentationByShipmentStatus) };

export const RefundStatuses: Story = { render: () => renderAll(presentationByRefundStatus) };

export const TicketStatuses: Story = {
  render: () => renderAll(presentationByShopTicketStatus),
};

export const Roles: Story = { render: () => renderAll(presentationByInternalRole) };

export const AccountStatuses: Story = { render: () => renderAll(presentationByAccountStatus) };

export const ConsoleTicketStatuses: Story = {
  render: () => renderAll(presentationByConsoleTicketStatus),
};

export const AiStatuses: Story = { render: () => renderAll(presentationByAiStatus) };

export const HandlingModes: Story = { render: () => renderAll(presentationByHandlingMode) };

export const DocumentValidities: Story = {
  render: () => renderAll(presentationByDocumentValidity),
};

export const AuthorityRequired: Story = { args: { presentation: authorityRequiredPresentation } };

/**
 * Render every presentation of one status set, so the story shows each variant (UI-04).
 *
 * @param presentations - The presentations of the set.
 * @returns The badges in a row.
 */
function renderAll(presentations: Readonly<Record<string, StatusPresentation>>) {
  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(presentations).map(([status, presentation]) => (
        <StatusBadge key={status} presentation={presentation} />
      ))}
    </div>
  );
}
