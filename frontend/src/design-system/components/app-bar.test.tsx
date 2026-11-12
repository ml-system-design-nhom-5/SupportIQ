import { screen } from "@testing-library/react";
import { LayoutGrid, ShoppingBag } from "lucide-react";
import { describe, expect, it } from "vitest";

import { AccountMenu } from "@/design-system/components/account-menu";
import { AppBar } from "@/design-system/components/app-bar";
import { NavItem } from "@/design-system/primitives/nav-item";
import { renderUi } from "@/test/render-app";

/** The handlers of the account menu, which these tests do not open. */
const menuHandlers = { onChangePassword: () => undefined, onSignOut: () => undefined };

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
          <AccountMenu
            variant="shop"
            displayName="Linh Tran"
            roleLabel="Customer"
            isSigningOut={false}
            {...menuHandlers}
          />
        }
      />,
    );

    expect(screen.getByRole("banner")).toHaveTextContent("Demo Shop");
    expect(screen.getByRole("navigation", { name: "Main" })).toHaveTextContent("Products");
    expect(screen.getByRole("button", { name: "Linh Tran · Customer" })).toBeVisible();
  });

  it("shows the console brand with its area name and the role of the account", () => {
    renderUi(
      <AppBar
        variant="console"
        brandName="SupportIQ"
        areaName="Console"
        account={
          <AccountMenu
            variant="console"
            displayName="Mai Nguyen"
            roleLabel="Staff"
            isSigningOut={false}
            {...menuHandlers}
          />
        }
      />,
    );

    expect(screen.getByRole("banner")).toHaveTextContent("SupportIQConsole");
    expect(screen.getByText("· Staff")).toBeVisible();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});
