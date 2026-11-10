/**
 * The path of the Accounts screen (admin UI design, Screens): `/admin/accounts`, which `/admin`
 * opens.
 */
import { rootPathByArea } from "@/features/session";

/** The route of Accounts, relative to the admin root. */
export const ACCOUNTS_ROUTE = "accounts";

/** The path of Accounts. */
export const ACCOUNTS_PATH = `${rootPathByArea.admin}/${ACCOUNTS_ROUTE}`;
