import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, within } from "storybook/test";

import { Stack } from "@/design-system";
import { DeveloperDetailsView } from "@/features/console-tickets/components/developer-details-view";
import { toDeveloperDetails } from "@/features/console-tickets/model/developer-details";
import { readExampleSuggestion } from "@/test/console-screen";

/** A Grafana trace link, as a developer sets one up (UI-35). */
const TRACE_HREF = "https://grafana.example/t/4bf92f3577b34da6a3ce929d0e0e4736";

/**
 * Read the developer details of a workspace example.
 *
 * @param name - The example of `getConsoleTicket`.
 * @returns The details of its suggestion.
 */
function readDetails(name: string) {
  return toDeveloperDetails(readExampleSuggestion(name));
}

const meta = {
  title: "Console/TicketWorkspace/DeveloperDetails",
  component: DeveloperDetailsView,
  decorators: [
    (Story) => (
      <Stack as="section" label="AI sidebar" gap="4">
        <Story />
      </Stack>
    ),
  ],
  args: { details: readDetails("draft-ready") },
} satisfies Meta<typeof DeveloperDetailsView>;

export default meta;

type Story = StoryObj<typeof meta>;

/** What the play functions of this file read of the story context. */
type PlayContext = { readonly canvasElement: HTMLElement };

/**
 * Open the panel, as a developer does.
 *
 * @param context - The story context.
 * @param context.canvasElement - The element that holds the story.
 * @returns The queries of the story.
 */
async function openPanel({ canvasElement }: PlayContext) {
  const canvas = within(canvasElement);
  await userEvent.click(canvas.getByRole("button", { name: "Developer details" }));
  return canvas;
}

/** Collapsed at the bottom of the sidebar, as in the mockups. */
export const Closed: Story = {
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("button", { name: "Developer details" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  },
};
/** Open on a ready draft: the trace with its Grafana link, the versions, and the latencies. */
export const Open: Story = {
  args: { traceHref: TRACE_HREF },
  play: async (context) => {
    const canvas = await openPanel(context);

    await expect(canvas.getByRole("link", { name: /^Open in Grafana/ })).toHaveAttribute(
      "href",
      TRACE_HREF,
    );
    await expect(canvas.getByRole("region", { name: "Draft" })).toHaveTextContent("3,205 ms");
  },
};
/** Without Grafana set up: the trace ID with its copy button only. */
export const WithoutGrafanaLink: Story = {
  play: async (context) => {
    const canvas = await openPanel(context);

    await expect(canvas.queryByRole("link")).toBeNull();
  },
};
/** Both parts pending: only their raw status, with no reason codes, versions, or latencies. */
export const PartsPending: Story = {
  args: { details: readDetails("suggestion-pending") },
  play: async (context) => {
    const canvas = await openPanel(context);

    const draft = canvas.getByRole("region", { name: "Draft" });
    await expect(draft).toHaveTextContent("pending");
    await expect(draft).not.toHaveTextContent("Reason codes");
    await expect(draft).not.toHaveTextContent("Release");
  },
};
/** Both parts unavailable: the raw status and the reason code of each. */
export const PartsUnavailable: Story = {
  args: { details: readDetails("ai-service-unavailable") },
  play: async (context) => {
    const canvas = await openPanel(context);

    await expect(canvas.getByRole("region", { name: "Analysis" })).toHaveTextContent(
      "ai_service_unavailable",
    );
  },
};
/** A draft without an LLM call: the LLM time says so instead of 0 ms. */
export const NoLlmCall: Story = {
  args: { details: readDetails("escalated") },
  play: async (context) => {
    const canvas = await openPanel(context);

    await expect(canvas.getByRole("region", { name: "Draft" })).toHaveTextContent("No LLM call");
  },
};
