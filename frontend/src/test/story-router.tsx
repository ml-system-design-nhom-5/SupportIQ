/**
 * Render a layout in stories as the router does: inside a data router, with a screen in its
 * outlet. Such a story sets `hasOwnRouter`.
 */
import { type ReactNode, useState } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";

/** Props of {@link LayoutInRouter}. */
type LayoutInRouterProps = {
  readonly layout: ReactNode;
};

/**
 * Render a layout around a stand-in screen.
 *
 * @param props - The layout.
 * @returns The router.
 */
export function LayoutInRouter({ layout }: LayoutInRouterProps) {
  const [router] = useState(() =>
    createMemoryRouter([
      { path: "/", element: layout, children: [{ index: true, element: <p>The screen.</p> }] },
    ]),
  );
  return <RouterProvider router={router} />;
}
