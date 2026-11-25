/**
 * The contract types of the shop ticket operations, for the mappings in model/ (TS-09).
 */
import type { components } from "@/api/generated/backend";

/** `ShopTicketView`: a customer's ticket as the shop shows it. */
export type ShopTicketContract = components["schemas"]["ShopTicketView"];

/** `ShopTicketPage`: one page of `listShopTickets`. */
export type ShopTicketPageContract = components["schemas"]["ShopTicketPage"];
