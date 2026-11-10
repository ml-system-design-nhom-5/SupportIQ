/**
 * The `backend` operations that tests answer with the fake backend, named after their operation
 * IDs in contracts/backend.openapi.yaml.
 */
import type { FakeRoute } from "@/test/fake-backend";

export const createSessionRoute: FakeRoute = { method: "POST", path: "/v1/sessions" };
export const getCurrentSessionRoute: FakeRoute = { method: "GET", path: "/v1/sessions/current" };
export const deleteCurrentSessionRoute: FakeRoute = {
  method: "DELETE",
  path: "/v1/sessions/current",
};
export const listShopProductsRoute: FakeRoute = { method: "GET", path: "/v1/shop/products" };
export const getShopProductRoute: FakeRoute = {
  method: "GET",
  path: /^\/v1\/shop\/products\/[^/]+$/,
};
export const listShopOrdersRoute: FakeRoute = { method: "GET", path: "/v1/shop/orders" };
export const getShopOrderRoute: FakeRoute = { method: "GET", path: /^\/v1\/shop\/orders\/[^/]+$/ };
export const listShopTicketsRoute: FakeRoute = { method: "GET", path: "/v1/shop/tickets" };
export const createShopTicketRoute: FakeRoute = { method: "POST", path: "/v1/shop/tickets" };
export const listAdminAccountsRoute: FakeRoute = { method: "GET", path: "/v1/admin/accounts" };
export const changeAccountRoleRoute: FakeRoute = {
  method: "POST",
  path: /^\/v1\/admin\/accounts\/[^/]+\/role-changes$/,
};
export const changeAccountStatusRoute: FakeRoute = {
  method: "POST",
  path: /^\/v1\/admin\/accounts\/[^/]+\/status-changes$/,
};
