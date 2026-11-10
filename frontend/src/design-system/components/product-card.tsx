/**
 * A product in the catalog grid (shop UI design, Products): the neutral image, the name as a link
 * to the product page, the category, and the price.
 */
import { MoneyText } from "@/design-system/components/money-text";
import { ProductImage } from "@/design-system/components/product-image";
import type { Money } from "@/design-system/format/money";
import { TextLink } from "@/design-system/primitives/text-link";

/** Props of {@link ProductCard}. */
export type ProductCardProps = {
  readonly name: string;
  readonly category: string;
  readonly price: Money;
  /** The path of the product's page. */
  readonly href: string;
};

/**
 * Render a product card as a list item of the catalog grid.
 *
 * @param props - The name, the category, the price, and the product's path.
 * @returns The list item.
 */
export function ProductCard({ name, category, price, href }: ProductCardProps) {
  return (
    <li className="flex flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
      <ProductImage size="card" />
      <div className="flex flex-col gap-1 px-4 py-3">
        <h2 className="text-base">
          <TextLink to={href} emphasis="strong">
            {name}
          </TextLink>
        </h2>
        <p className="text-sm text-text-muted">{category}</p>
        <p className="text-lg font-semibold text-text">
          <MoneyText money={price} />
        </p>
      </div>
    </li>
  );
}
