import { describe, expect, it } from "vitest";

import { buildContentSecurityPolicy } from "@/app/content-security-policy";

/**
 * Read one directive of a policy.
 *
 * @param policy - The policy.
 * @param name - The directive name, such as `connect-src`.
 * @returns The directive with its sources, or undefined when the policy lacks it.
 */
function directiveOf(policy: string, name: string): string | undefined {
  return policy.split("; ").find((directive) => directive.startsWith(`${name} `));
}

describe("buildContentSecurityPolicy (SEC-23)", () => {
  it("allows only the page's origin to connect without a wake origin (rule 9)", () => {
    expect(directiveOf(buildContentSecurityPolicy(undefined), "connect-src")).toBe(
      "connect-src 'self'",
    );
  });

  it("adds exactly the wake origin to connect-src, and nothing else (ADR-0016, statement 11)", () => {
    const withOrigin = buildContentSecurityPolicy("https://backend.example.com");
    const without = buildContentSecurityPolicy(undefined);

    expect(directiveOf(withOrigin, "connect-src")).toBe(
      "connect-src 'self' https://backend.example.com",
    );
    expect(withOrigin.replace(" https://backend.example.com", "")).toBe(without);
  });

  it("keeps the other directives: no inline script and no other origin", () => {
    const policy = buildContentSecurityPolicy(undefined);

    expect(directiveOf(policy, "default-src")).toBe("default-src 'self'");
    expect(directiveOf(policy, "script-src")).toBe("script-src 'self'");
    expect(directiveOf(policy, "object-src")).toBe("object-src 'none'");
  });
});
