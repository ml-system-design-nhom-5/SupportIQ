import type { Meta, StoryObj } from "@storybook/react-vite";
import { type ReactNode, useState } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";

import { RouteErrorBoundary } from "@/app/route-error-boundary";
import { ScreenErrorBoundary } from "@/app/screen-error-boundary";
import { RequestFailureError } from "@/features/backend-requests";

const meta = {
  title: "App/Route error boundaries",
  component: BoundaryOfFailedRoute,
  parameters: { hasOwnRouter: true },
  args: {
    error: new Error("A defect that this story causes on purpose."),
    boundary: <ScreenErrorBoundary />,
  },
} satisfies Meta<typeof BoundaryOfFailedRoute>;

export default meta;

/** Props of {@link BoundaryOfFailedRoute}. */
type BoundaryOfFailedRouteProps = {
  /** What the route throws while rendering. */
  readonly error: Error;
  readonly boundary: ReactNode;
};

type Story = StoryObj<typeof meta>;

export const ScreenWithDefect: Story = {};

export const ScreenWithRequestFailure: Story = {
  args: {
    error: new RequestFailureError({
      kind: "problem",
      status: 500,
      problemType: "internal_error",
      traceId: "319c0af7651916cd43dd8448eb211c80",
    }),
  },
};

export const RouteWithDefect: Story = { args: { boundary: <RouteErrorBoundary /> } };

/**
 * Throw while rendering.
 *
 * @param props - The error.
 * @throws The error always.
 */
function FailedScreen({ error }: { readonly error: Error }): never {
  throw error;
}

/**
 * Render a route that fails, inside a data router, which the error boundaries read.
 *
 * @param props - The error and the boundary.
 * @returns The router.
 */
function BoundaryOfFailedRoute({ error, boundary }: BoundaryOfFailedRouteProps) {
  const [router] = useState(() =>
    createMemoryRouter([
      { path: "/", element: <FailedScreen error={error} />, errorElement: boundary },
    ]),
  );
  return <RouterProvider router={router} />;
}
