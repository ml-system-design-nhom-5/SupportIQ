import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { createSuggestionRoute, getConsoleTicketRoute } from "@/test/backend-routes";
import {
  type ConsoleAnswers,
  openConsole,
  TICKET_PATH,
  workspaceExample,
} from "@/test/console-screen";
import { exampleAnswer, type FakeBackend } from "@/test/fake-backend";

/** A UUID in lowercase, as the contract requires of an `Idempotency-Key`. */
const idempotencyKeyPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** What the reply area says when the AI could not write a draft, as after `llm_unavailable`. */
const GENERAL_UNAVAILABLE_TEXT = "The AI could not write a draft for this ticket.";

/**
 * Open the workspace at {@link TICKET_PATH} after an AI failure and wait for its manual handling.
 *
 * @param answers - The answers that differ from the defaults; the ai-service-unavailable workspace,
 *   which allows `retry_suggestion`, by default.
 * @returns The rendered app and the `main` landmark of the workspace.
 */
async function openAfterAiFailure(answers: ConsoleAnswers) {
  const rendered = openConsole(TICKET_PATH, {
    workspace: [workspaceExample("ai-service-unavailable")],
    ...answers,
  });
  await screen.findByRole("heading", { level: 1, name: /^Ticket / });
  return { ...rendered, main: screen.getByRole("main") };
}

/**
 * Read the `Idempotency-Key` of each `createSuggestion` request, once the expected number arrived.
 *
 * @param backend - The fake backend.
 * @param count - How many requests to wait for.
 * @returns The keys, in order.
 */
async function readSuggestionKeys(
  backend: FakeBackend,
  count: number,
): Promise<readonly (string | null)[]> {
  await waitFor(() => {
    expect(backend.requestsTo(createSuggestionRoute)).toHaveLength(count);
  });
  return backend
    .requestsTo(createSuggestionRoute)
    .map((request) => request.headers.get("Idempotency-Key"));
}

/**
 * Wait until the workspace loaded the ticket a number of times.
 *
 * @param backend - The fake backend.
 * @param count - How many loads of `getConsoleTicket` to wait for.
 */
async function waitForWorkspaceLoads(backend: FakeBackend, count: number): Promise<void> {
  await waitFor(() => {
    expect(backend.requestsTo(getConsoleTicketRoute)).toHaveLength(count);
  });
}

describe("Try AI again (UI-26)", () => {
  it("is absent when backend does not allow retry_suggestion (UI-40)", async () => {
    const { main } = await openAfterAiFailure({
      workspace: [workspaceExample("pseudonymization-failed")],
    });

    expect(main).toHaveTextContent(
      "Personal data in the message could not be hidden, so nothing was sent to the AI.",
    );
    expect(within(main).queryByRole("button", { name: "Try AI again" })).toBeNull();
  });

  it("sends createSuggestion with an empty body and an Idempotency-Key", async () => {
    const { user, backend, main } = await openAfterAiFailure({
      suggestion: [exampleAnswer(202, "createSuggestion", "retry")],
    });

    await user.click(within(main).getByRole("button", { name: "Try AI again" }));

    const [key] = await readSuggestionKeys(backend, 1);
    const [request] = backend.requestsTo(createSuggestionRoute);
    expect(request?.path).toBe("/v1/console/tickets/TCK-1042/suggestions");
    expect(request?.body).toEqual({});
    expect(key).toMatch(idempotencyKeyPattern);
  });
});

describe("A Try AI again that fails", () => {
  it("says that the AI did not start again after 422 invalid-request, and reloads the ticket", async () => {
    const { user, backend, main } = await openAfterAiFailure({
      suggestion: [exampleAnswer(422, "problems", "nothing-to-retry")],
    });

    await user.click(within(main).getByRole("button", { name: "Try AI again" }));

    const alert = await within(main).findByRole("alert");
    expect(alert).toHaveTextContent(
      "The AI did not start again. This ticket changed in the meantime. It now shows its current state.",
    );
    expect(alert).toHaveTextContent(/Details: trace [0-9a-f]{32}/);
    await waitForWorkspaceLoads(backend, 2);
  });

  it("says that the AI may have started again after a lost connection (ERR-16)", async () => {
    const { user, backend, main } = await openAfterAiFailure({
      suggestion: [{ kind: "network_error" }],
    });

    await user.click(within(main).getByRole("button", { name: "Try AI again" }));

    expect(await within(main).findByRole("alert")).toHaveTextContent(
      "The AI may have started again. The server could not be reached. Check your connection and try again.",
    );
    await waitForWorkspaceLoads(backend, 2);
  });
});

describe("The Idempotency-Key of Try AI again (TS-29)", () => {
  it("is reused when staff try again on the same suggestion after a lost connection", async () => {
    const { user, backend, main } = await openAfterAiFailure({
      suggestion: [{ kind: "network_error" }, exampleAnswer(202, "createSuggestion", "retry")],
    });
    await user.click(within(main).getByRole("button", { name: "Try AI again" }));
    await within(main).findByRole("alert");
    await waitForWorkspaceLoads(backend, 2);

    await user.click(within(main).getByRole("button", { name: "Try AI again" }));

    const [firstKey, secondKey] = await readSuggestionKeys(backend, 2);
    expect(secondKey).toBe(firstKey);
  });

  it("is new once the reloaded ticket shows another suggestion", async () => {
    const { user, backend, main } = await openAfterAiFailure({
      workspace: [workspaceExample("ai-service-unavailable"), workspaceExample("llm-unavailable")],
      suggestion: [{ kind: "network_error" }, exampleAnswer(202, "createSuggestion", "retry")],
    });
    expect(main).not.toHaveTextContent(GENERAL_UNAVAILABLE_TEXT);
    await user.click(within(main).getByRole("button", { name: "Try AI again" }));
    await waitFor(() => {
      expect(main).toHaveTextContent(GENERAL_UNAVAILABLE_TEXT);
    });

    await user.click(within(main).getByRole("button", { name: "Try AI again" }));

    const [firstKey, secondKey] = await readSuggestionKeys(backend, 2);
    expect(secondKey).toMatch(idempotencyKeyPattern);
    expect(secondKey).not.toBe(firstKey);
  });
});
