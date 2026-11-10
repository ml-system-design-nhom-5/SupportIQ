/**
 * The message box of the order page (shop UI design, Support for this order): a visible label, a
 * counter up to the limit, a help line that says a person replies once, and Send message, which is
 * disabled while the box is empty, over the limit, or sending. The text cannot change while it is
 * sent, and it stays when sending fails. When sending ends, the focus moves from Send message to
 * the box (UI-30).
 */
import { Info, Send } from "lucide-react";
import { type ReactNode, type RefObject, type SubmitEvent, useEffect, useRef } from "react";

import { FormField } from "@/design-system/components/form-field";
import { InlineMessage } from "@/design-system/components/inline-message";
import { formatCount } from "@/design-system/format/number";
import { Button } from "@/design-system/primitives/button";
import { TextArea } from "@/design-system/primitives/text-area";

/** The text of the box, controlled by its container. */
export type MessageBoxText = {
  readonly value: string;
  readonly onChange: (value: string) => void;
};

/** How long the text is and may be, counted as the contract counts (`MessageText`). */
export type MessageBoxLimit = {
  readonly count: number;
  readonly max: number;
};

/** Props of {@link MessageBox}. */
export type MessageBoxProps = {
  readonly inputId: string;
  readonly label: string;
  readonly text: MessageBoxText;
  readonly limit: MessageBoxLimit;
  /** True while the message is sent; Send message is disabled, so it is sent once. */
  readonly isSending: boolean;
  readonly onSend: () => void;
  /** Feedback above the box, such as the banner of a failed send. */
  readonly children?: ReactNode;
};

/**
 * Render the message box.
 *
 * @param props - The field, the text, the limit, the sending state, and the feedback.
 * @returns The form.
 */
export function MessageBox({
  inputId,
  label,
  text,
  limit,
  isSending,
  onSend,
  children,
}: MessageBoxProps) {
  const counterId = `${inputId}-counter`;
  const helpId = `${inputId}-help`;
  const isTooLong = limit.count > limit.max;
  const hasValidText = limit.count > 0 && !isTooLong;
  const canSend = hasValidText && !isSending;
  const boxRef = useRef<HTMLTextAreaElement>(null);
  const sendButtonRef = useRef<HTMLButtonElement>(null);
  useFocusBoxWhenSendingEnds(isSending, boxRef, sendButtonRef);

  const handleSubmit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (canSend) {
      onSend();
    }
  };

  return (
    <form aria-label={label} className="flex flex-col gap-3" onSubmit={handleSubmit}>
      {children}
      <FormField inputId={inputId} label={label}>
        <TextArea
          ref={boxRef}
          id={inputId}
          name="message"
          placeholder="Describe your question."
          value={text.value}
          readOnly={isSending}
          aria-invalid={isTooLong}
          aria-describedby={`${counterId} ${helpId}`}
          onChange={(event) => {
            text.onChange(event.target.value);
          }}
        />
      </FormField>
      <div className="flex flex-wrap items-center gap-3">
        <p id={counterId} className={isTooLong ? "text-sm text-danger" : "text-sm text-text-muted"}>
          {formatCount(limit.count)} / {formatCount(limit.max)} characters
          {isTooLong ? ". Shorten your message to send it." : ""}
        </p>
        <InlineMessage tone="muted" icon={Info} id={helpId}>
          Each message gets one reply from a person on our support team.
        </InlineMessage>
        <div className="w-full sm:ml-auto sm:w-auto">
          <Button
            ref={sendButtonRef}
            type="submit"
            variant="primary"
            size="lg"
            width="full-on-phone"
            leadingIcon={Send}
            disabled={!hasValidText && !isSending}
            isPending={isSending}
          >
            {isSending ? "Sending…" : "Send message"}
          </Button>
        </div>
      </div>
    </form>
  );
}

/**
 * Move the focus from Send message to the box when sending ends.
 *
 * @param isSending - True while the message is sent.
 * @param boxRef - The box.
 * @param sendButtonRef - Send message.
 */
function useFocusBoxWhenSendingEnds(
  isSending: boolean,
  boxRef: RefObject<HTMLTextAreaElement | null>,
  sendButtonRef: RefObject<HTMLButtonElement | null>,
): void {
  const hasBeenSending = useRef(false);
  useEffect(() => {
    // An empty box disables Send message, and the browser then drops its focus to the body. Focus
    // anywhere else means that the customer moved on, and they keep their place.
    const { activeElement, body } = document;
    if (
      hasBeenSending.current &&
      !isSending &&
      (activeElement === body || activeElement === sendButtonRef.current)
    ) {
      boxRef.current?.focus();
    }
    hasBeenSending.current = isSending;
  }, [isSending, boxRef, sendButtonRef]);
}
