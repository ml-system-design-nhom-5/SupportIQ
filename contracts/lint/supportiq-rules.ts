// Custom Redocly lint rules for the contract rules that the built-in rules do not cover
// (RULE-03). Each rule names the rule ID it checks. See contracts/README.md.
import { existsSync, readdirSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";

const ROLES: ReadonlySet<string> = new Set(["customer", "staff", "manager", "admin"]);
const CAMEL_CASE = /^[a-z][a-z0-9]*(?:[A-Z][a-z0-9]+)*$/;
const SNAKE_CASE = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/;
const DATA_CLASS =
  /Data class: (?:(?:Public|Internal|Confidential|Secret)\b|that of the property holding this value\.)/;
const PROBLEM_TYPE = /^urn:supportiq:problem:[a-z0-9]+(?:-[a-z0-9]+)*$/;
// CON-18: the timestamps whose glossary name has no `_at` suffix.
const TIMESTAMP_TERMS: ReadonlySet<string> = new Set(["as_of"]);
const CLIENT_ERROR_STATUS = /^4(?:\d\d|XX)$/;
// The schema of a parameter or a header is described by the parameter or header itself.
const PARAMETER_OR_HEADER_SCHEMA = /\/(?:parameters|headers)\/[^/]+\/schema$/;
const SHARED_RESPONSE_POINTER = "#/components/responses/";
const SESSION_SCHEME = "sessionCookie";
const SHARED_EXAMPLE_FOLDER = "problems";

// The parts of the Redocly visitor API that these rules use. Redocly CLI ships no typings.
interface Location {
  readonly source: { readonly absoluteRef: string };
  readonly pointer: string;
  readonly absolutePointer: string;
  child(path: string | number | readonly (string | number)[]): Location;
  key(): Location;
}

interface Context {
  readonly location: Location;
  report(problem: { readonly message: string; readonly location?: Location }): void;
  resolve(node: unknown): { readonly node: unknown };
}

interface Parents {
  readonly Operation?: Node;
}

type Node = Readonly<Record<string, unknown>>;
type Visit = (node: Node, ctx: Context, parents: Parents) => void;
type Visitor = Readonly<Record<string, Visit | Readonly<Record<string, Visit>>>>;

interface ExampleUse {
  readonly checked: Set<string>;
  readonly used: Set<string>;
  readonly operationIds: Set<string>;
}

interface ExampleSite {
  readonly ctx: Context;
  readonly location: Location;
  readonly use: ExampleUse;
}

export default function supportiqRules(): object {
  return {
    id: "supportiq",
    rules: {
      oas3: {
        "operation-id-camel-case": operationIdCamelCase,
        "operation-documented": operationDocumented,
        "operation-security": operationSecurity,
        "operation-4xx-response": operation4xxResponse,
        "schema-description": schemaDescription,
        "request-body-closed": requestBodyClosed,
        "property-naming": propertyNaming,
        "problem-type-urn": problemTypeUrn,
        "limit-maximum": limitMaximum,
        "response-examples": responseExamples,
      },
    },
  };
}

// CON-04: every operationId is camelCase.
function operationIdCamelCase(): Visitor {
  return {
    Operation(operation, ctx) {
      const id = operation.operationId;
      if (typeof id !== "string" || !CAMEL_CASE.test(id)) {
        const location = ctx.location.child("operationId");
        ctx.report({ message: "operationId must be camelCase (CON-04).", location });
      }
    },
  };
}

// CON-04: every operation has a summary and a description.
function operationDocumented(): Visitor {
  return {
    Operation(operation, ctx) {
      for (const field of ["summary", "description"]) {
        if (!hasText(operation[field])) {
          ctx.report({
            message: `Operation must have a ${field} (CON-04).`,
            location: ctx.location,
          });
        }
      }
    },
  };
}

// CON-04, SEC-16: every operation declares its own security requirement, and every operation
// that needs a session lists the roles that may call it in x-supportiq-roles.
function operationSecurity(): Visitor {
  return {
    Operation(operation, ctx) {
      const security = operation.security;
      const message = Array.isArray(security)
        ? rolesProblem(needsSession(security), operation["x-supportiq-roles"])
        : "Operation must declare `security`, `[]` when no session is needed (CON-04).";
      if (message !== undefined) {
        ctx.report({ message, location: ctx.location });
      }
    },
  };
}

// CON-06, ERR-18: every operation documents a 4xx outcome, except an operation that needs no
// session and takes no input other than `traceparent`, such as a health check.
function operation4xxResponse(): Visitor {
  return {
    Operation(operation, ctx) {
      const statuses = Object.keys(isNode(operation.responses) ? operation.responses : {});
      const hasClientError = statuses.some((status) => CLIENT_ERROR_STATUS.test(status));
      if (!hasClientError && !takesNoInput(operation, ctx)) {
        const location = ctx.location.child("responses");
        ctx.report({
          message: "Operation must have at least one 4xx response (CON-06).",
          location,
        });
      }
    },
  };
}

// CON-05, SEC-03: every schema and every property has a description that states a data class.
function schemaDescription(): Visitor {
  return {
    Schema(schema, ctx) {
      if (!PARAMETER_OR_HEADER_SCHEMA.test(ctx.location.pointer)) {
        checkDescription(schema.description, ctx, ctx.location, "Schema");
      }
      for (const [name, property] of entries(schema.properties)) {
        const own = isNode(property) ? property.description : undefined;
        const location = ctx.location.child(["properties", name]);
        checkDescription(own, ctx, location, `Property \`${name}\``);
      }
    },
    Parameter(parameter, ctx) {
      const what = `Parameter \`${String(parameter.name)}\``;
      checkDescription(parameter.description, ctx, ctx.location, what);
    },
    Header(header, ctx) {
      checkDescription(header.description, ctx, ctx.location, "Header");
    },
  };
}

// CON-07: request bodies, and every object nested in them, set additionalProperties: false.
function requestBodyClosed(): Visitor {
  return {
    RequestBody(body, ctx) {
      for (const [mediaType, media] of entries(body.content)) {
        const schema = isNode(media) ? media.schema : undefined;
        checkClosed(schema, ctx, ctx.location.child(["content", mediaType, "schema"]));
      }
    },
  };
}

// CON-18: snake_case names, and the suffixes and prefixes of the naming table.
function propertyNaming(): Visitor {
  return {
    Schema(schema, ctx) {
      for (const [name, property] of entries(schema.properties)) {
        const location = ctx.location.child(["properties", name]).key();
        for (const message of namingProblems(name, resolved(ctx, property))) {
          ctx.report({ message, location });
        }
      }
    },
    Parameter(parameter, ctx) {
      const name = parameter.name;
      const inUrl = parameter.in === "query" || parameter.in === "path";
      if (inUrl && typeof name === "string" && !SNAKE_CASE.test(name)) {
        const location = ctx.location.child("name");
        ctx.report({ message: `Parameter \`${name}\` must be snake_case (CON-18).`, location });
      }
    },
  };
}

// CON-12: every problem type in the ProblemDetails registry is urn:supportiq:problem:<kebab-case>.
function problemTypeUrn(): Visitor {
  return {
    Components(components, ctx) {
      const problem = resolved(ctx, resolved(ctx, components.schemas).ProblemDetails);
      const types = resolved(ctx, resolved(ctx, problem.properties).type).enum;
      if (!Array.isArray(types) || types.length === 0) {
        const message = "ProblemDetails must define `type` as an enum of problem types (CON-12).";
        ctx.report({ message, location: ctx.location });
        return;
      }
      for (const type of types.filter((value) => !isProblemType(value))) {
        const message = `Problem type \`${String(type)}\` must match ${PROBLEM_TYPE.source} (CON-12).`;
        ctx.report({ message, location: ctx.location });
      }
    },
  };
}

// CON-14: every `limit` parameter is an integer with a documented maximum.
function limitMaximum(): Visitor {
  return {
    Parameter(parameter, ctx) {
      const schema = resolved(ctx, parameter.schema);
      const bounded = schema.type === "integer" && typeof schema.maximum === "number";
      if (parameter.name === "limit" && !bounded) {
        const location = ctx.location.child("schema");
        ctx.report({ message: "`limit` must be an integer with a `maximum` (CON-14).", location });
      }
    },
  };
}

// CON-06: every response with a body has at least one example, and every example is a file that
// Prism and the example validation both read: examples/<operationId>/<name>.json for an
// operation's own response, examples/problems/<name>.json for a shared response. Every file in an
// operation's folder is used by that operation.
function responseExamples(): Visitor {
  const use: ExampleUse = { checked: new Set(), used: new Set(), operationIds: new Set() };
  return {
    Operation: {
      Response(response, ctx, parents) {
        const operationId = String(parents.Operation?.operationId);
        use.operationIds.add(operationId);
        if (!use.checked.has(ctx.location.absolutePointer)) {
          use.checked.add(ctx.location.absolutePointer);
          checkResponseExamples(response, ctx, operationId, use);
        }
      },
    },
    Root: {
      leave(_root, ctx) {
        reportUnusedExamples(ctx, use);
      },
    },
  };
}

function isNode(value: unknown): value is Node {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isProblemType(value: unknown): boolean {
  return typeof value === "string" && PROBLEM_TYPE.test(value);
}

function entries(value: unknown): readonly [string, unknown][] {
  return isNode(value) ? Object.entries(value) : [];
}

function resolved(ctx: Context, value: unknown): Node {
  const node = ctx.resolve(value).node;
  return isNode(node) ? node : {};
}

function needsSession(security: readonly unknown[]): boolean {
  return security.some((requirement) => isNode(requirement) && SESSION_SCHEME in requirement);
}

function rolesProblem(withSession: boolean, roles: unknown): string | undefined {
  if (!withSession) {
    return roles === undefined
      ? undefined
      : "x-supportiq-roles applies only to operations that need a session.";
  }
  return isRoleList(roles)
    ? undefined
    : "x-supportiq-roles must list distinct roles among customer, staff, manager, admin (SEC-16).";
}

function isRoleList(roles: unknown): boolean {
  return (
    Array.isArray(roles) &&
    roles.length > 0 &&
    roles.every((role) => typeof role === "string" && ROLES.has(role)) &&
    new Set(roles).size === roles.length
  );
}

function takesNoInput(operation: Node, ctx: Context): boolean {
  const security = operation.security;
  const parameters: readonly unknown[] = Array.isArray(operation.parameters)
    ? operation.parameters
    : [];
  const onlyTraceparent = parameters.every((parameter) => {
    const node = resolved(ctx, parameter);
    return node.in === "header" && node.name === "traceparent";
  });
  const noSession = Array.isArray(security) && security.length === 0;
  return noSession && operation.requestBody === undefined && onlyTraceparent;
}

function checkDescription(
  description: unknown,
  ctx: Context,
  location: Location,
  what: string,
): void {
  if (!hasText(description)) {
    ctx.report({ message: `${what} must have its own description (CON-05).`, location });
  } else if (!DATA_CLASS.test(description)) {
    ctx.report({
      message: `${what} description must state "Data class: <class>." (SEC-03).`,
      location,
    });
  }
}

function checkClosed(schema: unknown, ctx: Context, location: Location): void {
  const node = resolved(ctx, schema);
  if (node.type === "array") {
    checkClosed(node.items, ctx, location.child("items"));
    return;
  }
  if (node.type !== "object") {
    return;
  }
  if (node.additionalProperties !== false) {
    const message = "Request body objects must set `additionalProperties: false` (CON-07).";
    ctx.report({ message, location });
  }
  for (const [name, property] of entries(node.properties)) {
    checkClosed(property, ctx, location.child(["properties", name]));
  }
}

function namingProblems(name: string, property: Node): readonly string[] {
  const type = property.type;
  const isTimestamp = property.format === "date-time";
  const hasTimestampName = name.endsWith("_at") || TIMESTAMP_TERMS.has(name);
  const checks: readonly [boolean, string][] = [
    [!SNAKE_CASE.test(name), "must be snake_case"],
    [
      type === "boolean" && !/^(?:is|has|can)_/.test(name),
      "is a boolean, so it must start with is_, has_, or can_",
    ],
    [
      isTimestamp !== hasTimestampName,
      "must end with _at exactly when it is a timestamp, or be as_of",
    ],
    [
      name.endsWith("_ms") && type !== "integer",
      "ends with _ms, so it must be an integer duration",
    ],
    [name.endsWith("_count") && type !== "integer", "ends with _count, so it must be an integer"],
    [name.endsWith("_id") && type !== "string", "ends with _id, so it must be a string"],
    [name.endsWith("_version") && type !== "string", "ends with _version, so it must be a string"],
  ];
  return checks
    .filter(([broken]) => broken)
    .map(([, rule]) => `Property \`${name}\` ${rule} (CON-18).`);
}

function checkResponseExamples(
  response: Node,
  ctx: Context,
  operationId: string,
  use: ExampleUse,
): void {
  const isShared = ctx.location.pointer.startsWith(SHARED_RESPONSE_POINTER);
  const folder = isShared ? SHARED_EXAMPLE_FOLDER : operationId;
  for (const [mediaType, media] of entries(response.content)) {
    const location = ctx.location.child(["content", mediaType]);
    const examples = isNode(media) ? entries(media.examples) : [];
    if (examples.length === 0) {
      const message = "Every response body needs at least one entry in `examples` (CON-06).";
      ctx.report({ message, location });
    }
    for (const [name, example] of examples) {
      checkExampleFile(name, example, folder, { ctx, location, use });
    }
  }
}

function checkExampleFile(name: string, example: unknown, folder: string, site: ExampleSite): void {
  const base = dirname(site.ctx.location.source.absoluteRef);
  const expected = join(base, "examples", folder, `${name}.json`);
  const ref = isNode(example) ? example.$ref : undefined;
  if (typeof ref === "string" && resolve(base, ref) === expected) {
    site.use.used.add(expected);
    return;
  }
  site.ctx.report({
    message: `Example \`${name}\` must be \`$ref: ./examples/${folder}/${name}.json\` (CON-06).`,
    location: site.location.child(["examples", name]),
  });
}

function reportUnusedExamples(ctx: Context, use: ExampleUse): void {
  const base = dirname(ctx.location.source.absoluteRef);
  for (const operationId of use.operationIds) {
    const folder = join(base, "examples", operationId);
    const files = existsSync(folder) ? readdirSync(folder).map((name) => join(folder, name)) : [];
    for (const file of files.filter((path) => !use.used.has(path))) {
      const message = `Example file examples/${operationId}/${basename(file)} is not used by ${operationId}.`;
      ctx.report({ message, location: ctx.location });
    }
  }
}
