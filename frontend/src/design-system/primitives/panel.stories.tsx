import type { Meta, StoryObj } from "@storybook/react-vite";
import { LifeBuoy, MessageSquare, Pencil, Send, Sparkles } from "lucide-react";
import { expect, within } from "storybook/test";

import { ActionBar } from "@/design-system/components/action-bar";
import { Button } from "@/design-system/primitives/button";
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

/** The least height of a `fill` panel in rem: the reply panel token, 280 px in the mockups. */
const REPLY_PANEL_MIN_HEIGHT_REM = 17.5;

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
  play: async ({ canvas }) => {
    const panel = canvas.getByRole("region", { name: "Support for this order" });

    // One 1 px line under the header and one between the sections, as in the mockups: the
    // section right after the header draws no line of its own.
    await expect(measureBorders(panel)).toEqual([
      { top: 0, bottom: 1 },
      { top: 0, bottom: 0 },
      { top: 1, bottom: 0 },
    ]);
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

export const HeaderWithoutIcon: Story = {
  args: {
    as: "section",
    label: "ai-service",
    children: (
      <>
        <PanelHeader level={2} title="ai-service" trailing={<Text tone="muted">Available</Text>} />
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

export const CompactAiPanel: Story = {
  args: {
    as: "section",
    label: "AI recommendation",
    tone: "ai",
    density: "compact",
    children: (
      <>
        <PanelHeader icon={LifeBuoy} level={2} title="AI recommendation" />
        <PanelSection>
          <Text>A console panel of AI output.</Text>
        </PanelSection>
        <PanelSection layout="centered">
          <Text>A centered section.</Text>
        </PanelSection>
      </>
    ),
  },
};

export const FillsItsColumn: Story = {
  parameters: { layout: "fullscreen" },
  args: {
    as: "section",
    label: "AI draft",
    tone: "ai",
    height: "fill",
    density: "compact",
    children: (
      <>
        <PanelHeader icon={Sparkles} level={2} title="AI draft" />
        <PanelSection>
          <Text>Thank you for your patience.</Text>
        </PanelSection>
        <ActionBar
          actions={<Button leadingIcon={Pencil}>Edit draft</Button>}
          primaryAction={
            <Button variant="primary" leadingIcon={Send}>
              Send reply
            </Button>
          }
        />
      </>
    ),
  },
  render: (args) => (
    <section
      aria-label="Middle column"
      className="flex h-screen flex-col gap-4 overflow-y-auto p-4"
    >
      <Panel as="section" label="Customer message" density="compact">
        <PanelHeader icon={MessageSquare} level={2} title="Customer message" />
        <PanelSection>
          <Text>Can you check what is happening with my refund?</Text>
        </PanelSection>
      </Panel>
      <Panel {...args} />
    </section>
  ),
  play: async ({ canvas }) => {
    const column = canvas.getByRole("region", { name: "Middle column" });
    const panel = within(column).getByRole("region", { name: "AI draft" });
    const remSize = Number.parseFloat(getComputedStyle(document.documentElement).fontSize);
    const columnContentBottom =
      column.getBoundingClientRect().bottom -
      Number.parseFloat(getComputedStyle(column).paddingBottom);

    await expect(Number.parseFloat(getComputedStyle(panel).minHeight)).toBe(
      REPLY_PANEL_MIN_HEIGHT_REM * remSize,
    );
    // The panel takes the rest of the column, so its action bar is at the bottom of the column.
    await expect(panel.getBoundingClientRect().bottom).toBeCloseTo(columnContentBottom);
  },
};

/**
 * Measure the top and bottom borders of each child of a panel, so a story can check that two
 * children never draw a line each between them.
 *
 * @param panel - The panel element.
 * @returns The border widths in px, one entry per child, in order.
 */
function measureBorders(panel: HTMLElement) {
  return Array.from(panel.children, (child) => {
    const style = getComputedStyle(child);
    return {
      top: Number.parseFloat(style.borderTopWidth),
      bottom: Number.parseFloat(style.borderBottomWidth),
    };
  });
}
