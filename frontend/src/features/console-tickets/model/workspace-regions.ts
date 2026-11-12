/**
 * Everything that the regions of the workspace derive from the ticket, built once per render
 * (TS-21): the state of each region, the warnings, the citation numbers, and the sources.
 */
import {
  getIntentAreaState,
  type IntentAreaState,
} from "@/features/console-tickets/model/intent-area";
import type { SuggestionWarning } from "@/features/console-tickets/model/reason-codes";
import {
  buildSources,
  numberCitedDocuments,
  type Source,
} from "@/features/console-tickets/model/sources";
import type { TicketWorkspace } from "@/features/console-tickets/model/workspace";
import {
  getReplyAreaState,
  getSidebarState,
  type ReplyAreaState,
  type SidebarState,
} from "@/features/console-tickets/model/workspace-state";

/** What the regions of the workspace show. */
export type WorkspaceRegions = {
  readonly intent: IntentAreaState;
  readonly reply: ReplyAreaState;
  readonly sidebar: SidebarState;
  /** The warnings of the analysis; empty without a ready analysis. */
  readonly warnings: readonly SuggestionWarning[];
  /** When the current suggestion started; the creation of the ticket without one. */
  readonly generatedAt: string;
  /** The citation number of each document version that the draft cites. */
  readonly numberByKey: ReadonlyMap<string, number>;
  /** The sources of the analysis, in the order of their rank. */
  readonly sources: readonly Source[];
};

/**
 * Build the regions of a ticket.
 *
 * @param workspace - The ticket.
 * @returns The state and the data of every region.
 */
export function buildWorkspaceRegions(workspace: TicketWorkspace): WorkspaceRegions {
  const reply = getReplyAreaState(workspace);
  const sidebar = getSidebarState(workspace);
  const analysis = sidebar.kind === "analysis" ? sidebar.analysis : undefined;
  const numberByKey = numberCitedDocuments(reply.kind === "draft" ? reply.draft : undefined);
  return {
    intent: getIntentAreaState(workspace),
    reply,
    sidebar,
    warnings: analysis?.warnings ?? [],
    generatedAt: workspace.suggestion?.createdAt ?? workspace.createdAt,
    numberByKey,
    sources: analysis === undefined ? [] : buildSources(analysis.documents, numberByKey),
  };
}
