import { waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { createSuggestionRoute, sendReplyRoute } from "@/test/backend-routes";
import {
  DRAFT_READY_SUGGESTION_ID,
  openReplyArea,
  sendAndConfirm,
  workspaceExample,
  writeReply,
} from "@/test/console-screen";

describe("Reject draft (ADR-0006)", () => {
  it("needs a reason code, and sends the basis rejected_ai_draft with it", async () => {
    const { user, main, backend } = await openReplyArea();
    await user.click(within(main).getByRole("button", { name: "Reject draft" }));
    const rejected = within(main).getByRole("region", { name: "Draft rejected" });
    expect(rejected).toHaveTextContent("Rejected");
    await writeReply(user, main, "Your refund is under review.");
    expect(main).toHaveTextContent("Choose why you rejected the draft to send the reply.");

    await user.click(within(rejected).getByRole("button", { name: "Unsupported claim" }));
    await sendAndConfirm(user, main);

    await waitFor(() => {
      expect(backend.requestsTo(sendReplyRoute)[0]?.body).toEqual({
        basis: "rejected_ai_draft",
        body: "Your refund is under review.",
        suggestion_id: DRAFT_READY_SUGGESTION_ID,
        staff_reason_codes: ["unsupported_claim"],
      });
    });
  });

  it("asks for a note with the reason code Other", async () => {
    const { user, main } = await openReplyArea();
    await user.click(within(main).getByRole("button", { name: "Reject draft" }));
    await writeReply(user, main, "Your refund is under review.");

    await user.click(within(main).getByRole("button", { name: "Other" }));

    expect(main).toHaveTextContent("Write a note for the reason Other to send the reply.");
    await user.type(within(main).getByRole("textbox", { name: "Note for the reason Other" }), "x");
    expect(within(main).getByRole("button", { name: "Send reply" })).toBeEnabled();
  });
});

describe("A reply without a draft", () => {
  it("highlights a placeholder and keeps Send reply disabled until it is replaced (UI-43)", async () => {
    const { user, main } = await openReplyArea({ workspace: [workspaceExample("manual-mode")] });
    // user-event reads "[[" as one "[".
    await writeReply(user, main, "We sent the label to [[EMAIL].");

    expect(within(main).getByRole("button", { name: "Send reply" })).toBeDisabled();
    expect(main).toHaveTextContent("Replace the highlighted text to send the reply.");
    expect(main).toHaveTextContent("Personal data or reserved text: replace before sending.");
    expect(within(main).getByText("[EMAIL]").tagName).toBe("MARK");

    await user.clear(within(main).getByRole("textbox", { name: "Reply to the customer" }));
    await writeReply(user, main, "We sent the label to your email address.");
    expect(within(main).getByRole("button", { name: "Send reply" })).toBeEnabled();
  });

  it("sends the basis no_ai_draft without a suggestion in manual mode", async () => {
    const { user, main, backend } = await openReplyArea({
      workspace: [workspaceExample("manual-mode")],
    });
    await writeReply(user, main, "Here is the return label.");

    await sendAndConfirm(user, main);

    await waitFor(() => {
      expect(backend.requestsTo(sendReplyRoute)[0]?.body).toEqual({
        basis: "no_ai_draft",
        body: "Here is the return label.",
      });
    });
  });

  it("retries the AI with Try AI again after an AI failure (UI-26)", async () => {
    const { user, main, backend } = await openReplyArea({
      workspace: [workspaceExample("ai-service-unavailable")],
      suggestion: [{ kind: "example", status: 202, folder: "createSuggestion", name: "retry" }],
    });

    await user.click(within(main).getByRole("button", { name: "Try AI again" }));

    await waitFor(() => {
      expect(backend.requestsTo(createSuggestionRoute)[0]?.body).toEqual({});
    });
  });
});

describe("Send reply while no draft is ready", () => {
  it.each([
    ["suggestion-pending", "The AI is still working on this ticket."],
    ["abstained-low-confidence", "Choose an intent to get a draft."],
  ])("is disabled on the %s example, with Edit draft and Reject draft", async (name, reason) => {
    const { main } = await openReplyArea({ workspace: [workspaceExample(name)] });

    expect(main).toHaveTextContent(reason);
    expect(within(main).getByRole("button", { name: "Send reply" })).toBeDisabled();
    expect(within(main).getByRole("button", { name: "Edit draft" })).toBeDisabled();
    expect(within(main).getByRole("button", { name: "Reject draft" })).toBeDisabled();
    expect(within(main).queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("is disabled with the reason on a closed ticket, under the sent reply (state-closed.png)", async () => {
    const { main } = await openReplyArea({ workspace: [workspaceExample("closed")] });

    const sent = within(main).getByRole("region", { name: "Reply sent" });
    expect(sent).toHaveTextContent("This ticket is closed. A reply was already sent.");
    expect(within(sent).getByRole("button", { name: "Send reply" })).toBeDisabled();
    expect(within(sent).getByRole("button", { name: "Edit draft" })).toBeDisabled();
    expect(within(sent).getByRole("button", { name: "Reject draft" })).toBeDisabled();
    expect(within(main).queryByRole("textbox")).not.toBeInTheDocument();
  });
});
