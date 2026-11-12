/**
 * The schema files of contracts/schemas/, and the schemas of the backend contract, as text, so that
 * a unit test fails when the contract changes a value that frontend repeats. Only unit tests use
 * this file: the `unit` project of vite.config.ts allows the folder.
 */
const BACKEND_CONTRACT_PATH = "../../../contracts/backend.openapi.yaml";

const SCHEMAS_PATH_PREFIX = "../../../contracts/schemas/";

/** The indentation of a schema name under `components.schemas` of the backend contract. */
const SCHEMA_NAME_INDENT = "    ";

/** The backend contract as text, keyed by its path relative to this file. */
const backendContractFiles: Readonly<Record<string, unknown>> = import.meta.glob(
  "../../../contracts/backend.openapi.yaml",
  { eager: true, import: "default", query: "?raw" },
);

/** Every schema file as text, keyed by its path relative to this file. */
const schemaFiles: Readonly<Record<string, unknown>> = import.meta.glob(
  "../../../contracts/schemas/*.yaml",
  { eager: true, import: "default", query: "?raw" },
);

/**
 * Read a schema file of the contract.
 *
 * @param name - The schema name: the file name without `.yaml`.
 * @returns The text of the file.
 * @throws Error when the file does not exist.
 */
export function readContractSchema(name: string): string {
  const file = schemaFiles[`${SCHEMAS_PATH_PREFIX}${name}.yaml`];
  if (typeof file !== "string") {
    throw new Error(`No schema in contracts/schemas/${name}.yaml.`);
  }
  return file;
}

/**
 * Read one schema of `components.schemas` in contracts/backend.openapi.yaml.
 *
 * @param name - The schema name, such as `Password`.
 * @returns The text of the schema: its name line and every line indented below it.
 * @throws Error when the contract has no such schema.
 */
export function readBackendSchema(name: string): string {
  const backendContract = backendContractFiles[BACKEND_CONTRACT_PATH];
  if (typeof backendContract !== "string") {
    throw new Error("No contract in contracts/backend.openapi.yaml.");
  }
  const lines = backendContract.split("\n");
  const start = lines.indexOf(`${SCHEMA_NAME_INDENT}${name}:`);
  if (start === -1) {
    throw new Error(`No schema ${name} in contracts/backend.openapi.yaml.`);
  }
  const end = lines.findIndex(
    (line, index) =>
      index > start && line.trim() !== "" && !line.startsWith(`${SCHEMA_NAME_INDENT} `),
  );
  return `${lines.slice(start, end === -1 ? undefined : end).join("\n")}\n`;
}
