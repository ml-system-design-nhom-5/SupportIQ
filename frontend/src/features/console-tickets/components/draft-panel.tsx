/**
 * The AI draft in the reply area (console UI design, Draft editing and citations; UI-18): the
 * warnings at the top, next to the action they block, and the draft below them. The panel carries
 * the `ai` marker (UI-13).
 */
import { Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import {
  Panel,
  PanelHeader,
  PanelSection,
  presentationByAiReasonCode,
  presentationByAiStatus,
  RelativeTime,
  Stack,
  StatusBadge,
  Text,
  WarningList,
} from "@/design-system";
import type { SuggestionWarning } from "@/features/console-tickets/model/reason-codes";

/** Props of {@link DraftPanel}. */
type DraftPanelProps = {
  readonly warnings: readonly SuggestionWarning[];
  /** When the suggestion started, as an RFC 3339 timestamp. */
  readonly generatedAt: string;
  /** The draft text with its citation markers. */
  readonly children: ReactNode;
};

/**
 * Render the draft panel.
 *
 * @param props - The warnings, the time, and the draft.
 * @returns The panel.
 */
export function DraftPanel({ warnings, generatedAt, children }: DraftPanelProps) {
  return (
    <Panel density="compact" as="section" label="AI draft" tone="ai">
      <PanelHeader
        icon={Sparkles}
        level={2}
        title="AI draft"
        trailing={
          <Stack direction="row" gap="2" align="center">
            <StatusBadge presentation={presentationByAiStatus.draft_ready} />
            <Text tone="muted">
              Generated <RelativeTime timestamp={generatedAt} />
            </Text>
          </Stack>
        }
      />
      {warnings.length === 0 ? null : (
        <PanelSection>
          <WarningList
            warnings={warnings.map((warning) => ({
              warningId: warning.warningId,
              title: presentationByAiReasonCode[warning.reasonCode].label,
              description: warning.text,
            }))}
          />
        </PanelSection>
      )}
      <PanelSection>{children}</PanelSection>
    </Panel>
  );
}
