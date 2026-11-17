/**
 * Which state each region of the workspace shows (console UI design, States and Flow), derived
 * from the ticket during render (TS-21). The UI computes no band, threshold, or routing: it reads
 * the statuses and reason codes that `backend` sent (UI-14, UI-39).
 */
import type { AiReasonCodeName, RecommendationName } from "@/design-system";
import { assertNever } from "@/features/backend-requests";
import type { ReadyAnalysis } from "@/features/console-tickets/model/analysis";
import type { DraftPart, NoDraft, ReadyDraft } from "@/features/console-tickets/model/draft";
import type {
  ReplyProposal,
  TicketEscalation,
} from "@/features/console-tickets/model/manager-handoff";
import type { SentReply, TicketWorkspace } from "@/features/console-tickets/model/workspace";

/** The reply area. */
export type ReplyAreaState =
  | { readonly kind: "sent"; readonly reply: SentReply }
  | {
      readonly kind: "proposal";
      readonly proposal: ReplyProposal;
      /** The ready AI draft, shown for comparison; absent when there is none. */
      readonly draft?: ReadyDraft;
    }
  | { readonly kind: "escalated"; readonly escalation: TicketEscalation }
  | { readonly kind: "manual_mode" }
  | { readonly kind: "ai_unavailable"; readonly reasonCode: AiReasonCodeName }
  | { readonly kind: "pending" }
  | { readonly kind: "draft"; readonly draft: ReadyDraft }
  | { readonly kind: "choose_intent" }
  | {
      readonly kind: "no_draft";
      readonly status: "abstained" | "escalation_recommended";
      readonly reasonCodes: readonly AiReasonCodeName[];
    };

/** The reply area when the AI made no draft: the choice of an intent, or the reason codes. */
export type NoDraftReplyState = Extract<
  ReplyAreaState,
  { readonly kind: "choose_intent" | "no_draft" }
>;

/** The AI sidebar. */
export type SidebarState =
  | { readonly kind: "manual_mode" }
  | { readonly kind: "loading" }
  | { readonly kind: "ai_unavailable"; readonly reasonCode: AiReasonCodeName }
  | {
      readonly kind: "analysis";
      readonly analysis: ReadyAnalysis;
      readonly recommendation: RecommendationName;
      /** The reason of a draft that failed after the analysis (`llm_unavailable`). */
      readonly draftFailure?: AiReasonCodeName;
      readonly staffNote?: string;
    };

/**
 * Choose the state of the reply area.
 *
 * @param workspace - The ticket.
 * @returns The sent reply of a closed ticket; the proposal of a ticket awaiting approval; the
 *   escalation of an escalated ticket without a ready draft; otherwise manual handling, the
 *   pending skeleton, the draft, the choice of intent (ESC-01), or the reason codes of a missing
 *   draft.
 */
export function getReplyAreaState(workspace: TicketWorkspace): ReplyAreaState {
  if (workspace.reply !== undefined) {
    return { kind: "sent", reply: workspace.reply };
  }
  return getManagerHandoffState(workspace) ?? getSuggestionReplyState(workspace);
}

/**
 * Read the ready draft that the reply area shows: the draft to review, or the AI draft next to a
 * proposal.
 *
 * @param reply - The state of the reply area.
 * @returns The ready draft, or undefined when the area shows none.
 */
export function getShownDraft(reply: ReplyAreaState): ReadyDraft | undefined {
  return reply.kind === "draft" || reply.kind === "proposal" ? reply.draft : undefined;
}

/**
 * Choose the state of a ticket that staff handed to a manager. An escalated ticket with a ready
 * draft shows the draft, because a reply then needs it as its basis; its escalation shows above.
 *
 * @param workspace - The ticket.
 * @returns The proposal while the ticket awaits approval, the escalation of an escalated ticket
 *   without a ready draft, or undefined.
 */
function getManagerHandoffState(workspace: TicketWorkspace): ReplyAreaState | undefined {
  const readyDraft = getReadyDraft(workspace);
  if (workspace.status === "awaiting_approval" && workspace.proposal !== undefined) {
    return {
      kind: "proposal",
      proposal: workspace.proposal,
      ...(readyDraft === undefined ? {} : { draft: readyDraft }),
    };
  }
  const escalation = workspace.status === "escalated" ? workspace.escalation : undefined;
  return escalation === undefined || readyDraft !== undefined
    ? undefined
    : { kind: "escalated", escalation };
}

/**
 * Read the ready draft of the current suggestion.
 *
 * @param workspace - The ticket.
 * @returns The draft when it is `draft_ready`; undefined otherwise.
 */
function getReadyDraft(workspace: TicketWorkspace): ReadyDraft | undefined {
  const draft = workspace.suggestion?.draft;
  return draft?.status === "draft_ready" ? draft : undefined;
}

/**
 * Choose the state of the reply area from the current suggestion.
 *
 * @param workspace - The ticket.
 * @returns Manual handling, the pending skeleton, the draft, the choice of intent, or the reason
 *   codes of a missing draft.
 */
function getSuggestionReplyState(workspace: TicketWorkspace): ReplyAreaState {
  const suggestion = workspace.suggestion;
  if (workspace.handlingMode === "manual" || suggestion === undefined) {
    return { kind: "manual_mode" };
  }
  if (suggestion.analysis.status === "unavailable") {
    return { kind: "ai_unavailable", reasonCode: suggestion.analysis.reasonCode };
  }
  return getDraftReplyState(suggestion.draft);
}

/**
 * Choose the state of the reply area from the draft part, once the analysis is not unavailable.
 *
 * @param draft - The draft part of the suggestion.
 * @returns The pending skeleton, the draft, the choice of intent, the reason codes, or manual
 *   handling after a failure of the draft.
 */
function getDraftReplyState(draft: DraftPart): ReplyAreaState {
  switch (draft.status) {
    case "pending":
      return { kind: "pending" };
    case "draft_ready":
      return { kind: "draft", draft };
    case "abstained":
    case "escalation_recommended":
      return getNoDraftState(draft.status, draft.reasonCodes);
    case "llm_unavailable":
      return { kind: "ai_unavailable", reasonCode: getDraftFailure(draft) };
    case "unavailable":
      return { kind: "ai_unavailable", reasonCode: draft.reasonCode };
    default:
      assertNever(draft);
  }
}

/**
 * Choose the state of the AI sidebar.
 *
 * @param workspace - The ticket.
 * @returns The manual-handling panel, the loading skeleton, "AI unavailable" with the reason, or
 *   the analysis with the recommendation and the staff note.
 */
export function getSidebarState(workspace: TicketWorkspace): SidebarState {
  const suggestion = workspace.suggestion;
  if (workspace.handlingMode === "manual" || suggestion === undefined) {
    return { kind: "manual_mode" };
  }
  const { analysis, draft } = suggestion;
  if (analysis.status === "pending") {
    return { kind: "loading" };
  }
  if (analysis.status === "unavailable") {
    return { kind: "ai_unavailable", reasonCode: analysis.reasonCode };
  }
  return {
    kind: "analysis",
    analysis,
    recommendation: getRecommendation(analysis),
    ...(draft.status === "llm_unavailable" ? { draftFailure: getDraftFailure(draft) } : {}),
    ...getStaffNote(draft),
  };
}

/**
 * Tell whether a part of the current suggestion is `pending`, while the workspace polls.
 *
 * @param workspace - The ticket.
 * @returns True while the analysis or the draft is `pending`.
 */
export function hasPendingPart(workspace: TicketWorkspace): boolean {
  const suggestion = workspace.suggestion;
  return (
    suggestion !== undefined &&
    (suggestion.analysis.status === "pending" || suggestion.draft.status === "pending")
  );
}

/**
 * Tell whether an analysis abstained for low confidence, so staff choose an intent (ESC-01).
 *
 * @param reasonCodes - The reason codes of the outcome.
 * @returns True when they hold `low_confidence`.
 */
export function isLowConfidence(reasonCodes: readonly AiReasonCodeName[]): boolean {
  return reasonCodes.includes("low_confidence");
}

/**
 * Name what the AI recommends.
 *
 * @param analysis - A ready analysis.
 * @returns The routing recommendation, or `choose_intent` for an abstention for low confidence.
 */
function getRecommendation(analysis: ReadyAnalysis): RecommendationName {
  if (analysis.recommendation === "abstain" && isLowConfidence(analysis.reasonCodes)) {
    return "choose_intent";
  }
  return analysis.recommendation;
}

/**
 * Read the reason of a draft that failed after the analysis.
 *
 * @param draft - An `llm_unavailable` draft outcome.
 * @returns Its first reason code, or `llm_unavailable` when it lists none.
 */
function getDraftFailure(draft: NoDraft): AiReasonCodeName {
  return draft.reasonCodes[0] ?? "llm_unavailable";
}

/**
 * Read the staff note of a draft part.
 *
 * @param draft - The draft part.
 * @returns The note as a member to spread, or nothing when the part has none.
 */
function getStaffNote(draft: DraftPart): { readonly staffNote?: string } {
  return "staffNote" in draft ? { staffNote: draft.staffNote } : {};
}

/**
 * Choose the state of a draft outcome without a draft.
 *
 * @param status - `abstained` or `escalation_recommended`.
 * @param reasonCodes - The reason codes of the outcome.
 * @returns The choice of intent for low confidence (UI-42), otherwise the reason codes.
 */
function getNoDraftState(
  status: "abstained" | "escalation_recommended",
  reasonCodes: readonly AiReasonCodeName[],
): ReplyAreaState {
  if (status === "abstained" && isLowConfidence(reasonCodes)) {
    return { kind: "choose_intent" };
  }
  return { kind: "no_draft", status, reasonCodes };
}
