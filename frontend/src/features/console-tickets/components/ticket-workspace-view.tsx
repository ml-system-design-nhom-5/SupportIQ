/**
 * The ticket workspace of a loaded ticket (console UI design, Layout, Workspace regions, and
 * States): the header with the order chip, the banners, the customer message, the intent, the
 * reply area, and the AI sidebar. Every region derives its state from the ticket during render
 * (TS-21). The order popover and the KB side sheet open from the header, the sources, and the
 * citation markers. Staff correct the intent from the strip; the reply area keeps the draft that
 * the correction made outdated while the new one generates (UI-22). Send reply opens the
 * confirmation, and only its Send reply sends the reply (UI-17, FR-04). After an action that
 * replaces the element with the focus, the focus moves to what replaced it (UI-30).
 */
import { useState } from "react";

import { WorkspaceLayout } from "@/design-system";
import type { RequestFailure } from "@/features/backend-requests";
import { useCreateSuggestion } from "@/features/console-tickets/api/use-create-suggestion";
import { AiSidebar } from "@/features/console-tickets/components/ai-sidebar";
import { CustomerMessagePanel } from "@/features/console-tickets/components/customer-message-panel";
import { DeveloperDetailsPanel } from "@/features/console-tickets/components/developer-details-panel";
import { ESCALATED_HEADING_ID } from "@/features/console-tickets/components/escalated-panel";
import {
  IntentSection,
  OTHER_INTENT_ID,
} from "@/features/console-tickets/components/intent-section";
import { KbDocumentSheet } from "@/features/console-tickets/components/kb-document-sheet";
import { PENDING_DRAFT_HEADING_ID } from "@/features/console-tickets/components/pending-draft-panel";
import { PROPOSAL_HEADING_ID } from "@/features/console-tickets/components/proposal-panel";
import { ReplyArea } from "@/features/console-tickets/components/reply-area";
import { ReplyDialogs } from "@/features/console-tickets/components/reply-dialogs";
import { SENT_REPLY_HEADING_ID } from "@/features/console-tickets/components/sent-reply-panel";
import type { OrderPopoverState } from "@/features/console-tickets/components/ticket-order-chip";
import { useFocusRequest } from "@/features/console-tickets/components/use-focus-request";
import { useReplyComposer } from "@/features/console-tickets/components/use-reply-composer";
import { WorkspaceBanners } from "@/features/console-tickets/components/workspace-banners";
import { WorkspaceHeader } from "@/features/console-tickets/components/workspace-header";
import { toComposerTicket } from "@/features/console-tickets/model/composer-ticket";
import { type SourceSelection, toSourceSelection } from "@/features/console-tickets/model/sources";
import type { TicketWorkspace } from "@/features/console-tickets/model/workspace";
import { buildWorkspaceRegions } from "@/features/console-tickets/model/workspace-regions";
import { useSignedInRole } from "@/features/session";

/** The ID of the ticket heading, which takes the focus when the opener of a dialog is gone. */
const WORKSPACE_HEADING_ID = "ticket-workspace-heading";

/** A source open in the side sheet, and the element that opened it. */
type OpenedSource = {
  readonly selection: SourceSelection;
  readonly opener: HTMLElement;
};

/** Props of {@link TicketWorkspaceView}. */
type TicketWorkspaceViewProps = {
  /** The ticket of the address: the key of its workspace query, and the ticket of every write. */
  readonly ticketId: string;
  readonly workspace: TicketWorkspace;
  /** The failure of `recordTicketView`, after its automatic retries. */
  readonly viewFailure?: RequestFailure;
  /** The failure of the last reload while the ticket polls. */
  readonly refreshFailure?: RequestFailure;
};

/**
 * Render the workspace.
 *
 * @param props - The ticket of the address, the ticket, and the failures of its view and of its
 *   last reload.
 * @returns The workspace and, while a source is open, its side sheet.
 */
export function TicketWorkspaceView({
  ticketId,
  workspace,
  viewFailure,
  refreshFailure,
}: TicketWorkspaceViewProps) {
  const [orderPopover, setOrderPopover] = useState<OrderPopoverState>({ isOpen: false });
  const [openedSource, setOpenedSource] = useState<OpenedSource | undefined>(undefined);
  const regions = buildWorkspaceRegions(workspace);
  const requestFocus = useFocusRequest();
  const role = useSignedInRole();
  const suggestionRequests = useCreateSuggestion(ticketId, workspace, (request) => {
    requestFocus(request === "retry" ? PENDING_DRAFT_HEADING_ID : OTHER_INTENT_ID);
  });
  const composer = useReplyComposer(
    ticketId,
    toComposerTicket(workspace, regions, {
      isSuggestionRequested: suggestionRequests.isSending,
      isManager: role === "manager",
    }),
    {
      onSent: () => {
        requestFocus(SENT_REPLY_HEADING_ID);
      },
      onSubmitted: () => {
        requestFocus(PROPOSAL_HEADING_ID);
      },
      onEscalated: () => {
        requestFocus(ESCALATED_HEADING_ID);
      },
    },
  );
  const hasBanners =
    workspace.isAuthorityRequired || viewFailure !== undefined || refreshFailure !== undefined;
  const openSource = (selection: SourceSelection, opener: HTMLElement) => {
    setOpenedSource({ selection, opener });
  };
  // The chip opens the popover with the focus returning to it; a closing keeps where it returns.
  const changeOrderOpen = (isOpen: boolean) => {
    setOrderPopover((current) => (isOpen ? { isOpen } : { ...current, isOpen }));
  };
  return (
    <>
      <title>{`Ticket ${workspace.ticketId} · Console · SupportIQ`}</title>
      <WorkspaceLayout
        header={
          <WorkspaceHeader
            headingId={WORKSPACE_HEADING_ID}
            workspace={workspace}
            orderPopover={orderPopover}
            onOrderOpenChange={changeOrderOpen}
          />
        }
        banners={
          hasBanners ? (
            <WorkspaceBanners
              isAuthorityRequired={workspace.isAuthorityRequired}
              viewFailure={viewFailure}
              refreshFailure={refreshFailure}
            />
          ) : undefined
        }
        main={
          <>
            <CustomerMessagePanel
              customerName={workspace.customerName}
              body={workspace.message.body}
              sentAt={workspace.message.createdAt}
            />
            <IntentSection
              state={regions.intent}
              isSending={suggestionRequests.isSending}
              correctionFailure={suggestionRequests.correctionFailure}
              onCorrectIntent={suggestionRequests.correctIntent}
            />
            <ReplyArea
              state={regions.reply}
              composer={composer}
              {...(workspace.status === "escalated" && workspace.escalation !== undefined
                ? { escalation: workspace.escalation }
                : {})}
              aiRequests={{
                ...suggestionRequests,
                canRetry: workspace.allowedActions.has("retry_suggestion"),
              }}
              draftContext={{
                warnings: regions.warnings,
                generatedAt: regions.generatedAt,
                citations: {
                  numberByKey: regions.numberByKey,
                  sourceByKey: new Map(regions.sources.map((source) => [source.key, source])),
                  orderId: workspace.order?.orderId,
                  onOpenSource: openSource,
                  onOpenOrder: (opener) => {
                    setOrderPopover({
                      isOpen: true,
                      returnFocus: { opener, fallbackId: WORKSPACE_HEADING_ID },
                    });
                  },
                },
              }}
            />
          </>
        }
        sidebar={
          <>
            <AiSidebar
              state={regions.sidebar}
              sources={regions.sources}
              onOpenSource={(source, opener) => {
                openSource(toSourceSelection(source, source), opener);
              }}
            />
            <DeveloperDetailsPanel suggestion={workspace.suggestion} />
          </>
        }
      />
      <ReplyDialogs composer={composer} ticket={workspace} fallbackId={WORKSPACE_HEADING_ID} />
      {openedSource === undefined ? null : (
        <KbDocumentSheet
          selection={openedSource.selection}
          returnFocus={{ opener: openedSource.opener, fallbackId: WORKSPACE_HEADING_ID }}
          onClose={() => {
            setOpenedSource(undefined);
          }}
        />
      )}
    </>
  );
}
