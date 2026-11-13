import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getConsoleTicketRoute, sendReplyRoute } from "@/test/backend-routes";
import {
  type ConsoleAnswers,
  openConsole,
  sendAndConfirm,
  workspaceExample,
} from "@/test/console-screen";
import { exampleAnswer } from "@/test/fake-backend";
import { testSettings } from "@/test/render-app";

/** The path of the ticket of the manual-mode example. */
const MANUAL_TICKET_PATH = "/console/tickets/TCK-1050";

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
