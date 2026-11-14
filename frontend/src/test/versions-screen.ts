/**
 * The Versions screen in tests: a fake backend that answers the session and the versions with the
 * example files of the contract (TEST-11), and the rows of a panel, read by role and accessible
 * name only (UI-37).
 */
import { screen, within } from "@testing-library/react";

import { VERSIONS_PATH } from "@/features/admin-versions";
import { getAdminVersionsRoute, getCurrentSessionRoute } from "@/test/backend-routes";
import {
  createFakeBackend,
  exampleAnswer,
  type FakeAnswer,
  type FakeBackend,
} from "@/test/fake-backend";
import { renderApp, testSettings } from "@/test/render-app";

/**
 * What the Versions screen of a test receives. Each list is used in order, and its last answer
 * repeats.
 */
export type VersionsAnswers = {
  /** The example of `getCurrentSession`; `admin` by default. */
  readonly session?: string;
  /** The answers of `getAdminVersions`; the `ai-service-available` example by default. */
  readonly versions?: readonly FakeAnswer[];
};

/** One row of a panel as the screen shows it. */
export type ShownVersion = {
  readonly term: string;
  readonly value: string;
};

/**
 * Answer with an example of `getAdminVersions`.
 *
 * @param name - `ai-service-available` or `ai-service-unavailable`.
 * @returns The answer.
 */
export function versionsExample(name: string): FakeAnswer {
  return exampleAnswer(200, "getAdminVersions", name);
}

/**
 * Register the answers of the Versions screen on a fake backend, for a test or a story.
 *
 * @param backend - The fake backend.
 * @param answers - The answers that differ from the defaults: an admin session and the versions
 *   of an available `ai-service`.
 */
export function answerVersions(backend: FakeBackend, answers: VersionsAnswers = {}): void {
  backend.answer(
    getCurrentSessionRoute,
    exampleAnswer(200, "getCurrentSession", answers.session ?? "admin"),
  );
  backend.answer(
    getAdminVersionsRoute,
    ...(answers.versions ?? [versionsExample("ai-service-available")]),
  );
}

/**
 * Open the Versions screen with the given answers.
 *
 * @param answers - The answers that differ from the defaults.
 * @returns The rendered app.
 */
export function openVersions(answers: VersionsAnswers = {}) {
  const backend = createFakeBackend();
  answerVersions(backend, answers);
  return renderApp({ path: VERSIONS_PATH, backend, settings: testSettings });
}

/**
 * Read every row of a panel, in order.
 *
 * @param panel - The name of the panel: `ai-service` or `backend`.
 * @returns The term and the value of each row.
 */
export async function readVersionRows(panel: string): Promise<readonly ShownVersion[]> {
  const section = await screen.findByRole("region", { name: panel });
  const values = within(section).getAllByRole("definition");
  return within(section)
    .getAllByRole("term")
    .map((term, index) => ({ term: term.textContent, value: values[index]?.textContent ?? "" }));
}
