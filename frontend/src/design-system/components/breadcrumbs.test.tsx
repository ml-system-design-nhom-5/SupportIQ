import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Breadcrumbs } from "@/design-system/components/breadcrumbs";
import { renderUi } from "@/test/render-app";

describe("Breadcrumbs", () => {
  it("links each earlier step and marks the last one as the current page", () => {
    renderUi(
      <Breadcrumbs
        steps={[
          { label: "My orders", to: "/shop/orders" },
          { label: "ORD-20931", isIdentifier: true },
        ]}
      />,
    );

    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "My orders" })).toHaveAttribute("href", "/shop/orders");
    expect(screen.getByText("ORD-20931")).toHaveAttribute("aria-current", "page");
  });

  it("shows a name as the current page", () => {
    renderUi(<Breadcrumbs steps={[{ label: "Products", to: "/shop" }, { label: "Desk lamp" }]} />);

    expect(screen.getByText("Desk lamp")).toHaveAttribute("aria-current", "page");
  });
});
