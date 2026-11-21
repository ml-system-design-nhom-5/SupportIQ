/**
 * An amount of money, formatted by the shared formatter (UI-29).
 */
import { formatMoney, type Money } from "@/design-system/format/money";

/** Props of {@link MoneyText}. */
export type MoneyTextProps = {
  readonly money: Money;
};

/**
 * Render a formatted amount.
 *
 * @param props - The amount and its currency.
 * @returns The amount as text, for example `$89.00`.
 */
export function MoneyText({ money }: MoneyTextProps) {
  return <span className="whitespace-nowrap">{formatMoney(money)}</span>;
}
