/**
 * Choose what the Prism mock answers (contracts/README.md, The mock): the browser request gets a
 * `Prefer` header on its way out. The mock is stateless, so a test that needs a list to change
 * chooses another outcome for the later requests.
 */
import type { Page, Route } from "@playwright/test";

/** Which requests a `Prefer` header is for. */
export type MockedRequest = {
  readonly method: "GET" | "POST" | "DELETE";
  /** The path, without the query. A `*` matches one path segment. */
  readonly path: string;
};

/**
 * Send a `Prefer` header with every matching request.
 *
 * @param page - The page.
 * @param request - The method and the path.
 * @param firstPrefer - The header value.
 * @returns A function that chooses the header value of the later requests.
 */
export async function preferOutcome(
  page: Page,
  request: MockedRequest,
  firstPrefer: string,
): Promise<(prefer: string) => void> {
  let currentPrefer = firstPrefer;
  await page.route("**/v1/**", async (route) => {
    if (!isMatch(route, request)) {
      await route.fallback();
      return;
    }
    await route.fallback({ headers: { ...route.request().headers(), prefer: currentPrefer } });
  });
  return (prefer) => {
    currentPrefer = prefer;
  };
}

/**
 * Lose the connection for every matching request, as a person does when the network drops. No
 * response reaches the page, so nothing imitates `backend`.
 *
 * @param page - The page.
 * @param request - The method and the path.
 * @returns A function that brings the connection back.
 */
export async function loseConnection(
  page: Page,
  request: MockedRequest,
): Promise<() => Promise<void>> {
  const handler = async (route: Route) => {
    if (!isMatch(route, request)) {
      await route.fallback();
      return;
    }
    await route.abort("connectionfailed");
  };
  await page.route("**/v1/**", handler);
  return () => page.unroute("**/v1/**", handler);
}

/**
 * Tell whether a route's request matches.
 *
 * @param route - The intercepted route.
 * @param request - The method and the path.
 * @returns True when both match.
 */
function isMatch(route: Route, request: MockedRequest): boolean {
  const pattern = new RegExp(`^${request.path.replaceAll("*", "[^/]+")}$`);
  return (
    route.request().method() === request.method &&
    pattern.test(new URL(route.request().url()).pathname)
  );
}
