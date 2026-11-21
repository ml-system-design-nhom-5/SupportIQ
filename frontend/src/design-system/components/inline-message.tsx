/**
 * A short message next to a form: an error after a failed action, or a hint. The icon keeps color
 * from being the only signal (UI-11).
 */
import { cva } from "class-variance-authority";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Icon } from "@/design-system/primitives/icon";

const messageVariants = cva("flex items-start gap-2 text-sm", {
  variants: {
    tone: { danger: "text-danger", muted: "text-text-muted", success: "text-success" },
  },
});

/** `danger` for an error, `muted` for a hint, `success` for a confirmation. */
export type InlineMessageTone = "danger" | "muted" | "success";

/** Props of {@link InlineMessage}. */
export type InlineMessageProps = {
  readonly tone: InlineMessageTone;
  readonly icon: LucideIcon;
  /** `alert` announces an error when it appears. */
  readonly role?: "alert" | "status";
  /** Lets an input point to the message with `aria-describedby`. */
  readonly id?: string;
  readonly children: ReactNode;
};

/**
 * Render the message.
 *
 * @param props - The tone, the icon, the role, the `id`, and the text.
 * @returns The message.
 */
export function InlineMessage({ tone, icon, role, id, children }: InlineMessageProps) {
  return (
    <p id={id} role={role} className={messageVariants({ tone })}>
      <Icon icon={icon} />
      <span>{children}</span>
    </p>
  );
}
