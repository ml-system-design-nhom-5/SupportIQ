/**
 * Read the parameters of the current route.
 */
import { useParams } from "react-router";

/**
 * Read a parameter that the route pattern always has.
 *
 * @param name - The parameter name in the route pattern, for example `orderId`.
 * @returns The decoded value.
 * @throws Error when the route has no such parameter, which is a defect of the route table.
 */
export function useRouteParam(name: string): string {
  const value = useParams()[name];
  if (value === undefined) {
    throw new Error(`The route has no parameter ${name}.`);
  }
  return value;
}
