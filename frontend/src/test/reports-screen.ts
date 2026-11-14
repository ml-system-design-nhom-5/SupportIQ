/**
 * The Reports page in tests: a fake backend that answers the session and the report with the
 * example files of the contract (TEST-11), and the steps that several tests share.
 */
import { screen, within } from "@testing-library/react";

import { getConsoleReportRoute, getCurrentSessionRoute } from "@/test/backend-routes";
import {
  createFakeBackend,
  exampleAnswer,
  type FakeAnswer,
  type FakeBackend,
} from "@/test/fake-backend";
import { renderApp, testSettings } from "@/test/render-app";

/** The path of the Reports page. */
export const REPORTS_PATH = "/console/reports";

/** What the Reports page of a test receives. Each list is used in order, and its last answer repeats. */
export type ReportAnswers = {
  /** The example of `getCurrentSession`; `manager` by default. */
  readonly session?: string;
  /** The answers of `getConsoleReport`; the `period-with-activity` example by default. */
  readonly report?: readonly FakeAnswer[];
};

/**
 * Answer with an example of `getConsoleReport`.
 *
 * @param name - `period-with-activity` or `empty-period`.
 * @returns The answer.
 */
export function reportExample(name: string): FakeAnswer {
  return exampleAnswer(200, "getConsoleReport", name);
}

/**
 * Register the answers of the Reports page on a fake backend, for a test or a story.
 *
 * @param backend - The fake backend.
 * @param answers - The answers that differ from the defaults: a manager session and the report
 *   of a period with activity.
 */
export function answerReports(backend: FakeBackend, answers: ReportAnswers = {}): void {
  backend.answer(
    getCurrentSessionRoute,
    exampleAnswer(200, "getCurrentSession", answers.session ?? "manager"),
  );
  backend.answer(
    getConsoleReportRoute,
    ...(answers.report ?? [reportExample("period-with-activity")]),
  );
}

/**
 * Open the Reports page with the given answers.
 *
 * @param answers - The answers that differ from the defaults.
 * @returns The rendered app.
 */
export function openReports(answers: ReportAnswers = {}) {
  const backend = createFakeBackend();
  answerReports(backend, answers);
  return renderApp({ path: REPORTS_PATH, backend, settings: testSettings });
}

/**
 * Find a figure of the report and read its cells.
 *
 * @param section - The title of the section, such as "Speed".
 * @param label - The label of the figure, such as "End-to-end latency p50".
 * @returns The value and the target of the figure.
 */
export async function readFigure(
  section: string,
  label: string,
): Promise<{ readonly value: string; readonly target: string }> {
  const table = await screen.findByRole("table", { name: section });
  const row = within(table).getByRole("rowheader", { name: label }).closest("tr");
  if (row === null) {
    throw new Error(`The figure ${label} has no table row.`);
  }
  const [value = "", target = ""] = within(row)
    .getAllByRole("cell")
    .map((cell) => cell.textContent);
  return { value, target };
}
