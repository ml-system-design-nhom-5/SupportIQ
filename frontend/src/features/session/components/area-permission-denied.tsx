/**
 * The permission-denied state of an area (`403` when a screen loads): the shop for a support or
 * admin account (shop UI design, States), the admin area for any other role (admin UI design,
 * States). `backend` decided it; the UI only shows it (UI-40).
 */
import { Lock } from "lucide-react";

import { StateMessage } from "@/design-system";
import { SignOutButton } from "@/features/session/components/sign-out-button";

const textByArea: Readonly<
  Record<RestrictedArea, { readonly title: string; readonly description: string }>
> = {
  shop: {
    title: "The shop is for customer accounts",
    description:
      "You are signed in with a support or admin account. Sign out, then sign in with a customer account.",
  },
  admin: {
    title: "The admin area is for admin accounts",
    description:
      "You are signed in with a customer or support account. Sign out, then sign in with an admin account.",
  },
};

/** The area that refused the account. */
export type RestrictedArea = "shop" | "admin";

/** Props of {@link AreaPermissionDenied}. */
export type AreaPermissionDeniedProps = {
  readonly area: RestrictedArea;
  /** The trace ID of the `403` answer, when there is one (UI-25). */
  readonly traceId?: string;
};

/**
 * Render the permission-denied state with Sign out.
 *
 * @param props - The area and the trace ID.
 * @returns The state message.
 */
export function AreaPermissionDenied({ area, traceId }: AreaPermissionDeniedProps) {
  // TODO(#7): when this state replaces a screen, the focused button goes with it, and the focus
  // falls to the page (UI-30).
  const text = textByArea[area];
  return (
    <StateMessage
      icon={Lock}
      headingLevel={1}
      title={text.title}
      description={text.description}
      actions={<SignOutButton />}
      {...(traceId === undefined ? {} : { traceId })}
    />
  );
}
