/**
 * The Support screen (`/shop/support`, shop UI design): every ticket of the customer, newest
 * first, with Show more tickets while there is a next page (CON-14). Each row opens its order page
 * at that ticket.
 */
import { Info } from "lucide-react";

import {
  InlineMessage,
  LoadMoreButton,
  PageHeader,
  RowList,
  Skeleton,
  Stack,
  StateMessage,
  VisuallyHidden,
} from "@/design-system";
import { collectPageItems, FailureBanner, getRequestFailure } from "@/features/backend-requests";
import { AreaLoadFailure } from "@/features/session";
import { buildShopTitle } from "@/features/shop-catalog";
import { useAllTickets } from "@/features/shop-support/api/use-ticket-lists";
import { SupportTicketRow } from "@/features/shop-support/components/support-ticket-row";
import type { ShopTicket } from "@/features/shop-support/model/ticket";

/**
 * Render the Support screen.
 *
 * @returns The screen in the state of its data.
 */
export function SupportPage() {
  const ticketsQuery = useAllTickets();
  const failure = getRequestFailure(ticketsQuery.error);

  if (ticketsQuery.data === undefined && failure !== undefined) {
    return (
      <AreaLoadFailure
        area="shop"
        title="Your messages could not be loaded"
        failure={failure}
        headingLevel={1}
        isRetrying={ticketsQuery.isFetching}
        onRetry={() => {
          void ticketsQuery.refetch();
        }}
      />
    );
  }
  const tickets =
    ticketsQuery.data === undefined
      ? undefined
      : collectPageItems(
          ticketsQuery.data.pages.map((page) => page.tickets),
          (ticket: ShopTicket) => ticket.ticketId,
        );
  const loadMoreFailure = ticketsQuery.isFetchNextPageError ? failure : undefined;

  return (
    <Stack gap="6">
      <title>{buildShopTitle("Support")}</title>
      <PageHeader title="Support" />
      <InlineMessage tone="muted" icon={Info}>
        Your messages to support, newest first. Each one opens on the page of its order.
      </InlineMessage>
      {tickets === undefined ? <SupportLoading /> : <SupportTicketList tickets={tickets} />}
      {loadMoreFailure === undefined ? null : (
        <FailureBanner lead="More messages could not be loaded." failure={loadMoreFailure} />
      )}
      {ticketsQuery.hasNextPage ? (
        <LoadMoreButton
          label="Show more messages"
          isLoading={ticketsQuery.isFetchingNextPage}
          onLoadMore={() => {
            void ticketsQuery.fetchNextPage();
          }}
        />
      ) : null}
    </Stack>
  );
}

/**
 * Render the loading state of the list (UI-24).
 *
 * @returns Skeleton rows.
 */
function SupportLoading() {
  return (
    <Stack gap="3">
      <p role="status">
        <VisuallyHidden>Loading your messages…</VisuallyHidden>
      </p>
      <Skeleton width="full" height="block" />
      <Skeleton width="full" height="block" />
    </Stack>
  );
}

/**
 * Render the tickets of the loaded pages.
 *
 * @param props - The tickets.
 * @returns The list, or the empty state.
 */
function SupportTicketList({ tickets }: { readonly tickets: readonly ShopTicket[] }) {
  if (tickets.length === 0) {
    return (
      <StateMessage icon={Info} headingLevel={2} title="You have not written to support yet." />
    );
  }
  return (
    <RowList label="Your messages to support">
      {tickets.map((ticket) => (
        <SupportTicketRow key={ticket.ticketId} ticket={ticket} />
      ))}
    </RowList>
  );
}
