/**
 * The tickets of a console queue (console UI design, Inbox) and their mapping from `TicketSummary`
 * (TS-09). Each item shows the ticket ID, the time received, the customer, the message excerpt,
 * the predicted intent with its confidence, the AI status, the authority flag, and who opened it.
 */
import type { AiStatusName, ConfidenceBandName, ConsoleTicketStatusName } from "@/design-system";
import { requireMembers } from "@/features/backend-requests";
import type {
  TicketSummaryContract,
  TicketSummaryPageContract,
} from "@/features/console-tickets/api/contract-types";
import { toIntent } from "@/features/console-tickets/model/intent";
import {
  toAiStatus,
  toConfidenceBand,
  toHandlingMode,
  toTicketStatus,
} from "@/features/console-tickets/model/ticket-status";

/** The intent line of a queue item. */
export type SummaryIntent =
  | {
      readonly kind: "predicted";
      readonly name: string;
      readonly band: ConfidenceBandName;
      readonly probability: number;
    }
  | { readonly kind: "none"; readonly text: string };

/** The badge of a queue item: the AI status of an open ticket, the ticket status otherwise. */
export type SummaryBadge =
  | { readonly kind: "ai"; readonly status: AiStatusName }
  | { readonly kind: "ticket"; readonly status: ConsoleTicketStatusName };

/** One ticket of a queue. The customer name and the excerpt are Confidential: never logged. */
export type TicketSummary = {
  readonly ticketId: string;
  readonly createdAt: string;
  readonly customerName: string;
  readonly excerpt: string;
  readonly intent: SummaryIntent;
  readonly badge: SummaryBadge;
  readonly isAuthorityRequired: boolean;
  /** When a person first opened the ticket; absent until then. */
  readonly openedAt?: string;
};

/** One page of a queue (CON-14). */
export type TicketSummaryPage = {
  readonly tickets: readonly TicketSummary[];
  readonly nextCursor?: string;
};

/**
 * Map a ticket of a queue.
 *
 * @param summary - A `TicketSummary`.
 * @returns The view model.
 */
export function toTicketSummary(summary: TicketSummaryContract): TicketSummary {
  requireMembers(summary, [
    "ticket_id",
    "created_at",
    "status",
    "handling_mode",
    "is_authority_required",
    "customer",
    "message_excerpt",
  ]);
  const mapped: TicketSummary = {
    ticketId: summary.ticket_id,
    createdAt: summary.created_at,
    customerName: summary.customer.display_name,
    excerpt: summary.message_excerpt,
    intent: toSummaryIntent(summary),
    badge: toSummaryBadge(summary),
    isAuthorityRequired: summary.is_authority_required,
  };
  return summary.handling_started_at === undefined
    ? mapped
    : { ...mapped, openedAt: summary.handling_started_at };
}

/**
 * Map a page of `listConsoleTickets`.
 *
 * @param page - A `TicketSummaryPage`.
 * @returns The tickets and the cursor of the next page.
 */
export function toTicketSummaryPage(page: TicketSummaryPageContract): TicketSummaryPage {
  const tickets = page.items.map(toTicketSummary);
  return page.next_cursor === undefined ? { tickets } : { tickets, nextCursor: page.next_cursor };
}

/**
 * Choose the intent line of a queue item. The predicted intent is absent while the analysis is not
 * ready, when it failed, and when staff chose the intent (`TicketSummary`).
 *
 * @param summary - A `TicketSummary`.
 * @returns The predicted intent with its confidence, or a line that says why there is none.
 */
function toSummaryIntent(summary: TicketSummaryContract): SummaryIntent {
  const predicted = summary.predicted_intent;
  if (predicted !== undefined) {
    return {
      kind: "predicted",
      name: toIntent(predicted.label).name,
      band: toConfidenceBand(predicted.confidence_band),
      probability: predicted.probability,
    };
  }
  if (toHandlingMode(summary.handling_mode) === "manual") {
    return { kind: "none", text: "No AI (manual)" };
  }
  return { kind: "none", text: getMissingIntentText(summary.draft_status) };
}

/**
 * Say why an assisted ticket has no predicted intent.
 *
 * @param draftStatus - The `draft_status` of the summary, absent in `manual` mode.
 * @returns The line of the queue item.
 */
function getMissingIntentText(draftStatus: string | undefined): string {
  const aiStatus = draftStatus === undefined ? "unavailable" : toAiStatus(draftStatus);
  if (aiStatus === "pending") {
    return "Analysis in progress";
  }
  if (aiStatus === "unavailable") {
    return "No analysis";
  }
  return "Intent chosen by staff";
}

/**
 * Choose the badge of a queue item.
 *
 * @param summary - A `TicketSummary`.
 * @returns The AI status of an open ticket, `manual` in manual mode; the ticket status otherwise.
 */
function toSummaryBadge(summary: TicketSummaryContract): SummaryBadge {
  const status = toTicketStatus(summary.status);
  if (status !== "open") {
    return { kind: "ticket", status };
  }
  if (toHandlingMode(summary.handling_mode) === "manual") {
    return { kind: "ai", status: "manual" };
  }
  return {
    kind: "ai",
    status: summary.draft_status === undefined ? "unavailable" : toAiStatus(summary.draft_status),
  };
}
