/**
 * Follow the progress of the current suggestion while a part is `pending` (ADR-0022, statements
 * 6 and 7; console UI design, Flow). The workspace listens to the stream of the ticket and loads
 * again with `getConsoleTicket` after each event, which restores the pseudonyms and checks the
 * role. When the stream cannot start, ends for good, or sends no first event, the workspace loads
 * once, then every 30 s, and opens a new stream after a load that succeeds. A load after an event
 * that fails starts the same poll.
 */
import type { QueryObserverResult } from "@tanstack/react-query";
import { use, useEffect, useState } from "react";

import {
  buildSuggestionEventsPath,
  CLOSED_READY_STATE,
  EventSourceContext,
  type OpenEventSource,
  SUGGESTION_EVENT,
  type SuggestionEventSource,
} from "@/features/console-tickets/api/suggestion-events";
import {
  FIRST_EVENT_TIMEOUT_MS,
  WORKSPACE_FALLBACK_POLLING_INTERVAL_MS,
} from "@/features/console-tickets/model/polling";
import {
  canFollowProgress,
  parseSuggestionProgress,
} from "@/features/console-tickets/model/suggestion-progress";
import type { TicketWorkspace } from "@/features/console-tickets/model/workspace";

/** Loads the workspace again. */
type ReloadWorkspace = () => Promise<QueryObserverResult<TicketWorkspace>>;

/** The part of the workspace query that the progress uses. */
export type ProgressWorkspaceQuery = {
  readonly data: TicketWorkspace | undefined;
  readonly refetch: ReloadWorkspace;
};

/**
 * Follow the progress of the suggestion of a workspace.
 *
 * @param ticketId - The ticket of the workspace.
 * @param workspaceQuery - The loaded workspace, and how to load it again.
 * @throws Error when no composition root provides the opener of the stream.
 */
export function useSuggestionProgress(ticketId: string, workspaceQuery: ProgressWorkspaceQuery) {
  const openEventSource = useEventSourceOpener();
  // The suggestion whose stream failed: the workspace polls for it instead.
  const [failedSuggestionId, setFailedSuggestionId] = useState<string | undefined>(undefined);
  const { data: workspace, refetch: reload } = workspaceQuery;
  const followedId =
    workspace !== undefined && canFollowProgress(workspace)
      ? workspace.suggestion?.suggestionId
      : undefined;
  const isPolling = followedId !== undefined && followedId === failedSuggestionId;
  useEffect(() => {
    if (followedId === undefined || isPolling) {
      return;
    }
    return followStream(openEventSource(buildSuggestionEventsPath(ticketId)), reload, () => {
      setFailedSuggestionId(followedId);
    });
  }, [openEventSource, ticketId, followedId, isPolling, reload]);
  useEffect(() => {
    if (!isPolling) {
      return;
    }
    const timer = setInterval(() => {
      // "After the next successful read" (statement 7) is read as the next poll, not the load
      // right after the failure, so a stream that keeps failing is tried at most every 30 s.
      void reload().then((result) => {
        if (result.isSuccess) {
          setFailedSuggestionId(undefined);
        }
      });
    }, WORKSPACE_FALLBACK_POLLING_INTERVAL_MS);
    return () => {
      clearInterval(timer);
    };
  }, [isPolling, reload]);
}

/**
 * Listen to a stream until it fails or no part is `pending` any more.
 *
 * @param source - The stream that the browser opened.
 * @param reload - Loads the workspace again.
 * @param onFailure - Called when the stream fails, or when a load after an event fails.
 * @returns Closes the stream.
 */
function followStream(
  source: SuggestionEventSource,
  reload: ReloadWorkspace,
  onFailure: () => void,
): () => void {
  let hasEvent = false;
  const fail = () => {
    clearTimeout(firstEventTimer);
    source.close();
    // A stream that ends at once may be a `204`: nothing is pending any more. One load tells.
    void reload();
    onFailure();
  };
  const firstEventTimer = setTimeout(fail, FIRST_EVENT_TIMEOUT_MS);
  source.addEventListener(SUGGESTION_EVENT, (event) => {
    hasEvent = true;
    clearTimeout(firstEventTimer);
    reloadAfterEvent(reload, onFailure);
    const progress =
      typeof event.data === "string" ? parseSuggestionProgress(event.data) : undefined;
    if (progress?.hasPendingPart === false) {
      source.close();
    }
  });
  source.addEventListener("error", () => {
    // After its first event, a stream that ends is connected again by the browser, such as at its
    // maximum length. A stream that the browser closed, or that ended before its first event, has
    // failed: a `204`, a refusal, or a proxy that cuts it off.
    if (source.readyState === CLOSED_READY_STATE || !hasEvent) {
      fail();
    }
  });
  return () => {
    clearTimeout(firstEventTimer);
    source.close();
  };
}

/**
 * Load the workspace again after an event. A load that fails starts the fallback poll, as a stream
 * that fails does (ADR-0022, statement 7): the workspace still shows the state from before the
 * event, and after the last event no stream is left to load it again.
 *
 * @param reload - Loads the workspace again.
 * @param onFailure - Called when the load fails.
 */
function reloadAfterEvent(reload: ReloadWorkspace, onFailure: () => void): void {
  void reload().then((result) => {
    if (!result.isSuccess) {
      onFailure();
    }
  });
}

/**
 * Read the opener of the stream.
 *
 * @returns The opener that the composition root provides.
 * @throws Error when there is none.
 */
function useEventSourceOpener(): OpenEventSource {
  const openEventSource = use(EventSourceContext);
  if (openEventSource === null) {
    throw new Error("useSuggestionProgress needs EventSourceContext.");
  }
  return openEventSource;
}
