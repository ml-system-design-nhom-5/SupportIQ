/**
 * The texts of manual handling (UI-26; console UI design, States): why the AI did not help, the
 * manual-process instructions, and the reminder to route refund decisions and disputes to a
 * manager. When the AI is down, nothing flags a ticket, so the reminder and staff judgment are the
 * only control (contracts v1 design, Authority rule).
 */
import type { AiReasonCodeName } from "@/design-system";

/**
 * The manual-process instructions. The team provides the final text (console UI design, Open
 * questions); this neutral line stands in for it and states no policy.
 */
export const MANUAL_PROCESS_INSTRUCTIONS =
  "Handle this ticket without AI help: read the message and the order, then write the reply yourself.";

/** The bold start of the reminder (console UI design, States). */
export const MANUAL_REMINDER_LEAD = "Refund decision or dispute?";

/** The rest of the reminder. */
export const MANUAL_REMINDER_TEXT =
  "Do not decide it here. Use Submit for approval, so a manager sends the reply.";

/** Why a ticket is handled manually after an AI failure, by the reason code of the failure. */
const unavailableTextByReasonCode: Readonly<Partial<Record<AiReasonCodeName, string>>> = {
  ai_service_unavailable:
    "The AI service did not answer, so there is no analysis, draft, or source.",
  pseudonymization_failed:
    "Personal data in the message could not be hidden, so nothing was sent to the AI.",
};

/** Why a ticket is handled manually after any other AI failure. */
const GENERAL_UNAVAILABLE_TEXT = "The AI could not write a draft for this ticket.";

/**
 * Say why the AI could not help.
 *
 * @param reasonCode - The reason code of the failure.
 * @returns A plain-language sentence for the sidebar and the reply area (UI-25).
 */
export function describeAiUnavailable(reasonCode: AiReasonCodeName): string {
  return unavailableTextByReasonCode[reasonCode] ?? GENERAL_UNAVAILABLE_TEXT;
}
