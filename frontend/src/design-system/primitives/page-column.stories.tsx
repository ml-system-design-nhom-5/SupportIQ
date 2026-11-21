import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";

import { AppBar } from "@/design-system/components/app-bar";
import { ConsoleShell } from "@/design-system/components/console-shell";
import { PageHeader } from "@/design-system/components/page-header";
import { Button } from "@/design-system/primitives/button";
import { PageColumn } from "@/design-system/primitives/page-column";
import { Panel } from "@/design-system/primitives/panel";
import { PanelSection } from "@/design-system/primitives/panel-section";
import { Text } from "@/design-system/primitives/text";

/** Enough panels to be taller than the window. */
const panelNumbers = Array.from({ length: 20 }, (_unused, index) => index + 1);

const meta = {
  title: "Design system/Primitives/PageColumn",
  component: PageColumn,
  parameters: { layout: "fullscreen" },
  args: { area: "shop", children: <Text size="base">The content of the screen.</Text> },
} satisfies Meta<typeof PageColumn>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Shop: Story = {};
export const Admin: Story = { args: { area: "admin" } };
/** A console screen without the inbox, taller than the window, inside the console shell. */
export const Console: Story = {
  args: {
    area: "console",
    children: (
      <>
        {/* A scrolling region holds something to focus, so the keyboard can scroll it (UI-30). */}
        <PageHeader title="Reports" density="compact" action={<Button>Last 7 days</Button>} />
        {panelNumbers.map((panelNumber) => (
          <Panel key={panelNumber} density="compact">
            <PanelSection>
              <Text>{`Panel ${String(panelNumber)}`}</Text>
            </PanelSection>
          </Panel>
        ))}
      </>
    ),
  },
  render: (args) => (
    <ConsoleShell appBar={<AppBar variant="console" brandName="SupportIQ" areaName="Console" />}>
      <PageColumn {...args} />
    </ConsoleShell>
  ),
  play: async ({ canvasElement }) => {
    const main = within(canvasElement).getByRole("main");

    // The screen scrolls inside the shell, so the app bar stays visible.
    await expect(main.scrollHeight).toBeGreaterThan(main.clientHeight);
    await expect(main.getBoundingClientRect().bottom).toBeLessThanOrEqual(window.innerHeight);
  },
};
