import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RowList } from "@/design-system/components/row-list";
import { RowListItem } from "@/design-system/components/row-list-item";
import { renderUi } from "@/test/render-app";

describe("RowList and RowListItem", () => {
  it("is a named list whose rows are links to their pages", () => {
    renderUi(
      <RowList label="Your orders">
        <RowListItem to="/shop/orders/ORD-20990" trailing="$42.50">
          Order ORD-20990
        </RowListItem>
        <RowListItem to="/shop/orders/ORD-20955">Order ORD-20955</RowListItem>
      </RowList>,
    );

    const list = screen.getByRole("list", { name: "Your orders" });
    const links = within(list).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/shop/orders/ORD-20990",
      "/shop/orders/ORD-20955",
    ]);
    expect(links[0]).toHaveTextContent("Order ORD-20990$42.50");
  });
});
