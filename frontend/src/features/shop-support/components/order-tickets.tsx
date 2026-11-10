/**
 * The tickets of one order on its order page, oldest first (shop UI design, Support for this
 * order). `listShopTickets` returns them newest first, so the list is reversed, and Show earlier
 * tickets loads the next page.
 */
import { useEffect } from "react";
import { useLocation } from "react-router";

import {
  LoadMoreButton,
  PanelSection,
  presentationByShopTicketStatus,
  Skeleton,
  Stack,
  TicketItem,
  VisuallyHidden,
} from "@/design-system";
import {
  collectPageItems,
  FailureBanner,
  FailureState,
  getRequestFailure,
} from "@/features/backend-requests";
import type { TicketListQuery } from "@/features/shop-support/api/use-ticket-lists";
import {
  buildTicketAnchorId,
  readAnchorIdOfHash,
  type ShopTicket,
} from "@/features/shop-support/model/ticket";

/** Props of {@link OrderTickets}. */
export type OrderTicketsProps = {
  /** The infinite query of the order's tickets. */
  readonly query: TicketListQuery;
};

/**
 * Render the tickets of an order.
 *
 * @param props - The query of the order's tickets.
 * @returns The ticket section, a loading or error state, or nothing when there is no ticket.
 */
export function OrderTickets({ query }: OrderTicketsProps) {
  const failure = getRequestFailure(query.error);
  useFocusTicketOfAddress(query.data !== undefined);

  if (query.data === undefined && failure !== undefined) {
    return (
      <PanelSection>
        <FailureState
          title="Your tickets could not be loaded"
          failure={failure}
          headingLevel={2}
          isRetrying={query.isFetching}
          onRetry={() => {
            void query.refetch();
          }}
          actionSize="lg"
        />
      </PanelSection>
    );
  }
  if (query.data === undefined) {
    return (
      <PanelSection>
        <p role="status">
          <VisuallyHidden>Loading your tickets…</VisuallyHidden>
        </p>
        <Skeleton width="three-quarters" height="block" />
      </PanelSection>
    );
  }
  const tickets = collectPageItems(
    query.data.pages.map((page) => page.tickets),
    (ticket: ShopTicket) => ticket.ticketId,
  ).toReversed();
  if (tickets.length === 0) {
    return null;
  }
  const loadMoreFailure = query.isFetchNextPageError ? failure : undefined;

  return (
    <PanelSection>
      <Stack gap="6">
        {query.hasNextPage ? (
          <LoadMoreButton
            label="Show earlier tickets"
            isLoading={query.isFetchingNextPage}
            onLoadMore={() => {
              void query.fetchNextPage();
            }}
          />
        ) : null}
        {loadMoreFailure === undefined ? null : (
          <FailureBanner lead="Earlier tickets could not be loaded." failure={loadMoreFailure} />
        )}
        <Stack as="ul" gap="6" label="Tickets about this order">
          {tickets.map((ticket) => (
            <TicketItem
              key={ticket.ticketId}
              anchorId={buildTicketAnchorId(ticket.ticketId)}
              ticketId={ticket.ticketId}
              status={presentationByShopTicketStatus[ticket.status]}
              message={ticket.message}
              createdAt={ticket.createdAt}
              {...(ticket.reply === undefined ? {} : { reply: ticket.reply })}
            />
          ))}
        </Stack>
      </Stack>
    </PanelSection>
  );
}

/**
 * Move the focus to the ticket that the address names, once the tickets are shown. A link from
 * Support opens the order page "at that ticket" (shop UI design, Screens). Focusing the element
 * also scrolls it into view.
 *
 * @param isShown - True once the tickets are rendered.
 */
function useFocusTicketOfAddress(isShown: boolean): void {
  const { hash } = useLocation();
  useEffect(() => {
    const anchorId = readAnchorIdOfHash(hash);
    if (isShown && anchorId !== undefined) {
      document.getElementById(anchorId)?.focus();
    }
  }, [isShown, hash]);
}
