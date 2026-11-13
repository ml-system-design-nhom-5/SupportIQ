/**
 * The ticket workspace (console UI design, Workspace regions), mapped from `TicketWorkspace`
 * (TS-09). Every field has one place on screen. AI text has pseudonyms restored and is shown
 * exactly as `backend` returns it (UI-43). All text is Confidential: shown, never logged.
 */
import type { ConsoleTicketStatusName, HandlingModeName } from "@/design-system";
import { requireMembers } from "@/features/backend-requests";
import type {
  ConsoleReplyContract,
  SuggestionContract,
  TicketWorkspaceContract,
} from "@/features/console-tickets/api/contract-types";
import { type AnalysisPart, toAnalysisPart } from "@/features/console-tickets/model/analysis";
import { type DraftPart, toDraftPart } from "@/features/console-tickets/model/draft";
import { type Intent, toIntent } from "@/features/console-tickets/model/intent";
import {
  type Order,
  type TicketOrder,
  toOrder,
  toTicketOrder,
} from "@/features/console-tickets/model/order";
import {
  type TicketAction,
  toTicketActions,
} from "@/features/console-tickets/model/ticket-actions";
import { toHandlingMode, toTicketStatus } from "@/features/console-tickets/model/ticket-status";

/** One run of the AI for the ticket. */
export type Suggestion = {
  readonly suggestionId: string;
  readonly createdAt: string;
  /** The intent that staff confirmed or chose for this suggestion; absent when they chose none. */
  readonly intentOverride?: Intent;
  readonly analysis: AnalysisPart;
  readonly draft: DraftPart;
};

/** The reply that staff or a manager sent. */
export type SentReply = {
  readonly body: string;
  readonly sentByName: string;
  readonly sentAt: string;
};

/** Everything that the workspace shows of one ticket. */
export type TicketWorkspace = {
  readonly ticketId: string;
  readonly status: ConsoleTicketStatusName;
  readonly handlingMode: HandlingModeName;
  readonly isAuthorityRequired: boolean;
  readonly createdAt: string;
  readonly customerName: string;
  readonly message: { readonly body: string; readonly createdAt: string };
  /** Absent for an imported ticket without an order. */
  readonly order?: TicketOrder;
  /** The customer's other orders, newest first; empty when there are none. */
  readonly otherOrders: readonly Order[];
  /** Absent in `manual` mode. */
  readonly suggestion?: Suggestion;
  /** Present exactly when the ticket is `closed`. */
  readonly reply?: SentReply;
  /** What the caller may do now; empty for staff on a ticket that is not `open`. */
  readonly allowedActions: ReadonlySet<TicketAction>;
};

/**
 * Map the body of `getConsoleTicket`.
 *
 * @param workspace - A `TicketWorkspace`.
 * @returns The view model.
 */
export function toTicketWorkspace(workspace: TicketWorkspaceContract): TicketWorkspace {
  requireMembers(workspace, [
    "ticket_id",
    "status",
    "handling_mode",
    "is_authority_required",
    "created_at",
    "customer",
    "message",
    "allowed_actions",
  ]);
  return {
    ticketId: workspace.ticket_id,
    status: toTicketStatus(workspace.status),
    handlingMode: toHandlingMode(workspace.handling_mode),
    isAuthorityRequired: workspace.is_authority_required,
    createdAt: workspace.created_at,
    customerName: workspace.customer.display_name,
    message: { body: workspace.message.body, createdAt: workspace.message.created_at },
    ...(workspace.order === undefined ? {} : { order: toTicketOrder(workspace.order) }),
    otherOrders: (workspace.other_orders ?? []).map(toOrder),
    ...(workspace.suggestion === undefined
      ? {}
      : { suggestion: toSuggestion(workspace.suggestion) }),
    ...(workspace.reply === undefined ? {} : { reply: toSentReply(workspace.reply) }),
    allowedActions: toTicketActions(workspace.allowed_actions),
  };
}

/**
 * Map a suggestion: the current one of a ticket, or the one that `createSuggestion` started.
 *
 * @param suggestion - A `SuggestionView`.
 * @returns The view model.
 */
export function toSuggestion(suggestion: SuggestionContract): Suggestion {
  requireMembers(suggestion, ["suggestion_id", "created_at", "analysis", "draft"]);
  return {
    suggestionId: suggestion.suggestion_id,
    createdAt: suggestion.created_at,
    ...(suggestion.intent_override === undefined
      ? {}
      : { intentOverride: toIntent(suggestion.intent_override) }),
    analysis: toAnalysisPart(suggestion.analysis),
    draft: toDraftPart(suggestion.draft),
  };
}

/**
 * Map a sent reply: the reply of a closed ticket, or the answer of `sendReply`.
 *
 * @param reply - A `ConsoleReplyView`.
 * @returns The body, who sent it, and when.
 */
export function toSentReply(reply: ConsoleReplyContract): SentReply {
  requireMembers(reply, ["body", "sent_by", "sent_at"]);
  return { body: reply.body, sentByName: reply.sent_by.display_name, sentAt: reply.sent_at };
}
