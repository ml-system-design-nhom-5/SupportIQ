import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProductCard } from "@/design-system/components/product-card";
import { ProductCardSkeleton } from "@/design-system/components/product-card-skeleton";
import { ProductDetails } from "@/design-system/components/product-details";
import { Grid } from "@/design-system/primitives/grid";
import { renderUi } from "@/test/render-app";

describe("ProductCard", () => {
  it("links the name to the product page and shows the category and the price", () => {
    renderUi(
      <Grid as="ul" label="Products">
        <ProductCard
          name="Desk lamp"
          category="Home office"
          price={{ amountMinor: 2450, currency: "USD" }}
          href="/shop/products/PRD-1001"
        />
      </Grid>,
    );

    const card = screen.getByRole("listitem");
    expect(within(card).getByRole("link", { name: "Desk lamp" })).toHaveAttribute(
      "href",
      "/shop/products/PRD-1001",
    );
    expect(within(card).getByText("Home office")).toBeVisible();
    expect(within(card).getByText("$24.50")).toBeVisible();
  });
});

describe("ProductCardSkeleton", () => {
  it("is hidden from assistive technology", () => {
    renderUi(
      <Grid as="ul" label="Products">
        <ProductCardSkeleton />
      </Grid>,
    );

    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });
});

describe("ProductDetails", () => {
  it("shows the name as the page heading, the price, the description, and the no-cart note", () => {
    renderUi(
      <ProductDetails
        name="Wireless headphones"
        category="Audio"
        price={{ amountMinor: 8900, currency: "USD" }}
        description="Over-ear headphones with a 30-hour battery."
      />,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Wireless headphones" })).toBeVisible();
    expect(screen.getByText("$89.00")).toBeVisible();
    expect(screen.getByText("Over-ear headphones with a 30-hour battery.")).toBeVisible();
    expect(
      screen.getByText("The demo shop has no cart. Questions about an order go through My orders."),
    ).toBeVisible();
  });
});
