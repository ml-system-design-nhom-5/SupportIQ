/**
 * The schema files of contracts/schemas/ as text, so that a unit test fails when the contract
 * changes a value that frontend repeats. Only unit tests use this file: the `unit` project of
 * vite.config.ts allows the folder.
 */

const SCHEMAS_PATH_PREFIX = "../../../contracts/schemas/";

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
