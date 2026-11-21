// Lints lint/fixtures/violations.openapi.yaml, which breaks each custom rule once, and checks that
// every supportiq rule enabled in redocly.yaml reports a problem there. A rule that stops working
// then fails `pnpm run check`, which puts `redocly` on the PATH of this script.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";

const FIXTURE = "lint/fixtures/violations.openapi.yaml";
const CONFIG = "redocly.yaml";
const ENABLED_RULE = /^ {2}(supportiq\/[a-z0-9-]+): error$/gm;

interface LintProblem {
  readonly ruleId: string;
}

interface LintReport {
  readonly problems: readonly LintProblem[];
}

process.exitCode = main();

function main(): number {
  const enabled = [...readFileSync(CONFIG, "utf8").matchAll(ENABLED_RULE)].map((match) => match[1]);
  const reported = new Set(lintFixture().problems.map((problem) => problem.ruleId));
  const missing = enabled.filter((rule) => rule === undefined || !reported.has(rule));
  for (const rule of enabled) {
    console.log(
      `${missing.includes(rule) ? "FAILED  no problem from" : "ok      reported by"} ${String(rule)}`,
    );
  }
  return enabled.length > 0 && missing.length === 0 ? 0 : 1;
}

function lintFixture(): LintReport {
  const run = spawnSync("redocly", ["lint", FIXTURE, "--config", CONFIG, "--format=json"], {
    encoding: "utf8",
  });
  if (run.error !== undefined) {
    throw new Error(`redocly lint did not start: ${run.error.message}`);
  }
  const report: unknown = JSON.parse(run.stdout);
  if (!isLintReport(report)) {
    throw new Error(`redocly lint returned no valid report: ${run.stderr}`);
  }
  return report;
}

function isLintReport(value: unknown): value is LintReport {
  return isObject(value) && Array.isArray(value.problems) && value.problems.every(isLintProblem);
}

function isLintProblem(value: unknown): value is LintProblem {
  return isObject(value) && typeof value.ruleId === "string";
}

function isObject(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
