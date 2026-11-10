/**
 * The neutral product image: the same for every product (UI-38, ADR-0013).
 */
import { cva } from "class-variance-authority";
import { Box } from "lucide-react";

import { Icon } from "@/design-system/primitives/icon";

const productImageVariants = cva("flex items-center justify-center bg-background text-text-muted", {
  variants: {
    size: {
      card: "h-product-card w-full",
      detail: "h-product-detail w-full rounded-md",
      thumbnail: "size-12 shrink-0 rounded-md border border-border",
    },
  },
});

/** `card` in the catalog grid, `detail` on the product page, `thumbnail` in an order line. */
export type ProductImageSize = "card" | "detail" | "thumbnail";

/** Props of {@link ProductImage}. */
export type ProductImageProps = {
  readonly size: ProductImageSize;
};

/**
 * Render the neutral product image. It carries no information, so it is hidden from assistive
 * technology.
 *
 * @param props - The size.
 * @returns The image area.
 */
export function ProductImage({ size }: ProductImageProps) {
  return (
    <div aria-hidden="true" className={productImageVariants({ size })}>
      <Icon icon={Box} size={size === "thumbnail" ? "sm" : "lg"} />
    </div>
  );
}
