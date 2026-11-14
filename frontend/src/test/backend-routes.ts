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
export const changeOwnPasswordRoute: FakeRoute = {
  method: "POST",
  path: "/v1/sessions/current/password-changes",
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
export const createAdminAccountRoute: FakeRoute = { method: "POST", path: "/v1/admin/accounts" };
export const changeAccountRoleRoute: FakeRoute = {
  method: "POST",
  path: /^\/v1\/admin\/accounts\/[^/]+\/role-changes$/,
};
export const changeAccountStatusRoute: FakeRoute = {
  method: "POST",
  path: /^\/v1\/admin\/accounts\/[^/]+\/status-changes$/,
};
export const resetAccountPasswordRoute: FakeRoute = {
  method: "POST",
  path: /^\/v1\/admin\/accounts\/[^/]+\/password-resets$/,
};
export const listConsoleTicketsRoute: FakeRoute = { method: "GET", path: "/v1/console/tickets" };
export const getConsoleTicketRoute: FakeRoute = {
  method: "GET",
  path: /^\/v1\/console\/tickets\/[^/]+$/,
};
export const recordTicketViewRoute: FakeRoute = {
  method: "POST",
  path: /^\/v1\/console\/tickets\/[^/]+\/views$/,
};
export const getConsoleKbDocumentVersionRoute: FakeRoute = {
  method: "GET",
  path: /^\/v1\/console\/kb-documents\/[^/]+\/versions\/[^/]+$/,
};
export const createSuggestionRoute: FakeRoute = {
  method: "POST",
  path: /^\/v1\/console\/tickets\/[^/]+\/suggestions$/,
};
export const sendReplyRoute: FakeRoute = {
  method: "POST",
  path: /^\/v1\/console\/tickets\/[^/]+\/replies$/,
};
export const createReplyProposalRoute: FakeRoute = {
  method: "POST",
  path: /^\/v1\/console\/tickets\/[^/]+\/reply-proposals$/,
};
export const createEscalationRoute: FakeRoute = {
  method: "POST",
  path: /^\/v1\/console\/tickets\/[^/]+\/escalations$/,
};
