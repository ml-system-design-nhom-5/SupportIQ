/**
 * The routes of frontend. Every route has an error boundary (TS-26): top-level routes use
 * {@link RouteErrorBoundary}, screens inside an area shell use {@link ScreenErrorBoundary}, so the
 * shell stays. Each screen shows its own loading state while its data loads.
 */
import { Navigate, type RouteObject } from "react-router";

import { AdminLayout } from "@/app/layouts/admin-layout";
import { ConsoleLayout } from "@/app/layouts/console-layout";
import { ConsoleTicketsLayout } from "@/app/layouts/console-tickets-layout";
import { ShopLayout } from "@/app/layouts/shop-layout";
import { RouteErrorBoundary } from "@/app/route-error-boundary";
import { NotFoundPage } from "@/app/routes/not-found-page";
import { OrderRoute } from "@/app/routes/order-route";
import { ProductRoute } from "@/app/routes/product-route";
import { TicketRoute } from "@/app/routes/ticket-route";
import { ScreenErrorBoundary } from "@/app/screen-error-boundary";
import { ACCOUNTS_ROUTE, AccountsPage } from "@/features/admin-accounts";
import { VERSIONS_ROUTE, VersionsPage } from "@/features/admin-versions";
import { REPORTS_ROUTE, ReportsPage } from "@/features/console-reports";
import { NoTicketSelected, TICKET_ROUTE } from "@/features/console-tickets";
import {
  CHANGE_PASSWORD_PATH,
  ChangePasswordPage,
  rootPathByArea,
  SIGN_IN_PATH,
  SignInPage,
  StartPage,
} from "@/features/session";
import { PRODUCT_ROUTE, ProductsPage } from "@/features/shop-catalog";
import { ORDER_ROUTE, ORDERS_ROUTE, OrdersPage } from "@/features/shop-orders";
import { SUPPORT_ROUTE, SupportPage } from "@/features/shop-support";

/** The route tree, shared by the browser router and the memory routers of tests. */
export const appRoutes: RouteObject[] = [
  { path: SIGN_IN_PATH, element: <SignInPage />, errorElement: <RouteErrorBoundary /> },
  {
    path: CHANGE_PASSWORD_PATH,
    element: <ChangePasswordPage />,
    errorElement: <RouteErrorBoundary />,
  },
  { path: "/", element: <StartPage />, errorElement: <RouteErrorBoundary /> },
  {
    path: rootPathByArea.shop,
    element: <ShopLayout />,
    errorElement: <RouteErrorBoundary />,
    children: [
      { index: true, element: <ProductsPage />, errorElement: <ScreenErrorBoundary /> },
      { path: PRODUCT_ROUTE, element: <ProductRoute />, errorElement: <ScreenErrorBoundary /> },
      { path: ORDERS_ROUTE, element: <OrdersPage />, errorElement: <ScreenErrorBoundary /> },
      { path: ORDER_ROUTE, element: <OrderRoute />, errorElement: <ScreenErrorBoundary /> },
      { path: SUPPORT_ROUTE, element: <SupportPage />, errorElement: <ScreenErrorBoundary /> },
    ],
  },
  {
    path: rootPathByArea.console,
    element: <ConsoleLayout />,
    errorElement: <RouteErrorBoundary />,
    children: [
      {
        element: <ConsoleTicketsLayout />,
        errorElement: <ScreenErrorBoundary />,
        children: [
          { index: true, element: <NoTicketSelected />, errorElement: <ScreenErrorBoundary /> },
          { path: TICKET_ROUTE, element: <TicketRoute />, errorElement: <ScreenErrorBoundary /> },
        ],
      },
      { path: REPORTS_ROUTE, element: <ReportsPage />, errorElement: <ScreenErrorBoundary /> },
    ],
  },
  {
    path: rootPathByArea.admin,
    element: <AdminLayout />,
    errorElement: <RouteErrorBoundary />,
    children: [
      {
        index: true,
        element: <Navigate to={ACCOUNTS_ROUTE} replace />,
        errorElement: <ScreenErrorBoundary />,
      },
      { path: ACCOUNTS_ROUTE, element: <AccountsPage />, errorElement: <ScreenErrorBoundary /> },
      { path: VERSIONS_ROUTE, element: <VersionsPage />, errorElement: <ScreenErrorBoundary /> },
    ],
  },
  { path: "*", element: <NotFoundPage />, errorElement: <RouteErrorBoundary /> },
];
