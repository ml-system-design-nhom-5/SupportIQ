/**
 * The path of the Support screen (shop UI design, Screens): `/shop/support`.
 */
import { rootPathByArea } from "@/features/session";

/** The route of Support, relative to the shop root. */
export const SUPPORT_ROUTE = "support";

/** The path of Support. */
export const SUPPORT_PATH = `${rootPathByArea.shop}/${SUPPORT_ROUTE}`;
