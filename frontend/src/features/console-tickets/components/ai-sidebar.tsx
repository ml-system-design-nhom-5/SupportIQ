/**
 * The AI sidebar (console UI design, Workspace regions): the recommendation with its reason codes,
 * the staff note, and the sources; "AI unavailable" with the reason after an AI failure; and the
 * manual-handling panel in manual mode, so the layout does not move (UI-15). The workspace adds
 * the developer details below them in dev mode (developer-details-panel.tsx).
 */
import { CircleX, User } from "lucide-react";

import {
  Panel,
  PanelHeader,
  PanelSection,
  presentationByAiReasonCode,
  presentationByAiStatus,
  Stack,
  StatusBadge,
  Text,
} from "@/design-system";
import { assertNever } from "@/features/backend-requests";
import { RecommendationPanel } from "@/features/console-tickets/components/recommendation-panel";
import { SidebarLoading } from "@/features/console-tickets/components/sidebar-loading";
import { SourcesPanel } from "@/features/console-tickets/components/sources-panel";
import { StaffNotePanel } from "@/features/console-tickets/components/staff-note-panel";
import { describeAiUnavailable } from "@/features/console-tickets/model/manual-handling";
import type { Source } from "@/features/console-tickets/model/sources";
import type { SidebarState } from "@/features/console-tickets/model/workspace-state";

/** Props of {@link AiSidebar}. */
type AiSidebarProps = {
  readonly state: SidebarState;
  readonly sources: readonly Source[];
  readonly onOpenSource: (source: Source, opener: HTMLElement) => void;
};

/**
 * Render the AI sidebar.
 *
 * @param props - The state, the sources, and the handler that opens one.
 * @returns The panels of the state.
 */
export function AiSidebar({ state, sources, onOpenSource }: AiSidebarProps) {
  switch (state.kind) {
    case "manual_mode":
      return (
        <Panel density="compact">
          <PanelHeader icon={User} level={2} title="Manual handling" />
          <PanelSection>
            <Text>This ticket is handled without AI suggestions, so the AI panels stay empty.</Text>
          </PanelSection>
        </Panel>
      );
    case "loading":
      return <SidebarLoading />;
    case "ai_unavailable":
      return (
        <Panel density="compact" as="section" label="AI recommendation">
          <PanelHeader
            icon={CircleX}
            level={2}
            title="AI recommendation"
            trailing={<StatusBadge presentation={presentationByAiStatus.unavailable} />}
          />
          <PanelSection>
            <Text>{describeAiUnavailable(state.reasonCode)}</Text>
            <Text tone="muted">Sign-in, ticket viewing, and manual replies keep working.</Text>
            <Stack direction="row">
              <StatusBadge presentation={presentationByAiReasonCode[state.reasonCode]} />
            </Stack>
          </PanelSection>
        </Panel>
      );
    case "analysis":
      return (
        <>
          <RecommendationPanel
            recommendation={state.recommendation}
            reasonCodes={state.analysis.reasonCodes}
            {...(state.draftFailure === undefined ? {} : { draftFailure: state.draftFailure })}
          />
          {state.staffNote === undefined ? null : <StaffNotePanel note={state.staffNote} />}
          <SourcesPanel sources={sources} onOpenSource={onOpenSource} />
        </>
      );
    default:
      assertNever(state);
  }
}
