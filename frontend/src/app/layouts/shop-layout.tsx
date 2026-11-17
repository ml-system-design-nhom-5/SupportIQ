/**
 * The shop app shell (shop UI design, Layout): the top bar with "Demo Shop", the navigation, and
 * the account menu, above one content column. At phone width the menu shows only its icon. A
 * session of another role sees only the brand: every shop operation answers it with `403`, which
 * the screen shows.
 */
import { LayoutGrid, LifeBuoy, Package, ShoppingBag } from "lucide-react";
import { Outlet } from "react-router";

import { AppBar, NavItem, PageColumn } from "@/design-system";
import { RequireSession, type Session, SessionAccountMenu } from "@/features/session";
import { PRODUCTS_PATH, SHOP_NAME } from "@/features/shop-catalog";
import { ORDERS_PATH } from "@/features/shop-orders";
import { SUPPORT_PATH } from "@/features/shop-support";

/**
 * Render the shop shell around the current shop screen.
 *
 * @returns The shell, or the session's loading, error, or sign-in redirect.
 */
export function ShopLayout() {
  return (
    <RequireSession>
      {(session) => (
        <>
          {session.role === "customer" ? (
            renderCustomerBar(session)
          ) : (
            <AppBar variant="shop" brandName={SHOP_NAME} brandIcon={ShoppingBag} />
          )}
          <PageColumn area="shop">
            <Outlet />
          </PageColumn>
        </>
      )}
    </RequireSession>
  );
}

/**
 * Render the bar for a customer.
 *
 * @param session - The signed-in customer.
 * @returns The app bar with the navigation and the account.
 */
function renderCustomerBar(session: Session) {
  return (
    <AppBar
      variant="shop"
      brandName={SHOP_NAME}
      brandIcon={ShoppingBag}
      navigation={
        <>
          <NavItem to={PRODUCTS_PATH} icon={LayoutGrid} current={{ by: "exact-path" }}>
            Products
          </NavItem>
          <NavItem to={ORDERS_PATH} icon={Package}>
            My orders
          </NavItem>
          <NavItem to={SUPPORT_PATH} icon={LifeBuoy}>
            Support
          </NavItem>
        </>
      }
      account={<SessionAccountMenu session={session} variant="shop" />}
    />
  );
}
