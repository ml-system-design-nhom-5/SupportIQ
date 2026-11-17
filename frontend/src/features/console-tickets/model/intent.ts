/**
 * Intents as the console shows them (FR-01): the label of the contract and a name in sentence case
 * (UI-27), such as "Refund status" for `refund_status`. A label that this version does not know is
 * an unspecified intent (`IntentLabel`, CON-22), which staff can never choose.
 */
import type { IntentLabelContract } from "@/features/console-tickets/api/contract-types";

/** The 46 labels of `IntentLabel`. A unit test compares them with the contract. */
export const intentLabels = [
  "add_product",
  "availability",
  "availability_in_store",
  "availability_online",
  "cancel_order",
  "change_account",
  "change_order",
  "close_account",
  "customer_service",
  "damaged_delivery",
  "delivery_issue",
  "delivery_time",
  "exchange_product",
  "exchange_product_in_store",
  "human_agent",
  "missing_item",
  "open_account",
  "order_history",
  "pay",
  "payment_issue",
  "payment_methods",
  "product_information",
  "product_issue",
  "recover_password",
  "refund_policy",
  "refund_status",
  "remove_product",
  "request_invoice",
  "request_refund",
  "request_right_to_rectification",
  "return_policy",
  "return_product",
  "return_product_in_store",
  "return_product_online",
  "sales_period",
  "shipping_costs",
  "store_location",
  "store_opening_hours",
  "submit_feedback",
  "submit_product_feedback",
  "submit_product_idea",
  "technical_issue",
  "track_delivery",
  "track_order",
  "use_app",
  "wrong_item",
] as const satisfies readonly IntentLabelContract[];

const knownIntentLabels: ReadonlySet<string> = new Set(intentLabels);

/** The name of an intent that this version does not know. */
const UNSPECIFIED_INTENT_NAME = "Unspecified intent";

/** An intent label of the contract, or `unknown` for one that this version does not know. */
export type IntentLabel = IntentLabelContract | "unknown";

/** An intent as the console shows it. */
export type Intent = {
  readonly label: IntentLabel;
  /** The name in sentence case, for example "Refund status". */
  readonly name: string;
};

/**
 * Map an intent label from `backend`.
 *
 * @param value - An `IntentLabel`.
 * @returns The label and its name, or `unknown` with "Unspecified intent".
 */
export function toIntent(value: string): Intent {
  if (!isKnownIntentLabel(value)) {
    return { label: "unknown", name: UNSPECIFIED_INTENT_NAME };
  }
  const words = value.replaceAll("_", " ");
  return { label: value, name: `${words.charAt(0).toUpperCase()}${words.slice(1)}` };
}

/**
 * Tell whether a value is an intent label of the contract.
 *
 * @param value - An `IntentLabel` from `backend`.
 * @returns True for one of the 46 labels.
 */
function isKnownIntentLabel(value: string): value is IntentLabelContract {
  return knownIntentLabels.has(value);
}
