import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  openConsole,
  openReplyArea,
  readSuggestionPart,
  TICKET_PATH,
  workspaceExample,
  workspaceWith,
  workspaceWithSuggestion,
  writeReply,
} from "@/test/console-screen";
import type { FakeAnswer } from "@/test/fake-backend";

/**
 * Open the workspace of TCK-1042 with a workspace answer, and wait for it.
 *
 * @param workspace - The answer of `getConsoleTicket`.
 * @returns The `main` landmark of the workspace.
 */
async function openWorkspace(workspace: FakeAnswer): Promise<HTMLElement> {
  openConsole(TICKET_PATH, { workspace: [workspace] });
  await screen.findByRole("heading", { level: 1, name: /^Ticket / });
  return screen.getByRole("main");
}

/**
 * Find a panel of the workspace by its name.
 *
 * @param main - The `main` landmark.
 * @param name - The accessible name of the panel.
 * @returns The panel.
 */
function getPanel(main: HTMLElement, name: string): HTMLElement {
  return within(main).getByRole("region", { name });
}

describe("The workspace of a ready draft", () => {
  it("shows the header, the message, the intent, the draft with its warning, and the AI sidebar", async () => {
    const main = await openWorkspace(workspaceExample("draft-ready"));

    expect(within(main).getByRole("heading", { level: 1 })).toHaveTextContent("Ticket TCK-1042");
    expect(main).toHaveTextContent("OpenAssisted");
    expect(getPanel(main, "Customer message")).toHaveTextContent(
      "I asked for a refund for the headphones three weeks ago. When will it be paid?",
    );
    expect(getPanel(main, "Intent")).toHaveTextContent(
      "Refund statusConfidence High · 88%Predicted",
    );
    const draft = getPanel(main, "AI draft");
    expect(draft).toHaveTextContent("1 warning to check before sending");
    expect(draft).toHaveTextContent("Source review overdue");
    expect(draft).toHaveTextContent("Hello Lan Tran, thank you for your patience.");
    expect(getPanel(main, "AI recommendation")).toHaveTextContent(
      "Reply with a draftNo escalation reason",
    );
  });

  it("marks every AI region as AI output, and the order data as not AI (UI-13)", async () => {
    const main = await openWorkspace(workspaceExample("draft-ready"));

    expect(within(getPanel(main, "AI recommendation")).getByText("AI suggestion")).toBeVisible();
    expect(within(getPanel(main, "Intent")).getByText("Predicted")).toBeVisible();
    expect(
      within(getPanel(main, "AI draft")).getByRole("button", {
        name: "Order facts, from order records, not AI",
      }),
    ).toBeVisible();
  });

  it("shows the customer message and the AI text as plain text (SEC-22)", async () => {
    const main = await openWorkspace(
      workspaceWith("draft-ready", {
        message: {
          body: "<img src=x onerror=alert(1)> **bold**",
          created_at: "2026-11-05T08:12:30Z",
        },
      }),
    );

    expect(within(main).getByText("<img src=x onerror=alert(1)> **bold**")).toBeVisible();
    expect(main.querySelector("img")).toBeNull();
  });

  it("shows the authority banner on a ticket where authority is required (UI-19)", async () => {
    const main = await openWorkspace(workspaceExample("authority-required"));

    expect(within(main).getByText("Authority required.").parentElement).toHaveTextContent(
      "Authority required. The AI output is supporting information only. A manager decides and sends the reply.",
    );
    expect(getPanel(main, "AI recommendation")).toHaveTextContent("Requires authority");
  });

  it("marks an intent that staff chose", async () => {
    const main = await openWorkspace(workspaceExample("intent-corrected"));

    expect(getPanel(main, "Intent")).toHaveTextContent("Refund statusChosen by staff");
    expect(getPanel(main, "Intent")).not.toHaveTextContent("Next candidates");
  });

  it("shows a staff note for staff only, marked as AI text (UI-21)", async () => {
    const main = await openWorkspace(workspaceExample("abstained-low-confidence"));

    const note = getPanel(main, "For staff only");
    expect(note).toHaveTextContent("AI note");
    expect(note).toHaveTextContent(
      "The intent is uncertain. Confirm the intent or choose another to get a draft.",
    );
    expect(getPanel(main, "AI draft")).not.toHaveTextContent("The intent is uncertain");
  });
});

describe("The workspace while the AI works", () => {
  it("shows skeletons for the intent, the draft, and the sidebar while the analysis is pending", async () => {
    const main = await openWorkspace(workspaceExample("suggestion-pending"));

    expect(within(main).getByText("Analyzing the message…")).toBeInTheDocument();
    expect(getPanel(main, "AI draft")).toHaveTextContent("Generating draft");
    expect(within(main).getByText("Loading the AI recommendation…")).toBeInTheDocument();
  });

  it("shows the analysis and the draft skeleton when only the draft is pending (partial)", async () => {
    const main = await openWorkspace(
      workspaceWithSuggestion("draft-ready", { draft: { draft_status: "pending" } }),
    );

    expect(getPanel(main, "Intent")).toHaveTextContent("Refund status");
    expect(getPanel(main, "AI draft")).toHaveTextContent("Generating draft");
    expect(getPanel(main, "AI draft")).toHaveTextContent("The AI is still working on this ticket.");
    expect(getPanel(main, "Sources")).toHaveTextContent("Sample refund document");
  });
});

describe("The workspace without a draft", () => {
  it("offers the top three intents and creates no draft for low confidence (UI-42)", async () => {
    const main = await openWorkspace(workspaceExample("abstained-low-confidence"));

    expect(
      within(getPanel(main, "Choose an intent"))
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([
      "Refund statusConfidence Low · 41%Use this intent",
      "Request refund33%Use this intent",
      "Track order12%Use this intent",
    ]);
    expect(getPanel(main, "AI draft")).toHaveTextContent(
      "No draft is created until you choose an intent.",
    );
    expect(getPanel(main, "AI recommendation")).toHaveTextContent("Choose an intentLow confidence");
  });

  it.each([
    ["abstained", "no_valid_document", "AI abstained", "No valid document"],
    [
      "escalation_recommended",
      "human_agent_requested",
      "Escalation recommended",
      "Human agent requested",
    ],
  ])("shows the reason codes of a draft that is %s", async (...draftCase) => {
    const [status, reasonCode, badge, reason] = draftCase;
    const main = await openWorkspace(
      workspaceWithSuggestion("draft-ready", {
        draft: {
          ...readSuggestionPart("abstained-low-confidence", "draft"),
          draft_status: status,
          reason_codes: [reasonCode],
        },
      }),
    );

    const reply = getPanel(main, "Reply");
    expect(reply).toHaveTextContent(badge);
    expect(reply).toHaveTextContent(reason);
    expect(within(main).queryByRole("region", { name: "AI draft" })).not.toBeInTheDocument();
  });
});

describe("Manual handling", () => {
  it.each([
    [
      "ai-service-unavailable",
      "The AI service did not answer, so there is no analysis, draft, or source.",
    ],
    [
      "pseudonymization-failed",
      "Personal data in the message could not be hidden, so nothing was sent to the AI.",
    ],
    ["llm-unavailable", "The AI could not write a draft for this ticket."],
  ])(
    "handles the %s example manually, with the reason and the reminder (UI-26)",
    async (name, reason) => {
      const main = await openWorkspace(workspaceExample(name));

      const manual = getPanel(main, "Manual handling");
      expect(manual).toHaveTextContent("AI unavailable");
      expect(manual).toHaveTextContent(reason);
      expect(manual).toHaveTextContent(
        "Refund decision or dispute? Do not decide it here. Use Submit for approval, so a manager sends the reply.",
      );
    },
  );

  it("shows AI unavailable with the reason in the sidebar after an AI failure (ESC-05)", async () => {
    const main = await openWorkspace(workspaceExample("ai-service-unavailable"));

    const sidebar = getPanel(main, "AI recommendation");
    expect(sidebar).toHaveTextContent("AI unavailable");
    expect(sidebar).toHaveTextContent("AI service unavailable");
    expect(within(main).queryByRole("region", { name: "Intent" })).not.toBeInTheDocument();
  });

  it("says that drafting failed next to the analysis that is still shown", async () => {
    const main = await openWorkspace(workspaceExample("llm-unavailable"));

    expect(getPanel(main, "AI recommendation")).toHaveTextContent("AI unavailableDrafting failed");
    expect(getPanel(main, "Intent")).toHaveTextContent("Refund status");
  });

  it("replaces the AI panels in manual mode, and says that no order is attached", async () => {
    const main = await openWorkspace(workspaceExample("manual-mode"));

    expect(main).toHaveTextContent("Manual handling");
    expect(main).toHaveTextContent("No order attached");
    expect(within(main).getAllByRole("heading", { name: "Manual handling" })).toHaveLength(2);
    expect(
      within(getPanel(main, "AI details")).queryByText("AI unavailable"),
    ).not.toBeInTheDocument();
  });
});

describe("Manual handling of a manager (UI-16)", () => {
  it("says why Escalate ticket and Submit for approval are disabled once the reply can be sent", async () => {
    const { user, main } = await openReplyArea({
      session: "manager",
      workspace: [workspaceWith("manual-mode", { allowed_actions: ["send_reply"] })],
    });

    await writeReply(user, main, "We call you today.");

    expect(main).toHaveTextContent("Only staff escalate a ticket or submit a reply for approval.");
    expect(within(main).getByRole("button", { name: "Escalate ticket" })).toBeDisabled();
    expect(within(main).getByRole("button", { name: "Submit for approval" })).toBeDisabled();
    expect(within(main).getByRole("button", { name: "Send reply" })).toBeEnabled();
  });
});

describe("A closed ticket", () => {
  it("shows the sent reply, who sent it, and when", async () => {
    const main = await openWorkspace(workspaceExample("closed"));

    const reply = getPanel(main, "Reply sent");
    expect(reply).toHaveTextContent("Mai Nguyen · 3 weeks ago");
    expect(reply).toHaveTextContent(
      "Thank you for writing. Your refund request for the headphones is under review.",
    );
    expect(within(main).getByText("Closed")).toBeVisible();
  });
});
