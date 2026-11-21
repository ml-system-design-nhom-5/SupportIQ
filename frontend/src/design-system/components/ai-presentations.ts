/**
 * The one presentation of each AI reason code and of each recommendation of the AI sidebar
 * (UI-11, UI-12; console UI design, Workspace regions). Labels use business language without ML
 * jargon (UI-28). A reason code that this version does not know is an unspecified reason (CON-22).
 */
import {
  CircleArrowUp,
  CircleHelp,
  CircleX,
  Clock,
  Shield,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

import type { StatusPresentation } from "@/design-system/components/status-presentations";

/** Presentation of a condition that needs attention. */
function needsAttention(label: string): StatusPresentation {
  return { tone: "warning", icon: TriangleAlert, label };
}

/** Presentation of a failure of the AI. */
function aiFailure(label: string): StatusPresentation {
  return { tone: "danger", icon: CircleX, label };
}

/** AI reason codes (`AiReasonCode` of the contract). */
export const presentationByAiReasonCode: Readonly<Record<AiReasonCodeName, StatusPresentation>> = {
  low_confidence: needsAttention("Low confidence"),
  signal_disagreement: needsAttention("Intent and sources disagree"),
  out_of_scope_intent: needsAttention("Request out of scope"),
  human_agent_requested: { tone: "warning", icon: CircleArrowUp, label: "Human agent requested" },
  requires_authority: { tone: "warning", icon: Shield, label: "Requires authority" },
  no_valid_document: needsAttention("No valid document"),
  only_expired_documents: { tone: "warning", icon: Clock, label: "Only expired documents" },
  conflicting_sources: needsAttention("Conflicting sources"),
  missing_information: needsAttention("Missing information"),
  source_review_overdue: { tone: "warning", icon: Clock, label: "Source review overdue" },
  grounding_failed: aiFailure("Draft not supported by its sources"),
  llm_unavailable: aiFailure("Drafting failed"),
  llm_invalid_output: aiFailure("Draft failed the checks"),
  budget_exceeded: aiFailure("Time limit reached"),
  ai_service_unavailable: aiFailure("AI service unavailable"),
  pseudonymization_failed: aiFailure("Personal data could not be hidden"),
  unknown: { tone: "neutral", icon: CircleHelp, label: "Unspecified reason" },
};

/** What the AI recommends, as the AI sidebar names it (console UI design, mockups). */
export const presentationByRecommendation: Readonly<
  Record<RecommendationName, StatusPresentation>
> = {
  draft: { tone: "ai", icon: Sparkles, label: "Reply with a draft" },
  choose_intent: { tone: "ai", icon: Sparkles, label: "Choose an intent" },
  abstain: { tone: "ai", icon: Sparkles, label: "Handle manually" },
  escalate: { tone: "ai", icon: Sparkles, label: "Recommend escalation" },
};

/** An AI reason code, or `unknown` for a code that this version does not know. */
export type AiReasonCodeName =
  | "low_confidence"
  | "signal_disagreement"
  | "out_of_scope_intent"
  | "human_agent_requested"
  | "requires_authority"
  | "no_valid_document"
  | "only_expired_documents"
  | "conflicting_sources"
  | "missing_information"
  | "source_review_overdue"
  | "grounding_failed"
  | "llm_unavailable"
  | "llm_invalid_output"
  | "budget_exceeded"
  | "ai_service_unavailable"
  | "pseudonymization_failed"
  | "unknown";

/**
 * A recommendation of the AI: the routing recommendation (`RoutingRecommendation`, an unknown value
 * is `abstain`), and `choose_intent` for an abstention for low confidence (ESC-01, UI-42).
 */
export type RecommendationName = "draft" | "choose_intent" | "abstain" | "escalate";
