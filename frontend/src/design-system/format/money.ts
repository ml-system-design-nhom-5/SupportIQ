/**
 * The shared money formatter (UI-29). Amounts are integers in minor units with an ISO 4217 code
 * (CON-16); the formatter never converts them to floating-point numbers.
 */

/** The locale of money in the mockups: `$89.00`. */
const MONEY_LOCALE = "en-US";

/** An amount of money, as a view model holds it. */
export type Money = {
  /** The amount in the minor unit of the currency: cents for USD, whole dong for VND. */
  readonly amountMinor: number;
  /** The ISO 4217 code, for example `USD`. */
  readonly currency: string;
};

/**
 * Format an amount of money for display.
 *
 * @param money - The amount and its currency.
 * @returns The formatted amount, for example `$89.00`.
 */
export function formatMoney(money: Money): string {
  const formatter = new Intl.NumberFormat(MONEY_LOCALE, {
    style: "currency",
    currency: money.currency,
  });
  const fractionDigits = formatter.resolvedOptions().maximumFractionDigits ?? 0;
  const decimal = toDecimalString(money.amountMinor, fractionDigits);
  if (!isDecimalString(decimal)) {
    throw new RangeError("The amount must be a non-negative integer of minor units.");
  }
  // Intl.NumberFormat formats a decimal string exactly (ECMA-402, Intl.NumberFormat v3).
  return formatter.format(decimal);
}

/**
 * Write an integer amount of minor units as a decimal string, without floating-point arithmetic.
 *
 * @param amountMinor - The non-negative integer amount.
 * @param fractionDigits - The number of minor-unit digits of the currency.
 * @returns The decimal string, for example `42.50` for 4250 and 2 digits.
 */
function toDecimalString(amountMinor: number, fractionDigits: number): string {
  if (fractionDigits === 0) {
    return String(amountMinor);
  }
  const digits = String(amountMinor).padStart(fractionDigits + 1, "0");
  return `${digits.slice(0, -fractionDigits)}.${digits.slice(-fractionDigits)}`;
}

/**
 * Tell whether a string is a plain decimal number, so Intl formats it exactly.
 *
 * @param value - The string built by {@link toDecimalString}.
 * @returns True for digits with an optional fraction.
 */
function isDecimalString(value: string): value is `${number}` {
  return /^[0-9]+(\.[0-9]+)?$/.test(value);
}
