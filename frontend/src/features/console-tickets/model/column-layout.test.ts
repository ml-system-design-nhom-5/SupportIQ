import { describe, expect, it } from "vitest";

import {
  buildColumnLayoutKey,
  parseColumnLayout,
} from "@/features/console-tickets/model/column-layout";

/** The layout of an account that never changed it. */
const defaultLayout = {
  inbox: { width: 272, isCollapsed: false },
  aiDetails: { width: 340, isCollapsed: false },
};

describe("buildColumnLayoutKey", () => {
  it("keeps the layout under the account ID", () => {
    expect(buildColumnLayoutKey("9a7d3e21")).toBe("supportiq.console-columns.9a7d3e21");
  });
});

describe("parseColumnLayout", () => {
  it("gives the default columns when nothing is stored", () => {
    expect(parseColumnLayout(undefined)).toEqual(defaultLayout);
  });

  it("reads a stored layout", () => {
    const stored = {
      inbox: { width: 320, isCollapsed: true },
      aiDetails: { width: 400, isCollapsed: false },
    };

    expect(parseColumnLayout(JSON.stringify(stored))).toEqual(stored);
  });

  it("gives the default columns when the stored text is not JSON", () => {
    expect(parseColumnLayout("{inbox")).toEqual(defaultLayout);
  });

  it.each(["null", "42", '"wide"', "[]"])("gives the default columns for the JSON %s", (text) => {
    expect(parseColumnLayout(text)).toEqual(defaultLayout);
  });

  it("brings a stored width outside its limits within them", () => {
    const stored = {
      inbox: { width: 999, isCollapsed: false },
      aiDetails: { width: 10, isCollapsed: false },
    };

    expect(parseColumnLayout(JSON.stringify(stored))).toEqual({
      inbox: { width: 400, isCollapsed: false },
      aiDetails: { width: 280, isCollapsed: false },
    });
  });

  it("gives the default of a field whose stored value has the wrong type", () => {
    const stored = { inbox: { width: "wide", isCollapsed: "yes" }, aiDetails: 5 };

    expect(parseColumnLayout(JSON.stringify(stored))).toEqual(defaultLayout);
  });
});
