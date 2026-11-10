import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getCurrentSessionRoute, getShopProductRoute } from "@/test/backend-routes";
import { createFakeBackend, exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { renderApp } from "@/test/render-app";

/**
 * Open a product page as a customer.
 *
 * @param answer - What `getShopProduct` answers.
 * @returns The rendered app.
 */
function openProduct(answer: FakeAnswer) {
  const backend = createFakeBackend();
  backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
  backend.answer(getShopProductRoute, answer);
  return renderApp({ path: "/shop/products/PRD-1002", backend });
}

describe("ProductPage", () => {
  it("shows the product's details under the path back to Products", async () => {
    const { backend } = openProduct(exampleAnswer(200, "getShopProduct", "found"));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Wireless headphones" }),
    ).toBeVisible();
    expect(screen.getByText("Audio")).toBeVisible();
    expect(screen.getByText("$89.00")).toBeVisible();
    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(breadcrumb).getByRole("link", { name: "Products" })).toHaveAttribute(
      "href",
      "/shop",
    );
    expect(backend.requestsTo(getShopProductRoute)[0]?.path).toBe("/v1/shop/products/PRD-1002");
  });

  it("shows skeletons while the product loads", async () => {
    openProduct({ kind: "no_answer" });

    expect(await screen.findByText("Loading the product…")).toBeInTheDocument();
  });

  it("shows the not-found state with Back to Products (404)", async () => {
    openProduct(exampleAnswer(404, "problems", "not-found"));

    expect(
      await screen.findByRole("heading", { level: 1, name: "This product was not found" }),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Back to Products" })).toHaveAttribute("href", "/shop");
  });

  it("shows the permission-denied state for another role (403)", async () => {
    openProduct(exampleAnswer(403, "problems", "forbidden-role"));

    expect(
      await screen.findByRole("heading", { level: 1, name: "The shop is for customer accounts" }),
    ).toBeVisible();
  });

  it("shows the error state for an ingress failure", async () => {
    openProduct({ kind: "ingress", status: 502 });

    expect(
      await screen.findByRole("heading", { level: 1, name: "This product could not be loaded" }),
    ).toBeVisible();
    expect(
      screen.getByText("The service is not available right now. Try again in a moment."),
    ).toBeVisible();
  });
});
