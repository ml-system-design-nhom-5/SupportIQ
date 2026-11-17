/**
 * The facts of one order (console UI design, Order chip): each term with its value in bold and a
 * detail, such as "Order: Delivered · Placed 2 Oct 2026".
 */
import { DescriptionList } from "@/design-system/primitives/description-list";

/** One fact of an order. */
export type OrderFactItem = {
  readonly term: string;
  readonly value: string;
  readonly detail?: string;
};

/** Props of {@link OrderFacts}. */
export type OrderFactsProps = {
  readonly facts: readonly OrderFactItem[];
};

/**
 * Render the facts.
 *
 * @param props - The facts.
 * @returns The description list.
 */
export function OrderFacts({ facts }: OrderFactsProps) {
  return (
    <DescriptionList
      items={facts.map((fact) => ({
        term: fact.term,
        description: (
          <>
            <span className="font-medium">{fact.value}</span>
            {fact.detail === undefined ? null : (
              <span className="text-text-muted"> · {fact.detail}</span>
            )}
          </>
        ),
      }))}
    />
  );
}
