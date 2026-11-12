/**
 * The ticket workspace of a loaded ticket (console UI design, Layout, Workspace regions, and
 * States): the header with the order chip, the banners, the customer message, the intent, the
 * reply area, and the AI sidebar. Every region derives its state from the ticket during render
 * (TS-21). The order popover and the KB side sheet open from the header, the sources, and the
 * citation markers.
 */
import { useState } from "react";

import { WorkspaceLayout } from "@/design-system";
import type { RequestFailure } from "@/features/backend-requests";
import { AiSidebar } from "@/features/console-tickets/components/ai-sidebar";
import { CustomerMessagePanel } from "@/features/console-tickets/components/customer-message-panel";
import { IntentSection } from "@/features/console-tickets/components/intent-section";
import { KbDocumentSheet } from "@/features/console-tickets/components/kb-document-sheet";
import { ReplyArea } from "@/features/console-tickets/components/reply-area";
import type { OrderPopoverState } from "@/features/console-tickets/components/ticket-order-chip";
import { WorkspaceBanners } from "@/features/console-tickets/components/workspace-banners";
import { WorkspaceHeader } from "@/features/console-tickets/components/workspace-header";
import { type SourceSelection, toSourceSelection } from "@/features/console-tickets/model/sources";
import type { TicketWorkspace } from "@/features/console-tickets/model/workspace";
import { buildWorkspaceRegions } from "@/features/console-tickets/model/workspace-regions";

/** The ID of the ticket heading, which takes the focus when the opener of a sheet or popover is gone. */
const WORKSPACE_HEADING_ID = "ticket-workspace-heading";

/** A source open in the side sheet, and the element that opened it. */
type OpenedSource = {
  readonly selection: SourceSelection;
  readonly opener: HTMLElement;
};

/** Props of {@link TicketWorkspaceView}. */
type TicketWorkspaceViewProps = {
  readonly workspace: TicketWorkspace;
  /** The failure of `recordTicketView`, after its automatic retries. */
  readonly viewFailure?: RequestFailure;
  /** The failure of the last reload while the ticket polls. */
  readonly refreshFailure?: RequestFailure;
};

/**
 * Render the workspace.
 *
 * @param props - The ticket and the failures of its view and of its last reload.
 * @returns The workspace and, while a source is open, its side sheet.
 */
export function TicketWorkspaceView({
  workspace,
  viewFailure,
  refreshFailure,
}: TicketWorkspaceViewProps) {
  const [orderPopover, setOrderPopover] = useState<OrderPopoverState>({ isOpen: false });
  const [openedSource, setOpenedSource] = useState<OpenedSource | undefined>(undefined);
  const regions = buildWorkspaceRegions(workspace);
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
            <IntentSection state={regions.intent} />
            <ReplyArea
              state={regions.reply}
              draftContext={{
                warnings: regions.warnings,
                generatedAt: regions.generatedAt,
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
              }}
            />
          </>
        }
        sidebar={
          <AiSidebar
            state={regions.sidebar}
            sources={regions.sources}
            onOpenSource={(source, opener) => {
              openSource(toSourceSelection(source, source), opener);
            }}
          />
        }
      />
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
