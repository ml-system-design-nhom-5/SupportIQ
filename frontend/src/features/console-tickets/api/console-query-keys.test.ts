import { describe, expect, it } from "vitest";

import { consoleQueryKeys } from "@/features/console-tickets/api/console-query-keys";

describe("consoleQueryKeys", () => {
  it("puts every queue under one prefix, so one invalidation reloads them all (TS-19)", () => {
    expect(consoleQueryKeys.queues()).toEqual(["console-tickets", "queues"]);
    expect(consoleQueryKeys.queue("open")).toEqual(["console-tickets", "queues", "open"]);
    expect(consoleQueryKeys.queue("closed")).toEqual(["console-tickets", "queues", "closed"]);
  });

  it("builds the keys of a workspace and of a KB document version under the feature's root key", () => {
    expect(consoleQueryKeys.workspace("TCK-1042")).toEqual([
      "console-tickets",
      "workspaces",
      "TCK-1042",
    ]);
    expect(consoleQueryKeys.kbDocumentVersion("SAMPLE-REFUND-001", "1.0")).toEqual([
      "console-tickets",
      "kb-document-versions",
      "SAMPLE-REFUND-001",
      "1.0",
    ]);
  });
});

describe("consoleQueryKeys.sendReply", () => {
  it("is a mutation key outside the idempotent writes, so Send reply never retries (TS-29)", () => {
    expect(consoleQueryKeys.sendReply("TCK-1042")).toEqual([
      "console-tickets",
      "send-reply",
      "TCK-1042",
    ]);
  });
});
