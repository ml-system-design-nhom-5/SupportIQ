/**
 * Support for this order (shop UI design): the tickets of the order and the message box. Send
 * message creates a ticket with an `Idempotency-Key` that stays with the text until it is sent
 * (TS-29, shop UI design, Flow). After sending, the box empties, a banner confirms it, and the new
 * ticket shows as Received. When sending fails, the text stays in the box.
 */
import { LifeBuoy } from "lucide-react";
import { useState } from "react";

import { MessageBox, Panel, PanelHeader, PanelSection, Stack, StatusBanner } from "@/design-system";
import {
  describeFailure,
  FailureBanner,
  getRequestFailure,
  isWriteOutcomeUnknown,
  type RequestFailure,
  useCreateIdempotencyKey,
} from "@/features/backend-requests";
import { useCreateShopTicket } from "@/features/shop-support/api/use-create-shop-ticket";
import { useOrderTickets } from "@/features/shop-support/api/use-ticket-lists";
import { OrderTickets } from "@/features/shop-support/components/order-tickets";
import {
  countMessageCharacters,
  MESSAGE_MAX_LENGTH,
} from "@/features/shop-support/model/message-text";

/** Props of {@link OrderSupportSection}. */
export type OrderSupportSectionProps = {
  readonly orderId: string;
  /** The element ID of the message box, which "Contact support" on the order page focuses. */
  readonly messageBoxId: string;
};

/**
 * Render Support for this order.
 *
 * @param props - The order and the element ID of the message box.
 * @returns The section, with the confirmation banner after a message was sent.
 */
export function OrderSupportSection({ orderId, messageBoxId }: OrderSupportSectionProps) {
  const ticketsQuery = useOrderTickets(orderId);
  const createTicket = useCreateShopTicket(orderId);
  const createIdempotencyKey = useCreateIdempotencyKey();
  const [message, setMessage] = useState("");
  const [isSentBannerShown, setIsSentBannerShown] = useState(false);
  const sendFailure = getRequestFailure(createTicket.error);

  const handleSend = () => {
    setIsSentBannerShown(false);
    const failedSend = createTicket.isError ? createTicket.variables : undefined;
    createTicket.mutate(
      {
        message,
        idempotencyKey:
          failedSend?.message === message ? failedSend.idempotencyKey : createIdempotencyKey(),
      },
      {
        onSuccess: () => {
          setMessage("");
          setIsSentBannerShown(true);
        },
      },
    );
  };

  return (
    <Stack gap="4">
      {isSentBannerShown ? (
        <StatusBanner tone="success" lead="Message sent.">
          A person from our support team replies here.
        </StatusBanner>
      ) : null}
      <Panel as="section" label="Support for this order">
        <PanelHeader icon={LifeBuoy} level={2} title="Support for this order" />
        <OrderTickets query={ticketsQuery} />
        <PanelSection>
          <MessageBox
            inputId={messageBoxId}
            label="Write to support about this order"
            text={{ value: message, onChange: setMessage }}
            limit={{ count: countMessageCharacters(message), max: MESSAGE_MAX_LENGTH }}
            isSending={createTicket.isPending}
            onSend={handleSend}
          >
            {sendFailure === undefined ? null : <SendFailureBanner failure={sendFailure} />}
          </MessageBox>
        </PanelSection>
      </Panel>
    </Stack>
  );
}

/**
 * Say what happened to a message that failed. After a timeout, a lost connection, `502`, or `504`
 * nobody knows whether it arrived, and sending the same text again reuses its key.
 *
 * @param props - The failure of the send.
 * @returns The banner, announced as an alert.
 */
function SendFailureBanner({ failure }: { readonly failure: RequestFailure }) {
  if (!isWriteOutcomeUnknown(failure)) {
    return (
      <FailureBanner
        lead="Your message was not sent."
        failure={failure}
        notFoundMessage="This order was not found."
      />
    );
  }
  const { traceId } = describeFailure(failure);
  return (
    <StatusBanner
      tone="danger"
      lead="Your message may have arrived."
      {...(traceId === undefined ? {} : { traceId })}
    >
      We could not confirm it. Sending the same text again is safe: support gets it once.
    </StatusBanner>
  );
}
