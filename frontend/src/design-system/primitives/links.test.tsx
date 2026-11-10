import { screen } from "@testing-library/react";
import { render } from "@testing-library/react";
import { LayoutGrid } from "lucide-react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { NavItem } from "@/design-system/primitives/nav-item";
import { TextLink } from "@/design-system/primitives/text-link";
import { renderUi } from "@/test/render-app";

describe("TextLink", () => {
  it.each(["default", "strong"] as const)("is a %s link to its path", (emphasis) => {
    renderUi(
      <TextLink to="/shop/products/PRD-1002" emphasis={emphasis}>
        Wireless headphones
      </TextLink>,
    );

    expect(screen.getByRole("link", { name: "Wireless headphones" })).toHaveAttribute(
      "href",
      "/shop/products/PRD-1002",
    );
  });
});

describe("NavItem", () => {
  it("marks the entry of the open section as the current page (UI-11)", () => {
    render(
      <MemoryRouter initialEntries={["/shop/orders/ORD-1"]}>
        <NavItem to="/shop/orders" icon={LayoutGrid}>
          My orders
        </NavItem>
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "My orders" })).toHaveAttribute("aria-current", "page");
  });

  it("marks an exact-match entry only on its own path", () => {
    render(
      <MemoryRouter initialEntries={["/shop/orders"]}>
        <NavItem to="/shop" icon={LayoutGrid} isExactMatch>
          Products
        </NavItem>
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Products" })).not.toHaveAttribute("aria-current");
  });
});
