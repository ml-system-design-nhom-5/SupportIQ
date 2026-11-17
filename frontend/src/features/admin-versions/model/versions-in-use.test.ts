import { describe, expect, it } from "vitest";

import {
  buildAssetVersionRows,
  buildVersionBlock,
  toAiServiceStatus,
  toVersionsInUse,
  type VersionsInUse,
} from "@/features/admin-versions/model/versions-in-use";
import { readExampleWith, readOperationExample, withoutMembers } from "@/test/contract-examples";
import { readBackendSchema, readEnumValues } from "@/test/contract-schemas";

/** The body of the example `ai-service-available`. */
const availableBody = readOperationExample("getAdminVersions", 200, "ai-service-available");

/** The body of the example `ai-service-unavailable`. */
const unavailableBody = readOperationExample("getAdminVersions", 200, "ai-service-unavailable");

/** The versions of the example `ai-service-available`. */
const availableVersions: VersionsInUse = {
  backendVersion: "880b33a",
  aiService: {
    status: "available",
    assetVersions: {
      releaseId: "release-2026-11-12-sample",
      modelVersion: "intent-model-sample-1",
      kbVersion: "kb-sample-1",
      mappingVersion: "mapping-sample-1",
      promptVersion: "prompts-sample-1",
      routingVersion: "routing-sample-1",
      indexVersion: "index-sample-1",
    },
  },
  rawStatus: "available",
};

/** The versions of the example `ai-service-unavailable`. */
const unavailableVersions: VersionsInUse = {
  backendVersion: "880b33a",
  aiService: { status: "unavailable" },
  rawStatus: "unavailable",
};

/** Bodies that each lack one member that the contract requires, or that the status requires. */
const bodiesWithoutAMember: readonly (readonly [string, unknown])[] = [
  ["backend_version", withoutMembers(availableBody, ["backend_version"])],
  ["ai_service_status", withoutMembers(unavailableBody, ["ai_service_status"])],
  ["ai_service_versions", withoutMembers(availableBody, ["ai_service_versions"])],
  [
    "kb_version",
    readExampleWith("getAdminVersions", "ai-service-available", {
      ai_service_versions: readExampleWith("getAssetVersions", "loaded", { kb_version: null }),
    }),
  ],
];

describe("toVersionsInUse", () => {
  it("maps the versions of an available ai-service and the build of backend", () => {
    expect(toVersionsInUse(availableBody)).toEqual(availableVersions);
  });

  it("maps an unavailable ai-service without versions, with the build of backend", () => {
    expect(toVersionsInUse(unavailableBody)).toEqual(unavailableVersions);
  });

  it("treats a status that this version does not know as unavailable (CON-22)", () => {
    const body = readExampleWith("getAdminVersions", "ai-service-available", {
      ai_service_status: "a_later_status",
    });

    expect(Reflect.apply(toVersionsInUse, undefined, [body])).toEqual({
      ...unavailableVersions,
      rawStatus: "a_later_status",
    });
  });
});

describe("buildVersionBlock (admin UI design, Developer details in the admin area)", () => {
  it("lists the build, the status, and every field of ai_service_versions", () => {
    expect(buildVersionBlock(availableVersions)).toBe(
      [
        "backend_version: 880b33a",
        "ai_service_status: available",
        "release_id: release-2026-11-12-sample",
        "model_version: intent-model-sample-1",
        "kb_version: kb-sample-1",
        "mapping_version: mapping-sample-1",
        "prompt_version: prompts-sample-1",
        "routing_version: routing-sample-1",
        "index_version: index-sample-1",
      ].join("\n"),
    );
  });

  it("lists the raw status without versions while ai-service is not available", () => {
    expect(buildVersionBlock({ ...unavailableVersions, rawStatus: "a_later_status" })).toBe(
      "backend_version: 880b33a\nai_service_status: a_later_status",
    );
  });
});

describe("toVersionsInUse with a body of the wrong shape", () => {
  it.each(bodiesWithoutAMember)(
    "stops at a body without the required member %s (CODE-32)",
    (member, body) => {
      expect(() => {
        Reflect.apply(toVersionsInUse, undefined, [body]);
      }).toThrow(`The response has no ${member}.`);
    },
  );
});

describe("toAiServiceStatus", () => {
  it.each(readEnumValues(readBackendSchema("AiServiceStatus")))(
    "keeps the status %s of the contract",
    (status) => {
      expect(toAiServiceStatus(status)).toBe(status);
    },
  );

  it.each(["a_later_status", "Available", ""])("maps %j to unavailable (CON-22)", (status) => {
    expect(toAiServiceStatus(status)).toBe("unavailable");
  });
});

describe("buildAssetVersionRows", () => {
  it("lists each asset with its version, in the order of AssetVersions", () => {
    expect(buildAssetVersionRows(availableVersions.aiService)).toEqual([
      { term: "Release", version: "release-2026-11-12-sample" },
      { term: "Model artifact", version: "intent-model-sample-1" },
      { term: "KB", version: "kb-sample-1" },
      { term: "Document-to-intent mapping", version: "mapping-sample-1" },
      { term: "Prompts", version: "prompts-sample-1" },
      { term: "Routing configuration", version: "routing-sample-1" },
      { term: "Retrieval index", version: "index-sample-1" },
    ]);
  });

  it("lists each asset without a version while ai-service is unavailable", () => {
    expect(buildAssetVersionRows(unavailableVersions.aiService)).toEqual([
      { term: "Release" },
      { term: "Model artifact" },
      { term: "KB" },
      { term: "Document-to-intent mapping" },
      { term: "Prompts" },
      { term: "Routing configuration" },
      { term: "Retrieval index" },
    ]);
  });
});
