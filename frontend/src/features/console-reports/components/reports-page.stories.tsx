import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";

import { AppBar, ConsoleShell } from "@/design-system";
import { ReportsPage } from "@/features/console-reports/components/reports-page";
import { exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { answerReports, reportExample } from "@/test/reports-screen";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Console/Reports",
  component: ReportsPage,
  parameters: { layout: "fullscreen" },
  render: () => (
    <ConsoleShell appBar={<AppBar variant="console" brandName="SupportIQ" areaName="Console" />}>
      <ReportsPage />
    </ConsoleShell>
  ),
} satisfies Meta<typeof ReportsPage>;

export default meta;

type Story = StoryObj<typeof meta>;

/**
 * Build the decorators of a story whose report answers as given.
 *
 * @param report - The answer of `getConsoleReport`.
 * @param session - The example of `getCurrentSession`; `manager` by default.
 * @returns The decorators of the story.
 */
function withReport(report: FakeAnswer, session = "manager") {
  return [
    withFakeBackend((backend) => {
      answerReports(backend, { session, report: [report] });
    }),
  ];
}

export const Ready: Story = {
  decorators: withReport(reportExample("period-with-activity")),
  play: async ({ canvasElement }) => {
    const speed = await within(canvasElement).findByRole("table", { name: "Speed" });

    await expect(speed).toHaveTextContent("At most 12 s");
  },
};
export const EmptyPeriod: Story = {
  decorators: withReport(reportExample("empty-period")),
  play: async ({ canvasElement }) => {
    const speed = await within(canvasElement).findByRole("table", { name: "Speed" });

    await expect(speed).toHaveTextContent("No data");
  },
};
export const Loading: Story = { decorators: withReport({ kind: "no_answer" }) };
export const Error: Story = {
  decorators: withReport(exampleAnswer(500, "problems", "internal-error")),
  play: async ({ canvasElement }) => {
    await expect(
      await within(canvasElement).findByRole("heading", {
        name: "The report could not be loaded",
      }),
    ).toBeVisible();
  },
};
export const InvalidPeriod: Story = {
  decorators: withReport(exampleAnswer(422, "problems", "invalid-period")),
};
export const PermissionDenied: Story = {
  decorators: withReport(exampleAnswer(403, "problems", "forbidden-role"), "staff"),
  play: async ({ canvasElement }) => {
    await expect(
      await within(canvasElement).findByRole("heading", { name: "You cannot open this page" }),
    ).toBeVisible();
  },
};
export const PermissionDeniedWithoutTheConsole: Story = {
  decorators: withReport(exampleAnswer(403, "problems", "forbidden-role"), "customer"),
};
