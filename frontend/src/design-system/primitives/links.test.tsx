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

  it("marks an exact-path entry on its own path", () => {
    render(
      <MemoryRouter initialEntries={["/shop"]}>
        <NavItem to="/shop" icon={LayoutGrid} current={{ by: "exact-path" }}>
          Products
        </NavItem>
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Products" })).toHaveAttribute("aria-current", "page");
  });

  it("does not mark an exact-path entry on a path below it", () => {
    render(
      <MemoryRouter initialEntries={["/shop/orders"]}>
        <NavItem to="/shop" icon={LayoutGrid} current={{ by: "exact-path" }}>
          Products
        </NavItem>
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Products" })).not.toHaveAttribute("aria-current");
  });

  it("is not current on a path below it when the area says so", () => {
    render(
      <MemoryRouter initialEntries={["/console/reports"]}>
        <NavItem to="/console" icon={LayoutGrid} current={{ by: "area", isCurrent: false }}>
          Tickets
        </NavItem>
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: "Tickets" });
    expect(link).not.toHaveAttribute("aria-current");
    expect(link).not.toHaveClass("bg-background");
  });

  it("is current on another path when the area says so", () => {
    render(
      <MemoryRouter initialEntries={["/console/tickets/TCK-1045"]}>
        <NavItem to="/console" icon={LayoutGrid} current={{ by: "area", isCurrent: true }}>
          Tickets
        </NavItem>
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: "Tickets" });
    expect(link).toHaveAttribute("aria-current", "page");
    expect(link).toHaveAttribute("href", "/console");
    expect(link).toHaveClass("bg-background");
  });
});
