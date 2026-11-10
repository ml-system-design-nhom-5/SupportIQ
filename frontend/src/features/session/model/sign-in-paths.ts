/**
 * The sign-in path with its return path, and where to go after sign-in. A session that ends in the
 * middle of a task returns to the same page after sign-in; a return path never leaves the app and
 * never opens another area than the role's own.
 */
import { type AccountRole, getRoleArea, rootPathByArea } from "@/features/session/model/session";

/** The path of the sign-in screen (console UI design, Screens). */
export const SIGN_IN_PATH = "/sign-in";

/** The query parameter that holds the page to return to. */
export const RETURN_TO_PARAMETER = "returnTo";

/** The page that shows a role without an area. */
const START_PATH = "/";

/** The origin that return paths are normalized against. It is never part of a result. */
const NORMALIZING_ORIGIN = "https://supportiq.invalid";

/**
 * Build the sign-in path.
 *
 * @param returnTo - The page to open after sign-in, or undefined after a sign-out.
 * @returns For example `/sign-in?returnTo=%2Fshop%2Forders`.
 */
export function buildSignInPath(returnTo: string | undefined): string {
  if (returnTo === undefined) {
    return SIGN_IN_PATH;
  }
  return `${SIGN_IN_PATH}?${new URLSearchParams({ [RETURN_TO_PARAMETER]: returnTo }).toString()}`;
}

/**
 * Choose the page to open after sign-in. The return path is normalized first, exactly as the
 * browser will read it, so dot segments, encoded dots, and backslashes cannot leave the app or the
 * area.
 *
 * @param role - The role of the new session.
 * @param returnTo - The return path from the sign-in address, if any.
 * @returns The normalized return path when it is inside the role's area, otherwise the area's
 *   root. A role without an area opens the start page, which says so.
 */
export function resolvePathAfterSignIn(role: AccountRole, returnTo: string | null): string {
  const area = getRoleArea(role);
  if (area === "none") {
    return START_PATH;
  }
  const areaRoot = rootPathByArea[area];
  if (returnTo === null || !URL.canParse(returnTo, NORMALIZING_ORIGIN)) {
    return areaRoot;
  }
  const { origin, pathname, search, hash } = new URL(returnTo, NORMALIZING_ORIGIN);
  if (origin === NORMALIZING_ORIGIN && isInsideArea(pathname, areaRoot)) {
    return `${pathname}${search}${hash}`;
  }
  return areaRoot;
}

/**
 * Tell whether a path is inside an area.
 *
 * @param pathname - A normalized path, without its query and fragment.
 * @param areaRoot - The root path of the area.
 * @returns True for the root itself and every path below it.
 */
function isInsideArea(pathname: string, areaRoot: string): boolean {
  return pathname === areaRoot || pathname.startsWith(`${areaRoot}/`);
}
