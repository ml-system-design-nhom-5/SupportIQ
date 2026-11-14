/**
 * The console screens in tests: a fake backend that answers the session, the queue, the view, and
 * the workspace with the example files of the contract (TEST-11), the variants of a workspace
 * example that no example covers yet, such as an analysis that is ready while the draft is pending,
 * and the steps of the reply area that several tests share.
 */
import { screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";

import {
  type ComposerTicket,
  toComposerTicket,
} from "@/features/console-tickets/model/composer-ticket";
import { toTicketWorkspace } from "@/features/console-tickets/model/workspace";
import { buildWorkspaceRegions } from "@/features/console-tickets/model/workspace-regions";
import {
  createEscalationRoute,
  createReplyProposalRoute,
  createSuggestionRoute,
  getConsoleKbDocumentVersionRoute,
  getConsoleTicketRoute,
  getCurrentSessionRoute,
  listConsoleTicketsRoute,
  recordTicketViewRoute,
  sendReplyRoute,
} from "@/test/backend-routes";
import { readExample, readOperationExample } from "@/test/contract-examples";
import {
  createFakeBackend,
  exampleAnswer,
  type FakeAnswer,
  type FakeBackend,
  noContentAnswer,
} from "@/test/fake-backend";
import { renderApp, testSettings } from "@/test/render-app";

/** The path of the workspace of TCK-1042, the ticket of the examples. */
export const TICKET_PATH = "/console/tickets/TCK-1042";

/** The current suggestion of the draft-ready and abstained-low-confidence examples. */
export const DRAFT_READY_SUGGESTION_ID = "6b1f0c3e-2a4d-4e8f-9b7c-1d3e5f7a9b20";

/** What the console of a test receives. Each list is used in order, and its last answer repeats. */
export type ConsoleAnswers = {
  /** The example of `getCurrentSession`; `staff` by default. */
  readonly session?: string;
  readonly queue?: readonly FakeAnswer[];
  readonly view?: readonly FakeAnswer[];
  readonly workspace?: readonly FakeAnswer[];
  readonly kbDocument?: readonly FakeAnswer[];
  /** The answers of `createSuggestion`; the `intent-override` example by default. */
  readonly suggestion?: readonly FakeAnswer[];
  /** The answers of `sendReply`; the `from-ai-draft` example by default. */
  readonly reply?: readonly FakeAnswer[];
  /** The answers of `createReplyProposal`; the `from-ai-draft` example by default. */
  readonly proposal?: readonly FakeAnswer[];
  /** The answers of `createEscalation`; the `escalated` example by default. */
  readonly escalation?: readonly FakeAnswer[];
  readonly settings?: typeof testSettings;
};

/**
 * Answer with an example of `getConsoleTicket`.
 *
 * @param name - The example name, such as `draft-ready`.
 * @returns The answer.
 */
export function workspaceExample(name: string): FakeAnswer {
  return exampleAnswer(200, "getConsoleTicket", name);
}

/**
 * Answer with a workspace example whose suggestion has some members replaced.
 *
 * @param name - The example name.
 * @param overrides - The members of `suggestion` to replace, such as `draft`.
 * @returns The answer.
 */
export function workspaceWithSuggestion(
  name: string,
  overrides: Readonly<Record<string, unknown>>,
): FakeAnswer {
  const workspace = readObject("getConsoleTicket", name);
  const suggestion = workspace["suggestion"];
  if (typeof suggestion !== "object" || suggestion === null) {
    throw new Error(`contracts/examples/getConsoleTicket/${name}.json has no suggestion.`);
  }
  return {
    kind: "body",
    status: 200,
    body: { ...workspace, suggestion: { ...suggestion, ...overrides } },
  };
}

/**
 * Answer with a workspace example with some top-level members replaced.
 *
 * @param name - The example name.
 * @param overrides - The members to replace.
 * @returns The answer.
 */
export function workspaceWith(
  name: string,
  overrides: Readonly<Record<string, unknown>>,
): FakeAnswer {
  return {
    kind: "body",
    status: 200,
    body: { ...readObject("getConsoleTicket", name), ...overrides },
  };
}

/**
 * Register the answers of the console on a fake backend, for a test or a story.
 *
 * @param backend - The fake backend.
 * @param answers - The answers that differ from the defaults: a staff session, the open queue, a
 *   recorded view, the draft-ready workspace, the sample KB document version, a pending suggestion
 *   after an intent override, a sent reply, a stored proposal, and an escalation.
 */
export function answerConsole(backend: FakeBackend, answers: ConsoleAnswers = {}): void {
  const { session, ...writtenAnswers } = answers;
  const all = { ...readDefaultAnswers(), ...writtenAnswers };
  backend.answer(
    getCurrentSessionRoute,
    exampleAnswer(200, "getCurrentSession", session ?? "staff"),
  );
  backend.answer(listConsoleTicketsRoute, ...all.queue);
  backend.answer(recordTicketViewRoute, ...all.view);
  backend.answer(getConsoleTicketRoute, ...all.workspace);
  backend.answer(getConsoleKbDocumentVersionRoute, ...all.kbDocument);
  backend.answer(createSuggestionRoute, ...all.suggestion);
  backend.answer(sendReplyRoute, ...all.reply);
  backend.answer(createReplyProposalRoute, ...all.proposal);
  backend.answer(createEscalationRoute, ...all.escalation);
}

/**
 * List the default answers of the console.
 *
 * @returns The open queue, a recorded view, the draft-ready workspace, the sample KB document
 *   version, a pending suggestion after an intent override, a sent reply, a stored proposal, and an
 *   escalation.
 */
function readDefaultAnswers() {
  return {
    queue: [exampleAnswer(200, "listConsoleTickets", "open-queue")],
    view: [noContentAnswer],
    workspace: [workspaceExample("draft-ready")],
    kbDocument: [exampleAnswer(200, "getConsoleKbDocumentVersion", "document-version")],
    suggestion: [exampleAnswer(202, "createSuggestion", "intent-override")],
    reply: [exampleAnswer(201, "sendReply", "from-ai-draft")],
    proposal: [exampleAnswer(201, "createReplyProposal", "from-ai-draft")],
    escalation: [exampleAnswer(201, "createEscalation", "escalated")],
  } satisfies Required<Omit<ConsoleAnswers, "session" | "settings">>;
}

/**
 * Create the fake backend of a console test.
 *
 * @param answers - The answers that differ from the defaults of {@link answerConsole}.
 * @returns The backend.
 */
export function createConsoleBackend(answers: ConsoleAnswers = {}): FakeBackend {
  const backend = createFakeBackend();
  answerConsole(backend, answers);
  return backend;
}

/**
 * Open a console path with the given answers.
 *
 * @param path - The app path, such as {@link TICKET_PATH}.
 * @param answers - The answers that differ from the defaults.
 * @returns The rendered app.
 */
export function openConsole(path: string, answers: ConsoleAnswers = {}) {
  return renderApp({
    path,
    backend: createConsoleBackend(answers),
    settings: answers.settings ?? testSettings,
  });
}

/**
 * Read an example value that is an object.
 *
 * @param folder - The operation ID.
 * @param name - The example name.
 * @returns The value.
 */
function readObject(folder: string, name: string): Readonly<Record<string, unknown>> {
  const example = readExample(folder, name);
  if (typeof example !== "object" || example === null || Array.isArray(example)) {
    throw new Error(`contracts/examples/${folder}/${name}.json has no object value.`);
  }
  return Object.fromEntries(Object.entries(example));
}

/**
 * Read a part of the suggestion of a workspace example, to build a part that no example covers.
 *
 * @param name - The example of `getConsoleTicket`.
 * @param part - `analysis` or `draft`.
 * @returns The part, as the example holds it.
 */
export function readSuggestionPart(
  name: string,
  part: "analysis" | "draft",
): Readonly<Record<string, unknown>> {
  const suggestion = readObject("getConsoleTicket", name)["suggestion"];
  const value: unknown =
    typeof suggestion === "object" && suggestion !== null
      ? Reflect.get(suggestion, part)
      : undefined;
  if (typeof value !== "object" || value === null) {
    throw new Error(`contracts/examples/getConsoleTicket/${name}.json has no ${part}.`);
  }
  return Object.fromEntries(Object.entries(value));
}

/**
 * Read the canonical `text` of the ready draft of a workspace example, which Send reply sends as
 * is.
 *
 * @param name - The example of `getConsoleTicket`.
 * @returns The text.
 */
export function readDraftText(name: string): string {
  const text = readSuggestionPart(name, "draft")["text"];
  if (typeof text !== "string") {
    throw new Error(`contracts/examples/getConsoleTicket/${name}.json has no draft text.`);
  }
  return text;
}

/**
 * Open the workspace of TCK-1042 and wait for it.
 *
 * @param answers - The answers that differ from the defaults: the draft-ready workspace.
 * @returns The rendered app and the `main` landmark.
 */
export async function openReplyArea(answers: ConsoleAnswers = {}) {
  const rendered = openConsole(TICKET_PATH, answers);
  await screen.findByRole("heading", { level: 1, name: /^Ticket / });
  return { ...rendered, main: screen.getByRole("main") };
}

/**
 * Write a reply in the editor.
 *
 * @param user - The user of the test.
 * @param main - The `main` landmark.
 * @param text - The reply.
 */
export async function writeReply(user: UserEvent, main: HTMLElement, text: string): Promise<void> {
  await user.type(within(main).getByRole("textbox", { name: "Reply to the customer" }), text);
}

/**
 * Send the reply on the screen: Send reply, then the Send reply of the confirmation.
 *
 * @param user - The user of the test.
 * @param main - The `main` landmark.
 */
export async function sendAndConfirm(user: UserEvent, main: HTMLElement): Promise<void> {
  await user.click(within(main).getByRole("button", { name: "Send reply" }));
  const dialog = await screen.findByRole("alertdialog", { name: "Send this reply to Lan Tran?" });
  await user.click(within(dialog).getByRole("button", { name: "Send reply" }));
}

/**
 * Read what the composer reads of a workspace example.
 *
 * @param name - The example of `getConsoleTicket`.
 * @param isSuggestionRequested - True while an intent correction or Try AI again is sending.
 * @returns The composer ticket.
 */
export function readComposerTicket(name: string, isSuggestionRequested = false): ComposerTicket {
  const workspace = toTicketWorkspace(readOperationExample("getConsoleTicket", 200, name));
  return toComposerTicket(workspace, buildWorkspaceRegions(workspace), isSuggestionRequested);
}
