/**
 * One row of a {@link RowList}: the whole row is a link to the item's page, with a chevron.
 */
import { cva } from "class-variance-authority";
import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";

const rowContentVariants = cva("flex min-w-0 flex-1 flex-col gap-1", {
  variants: { trailingOnPhone: { beside: "", below: "basis-full sm:basis-0" } },
});

/** At phone width, `beside` keeps the trailing content in the row; `below` moves it under. */
export type RowTrailingOnPhone = "beside" | "below";

/** Props of {@link RowListItem}. */
export type RowListItemProps = {
  /** The app path of the item's page. */
  readonly to: string;
  /** The main content of the row. */
  readonly children: ReactNode;
  /** Content at the end of the row, such as a total or a status. */
  readonly trailing?: ReactNode;
  readonly trailingOnPhone?: RowTrailingOnPhone;
};

/**
 * Render a row that opens an item.
 *
 * @param props - The path, the content, and the trailing content with its phone placement.
 * @returns The list item.
 */
export function RowListItem({
  to,
  children,
  trailing,
  trailingOnPhone = "beside",
}: RowListItemProps) {
  return (
    <li className="border-border not-first:border-t">
      <Link
        to={to}
        className={cn(
          "flex flex-wrap items-center gap-x-4 gap-y-2 p-4 text-text hover:bg-background sm:flex-nowrap sm:px-6",
          FOCUS_RING_CLASSES,
        )}
      >
        <div className={rowContentVariants({ trailingOnPhone })}>{children}</div>
        {trailing === undefined ? null : <div className="shrink-0">{trailing}</div>}
        <span className="ml-auto">
          <Icon icon={ChevronRight} tone="muted" />
        </span>
      </Link>
    </li>
  );
}
