import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "@/design-system";
import { useCreateSuggestion } from "@/features/console-tickets/api/use-create-suggestion";
import {
  type TicketWorkspace,
  toTicketWorkspace,
} from "@/features/console-tickets/model/workspace";
import { createSuggestionRoute, getConsoleTicketRoute } from "@/test/backend-routes";
import {
  type ConsoleAnswers,
  createConsoleBackend,
  openConsole,
  TICKET_PATH,
  workspaceExample,
  workspaceWith,
  workspaceWithSuggestion,
} from "@/test/console-screen";
import { readOperationExample } from "@/test/contract-examples";
import { exampleAnswer, type FakeBackend } from "@/test/fake-backend";
import { renderWithDependencies } from "@/test/render-app";

/** A UUID in lowercase, as the contract requires of an `Idempotency-Key`. */
const idempotencyKeyPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** A suggestion of TCK-1042 that no example has, for a reload that shows another suggestion. */
const OTHER_SUGGESTION_ID = "3a5c7e9b-1d2f-4a6b-8c0d-e2f4a6b8c0d1";

/** The draft-ready ticket after a correction: its suggestion is the one that the `202` started. */
const workspaceAfterCorrection = workspaceWithSuggestion(
  "draft-ready",
  readOperationExample("createSuggestion", 202, "intent-override"),
);

/**
 * Open the workspace of TCK-1042 and wait for it.
 *
 * @param answers - The answers that differ from the defaults of the console.
 * @returns The rendered app and the `main` landmark of the workspace.
 */
async function openWorkspace(answers: ConsoleAnswers) {
  const rendered = openConsole(TICKET_PATH, answers);
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

/** The hook alone, with a button for each request, as the action bar will call it. */
function SuggestionButtons({ workspace }: { readonly workspace: TicketWorkspace }) {
  const requests = useCreateSuggestion(workspace.ticketId, workspace);
  return (
    <>
      <Button onClick={requests.retry}>Try AI again</Button>
      <Button
        onClick={() => {
          requests.correctIntent("request_refund");
        }}
      >
        Use Request refund
      </Button>
    </>
  );
}

/**
 * Render the hook for a workspace example.
 *
 * @param name - The example of `getConsoleTicket`.
 * @returns The rendered buttons, the user-event instance, and the backend.
 */
function renderSuggestionButtons(name: string) {
  const workspace = toTicketWorkspace(readOperationExample("getConsoleTicket", 200, name));
  return renderWithDependencies(<SuggestionButtons workspace={workspace} />, {
    path: TICKET_PATH,
    backend: createConsoleBackend({
      suggestion: [exampleAnswer(202, "createSuggestion", "retry")],
    }),
  });
}

describe("Correcting the intent from the strip (UI-22)", () => {
  it("sends the chosen candidate as intent_override with an Idempotency-Key", async () => {
    const { user, backend, main } = await openWorkspace({});

    await user.click(within(main).getByRole("button", { name: "Use Request refund 7%" }));

    const [key] = await readSuggestionKeys(backend, 1);
    const [request] = backend.requestsTo(createSuggestionRoute);
    expect(request?.path).toBe("/v1/console/tickets/TCK-1042/suggestions");
    expect(request?.body).toEqual({ intent_override: "request_refund" });
    expect(key).toMatch(idempotencyKeyPattern);
  });

  it("sends an intent from Other intent while the draft is generating", async () => {
    const { user, backend, main } = await openWorkspace({
      workspace: [workspaceWithSuggestion("draft-ready", { draft: { draft_status: "pending" } })],
    });

    await user.click(within(main).getByRole("button", { name: "Other intent" }));
    await user.click(await screen.findByRole("menuitem", { name: "Cancel order" }));

    await readSuggestionKeys(backend, 1);
    expect(backend.requestsTo(createSuggestionRoute)[0]?.body).toEqual({
      intent_override: "cancel_order",
    });
  });

  it("sends a new Idempotency-Key for each correction", async () => {
    const { user, backend, main } = await openWorkspace({});

    await user.click(within(main).getByRole("button", { name: "Use Request refund 7%" }));
    await readSuggestionKeys(backend, 1);
    await user.click(await within(main).findByRole("button", { name: "Use Track order 2%" }));

    const [firstKey, secondKey] = await readSuggestionKeys(backend, 2);
    expect(secondKey).toMatch(idempotencyKeyPattern);
    expect(secondKey).not.toBe(firstKey);
  });

  it("reuses the Idempotency-Key when staff repeat a correction that failed (TS-29)", async () => {
    const { user, backend, main } = await openWorkspace({
      suggestion: [
        exampleAnswer(503, "problems", "not-ready"),
        exampleAnswer(202, "createSuggestion", "intent-override"),
      ],
    });
    const candidate = within(main).getByRole("button", { name: "Use Request refund 7%" });

    await user.click(candidate);
    await screen.findByRole("alert");
    await user.click(candidate);

    const [firstKey, secondKey] = await readSuggestionKeys(backend, 2);
    expect(secondKey).toBe(firstKey);
  });

  it("gets a new Idempotency-Key once the reloaded ticket shows another suggestion", async () => {
    const { user, backend, main } = await openWorkspace({
      workspace: [
        workspaceExample("draft-ready"),
        workspaceWithSuggestion("draft-ready", {
          suggestion_id: OTHER_SUGGESTION_ID,
          draft: { draft_status: "pending" },
        }),
      ],
      suggestion: [
        { kind: "network_error" },
        exampleAnswer(202, "createSuggestion", "intent-override"),
      ],
    });
    await user.click(within(main).getByRole("button", { name: "Use Request refund 7%" }));
    await waitFor(() => {
      expect(within(main).getByRole("region", { name: "AI draft" })).toHaveTextContent(
        "Generating draft",
      );
    });

    await user.click(within(main).getByRole("button", { name: "Use Request refund 7%" }));

    const [firstKey, secondKey] = await readSuggestionKeys(backend, 2);
    expect(secondKey).toMatch(idempotencyKeyPattern);
    expect(secondKey).not.toBe(firstKey);
  });

  it("marks the previous draft as outdated while the new draft generates", async () => {
    const { user, main } = await openWorkspace({
      workspace: [workspaceExample("draft-ready"), workspaceAfterCorrection],
    });

    await user.click(within(main).getByRole("button", { name: "Use Request refund 7%" }));

    const outdated = await within(main).findByRole("region", { name: "Outdated draft" });
    expect(outdated).toHaveTextContent("Outdated");
    expect(outdated).toHaveTextContent("Hello Lan Tran, thank you for your patience.");
    expect(within(main).getByRole("region", { name: "AI draft" })).toHaveTextContent(
      "Generating draft",
    );
  });
});

describe("A correction that fails", () => {
  it.each([
    [
      409,
      "suggestion-pending",
      "The AI is still working on this ticket. Wait until it is done, then try again.",
    ],
    [
      422,
      "no-intent-known",
      "This ticket changed in the meantime. It now shows its current state.",
    ],
    [
      409,
      "invalid-ticket-state",
      "This ticket changed in the meantime. It now shows its current state.",
    ],
  ])("says so after %i %s, with the trace ID, and reloads the ticket", async (...failure) => {
    const [status, problem, message] = failure;
    const { user, backend, main } = await openWorkspace({
      suggestion: [exampleAnswer(status, "problems", problem)],
    });

    await user.click(within(main).getByRole("button", { name: "Use Request refund 7%" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(`The intent was not changed. ${message}`);
    expect(alert).toHaveTextContent(/Details: trace [0-9a-f]{32}/);
    await waitFor(() => {
      expect(backend.requestsTo(getConsoleTicketRoute)).toHaveLength(2);
    });
  });
});

describe("Choosing an intent (UI-42)", () => {
  it("sends the candidate of Use this intent", async () => {
    const { user, backend, main } = await openWorkspace({
      workspace: [workspaceExample("abstained-low-confidence")],
    });

    await user.click(within(main).getByRole("button", { name: "Use this intent: Request refund" }));

    await readSuggestionKeys(backend, 1);
    expect(backend.requestsTo(createSuggestionRoute)[0]?.body).toEqual({
      intent_override: "request_refund",
    });
  });

  it("sends an intent outside the top three from Other intent (ESC-01)", async () => {
    const { user, backend, main } = await openWorkspace({
      workspace: [workspaceExample("abstained-low-confidence")],
    });
    expect(within(main).queryByRole("region", { name: "Intent" })).toBeNull();

    await user.click(within(main).getByRole("button", { name: "Other intent" }));
    await user.click(await screen.findByRole("menuitem", { name: "Cancel order" }));

    const [key] = await readSuggestionKeys(backend, 1);
    expect(key).toMatch(idempotencyKeyPattern);
    expect(backend.requestsTo(createSuggestionRoute)[0]?.body).toEqual({
      intent_override: "cancel_order",
    });
  });

  it("offers every intent but the predicted one in Other intent", async () => {
    const { user, main } = await openWorkspace({
      workspace: [workspaceExample("abstained-low-confidence")],
    });
    const choice = within(main).getByRole("region", { name: "Choose an intent" });

    await user.click(within(choice).getByRole("button", { name: "Other intent" }));

    const menu = await screen.findByRole("menu", { name: "Other intent" });
    expect(within(menu).getAllByRole("menuitem")).toHaveLength(45);
    expect(within(menu).queryByRole("menuitem", { name: "Refund status" })).toBeNull();
  });
});

describe("No correction without correct_intent (UI-40)", () => {
  it("offers no intent of the choice when backend does not allow a correction", async () => {
    const { main } = await openWorkspace({
      workspace: [workspaceWith("abstained-low-confidence", { allowed_actions: [] })],
    });

    const choice = within(main).getByRole("region", { name: "Choose an intent" });
    expect(within(choice).getAllByRole("listitem")).toHaveLength(3);
    expect(within(choice).queryAllByRole("button")).toEqual([]);
  });

  it("shows the intent read-only when backend does not allow a correction", async () => {
    const { main } = await openWorkspace({ workspace: [workspaceExample("read-only-for-staff")] });

    const intent = within(main).getByRole("region", { name: "Intent" });
    expect(intent).toHaveTextContent("Next candidates:");
    expect(within(intent).queryAllByRole("button")).toEqual([]);
  });
});

describe("Retrying the AI (UI-26)", () => {
  it("sends createSuggestion without a body member, with an Idempotency-Key", async () => {
    const { user, backend } = renderSuggestionButtons("ai-service-unavailable");

    await user.click(screen.getByRole("button", { name: "Try AI again" }));

    const [key] = await readSuggestionKeys(backend, 1);
    expect(backend.requestsTo(createSuggestionRoute)[0]?.body).toEqual({});
    expect(key).toMatch(idempotencyKeyPattern);
  });

  it("sends nothing for a retry without retry_suggestion", async () => {
    const { user, backend } = renderSuggestionButtons("draft-ready");

    await user.click(screen.getByRole("button", { name: "Try AI again" }));
    await user.click(screen.getByRole("button", { name: "Use Request refund" }));

    await readSuggestionKeys(backend, 1);
    expect(backend.requestsTo(createSuggestionRoute)[0]?.body).toEqual({
      intent_override: "request_refund",
    });
  });
});
