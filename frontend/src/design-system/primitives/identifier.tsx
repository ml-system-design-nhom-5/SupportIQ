/**
 * An identifier, such as an order or ticket ID, in JetBrains Mono (UI-08).
 */
import { cva } from "class-variance-authority";

const identifierVariants = cva("font-mono", {
  variants: { size: { inherit: "", xs: "text-xs" } },
});

/** `inherit` keeps the size of the text around it; `xs` is the size in a secondary line. */
export type IdentifierSize = "inherit" | "xs";

/** Props of {@link Identifier}. */
export type IdentifierProps = {
  /** The opaque identifier (CON-15). */
  readonly children: string;
  readonly size?: IdentifierSize;
};

/**
 * Render an identifier.
 *
 * @param props - The identifier and its size.
 * @returns The identifier in the monospace family.
 */
export function Identifier({ children, size = "inherit" }: IdentifierProps) {
  return <span className={identifierVariants({ size })}>{children}</span>;
}
