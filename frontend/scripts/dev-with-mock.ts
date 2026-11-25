/**
 * Run frontend against the Prism mock with one command (WF-32): start the mock of
 * contracts/README.md on port 4010, then the Vite dev server, which proxies /v1 and /health to
 * it. Stopping this command stops both.
 */
import { type ChildProcess, spawn, type SpawnOptions } from "node:child_process";

/**
 * Each child leads its own process group, so a signal reaches the whole group: `pnpm` can run
 * behind a Corepack wrapper, which exits without passing a signal on. A background group cannot
 * read the terminal, so the children get no stdin.
 */
const childOptions: SpawnOptions = { detached: true, stdio: ["ignore", "inherit", "inherit"] };

const children: ChildProcess[] = [
  spawn("pnpm", ["--dir", "../contracts", "run", "mock"], childOptions),
  spawn("pnpm", ["exec", "vite"], childOptions),
];

/**
 * Stop every child process and exit with the given code.
 *
 * @param exitCode - The exit code of this command.
 */
function stopAll(exitCode: number): void {
  for (const child of children) {
    if (child.pid !== undefined && child.exitCode === null && child.signalCode === null) {
      process.kill(-child.pid, "SIGTERM");
    }
  }
  process.exit(exitCode);
}

for (const child of children) {
  child.on("exit", (code) => {
    stopAll(code ?? 1);
  });
}
// SIGHUP arrives when the terminal closes, which no longer reaches the detached children.
for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"] as const) {
  process.on(signal, () => {
    stopAll(0);
  });
}
