import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getCurrentSessionRoute, listShopProductsRoute } from "@/test/backend-routes";
import {
  countExampleItems,
  MAX_PAGE_LIMIT,
  readExampleItemPageWith,
  readFullPageOfExampleItem,
} from "@/test/contract-examples";
import { createFakeBackend, exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { renderApp } from "@/test/render-app";

/**
 * Open Products as a customer, with the given answers to `listShopProducts`.
 *
 * @param answers - The answers of the product list, in order.
 * @returns The rendered app.
 */
function openProducts(...answers: FakeAnswer[]) {
  const backend = createFakeBackend();
  backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
  backend.answer(listShopProductsRoute, ...answers);
  return renderApp({ path: "/shop", backend });
}

/**
 * Read the product names in the grid, once the products are shown.
 *
 * @returns The names, in order.
 */
async function readProductNames(): Promise<(string | null)[]> {
  const links = await waitFor(() =>
    within(screen.getByRole("list", { name: "Products" })).getAllByRole("link"),
  );
  return links.map((link) => link.textContent);
}

describe("ProductsPage", () => {
  it("shows placeholder cards while the first page loads (UI-24)", async () => {
    openProducts({ kind: "no_answer" });

    expect(await screen.findByText("Loading products…")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Products" })).toBeVisible();
  });

  it("shows the products of the first page with links, categories, and prices", async () => {
    openProducts(exampleAnswer(200, "listShopProducts", "first-page"));

    expect(await readProductNames()).toEqual(["Desk lamp", "Notebook set"]);
    expect(screen.getByRole("link", { name: "Desk lamp" })).toHaveAttribute(
      "href",
      "/shop/products/PRD-1001",
    );
    expect(screen.getByText("$24.50")).toBeVisible();
    expect(screen.getByText("Home office")).toBeVisible();
  });

  it("loads the next page with next_cursor and stops at the last page (CON-14)", async () => {
    const { user, backend } = openProducts(
      exampleAnswer(200, "listShopProducts", "first-page"),
      exampleAnswer(200, "listShopProducts", "last-page"),
    );
    await readProductNames();

    await user.click(screen.getByRole("button", { name: "Show more products" }));

    await waitFor(async () => {
      expect(await readProductNames()).toEqual([
        "Desk lamp",
        "Notebook set",
        "Running shoes",
        "Wireless headphones",
      ]);
    });
    const cursors = backend
      .requestsTo(listShopProductsRoute)
      .map((request) => request.searchParams.get("cursor"));
    expect(cursors).toEqual([null, "eyJwIjoyfQ"]);
    expect(screen.queryByRole("button", { name: "Show more products" })).not.toBeInTheDocument();
  });

  it("shows the largest page and the page after it without a duplicate or a lost item", async () => {
    const fullPage = readFullPageOfExampleItem(
      { folder: "listShopProducts", name: "first-page", index: 0 },
      "product_id",
    );
    const { user } = openProducts(
      { kind: "body", status: 200, body: fullPage },
      exampleAnswer(200, "listShopProducts", "last-page"),
    );
    expect(await readProductNames()).toHaveLength(MAX_PAGE_LIMIT);

    await user.click(screen.getByRole("button", { name: "Show more products" }));

    await waitFor(async () => {
      expect(await readProductNames()).toHaveLength(
        MAX_PAGE_LIMIT + countExampleItems("listShopProducts", "last-page"),
      );
    });
    const hrefs = within(screen.getByRole("list", { name: "Products" }))
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("shows the error state for a product of the wrong shape, never a broken link", async () => {
    const pageWithoutId = readExampleItemPageWith(
      { folder: "listShopProducts", name: "first-page", index: 0 },
      { product_id: undefined },
    );
    openProducts({ kind: "body", status: 200, body: pageWithoutId });

    expect(
      await screen.findByRole("heading", { name: "Products could not be loaded" }),
    ).toBeVisible();
    expect(screen.queryByRole("list", { name: "Products" })).not.toBeInTheDocument();
  });

  it("hides Show more products when the first page is the last", async () => {
    openProducts(exampleAnswer(200, "listShopProducts", "last-page"));

    await readProductNames();

    expect(screen.queryByRole("button", { name: "Show more products" })).not.toBeInTheDocument();
  });

  it("says that there is no product when the catalog is empty", async () => {
    openProducts(exampleAnswer(200, "listShopProducts", "empty"));

    expect(
      await screen.findByRole("heading", { level: 2, name: "No products to show." }),
    ).toBeVisible();
  });
});

describe("ProductsPage, failures", () => {
  it("shows the permission-denied state with Sign out for another role (403)", async () => {
    openProducts(exampleAnswer(403, "problems", "forbidden-role"));

    expect(
      await screen.findByRole("heading", { level: 1, name: "The shop is for customer accounts" }),
    ).toBeVisible();
    expect(
      within(screen.getByRole("main")).getByRole("button", { name: "Sign out" }),
    ).toBeVisible();
    expect(screen.getByText("b7ad6b7169203331b7ad6b7169203331")).toBeVisible();
  });

  it("shows an error with Try again and loads again", async () => {
    const { user } = openProducts(
      exampleAnswer(503, "problems", "not-ready"),
      exampleAnswer(200, "listShopProducts", "last-page"),
    );

    expect(
      await screen.findByRole("heading", { level: 1, name: "Products could not be loaded" }),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await readProductNames()).toEqual(["Running shoes", "Wireless headphones"]);
  });

  it("keeps the products shown and offers the button again when the next page fails", async () => {
    const { user } = openProducts(exampleAnswer(200, "listShopProducts", "first-page"), {
      kind: "network_error",
    });
    await readProductNames();

    await user.click(screen.getByRole("button", { name: "Show more products" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "More products could not be loaded. The server could not be reached.",
    );
    expect(await readProductNames()).toEqual(["Desk lamp", "Notebook set"]);
    expect(screen.getByRole("button", { name: "Show more products" })).toBeEnabled();
  });

  it("disables Show more products while the next page loads, so a double click loads it once", async () => {
    const { user, backend } = openProducts(exampleAnswer(200, "listShopProducts", "first-page"), {
      kind: "no_answer",
    });
    await readProductNames();

    await user.dblClick(screen.getByRole("button", { name: "Show more products" }));

    expect(await screen.findByRole("button", { name: "Loading…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(backend.requestsTo(listShopProductsRoute)).toHaveLength(2);
  });
});
