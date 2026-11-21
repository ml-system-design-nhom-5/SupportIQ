/**
 * The path of the Versions screen (admin UI design, Screens): `/admin/versions`.
 */
import { rootPathByArea } from "@/features/session";

/** The route of Versions, relative to the admin root. */
export const VERSIONS_ROUTE = "versions";

/** The path of Versions. */
export const VERSIONS_PATH = `${rootPathByArea.admin}/${VERSIONS_ROUTE}`;
