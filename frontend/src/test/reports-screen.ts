/**
 * The Reports page in tests: a fake backend that answers the session and the report with the
 * example files of the contract (TEST-11), and the steps that several tests share. Figures are
 * read by role and accessible name only (UI-37).
 */
import { screen, within } from "@testing-library/react";

import { REPORTS_PATH } from "@/features/console-reports";
import { getConsoleReportRoute, getCurrentSessionRoute } from "@/test/backend-routes";
import {
  createFakeBackend,
  exampleAnswer,
  type FakeAnswer,
  type FakeBackend,
} from "@/test/fake-backend";
import { renderApp, testSettings } from "@/test/render-app";

/** What the Reports page of a test receives. Each list is used in order, and its last answer repeats. */
export type ReportAnswers = {
  /** The example of `getCurrentSession`; `manager` by default. */
  readonly session?: string;
  /** The answers of `getConsoleReport`; the `period-with-activity` example by default. */
  readonly report?: readonly FakeAnswer[];
};

/** One figure of a section as the page shows it. */
export type ShownFigure = {
  readonly label: string;
  readonly value: string;
  readonly target: string;
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
 * Read every figure of a section, in order.
 *
 * @param section - The title of the section, such as "Speed".
 * @returns The label, the value, and the target of each figure.
 */
export async function readFigures(section: string): Promise<readonly ShownFigure[]> {
  const table = await screen.findByRole("table", { name: section });
  return within(table)
    .getAllByRole("row")
    .flatMap((row) => {
      const header = within(row).queryByRole("rowheader");
      if (header === null) {
        return [];
      }
      const [value = "", target = ""] = within(row)
        .getAllByRole("cell")
        .map((cell) => cell.textContent);
      return [{ label: header.textContent, value, target }];
    });
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
  const figure = (await readFigures(section)).find((candidate) => candidate.label === label);
  if (figure === undefined) {
    throw new Error(`The section ${section} has no figure ${label}.`);
  }
  return { value: figure.value, target: figure.target };
}
