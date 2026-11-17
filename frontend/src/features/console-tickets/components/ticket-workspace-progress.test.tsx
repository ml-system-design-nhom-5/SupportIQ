import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FIRST_EVENT_TIMEOUT_MS } from "@/features/console-tickets/model/polling";
import { getConsoleTicketRoute } from "@/test/backend-routes";
import {
  type ConsoleAnswers,
  openConsole,
  TICKET_PATH,
  workspaceExample,
  workspaceWith,
} from "@/test/console-screen";
import { exampleAnswer, type FakeAnswer, type FakeBackend } from "@/test/fake-backend";
import type { FakeEventSource, FakeEventSources } from "@/test/fake-event-source";
import { TEST_BASE_URL } from "@/test/render-app";

/** The stream of the ticket of the examples. */
const STREAM_URL = `${TEST_BASE_URL}/v1/console/tickets/TCK-1042/suggestion-events`;

/** The fallback poll of ADR-0022, statement 7: every 30 s, as the lead decided on 2026-11-13. */
const FALLBACK_POLL_MS = 30_000;

/** The workspace while the analysis and the draft are pending. */
const pendingWorkspace = workspaceExample("suggestion-pending");

/** The workspace once the draft is ready. */
const readyWorkspace = workspaceExample("draft-ready");

afterEach(() => {
  vi.useRealTimers();
});

/**
 * Write the data of an event of the stream.
 *
 * @param draftStatus - The `draft_status`; the analysis is ready.
 * @returns The data as `backend` sends it.
 */
function progressData(draftStatus: string): string {
  return JSON.stringify({
    suggestion_id: "6b1f0c3e-2a4d-4e8f-9b7c-1d3e5f7a9b20",
    analysis_status: "ready",
    draft_status: draftStatus,
  });
}

/**
 * Open the workspace at {@link TICKET_PATH} and wait until it shows the ticket of the example.
 *
 * @param workspace - The answers of `getConsoleTicket`, in order; the last one repeats.
 * @param answers - The other answers that differ from the defaults.
 * @returns The rendered app.
 */
async function openWorkspace(workspace: readonly FakeAnswer[], answers: ConsoleAnswers = {}) {
  const rendered = openConsole(TICKET_PATH, { workspace, ...answers });
  await screen.findByRole("heading", { level: 1, name: /^Ticket / });
  return rendered;
}

/**
 * Read the stream that the workspace opened last.
 *
 * @param eventSources - The streams of the test.
 * @returns The stream.
 */
function lastStream(eventSources: FakeEventSources): FakeEventSource {
  const stream = eventSources.opened.at(-1);
  if (stream === undefined) {
    throw new Error("The workspace opened no stream.");
  }
  return stream;
}

/**
 * Wait until the workspace loaded the ticket a number of times.
 *
 * @param backend - The fake backend.
 * @param count - How many loads of `getConsoleTicket` to wait for.
 */
async function waitForLoads(backend: FakeBackend, count: number): Promise<void> {
  await waitFor(() => {
    expect(backend.requestsTo(getConsoleTicketRoute)).toHaveLength(count);
  });
}

describe("The suggestion progress stream (ADR-0022, statement 6)", () => {
  it("opens one stream of the ticket while a part is pending", async () => {
    const { eventSources } = await openWorkspace([pendingWorkspace]);

    expect(eventSources.opened.map((stream) => stream.url)).toEqual([STREAM_URL]);
  });

  it.each([
    ["a ticket without a pending part", readyWorkspace],
    ["a ticket in manual mode", workspaceExample("manual-mode")],
    ["a ticket that is not open", workspaceWith("suggestion-pending", { status: "escalated" })],
  ])("opens no stream for %s", async (_case, workspace) => {
    const { eventSources } = await openWorkspace([workspace]);

    expect(eventSources.opened).toEqual([]);
  });

  it("loads the workspace again after an event, and shows the draft", async () => {
    const { eventSources, backend } = await openWorkspace([pendingWorkspace, readyWorkspace]);

    lastStream(eventSources).emit(progressData("draft_ready"));

    await waitForLoads(backend, 2);
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "AI draft" })).toHaveTextContent("Draft ready");
    });
  });

  it("closes the stream after an event that shows no pending part", async () => {
    const { eventSources } = await openWorkspace([pendingWorkspace, readyWorkspace]);

    lastStream(eventSources).emit(progressData("draft_ready"));

    expect(lastStream(eventSources).isClosed).toBe(true);
  });

  it("loads again and keeps the stream after an event whose data is not a progress event", async () => {
    const { eventSources, backend } = await openWorkspace([pendingWorkspace]);

    lastStream(eventSources).emit("{not json");

    await waitForLoads(backend, 2);
    expect(lastStream(eventSources).isClosed).toBe(false);
  });

  it("closes the stream when staff leave the ticket", async () => {
    const { eventSources, router } = await openWorkspace([pendingWorkspace]);

    await router.navigate("/console");

    await waitFor(() => {
      expect(lastStream(eventSources).isClosed).toBe(true);
    });
  });

  it("opens a stream for the suggestion that Try AI again starts", async () => {
    const { eventSources, user } = await openWorkspace(
      [workspaceExample("ai-service-unavailable"), pendingWorkspace],
      { suggestion: [exampleAnswer(202, "createSuggestion", "retry")] },
    );

    await user.click(screen.getByRole("button", { name: "Try AI again" }));

    await waitFor(() => {
      expect(eventSources.opened.map((stream) => stream.url)).toEqual([STREAM_URL]);
    });
  });
});

describe("The end of a stream (ADR-0022, statements 6 and 7)", () => {
  it("loads the workspace once when the stream ends at once, as after a 204", async () => {
    const { eventSources, backend } = await openWorkspace([pendingWorkspace, readyWorkspace]);

    lastStream(eventSources).endForGood();

    await waitForLoads(backend, 2);
    expect(screen.getByRole("region", { name: "AI draft" })).toHaveTextContent("Draft ready");
  });

  it("neither loads nor polls when the browser connects again after an event", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { eventSources, backend } = await openWorkspace([pendingWorkspace]);
    lastStream(eventSources).emit(progressData("pending"));
    await waitForLoads(backend, 2);

    lastStream(eventSources).endAndReconnect();
    await vi.advanceTimersByTimeAsync(FALLBACK_POLL_MS);

    expect(backend.requestsTo(getConsoleTicketRoute)).toHaveLength(2);
    expect(lastStream(eventSources).isClosed).toBe(false);
  });

  it("counts a stream that ends before its first event as failed, and loads the workspace", async () => {
    const { eventSources, backend } = await openWorkspace([pendingWorkspace]);

    lastStream(eventSources).endAndReconnect();

    await waitForLoads(backend, 2);
    expect(lastStream(eventSources).isClosed).toBe(true);
  });

  it("counts a stream without a first event within 10 s as failed, and loads the workspace", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { eventSources, backend } = await openWorkspace([pendingWorkspace]);

    await vi.advanceTimersByTimeAsync(FIRST_EVENT_TIMEOUT_MS);

    await waitForLoads(backend, 2);
    expect(lastStream(eventSources).isClosed).toBe(true);
  });
});

describe("The fallback poll (ADR-0022, statement 7)", () => {
  it("loads the workspace again every 30 s after a stream failure, and not sooner", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { eventSources, backend } = await openWorkspace([pendingWorkspace]);
    lastStream(eventSources).endForGood();
    await waitForLoads(backend, 2);

    await vi.advanceTimersByTimeAsync(FALLBACK_POLL_MS - 1_000);
    expect(backend.requestsTo(getConsoleTicketRoute)).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(1_000);

    await waitForLoads(backend, 3);
  });

  it("opens a new stream after a poll that succeeds while a part is still pending", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { eventSources, backend } = await openWorkspace([pendingWorkspace]);
    lastStream(eventSources).endForGood();
    await waitForLoads(backend, 2);

    await vi.advanceTimersByTimeAsync(FALLBACK_POLL_MS);

    await waitFor(() => {
      expect(eventSources.opened).toHaveLength(2);
    });
    expect(lastStream(eventSources).isClosed).toBe(false);
  });

  it("polls every 30 s when the load after the last event fails", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { eventSources, backend } = await openWorkspace([
      pendingWorkspace,
      { kind: "network_error" },
      readyWorkspace,
    ]);
    lastStream(eventSources).emit(progressData("draft_ready"));
    await waitForLoads(backend, 2);

    await vi.advanceTimersByTimeAsync(FALLBACK_POLL_MS);

    await waitForLoads(backend, 3);
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "AI draft" })).toHaveTextContent("Draft ready");
    });
  });

  it("keeps polling, without a new stream, after a poll that fails", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { eventSources, backend } = await openWorkspace([
      pendingWorkspace,
      pendingWorkspace,
      { kind: "network_error" },
      pendingWorkspace,
    ]);
    lastStream(eventSources).endForGood();
    await waitForLoads(backend, 2);

    await vi.advanceTimersByTimeAsync(FALLBACK_POLL_MS);
    await waitForLoads(backend, 3);
    expect(eventSources.opened).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(FALLBACK_POLL_MS);

    await waitForLoads(backend, 4);
  });

  it("keeps the ticket on screen when a poll fails, and says so", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { eventSources } = await openWorkspace([pendingWorkspace, { kind: "network_error" }]);

    lastStream(eventSources).endForGood();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This ticket could not be updated.");
    expect(
      within(screen.getByRole("region", { name: "Customer message" })).getByText(
        /I asked for a refund/,
      ),
    ).toBeVisible();
  });
});
