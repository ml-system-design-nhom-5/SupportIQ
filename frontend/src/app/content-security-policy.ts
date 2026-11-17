/**
 * The Content Security Policy of the built page (SEC-23): no inline script and no other origin.
 * Inline styles stay allowed, because the Radix primitives set styles on their elements. The only
 * other origin is the Render origin of `backend`, which `connect-src` adds for the wake request
 * when its setting has a value (ADR-0016, statement 11; backend wake-up design, rules 9 and 10).
 * This module imports nothing, so `vite.config.ts` can import it.
 */

/**
 * Build the policy.
 *
 * @param wakeOrigin - The Render origin of `backend`, or undefined when no wake request is sent.
 * @returns The policy, as the `content` of its `meta` element.
 */
export function buildContentSecurityPolicy(wakeOrigin: string | undefined): string {
  return [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    wakeOrigin === undefined ? "connect-src 'self'" : `connect-src 'self' ${wakeOrigin}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; ");
}
