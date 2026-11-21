import { readdirSync, readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { onRequest as healthRoute } from "../functions/health/[[path]].ts";
import { onRequest as v1Route } from "../functions/v1/[[path]].ts";
import { onRequest } from "./ingress.ts";

/** The folder of the Pages Function routes. */
const functionsFolder = new URL("../functions/", import.meta.url);

/** `_routes.json`, which Vite copies from `public/` to the root of the build. */
const routesFile = new URL("../public/_routes.json", import.meta.url);

describe("The routes of the ingress (ADR-0016, statement 2)", () => {
  it("sends exactly /v1/* and /health/* to the Function, so static files never invoke it", () => {
    const routes: unknown = JSON.parse(readFileSync(routesFile, "utf8"));

    expect(routes).toEqual({ version: 1, include: ["/v1/*", "/health/*"], exclude: [] });
  });

  it("has exactly the route folders of _routes.json, so a build without it routes the same", () => {
    const entries = readdirSync(functionsFolder, { withFileTypes: true });

    // No file at the root of functions/: a root catch-all would also take the static files.
    expect(entries.filter((entry) => !entry.isDirectory())).toEqual([]);
    expect(entries.map((entry) => `/${entry.name}/*`).toSorted()).toEqual(["/health/*", "/v1/*"]);
  });

  it("makes each route the ingress itself", () => {
    expect(v1Route).toBe(onRequest);
    expect(healthRoute).toBe(onRequest);
  });
});
