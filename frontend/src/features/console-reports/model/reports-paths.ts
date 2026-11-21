/**
 * The path of the Reports page (console UI design, Screens): `/console/reports`, for managers only
 * (UI-44).
 */
import { rootPathByArea } from "@/features/session";

/** The route of Reports, relative to the console root. */
export const REPORTS_ROUTE = "reports";

/** The path of Reports. */
export const REPORTS_PATH = `${rootPathByArea.console}/${REPORTS_ROUTE}`;
