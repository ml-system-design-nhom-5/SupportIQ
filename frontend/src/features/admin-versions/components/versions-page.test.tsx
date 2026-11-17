import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getAdminVersionsRoute } from "@/test/backend-routes";
import { readExampleWith, readOperationExample, withoutMembers } from "@/test/contract-examples";
import { exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import {
  openVersions,
  readVersionRows,
  type ShownVersion,
  versionsExample,
} from "@/test/versions-screen";

/** The rows of the ai-service panel for the example `ai-service-available`. */
const availableAssetRows: readonly ShownVersion[] = [
  { term: "Release", value: "release-2026-11-12-sample" },
  { term: "Model artifact", value: "intent-model-sample-1" },
  { term: "KB", value: "kb-sample-1" },
  { term: "Document-to-intent mapping", value: "mapping-sample-1" },
  { term: "Prompts", value: "prompts-sample-1" },
  { term: "Routing configuration", value: "routing-sample-1" },
  { term: "Retrieval index", value: "index-sample-1" },
];

/** The rows of the ai-service panel while its versions are unknown. */
const unknownAssetRows: readonly ShownVersion[] = [
  { term: "Release", value: "Unknown" },
  { term: "Model artifact", value: "Unknown" },
  { term: "KB", value: "Unknown" },
  { term: "Document-to-intent mapping", value: "Unknown" },
  { term: "Prompts", value: "Unknown" },
  { term: "Routing configuration", value: "Unknown" },
  { term: "Retrieval index", value: "Unknown" },
];

/** The row of the backend panel of both examples. */
const backendRows: readonly ShownVersion[] = [{ term: "Build", value: "880b33a" }];

/** Answers that say that `ai-service` cannot be reached. */
const unreachableCases: readonly (readonly [string, FakeAnswer])[] = [
  ["the unavailable status", versionsExample("ai-service-unavailable")],
  [
    "a status that this version does not know (CON-22)",
    {
      kind: "body",
      status: 200,
      body: readExampleWith("getAdminVersions", "ai-service-available", {
        ai_service_status: "a_later_status",
      }),
    },
  ],
];

/** Failures that show the load error without a trace ID. */
const failuresWithoutTrace: readonly (readonly [string, FakeAnswer])[] = [
  ["a lost connection", { kind: "network_error" }],
  ["an answer of the ingress", { kind: "ingress", status: 502 }],
  [
    "an available status without ai_service_versions (CODE-32)",
    {
      kind: "body",
      status: 200,
      body: withoutMembers(readOperationExample("getAdminVersions", 200, "ai-service-available"), [
        "ai_service_versions",
      ]),
    },
  ],
];

describe("VersionsPage, the versions in use", () => {
  it("shows the versions of ai-service with its status, and the build of backend", async () => {
    const { backend } = openVersions();

    expect(await readVersionRows("ai-service")).toEqual(availableAssetRows);
    expect(await readVersionRows("backend")).toEqual(backendRows);
    const aiService = screen.getByRole("region", { name: "ai-service" });
    expect(within(aiService).getByText("Available")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(backend.requestsTo(getAdminVersionsRoute)).toHaveLength(1);
  });

  it("says that the screen is read-only, offers no action, and names the browser tab", async () => {
    openVersions();

    await readVersionRows("backend");
    expect(screen.getByRole("heading", { level: 1, name: "Versions in use" })).toBeVisible();
    expect(
      screen.getByText("Read-only. Versions change only through the release process."),
    ).toBeVisible();
    expect(within(screen.getByRole("main")).queryByRole("button")).not.toBeInTheDocument();
    expect(document.title).toBe("Versions in use · SupportIQ Admin");
  });

  it("marks Versions as current in the navigation, and Accounts as not current", async () => {
    openVersions();

    const bar = await screen.findByRole("banner");
    expect(await within(bar).findByRole("link", { name: "Versions" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(bar).getByRole("link", { name: "Accounts" })).not.toHaveAttribute("aria-current");
  });
});

describe("VersionsPage when ai-service cannot be reached", () => {
  it.each(unreachableCases)(
    "shows the banner and Unknown versions after %s, and still the build of backend",
    async (_case, answer) => {
      openVersions({ versions: [answer] });

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "ai-service cannot be reached. Its versions are unknown. Reload this page later.",
      );
      expect(await readVersionRows("ai-service")).toEqual(unknownAssetRows);
      const aiService = screen.getByRole("region", { name: "ai-service" });
      expect(within(aiService).getByText("Unavailable")).toBeVisible();
      expect(await readVersionRows("backend")).toEqual(backendRows);
    },
  );
});

describe("VersionsPage, loading the versions", () => {
  it("shows skeleton rows below the header while the versions load (UI-24)", async () => {
    openVersions({ versions: [{ kind: "no_answer" }] });

    expect(await screen.findByText("Loading the versions…")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Versions in use" })).toBeVisible();
    expect(screen.queryByRole("region", { name: "ai-service" })).not.toBeInTheDocument();
  });

  it("shows the load error of a 5xx with the trace ID, and Try again loads again", async () => {
    const { user } = openVersions({
      versions: [
        exampleAnswer(500, "problems", "internal-error"),
        versionsExample("ai-service-available"),
      ],
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "The versions could not be loaded" }),
    ).toBeVisible();
    expect(screen.getByText(/Details: trace/)).toHaveTextContent(
      "319c0af7651916cd43dd8448eb211c80",
    );
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await readVersionRows("backend")).toEqual(backendRows);
  });

  it.each(failuresWithoutTrace)(
    "shows the load error with Try again after %s",
    async (_case, answer) => {
      openVersions({ versions: [answer] });

      expect(
        await screen.findByRole("heading", { level: 1, name: "The versions could not be loaded" }),
      ).toBeVisible();
      expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
      expect(screen.queryByText(/Details: trace/)).not.toBeInTheDocument();
    },
  );

  it("shows the permission-denied state with Sign out for another role (403)", async () => {
    openVersions({ versions: [exampleAnswer(403, "problems", "forbidden-role")] });

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "The admin area is for admin accounts",
      }),
    ).toBeVisible();
    expect(
      within(screen.getByRole("main")).getByRole("button", { name: "Sign out" }),
    ).toBeVisible();
  });
});
