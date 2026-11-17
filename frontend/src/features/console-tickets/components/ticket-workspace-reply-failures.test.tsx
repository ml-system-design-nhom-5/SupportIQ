import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { getConsoleTicketRoute, sendReplyRoute } from "@/test/backend-routes";
import {
  type ConsoleAnswers,
  openConsole,
  readSuggestionPart,
  sendAndConfirm,
  workspaceExample,
  workspaceWith,
} from "@/test/console-screen";
import { readOperationExample } from "@/test/contract-examples";
import { exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { testSettings } from "@/test/render-app";

/** The path of the ticket of the manual-mode example. */
const MANUAL_TICKET_PATH = "/console/tickets/TCK-1050";

/** The answer of Send reply after a colleague escalated the ticket or submitted it. */
const forbiddenSend = exampleAnswer(403, "problems", "forbidden-role");

/** The escalated ticket as staff see it: read-only. */
const escalatedForStaff = workspaceWith("escalated", { allowed_actions: [] });

/** The read-only states that the reload after `forbiddenSend` shows staff. */
const readOnlyStates: readonly (readonly [string, FakeAnswer])[] = [
  ["escalated without a ready draft", escalatedForStaff],
  [
    "escalated with a ready draft",
    workspaceWith("escalated", {
      allowed_actions: [],
      suggestion: {
        ...readOperationExample("getConsoleTicket", 200, "escalated").suggestion,
        draft: readSuggestionPart("draft-ready", "draft"),
      },
    }),
  ],
  ["awaiting approval", workspaceExample("read-only-for-staff")],
];

/**
 * Open a ticket in manual mode, write a reply, and send it.
 *
 * @param answers - The answers of `sendReply`, and the other answers that differ from the defaults.
 * @returns The rendered app and the `main` landmark.
 */
async function sendManualReply(answers: ConsoleAnswers) {
  const rendered = openConsole(MANUAL_TICKET_PATH, {
    workspace: [workspaceExample("manual-mode")],
    ...answers,
  });
  await screen.findByRole("heading", { level: 1, name: /^Ticket / });
  const main = screen.getByRole("main");
  await rendered.user.type(
    within(main).getByRole("textbox", { name: "Reply to the customer" }),
    "Here is the return label.",
  );
  await sendAndConfirm(rendered.user, main);
  return { ...rendered, main };
}

describe("A refused send (console UI design, Errors and guardrails)", () => {
  it.each([
    [
      409,
      "suggestion-superseded",
      "The AI made a new draft for this ticket. Check it; your text is kept.",
    ],
    [
      409,
      "invalid-ticket-state",
      "This ticket was already handled. It now shows its current state.",
    ],
    [
      403,
      "authority-required",
      "Only a manager can send the reply of this ticket. Submit it for approval instead.",
    ],
  ])(
    "says what happened after %i %s, keeps the text, and reloads the ticket",
    async (status, problem, message) => {
      const { main, backend } = await sendManualReply({
        reply: [exampleAnswer(status, "problems", problem)],
      });

      const alert = await within(main).findByRole("alert");
      expect(alert).toHaveTextContent(`The reply was not sent. ${message}`);
      expect(alert).toHaveTextContent(/Details: trace/);
      expect(within(main).getByRole("textbox", { name: "Reply to the customer" })).toHaveValue(
        "Here is the return label.",
      );
      await waitFor(() => {
        expect(backend.requestsTo(getConsoleTicketRoute)).toHaveLength(2);
      });
    },
  );

  it("keeps saying what happened once the reload shows the ticket closed", async () => {
    const { main } = await sendManualReply({
      workspace: [workspaceExample("manual-mode"), workspaceExample("closed")],
      reply: [exampleAnswer(409, "problems", "invalid-ticket-state")],
    });

    const sent = await within(main).findByRole("region", { name: "Reply sent" });
    expect(within(sent).getByRole("alert")).toHaveTextContent(
      "This ticket was already handled. It now shows its current state.",
    );
    expect(within(sent).getByRole("button", { name: "Send reply" })).toBeDisabled();
  });

  it("keeps the text after a 422 and does not reload the ticket", async () => {
    const { main, backend } = await sendManualReply({
      reply: [exampleAnswer(422, "problems", "placeholder-in-body")],
    });

    expect(await within(main).findByRole("alert")).toHaveTextContent(
      "The reply was not sent. The request was not accepted.",
    );
    expect(backend.requestsTo(getConsoleTicketRoute)).toHaveLength(1);
  });
});

describe("A send that a colleague's action refused (console UI design, Flow, step 6)", () => {
  it.each(readOnlyStates)(
    "shows the unsent text once, read-only, without an editor, once the ticket is %s",
    async (_state, reloaded) => {
      const { main } = await sendManualReply({
        workspace: [workspaceExample("manual-mode"), reloaded],
        reply: [forbiddenSend],
      });

      await waitFor(() => {
        expect(within(main).queryByRole("textbox")).not.toBeInTheDocument();
      });
      expect(within(main).getByRole("alert")).toHaveTextContent(
        "A colleague escalated this ticket or submitted it for approval. Your text is kept.",
      );
      const unsent = within(main).getAllByRole("region", { name: "Your unsent text" });
      expect(unsent).toHaveLength(1);
      expect(unsent[0]).toHaveTextContent("Here is the return label.");
    },
  );

  it("copies the unsent text", async () => {
    const { user, main } = await sendManualReply({
      workspace: [workspaceExample("manual-mode"), escalatedForStaff],
      reply: [forbiddenSend],
    });
    const unsent = await within(main).findByRole("region", { name: "Your unsent text" });
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();

    await user.click(within(unsent).getByRole("button", { name: "Copy text" }));

    expect(writeText).toHaveBeenCalledWith("Here is the return label.");
  });

  it("forgets the unsent text once staff open another ticket", async () => {
    const { main, router, backend } = await sendManualReply({
      workspace: [workspaceExample("manual-mode"), escalatedForStaff],
      reply: [forbiddenSend],
    });
    await within(main).findByRole("region", { name: "Your unsent text" });

    await router.navigate("/console/tickets/TCK-1042");

    await waitFor(() => {
      expect(backend.requestsTo(getConsoleTicketRoute)).toHaveLength(3);
    });
    expect(await screen.findByRole("region", { name: /^Escalated by / })).toBeVisible();
    expect(screen.queryByRole("region", { name: "Your unsent text" })).not.toBeInTheDocument();
  });

  it("is not shown after a refusal that keeps the editor", async () => {
    const { main } = await sendManualReply({
      reply: [exampleAnswer(422, "problems", "placeholder-in-body")],
    });

    await within(main).findByRole("alert");
    expect(
      within(main).queryByRole("region", { name: "Your unsent text" }),
    ).not.toBeInTheDocument();
  });
});

describe("A send whose outcome is unknown (TS-29, ERR-16)", () => {
  it("is never retried automatically, and says that the reply may have been sent", async () => {
    const { main, backend } = await sendManualReply({
      reply: [{ kind: "network_error" }],
      settings: { ...testSettings, requestRetryMaxCount: 2 },
    });

    expect(await within(main).findByRole("alert")).toHaveTextContent(
      "The reply may have been sent. We could not confirm it.",
    );
    expect(backend.requestsTo(sendReplyRoute)).toHaveLength(1);
  });

  it("reuses the key when the same reply is confirmed again", async () => {
    const { user, main, backend } = await sendManualReply({
      reply: [{ kind: "network_error" }, exampleAnswer(201, "sendReply", "without-ai-draft")],
    });
    await within(main).findByRole("alert");

    await sendAndConfirm(user, main);

    await waitFor(() => {
      expect(backend.requestsTo(sendReplyRoute)).toHaveLength(2);
    });
    const [first, second] = backend.requestsTo(sendReplyRoute);
    expect(second?.headers.get("Idempotency-Key")).toBe(first?.headers.get("Idempotency-Key"));
  });

  it("gets a new key for a changed reply", async () => {
    const { user, main, backend } = await sendManualReply({ reply: [{ kind: "network_error" }] });
    await within(main).findByRole("alert");
    await user.type(
      within(main).getByRole("textbox", { name: "Reply to the customer" }),
      " Thanks.",
    );

    await sendAndConfirm(user, main);

    await waitFor(() => {
      expect(backend.requestsTo(sendReplyRoute)).toHaveLength(2);
    });
    const [first, second] = backend.requestsTo(sendReplyRoute);
    expect(second?.headers.get("Idempotency-Key")).not.toBe(first?.headers.get("Idempotency-Key"));
  });
});
