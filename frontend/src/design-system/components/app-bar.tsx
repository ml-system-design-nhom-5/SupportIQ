/**
 * The app shell bar of every area (shop UI design, Layout; admin UI design, Layout): the brand,
 * the navigation, and the account menu (account management design, Account menu). At phone width
 * the shop navigation moves to a second row.
 */
import { cva } from "class-variance-authority";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Icon } from "@/design-system/primitives/icon";

const barVariants = cva("flex items-center border-b border-border bg-surface", {
  variants: {
    variant: {
      shop: "flex-wrap gap-x-6 gap-y-2 px-4 py-2 text-sm sm:flex-nowrap sm:px-6 sm:py-3 sm:text-base",
      console: "h-12 gap-6 px-4 text-sm",
    },
  },
});

const brandVariants = cva("flex items-center gap-2 font-semibold whitespace-nowrap text-text", {
  variants: { variant: { shop: "text-lg", console: "text-base" } },
});

/** `shop` has a 16 px body and wraps at phone width; `console` is the desktop bar of 48 px. */
export type AppBarVariant = "shop" | "console";

/** Props of {@link AppBar}. */
export type AppBarProps = {
  readonly variant: AppBarVariant;
  /** The product or shop name, for example "SupportIQ" or "Demo Shop". */
  readonly brandName: string;
  /** The area after the brand, in muted text, for example "Console". */
  readonly areaName?: string;
  readonly brandIcon?: LucideIcon;
  /** The navigation entries; absent when the account may not use the area. */
  readonly navigation?: ReactNode;
  /** The account menu, and a message when sign-out failed. */
  readonly account?: ReactNode;
};

/**
 * Render the app bar.
 *
 * @param props - The variant, the brand, the navigation, and the account.
 * @returns The `header` landmark.
 */
export function AppBar({
  variant,
  brandName,
  areaName,
  brandIcon,
  navigation,
  account,
}: AppBarProps) {
  return (
    <header className={barVariants({ variant })}>
      <p className={brandVariants({ variant })}>
        {brandIcon === undefined ? null : <Icon icon={brandIcon} />}
        {brandName}
        {areaName === undefined ? null : (
          <span className="font-normal text-text-muted">{areaName}</span>
        )}
      </p>
      {navigation === undefined ? null : (
        <nav
          aria-label="Main"
          className="order-last flex w-full justify-between gap-1 sm:order-none sm:w-auto sm:justify-start"
        >
          {navigation}
        </nav>
      )}
      {account === undefined ? null : (
        <div className="ml-auto flex min-w-0 items-center gap-3 text-text-muted">{account}</div>
      )}
    </header>
  );
}
