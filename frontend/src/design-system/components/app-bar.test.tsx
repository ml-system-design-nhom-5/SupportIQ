import { screen } from "@testing-library/react";
import { LayoutGrid, ShoppingBag } from "lucide-react";
import { describe, expect, it } from "vitest";

import { AccountLabel } from "@/design-system/components/account-label";
import { AppBar } from "@/design-system/components/app-bar";
import { Button } from "@/design-system/primitives/button";
import { NavItem } from "@/design-system/primitives/nav-item";
import { renderUi } from "@/test/render-app";

describe("AppBar", () => {
  it("shows the shop brand, the main navigation, and the account", () => {
    renderUi(
      <AppBar
        variant="shop"
        brandName="Demo Shop"
        brandIcon={ShoppingBag}
        navigation={
          <NavItem to="/shop" icon={LayoutGrid}>
            Products
          </NavItem>
        }
        account={
          <>
            <AccountLabel displayName="Linh Tran" />
            <Button variant="ghost">Sign out</Button>
          </>
        }
      />,
    );

    expect(screen.getByRole("banner")).toHaveTextContent("Demo Shop");
    expect(screen.getByRole("navigation", { name: "Main" })).toHaveTextContent("Products");
    expect(screen.getByText("Linh Tran")).toBeVisible();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeVisible();
  });

  it("shows the console brand with its area name and the role of the account", () => {
    renderUi(
      <AppBar
        variant="console"
        brandName="SupportIQ"
        areaName="Console"
        account={<AccountLabel displayName="Mai Nguyen" roleLabel="Staff" />}
      />,
    );

    expect(screen.getByRole("banner")).toHaveTextContent("SupportIQConsole");
    expect(screen.getByText("· Staff")).toBeVisible();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});
