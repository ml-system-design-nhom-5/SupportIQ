/**
 * The product page panel (shop UI design, Product): the neutral image, the name, the category, the
 * price, the description, and a note that the shop has no cart (ADR-0013).
 */
import { Info } from "lucide-react";

import { InlineMessage } from "@/design-system/components/inline-message";
import { MoneyText } from "@/design-system/components/money-text";
import { ProductImage } from "@/design-system/components/product-image";
import type { Money } from "@/design-system/format/money";

/** Props of {@link ProductDetails}. */
export type ProductDetailsProps = {
  readonly name: string;
  readonly category: string;
  readonly price: Money;
  /** Plain text, rendered as text (SEC-22). */
  readonly description: string;
};

/**
 * Render the product details.
 *
 * @param props - The name, the category, the price, and the description.
 * @returns The panel, with the name as the `h1` of the page.
 */
export function ProductDetails({ name, category, price, description }: ProductDetailsProps) {
  return (
    <article className="grid grid-cols-1 gap-6 rounded-lg border border-border bg-surface p-4 shadow-sm sm:grid-cols-2 sm:p-6">
      <ProductImage size="detail" />
      <div className="flex flex-col gap-4">
        <h1 className="text-xl font-semibold text-text sm:text-2xl">{name}</h1>
        <p className="text-base text-text-muted">{category}</p>
        <p className="text-xl font-semibold text-text">
          <MoneyText money={price} />
        </p>
        <p className="text-base whitespace-pre-wrap text-text">{description}</p>
        <InlineMessage tone="muted" icon={Info}>
          The demo shop has no cart. Questions about an order go through My orders.
        </InlineMessage>
      </div>
    </article>
  );
}
