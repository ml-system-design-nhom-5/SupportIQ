import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { consoleQueryKeys } from "@/features/console-tickets/api/console-query-keys";
import { createSuggestionRoute, sendReplyRoute } from "@/test/backend-routes";
import {
  openReplyArea,
  readDraftText,
  workspaceExample,
  workspaceWithSuggestion,
  writeReply,
} from "@/test/console-screen";
import { readOperationExample } from "@/test/contract-examples";
import { exampleAnswer, holdAnswer } from "@/test/fake-backend";

/** The suggestion that the `202` of an intent correction started. */
const NEW_SUGGESTION_ID = readOperationExample(
  "createSuggestion",
  202,
  "intent-override",
).suggestion_id;

/** The workspaces of TCK-1042 before and after a correction: the new draft has a warning `w1` too. */
const workspacesAroundCorrection = [
  workspaceExample("draft-ready"),
  workspaceWithSuggestion("draft-ready", { suggestion_id: NEW_SUGGESTION_ID }),
];

/** The text of the draft-ready example, which the new draft of these tests repeats. */
const draftText = readDraftText("draft-ready");

/**
 * Open the draft-ready workspace whose next load shows a new suggestion with the same warning ID.
 *
 * @returns The rendered app and the `main` landmark.
 */
function openBeforeCorrection() {
  return openReplyArea({ workspace: workspacesAroundCorrection });
}

/**
 * Correct the intent from the strip and wait until the new draft is ready.
 *
 * @param rendered - The app and its `main` landmark.
 */
async function correctIntent(rendered: Awaited<ReturnType<typeof openBeforeCorrection>>) {
  const { user, main, backend } = rendered;
  await user.click(within(main).getByRole("button", { name: "Use Request refund 7%" }));
  await waitFor(() => {
    expect(backend.requestsTo(createSuggestionRoute)).toHaveLength(1);
  });
  await waitFor(() => {
    expect(within(main).queryByText("Outdated")).not.toBeInTheDocument();
  });
}

describe("A new suggestion replaces the one that staff worked on (UI-18, ADR-0006)", () => {
  it("drops the acknowledgement of a warning with the same ID", async () => {
    const rendered = await openBeforeCorrection();
    const { user, main } = rendered;
    await user.click(within(main).getByRole("checkbox", { name: /^I have checked this/ }));

    await correctIntent(rendered);

    const checkbox = await within(main).findByRole("checkbox", { name: /^I have checked this/ });
    expect(checkbox).not.toBeChecked();
    expect(within(main).getByRole("button", { name: "Send reply" })).toBeDisabled();
    expect(main).toHaveTextContent("Acknowledge 1 warning to send the reply.");
  });

  it("keeps the text of a rejection, drops its reasons, and shows the new draft", async () => {
    const rendered = await openBeforeCorrection();
    const { user, main } = rendered;
    await user.click(within(main).getByRole("button", { name: "Reject draft" }));
    await user.click(within(main).getByRole("button", { name: "Wrong intent" }));
    await writeReply(user, main, "My own reply.");

    await correctIntent(rendered);

    const reply = await within(main).findByRole("region", { name: "Reply" });
    expect(reply).toHaveTextContent("The AI made a new draft. Your text is kept below it.");
    expect(reply).toHaveTextContent(draftText.slice(0, 40));
    expect(within(reply).getByRole("textbox", { name: "Reply to the customer" })).toHaveValue(
      "My own reply.",
    );
    expect(reply).not.toHaveTextContent("Started from AI draft");
    expect(within(reply).queryByRole("button", { name: "Wrong intent" })).not.toBeInTheDocument();
  });

  it("keeps an edit as an edit, under the new draft", async () => {
    const rendered = await openBeforeCorrection();
    const { user, main } = rendered;
    await user.click(within(main).getByRole("button", { name: "Edit draft" }));
    const editor = within(main).getByRole("textbox", { name: "Reply to the customer" });
    await user.clear(editor);
    await user.type(editor, "Edited reply.");

    await correctIntent(rendered);

    const edit = await within(main).findByRole("region", { name: "Edit draft" });
    expect(edit).toHaveTextContent("Started from AI draft");
    expect(edit).toHaveTextContent("The AI made a new draft.");
    expect(within(edit).getByRole("textbox", { name: "Reply to the customer" })).toHaveValue(
      "Edited reply.",
    );
  });
});

describe("The confirmation of Send reply (UI-17, FR-04)", () => {
  it("closes without a send when a new suggestion arrives while it is open", async () => {
    const { user, main, backend, dependencies } = await openBeforeCorrection();
    await user.click(within(main).getByRole("checkbox", { name: /^I have checked this/ }));
    await user.click(within(main).getByRole("button", { name: "Send reply" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Send this reply to Lan Tran?" });

    await dependencies.queryClient.invalidateQueries({
      queryKey: consoleQueryKeys.workspace("TCK-1042"),
    });

    await waitFor(() => {
      expect(dialog).not.toBeInTheDocument();
    });
    expect(backend.requestsTo(sendReplyRoute)).toHaveLength(0);
    expect(within(main).getByRole("button", { name: "Send reply" })).toBeDisabled();
  });

  it("is disabled while Try AI again is sending", async () => {
    const held = holdAnswer(exampleAnswer(202, "createSuggestion", "retry"));
    const { user, main } = await openReplyArea({
      workspace: [workspaceExample("ai-service-unavailable")],
      suggestion: [held.answer],
    });
    await writeReply(user, main, "Here is the return label.");
    const send = within(main).getByRole("button", { name: "Send reply" });
    expect(send).toBeEnabled();

    await user.click(within(main).getByRole("button", { name: "Try AI again" }));

    await waitFor(() => {
      expect(send).toBeDisabled();
    });
    expect(main).toHaveTextContent("The AI is still working on this ticket.");
    held.release();
  });
});

describe("The focus after an action (UI-30)", () => {
  it("moves to Draft rejected after Reject draft", async () => {
    const { user, main } = await openReplyArea();

    await user.click(within(main).getByRole("button", { name: "Reject draft" }));

    expect(within(main).getByRole("heading", { name: "Draft rejected" })).toHaveFocus();
  });

  it("moves to Other intent once a correction started a new draft", async () => {
    const rendered = await openBeforeCorrection();

    await rendered.user.click(
      within(rendered.main).getByRole("button", { name: "Use Request refund 7%" }),
    );

    const otherIntent = await within(rendered.main).findByRole("button", { name: "Other intent" });
    await waitFor(() => {
      expect(otherIntent).toHaveFocus();
    });
  });

  it("moves to Other intent of the strip once staff chose another intent", async () => {
    const { user, main } = await openReplyArea({
      workspace: [
        workspaceExample("abstained-low-confidence"),
        workspaceWithSuggestion(
          "draft-ready",
          readOperationExample("createSuggestion", 202, "intent-override"),
        ),
      ],
    });
    const choice = within(main).getByRole("region", { name: "Choose an intent" });

    await user.click(within(choice).getByRole("button", { name: "Other intent" }));
    await user.click(await screen.findByRole("menuitem", { name: "Cancel order" }));

    const strip = await within(main).findByRole("region", { name: "Intent" });
    await waitFor(() => {
      expect(within(strip).getByRole("button", { name: "Other intent" })).toHaveFocus();
    });
  });

  it("moves to the generating draft once Try AI again started it", async () => {
    const { user, main } = await openReplyArea({
      workspace: [
        workspaceExample("ai-service-unavailable"),
        workspaceWithSuggestion(
          "ai-service-unavailable",
          readOperationExample("createSuggestion", 202, "retry"),
        ),
      ],
      suggestion: [exampleAnswer(202, "createSuggestion", "retry")],
    });

    await user.click(within(main).getByRole("button", { name: "Try AI again" }));

    const heading = await within(main).findByRole("heading", { name: "AI draft" });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
  });

  it("moves to Reply sent once the reply was sent", async () => {
    const { user, main } = await openReplyArea({
      workspace: [workspaceExample("draft-ready"), workspaceExample("closed")],
    });
    await user.click(within(main).getByRole("checkbox", { name: /^I have checked this/ }));
    await user.click(within(main).getByRole("button", { name: "Send reply" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Send this reply to Lan Tran?" });

    await user.click(within(dialog).getByRole("button", { name: "Send reply" }));

    const sent = await within(main).findByRole("heading", { name: "Reply sent" });
    await waitFor(() => {
      expect(sent).toHaveFocus();
    });
  });
});
