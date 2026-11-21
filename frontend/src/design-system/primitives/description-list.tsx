/**
 * Terms with their values, such as the facts of an order (console UI design, Order chip), as a
 * description list: the terms in muted text on the left, the values on the right.
 */
import type { ReactNode } from "react";

/** One term and its value. */
export type DescriptionItem = {
  /** Unique within the list; it is also the key of the row. */
  readonly term: string;
  readonly description: ReactNode;
};

/** Props of {@link DescriptionList}. */
export type DescriptionListProps = {
  readonly items: readonly DescriptionItem[];
};

/**
 * Render the list.
 *
 * @param props - The terms and their values.
 * @returns The `dl` element.
 */
export function DescriptionList({ items }: DescriptionListProps) {
  return (
    <dl className="grid grid-cols-4 gap-x-3 gap-y-2 text-sm">
      {items.map((item) => (
        <div key={item.term} className="col-span-4 grid grid-cols-subgrid">
          <dt className="text-text-muted">{item.term}</dt>
          <dd className="col-span-3 min-w-0 wrap-break-word text-text">{item.description}</dd>
        </div>
      ))}
    </dl>
  );
}
