/**
 * The contract types of the console ticket operations, for the mappings in model/ (TS-09).
 */
import type { components } from "@/api/generated/backend";

type Schemas = components["schemas"];

/** `TicketSummary`: one ticket of a console queue. */
export type TicketSummaryContract = Schemas["TicketSummary"];

/** `TicketSummaryPage`: one page of `listConsoleTickets`. */
export type TicketSummaryPageContract = Schemas["TicketSummaryPage"];

/** `ConsoleTicketStatus`: the status of the tickets that a queue lists. */
export type ConsoleTicketStatusContract = Schemas["ConsoleTicketStatus"];

/** `TicketWorkspace`: the body of `getConsoleTicket`. */
export type TicketWorkspaceContract = Schemas["TicketWorkspace"];

/** `ConsoleOrderView`: the order of a ticket. */
export type ConsoleOrderContract = Schemas["ConsoleOrderView"];

/** `ConsoleOtherOrderView`: another order of the same customer. */
export type ConsoleOtherOrderContract = Schemas["ConsoleOtherOrderView"];

/** `ShopOrderLine`: one line of an order. */
export type OrderLineContract = Schemas["ShopOrderLine"];

/** `SuggestionView`: the current suggestion of a ticket. */
export type SuggestionContract = Schemas["SuggestionView"];

/** `AnalysisPart`: the analysis part of a suggestion. */
export type AnalysisPartContract = Schemas["AnalysisPart"];

/** `ReadyAnalysisPart`: an analysis that `ai-service` returned. */
export type ReadyAnalysisContract = Schemas["ReadyAnalysisPart"];

/** `DraftPart`: the draft part of a suggestion. */
export type DraftPartContract = Schemas["DraftPart"];

/** `ReadyDraftPart`: a draft for staff to review. */
export type ReadyDraftContract = Schemas["ReadyDraftPart"];

/** `CitationView`: a citation of a draft. */
export type CitationContract = Schemas["CitationView"];

/** `RankedDocument`: a KB document version that retrieval found. */
export type RankedDocumentContract = Schemas["RankedDocument"];

/** `IntentLabel`: one of the 46 intent labels. */
export type IntentLabelContract = Schemas["IntentLabel"];

/** `ConsoleReplyView`: the reply sent to the customer. */
export type ConsoleReplyContract = Schemas["ConsoleReplyView"];

/** `KbDocumentVersion`: the body of `getConsoleKbDocumentVersion`. */
export type KbDocumentVersionContract = Schemas["KbDocumentVersion"];

/** `SendReplyRequest`: the body of `sendReply`, discriminated by `basis`. */
export type SendReplyRequestContract = Schemas["SendReplyRequest"];

/** `StaffReasonCode`: why staff edited, rejected, or escalated a draft (ADR-0006). */
export type StaffReasonCodeContract = Schemas["StaffReasonCode"];

/** `TicketAction`: an action that `backend` allows the caller on a ticket now. */
export type TicketActionContract = Schemas["TicketAction"];

/** `ReplyProposalView`: a reply that staff prepared for a manager to send. */
export type ReplyProposalContract = Schemas["ReplyProposalView"];

/** `EscalationView`: the escalation of a ticket to the manager queue. */
export type EscalationContract = Schemas["EscalationView"];

/** `CreateReplyProposalRequest`: the body of `createReplyProposal`, discriminated by `basis`. */
export type CreateReplyProposalRequestContract = Schemas["CreateReplyProposalRequest"];

/** `CreateEscalationRequest`: the body of `createEscalation`. */
export type CreateEscalationRequestContract = Schemas["CreateEscalationRequest"];

/** `StaffMemberView`: the staff member of a proposal or an escalation. */
export type StaffMemberContract = Schemas["StaffMemberView"];

/** `ReplyProposalBasis`: what a proposal is based on. */
export type ReplyProposalBasisContract = Schemas["ReplyProposalBasis"];
