import fc from "fast-check";
import { describe, expect, it } from "vitest";

import { collectPageItems } from "@/features/backend-requests/model/collect-pages";

const getId = (item: Item) => item.id;

const first: Item = { id: "a", label: "first" };

const second: Item = { id: "b", label: "second" };

const third: Item = { id: "c", label: "third" };

/** TEST-14: a property test runs the same inputs on every run. */
const PROPERTY_SEED = 20261107;

type Item = { readonly id: string; readonly label: string };

describe("collectPageItems", () => {
  it("keeps every item exactly once, in the order first seen, for any pages (TEST-13)", () => {
    fc.assert(
      fc.property(fc.array(fc.array(fc.string())), (pages) => {
        expect(collectPageItems(pages, (id) => id)).toEqual([...new Set(pages.flat())]);
      }),
      { seed: PROPERTY_SEED },
    );
  });

  it("returns an empty list for no page", () => {
    expect(collectPageItems([], getId)).toEqual([]);
  });

  it("returns an empty list for one empty page", () => {
    expect(collectPageItems([[]], getId)).toEqual([]);
  });

  it("returns the items of one page in order", () => {
    expect(collectPageItems([[first, second]], getId)).toEqual([first, second]);
  });

  it("joins the pages in page order without losing an item", () => {
    expect(collectPageItems([[first], [second, third]], getId)).toEqual([first, second, third]);
  });

  it("keeps the first occurrence of an item that two pages hold", () => {
    const refetched: Item = { id: "a", label: "refetched" };

    expect(
      collectPageItems(
        [
          [first, second],
          [refetched, third],
        ],
        getId,
      ),
    ).toEqual([first, second, third]);
  });
});
