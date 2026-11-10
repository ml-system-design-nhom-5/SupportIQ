import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PageHeader } from "@/design-system/components/page-header";
import { Button } from "@/design-system/primitives/button";
import { renderUi } from "@/test/render-app";

describe("PageHeader", () => {
  it("shows the screen title as the h1, with its meta and action", () => {
    renderUi(
      <PageHeader
        title="Order ORD-20931"
        meta="Placed 2 Oct 2026"
        action={<Button>Contact support</Button>}
      />,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Order ORD-20931" })).toBeVisible();
    expect(screen.getByText("Placed 2 Oct 2026")).toBeVisible();
    expect(screen.getByRole("button", { name: "Contact support" })).toBeVisible();
  });

  it("can show only the title", () => {
    renderUi(<PageHeader title="My orders" />);

    expect(screen.getByRole("heading", { level: 1, name: "My orders" })).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
