import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { consoleQueryKeys } from "@/features/console-tickets/api/console-query-keys";
import { createEscalationRoute } from "@/test/backend-routes";
import {
  type ConsoleAnswers,
  openReplyArea,
  workspaceExample,
  workspaceWith,
  workspaceWithSuggestion,
} from "@/test/console-screen";
import { exampleAnswer } from "@/test/fake-backend";

/** The draft-ready ticket after another suggestion replaced the one that staff saw. */
const draftReadyWithNewSuggestion = workspaceWithSuggestion("draft-ready", {
  suggestion_id: "3a5c7e9b-1d2f-4a6b-8c0d-e2f4a6b8c0d1",
});

/**
 * Open Escalate ticket on the draft-ready ticket and choose a reason.
 *
 * @param answers - The answers that differ, such as the next workspaces.
 * @returns The rendered app, the `main` landmark, and the dialog.
 */
async function openDialogWithReason(answers: ConsoleAnswers) {
  const rendered = await openReplyArea(answers);
  await rendered.user.click(within(rendered.main).getByRole("button", { name: "Escalate ticket" }));
  const dialog = await screen.findByRole("dialog", { name: /^Escalate ticket / });
  await rendered.user.click(within(dialog).getByRole("button", { name: "KB gap" }));
  return { ...rendered, dialog };
}

describe("Escalate ticket while the ticket changes (ADR-0006)", () => {
  it.each([
    ["a new suggestion replaced the one that staff saw", draftReadyWithNewSuggestion],
    [
      "backend no longer allows the escalation",
      workspaceWith("draft-ready", { allowed_actions: ["send_reply"] }),
    ],
  ])("closes without an escalation when %s", async (_case, nextWorkspace) => {
    const { dialog, backend, dependencies } = await openDialogWithReason({
      workspace: [workspaceExample("draft-ready"), nextWorkspace],
    });

    await dependencies.queryClient.invalidateQueries({
      queryKey: consoleQueryKeys.workspace("TCK-1042"),
    });

    await waitFor(() => {
      expect(dialog).not.toBeInTheDocument();
    });
    expect(backend.requestsTo(createEscalationRoute)).toHaveLength(0);
  });

  it("keeps saying why the escalation failed once the reload closed the dialog", async () => {
    const { user, main, dialog } = await openDialogWithReason({
      workspace: [workspaceExample("draft-ready"), draftReadyWithNewSuggestion],
      escalation: [exampleAnswer(409, "problems", "suggestion-superseded")],
    });

    await user.click(within(dialog).getByRole("button", { name: "Escalate ticket" }));

    await waitFor(() => {
      expect(dialog).not.toBeInTheDocument();
    });
    expect(await within(main).findByRole("alert")).toHaveTextContent(
      "The ticket was not escalated. The AI made a new draft for this ticket.",
    );
  });

  it("keeps the key of an unknown outcome when the dialog is opened again (TS-29)", async () => {
    const { user, main, dialog, backend } = await openDialogWithReason({
      escalation: [{ kind: "network_error" }, exampleAnswer(201, "createEscalation", "escalated")],
    });
    await user.click(within(dialog).getByRole("button", { name: "Escalate ticket" }));
    await within(dialog).findByRole("alert");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    await user.click(within(main).getByRole("button", { name: "Escalate ticket" }));
    const reopened = await screen.findByRole("dialog", { name: /^Escalate ticket / });
    await user.click(within(reopened).getByRole("button", { name: "KB gap" }));
    await user.click(within(reopened).getByRole("button", { name: "Escalate ticket" }));

    await waitFor(() => {
      expect(backend.requestsTo(createEscalationRoute).length).toBeGreaterThanOrEqual(2);
    });
    const keys = new Set(
      backend
        .requestsTo(createEscalationRoute)
        .map((request) => request.headers.get("Idempotency-Key")),
    );
    expect(keys.size).toBe(1);
  });
});
