/**
 * The console screens in tests: a fake backend that answers the session, the queue, the view, and
 * the workspace with the example files of the contract (TEST-11), and the variants of a workspace
 * example that no example covers yet, such as an analysis that is ready while the draft is pending.
 */
import {
  getConsoleKbDocumentVersionRoute,
  getConsoleTicketRoute,
  getCurrentSessionRoute,
  listConsoleTicketsRoute,
  recordTicketViewRoute,
} from "@/test/backend-routes";
import { readExample } from "@/test/contract-examples";
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

/** What the console of a test receives. Each list is used in order, and its last answer repeats. */
export type ConsoleAnswers = {
  /** The example of `getCurrentSession`; `staff` by default. */
  readonly session?: string;
  readonly queue?: readonly FakeAnswer[];
  readonly view?: readonly FakeAnswer[];
  readonly workspace?: readonly FakeAnswer[];
  readonly kbDocument?: readonly FakeAnswer[];
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
 *   recorded view, the draft-ready workspace, and the sample KB document version.
 */
export function answerConsole(backend: FakeBackend, answers: ConsoleAnswers = {}): void {
  backend.answer(
    getCurrentSessionRoute,
    exampleAnswer(200, "getCurrentSession", answers.session ?? "staff"),
  );
  backend.answer(
    listConsoleTicketsRoute,
    ...(answers.queue ?? [exampleAnswer(200, "listConsoleTickets", "open-queue")]),
  );
  backend.answer(recordTicketViewRoute, ...(answers.view ?? [noContentAnswer]));
  backend.answer(
    getConsoleTicketRoute,
    ...(answers.workspace ?? [workspaceExample("draft-ready")]),
  );
  backend.answer(
    getConsoleKbDocumentVersionRoute,
    ...(answers.kbDocument ?? [
      exampleAnswer(200, "getConsoleKbDocumentVersion", "document-version"),
    ]),
  );
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
