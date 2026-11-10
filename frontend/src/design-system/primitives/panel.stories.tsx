import type { Meta, StoryObj } from "@storybook/react-vite";
import { LifeBuoy } from "lucide-react";

import { Panel } from "@/design-system/primitives/panel";
import { PanelHeader } from "@/design-system/primitives/panel-header";
import { PanelSection } from "@/design-system/primitives/panel-section";
import { Text } from "@/design-system/primitives/text";

const meta = {
  title: "Design system/Primitives/Panel",
  component: Panel,
} satisfies Meta<typeof Panel>;

export default meta;

type Story = StoryObj<typeof meta>;

export const WithHeaderAndSections: Story = {
  args: {
    as: "section",
    label: "Support for this order",
    children: (
      <>
        <PanelHeader icon={LifeBuoy} level={2} title="Support for this order" />
        <PanelSection>
          <Text size="base">The tickets of the order.</Text>
        </PanelSection>
        <PanelSection>
          <Text size="base">The message box.</Text>
        </PanelSection>
      </>
    ),
  },
};

export const WithTrailingHeaderContent: Story = {
  args: {
    children: (
      <>
        <PanelHeader
          icon={LifeBuoy}
          level={2}
          title="Support for this order"
          trailing={<Text tone="muted">2 tickets</Text>}
        />
        <PanelSection>
          <Text>Content</Text>
        </PanelSection>
      </>
    ),
  },
};

export const CenteredSection: Story = {
  args: {
    children: (
      <PanelSection layout="centered">
        <Text tone="muted">You have not written to support yet.</Text>
      </PanelSection>
    ),
  },
};
