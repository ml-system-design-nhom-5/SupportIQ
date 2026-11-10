/**
 * The route element of the Order screen: it reads the order ID from the address and composes the
 * order with Support for this order, so the two features never import each other (TS-06,
 * ARCH-18).
 */
import { useRouteParam } from "@/app/routes/route-params";
import { OrderPage } from "@/features/shop-orders";
import { OrderSupportSection } from "@/features/shop-support";

/**
 * Render the Order screen of the order in the address. The key starts a new screen for another
 * order, so the text in the message box never goes to the wrong order.
 *
 * @returns The screen.
 */
export function OrderRoute() {
  const orderId = useRouteParam("orderId");
  return (
    <OrderPage
      key={orderId}
      orderId={orderId}
      renderSupport={(messageBoxId) => (
        <OrderSupportSection orderId={orderId} messageBoxId={messageBoxId} />
      )}
    />
  );
}
