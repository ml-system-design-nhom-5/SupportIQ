/**
 * The order facts that a draft cites (ADR-0014; console UI design, Draft editing and citations):
 * each cited field of the order context, with the value that `backend` sent for it. A citation of a
 * field that this version does not know is ignored (`OrderContextField`, CON-22).
 */
import {
  formatDate,
  formatMoney,
  presentationByOrderStatus,
  presentationByRefundStatus,
  presentationByShipmentStatus,
} from "@/design-system";
import {
  assertNever,
  type MoneyContract,
  toMoney,
  toOrderStatus,
  toRefundStatus,
  toShipmentStatus,
} from "@/features/backend-requests";

/** How the value of each field is shown. */
type FieldFormat = "order_status" | "shipment_status" | "refund_status" | "date" | "money";

/** The fields of `OrderContextField`, with their names and value formats. */
const fieldByName: ReadonlyMap<string, { readonly term: string; readonly format: FieldFormat }> =
  new Map([
    ["order_status", { term: "Order status", format: "order_status" }],
    ["placed_at", { term: "Placed", format: "date" }],
    ["order_total", { term: "Order total", format: "money" }],
    ["shipping_cost", { term: "Shipping cost", format: "money" }],
    ["shipment_status", { term: "Shipment status", format: "shipment_status" }],
    ["estimated_delivery_at", { term: "Estimated delivery", format: "date" }],
    ["delivered_at", { term: "Delivered", format: "date" }],
    ["refund_status", { term: "Refund status", format: "refund_status" }],
    ["refund_amount", { term: "Refund amount", format: "money" }],
    ["refund_requested_at", { term: "Refund requested", format: "date" }],
  ]);

/** One cited order fact, such as "Refund status: Refund under review". */
export type OrderCitationFact = {
  readonly term: string;
  readonly value: string;
};

/**
 * Map the field and the value of an order citation.
 *
 * @param field - The `field` of the citation, an `OrderContextField`.
 * @param value - The `value` of the citation, typed as the field is in `OrderContext`.
 * @returns The fact, or undefined for a field that this version does not know.
 * @throws TypeError when the value does not have the type of its field.
 */
export function toOrderCitationFact(
  field: string,
  value: string | MoneyContract,
): OrderCitationFact | undefined {
  const known = fieldByName.get(field);
  if (known === undefined) {
    return undefined;
  }
  return { term: known.term, value: formatFieldValue(known.format, value) };
}

/**
 * Format the value of a field.
 *
 * @param format - How the field is shown.
 * @param value - The value of the field.
 * @returns The value as staff read it.
 * @throws TypeError when the value does not have the type of its field.
 */
function formatFieldValue(format: FieldFormat, value: string | MoneyContract): string {
  if (format === "money") {
    if (typeof value === "string") {
      throw new TypeError("An order citation of an amount has no Money value.");
    }
    return formatMoney(toMoney(value));
  }
  if (typeof value !== "string") {
    throw new TypeError("An order citation of a status or a time has no text value.");
  }
  return formatTextValue(format, value);
}

/**
 * Format a status or a time.
 *
 * @param format - How the field is shown.
 * @param value - The status or the RFC 3339 timestamp.
 * @returns The label of the status, or the date.
 */
function formatTextValue(format: Exclude<FieldFormat, "money">, value: string): string {
  switch (format) {
    case "order_status":
      return presentationByOrderStatus[toOrderStatus(value)].label;
    case "shipment_status":
      return presentationByShipmentStatus[toShipmentStatus(value)].label;
    case "refund_status":
      return presentationByRefundStatus[toRefundStatus(value)].label;
    case "date":
      return formatDate(value);
    default:
      assertNever(format);
  }
}
