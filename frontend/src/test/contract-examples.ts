import type { operations } from "@/api/generated/backend";

/**
 * The example files of contracts/examples/ as test fixtures (TEST-11, contracts/README.md,
 * Example files as test fixtures). Tests read the `value` of an example and never write a
 * `backend` response by hand.
 */

/** Every example file, keyed by its path relative to contracts/examples/. */
const exampleFiles: Readonly<Record<string, unknown>> = import.meta.glob(
  "../../../contracts/examples/**/*.json",
  { eager: true, import: "default" },
);

const EXAMPLES_PATH_PREFIX = "../../../contracts/examples/";

/** The largest `limit` of the contract, which is the most items a page can hold (CON-14). */
export const MAX_PAGE_LIMIT = 100;

/** The JSON body of one response of one operation, as the generated client types it. */
export type ResponseBody<
  Operation extends keyof operations,
  Status extends keyof operations[Operation]["responses"],
> = operations[Operation]["responses"][Status] extends {
  readonly content: { readonly "application/json": infer Body };
}
  ? Body
  : never;

/** The position of an item in the `items` of a page example. */
export type ExampleItem = {
  readonly folder: string;
  readonly name: string;
  readonly index: number;
};

/**
 * Read the `value` of an example file.
 *
 * @param folder - The operation ID, or `problems` for the shared error responses.
 * @param name - The example name: the file name without `.json`.
 * @returns The example body, exactly as the mock serves it.
 * @throws Error when the file does not exist or has no `value`.
 */
export function readExample(folder: string, name: string): unknown {
  const file = exampleFiles[`${EXAMPLES_PATH_PREFIX}${folder}/${name}.json`];
  if (typeof file !== "object" || file === null || !("value" in file)) {
    throw new Error(`No example value in contracts/examples/${folder}/${name}.json.`);
  }
  return file.value;
}

/**
 * Read a success example of an operation as the contract type of that response, for the tests of
 * model/ mappings. The contract checks validate every example against its schema
 * (contracts/README.md, Machine-checked rules), which makes this a validated boundary (TS-10).
 *
 * @param operation - The operation ID, which is also the example folder.
 * @param _status - The status of the response that the example belongs to; it selects the type.
 * @param name - The example name.
 * @returns The example body, typed as that response.
 */
export function readOperationExample<
  Operation extends keyof operations,
  Status extends keyof operations[Operation]["responses"],
>(operation: Operation, _status: Status, name: string): ResponseBody<Operation, Status> {
  // eslint-disable-next-line @typescript-eslint/consistent-type-assertions -- validated boundary: redocly lint validates each example against its schema (TS-10)
  return readExample(operation, name) as ResponseBody<Operation, Status>;
}

/**
 * Read an example body and replace some of its top-level members, for the cases that no example
 * covers yet: an enum value that a later contract version may add (CON-22), or a long text.
 *
 * @param folder - The operation ID, or `problems`.
 * @param name - The example name.
 * @param overrides - The members to replace.
 * @returns A copy of the example body with the overrides.
 */
export function readExampleWith(
  folder: string,
  name: string,
  overrides: Readonly<Record<string, unknown>>,
): unknown {
  const example = readExample(folder, name);
  if (typeof example !== "object" || example === null) {
    throw new Error(`contracts/examples/${folder}/${name}.json has no object value.`);
  }
  return { ...example, ...overrides };
}

/**
 * Count the items of a page example.
 *
 * @param folder - The operation ID.
 * @param name - The example name.
 * @returns How many items the page holds.
 */
export function countExampleItems(folder: string, name: string): number {
  return readExamplePageItems(folder, name).length;
}

/**
 * Build a one-item page from an item of a page example with some members replaced, for the cases
 * that no example covers yet, such as an enum value that a later contract version may add
 * (CON-22) or a very long message.
 *
 * @param item - Which item of which page example.
 * @param overrides - The members of the item to replace.
 * @returns A page body with that one item, without `next_cursor`.
 */
export function readExampleItemPageWith(
  item: ExampleItem,
  overrides: Readonly<Record<string, unknown>>,
): unknown {
  return { items: [{ ...readExampleItem(item), ...overrides }] };
}

/**
 * Build the largest page that the contract allows from one item of a page example, for the case
 * that no example covers: every item is a copy with its own ID, and another page follows.
 *
 * @param item - Which item of which page example.
 * @param idMember - The member that identifies an item, such as `order_id`.
 * @returns A page body with {@link MAX_PAGE_LIMIT} items and a `next_cursor`.
 */
export function readFullPageOfExampleItem(item: ExampleItem, idMember: string): unknown {
  const original = readExampleItem(item);
  return {
    items: Array.from({ length: MAX_PAGE_LIMIT }, (_unused, index) => ({
      ...original,
      [idMember]: `${idMember}-${String(index)}`,
    })),
    next_cursor: "next-page-after-a-full-page",
  };
}

/**
 * Read the items of a page example.
 *
 * @param folder - The operation ID.
 * @param name - The example name.
 * @returns The items, or an empty list for an example without items.
 */
function readExamplePageItems(folder: string, name: string): readonly unknown[] {
  const page = readExample(folder, name);
  const items = typeof page === "object" && page !== null && "items" in page ? page.items : [];
  return Array.isArray(items) ? items : [];
}

/**
 * Read one item of a page example.
 *
 * @param item - Which item of which page example.
 * @returns The item.
 * @throws Error when the example has no such item.
 */
function readExampleItem(item: ExampleItem): object {
  const original = readExamplePageItems(item.folder, item.name)[item.index];
  if (typeof original !== "object" || original === null) {
    throw new Error(
      `contracts/examples/${item.folder}/${item.name}.json has no item ${String(item.index)}.`,
    );
  }
  return original;
}

/**
 * Copy a body of an example without some of its optional members, for the cases that no example
 * covers yet, such as a ticket without a predicted intent.
 *
 * @param body - A body read with {@link readOperationExample}.
 * @param members - The members to leave out.
 * @returns The copy, typed without those members.
 */
export function withoutMembers<Body extends object, Member extends keyof Body>(
  body: Body,
  members: readonly Member[],
): Omit<Body, Member> {
  const copy = { ...body };
  for (const member of members) {
    Reflect.deleteProperty(copy, member);
  }
  return copy;
}
