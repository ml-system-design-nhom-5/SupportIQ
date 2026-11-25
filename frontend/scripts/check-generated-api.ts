/**
 * Fail when src/api/generated/ is out of date with contracts/backend.openapi.yaml (TS-27, CON-26).
 * It runs the same generator command as `pnpm run generate:api` into a temporary folder and
 * compares the result byte for byte with the committed file.
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CONTRACT_PATH = "../contracts/backend.openapi.yaml";
const COMMITTED_PATH = "src/api/generated/backend.ts";
const GENERATOR_PATH = "node_modules/.bin/openapi-typescript";

const temporaryFolder = mkdtempSync(join(tmpdir(), "supportiq-generated-api-"));
const regeneratedPath = join(temporaryFolder, "backend.ts");
try {
  execFileSync(GENERATOR_PATH, [CONTRACT_PATH, "--output", regeneratedPath], { stdio: "pipe" });
  const isUpToDate = readFileSync(regeneratedPath).equals(readFileSync(COMMITTED_PATH));
  if (!isUpToDate) {
    process.stderr.write(
      `${COMMITTED_PATH} is out of date with ${CONTRACT_PATH}. Run: pnpm run generate:api\n`,
    );
    process.exitCode = 1;
  } else {
    process.stdout.write(`ok: ${COMMITTED_PATH} matches ${CONTRACT_PATH}\n`);
  }
} finally {
  rmSync(temporaryFolder, { recursive: true, force: true });
}
