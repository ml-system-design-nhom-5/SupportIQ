/**
 * The signed-in account in the app bar: a person icon, the display name, and the role. At phone
 * width only the icon stays, as the shop design shows. The name is Confidential and is only
 * rendered, never logged (SEC-01).
 */
import { User } from "lucide-react";

import { Icon } from "@/design-system/primitives/icon";

/** Props of {@link AccountLabel}. */
export type AccountLabelProps = {
  readonly displayName: string;
  /** The role label, for example "Staff"; absent in the shop. */
  readonly roleLabel?: string;
};

/**
 * Render the signed-in account.
 *
 * @param props - The display name and the role label.
 * @returns The account label.
 */
export function AccountLabel({ displayName, roleLabel }: AccountLabelProps) {
  return (
    <p className="flex min-w-0 items-center gap-2">
      <Icon icon={User} />
      <span className="hidden truncate font-medium text-text sm:inline">{displayName}</span>
      {roleLabel === undefined ? null : <span className="whitespace-nowrap">· {roleLabel}</span>}
    </p>
  );
}
