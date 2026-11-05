# ADR-0012: Roles v1: customer, staff, manager, and admin

- **Status:** Accepted
- **Date:** 2026-11-05
- **Deciders:** Team
- **Related:** [Requirements](../product/requirements.md) (FR-06, FR-08, FR-10), [ADR-0009](0009-demo-accounts-and-cookie-sessions.md), [ADR-0011](0011-deployment-and-runtime-topology.md), [security rules](../rules/security-and-privacy.md#authentication-and-authorization), [Design: contracts v1](../design/contracts-v1.md#roles-and-permissions)

## Context

- FR-08 (Must) requires sign-in and role-based access for four roles: customer, support staff, support manager, and administrator. Each role reaches only the functions and data it is allowed, and `backend` enforces every check.
- FR-06 gives refund decisions, transaction disputes, and policy exceptions to a support manager. FR-10 gives reports to managers.
- The team's specification describes the roles this way (section 1.2):
  - support staff are Tier 1;
  - support managers are Tier 2 and handle escalations, decide business cases, view reports, and approve improvements;
  - administrators manage accounts, roles, configuration, and model and KB versions.
- Before this decision, the contracts v1 design had the roles `customer`, `staff`, and `supervisor`, and listed "an admin role" as a non-goal. [ADR-0009](0009-demo-accounts-and-cookie-sessions.md) seeds customer personas, staff, and supervisor accounts.
- Model, KB, prompt, and routing versions are versioned assets ([ARCH-38](../rules/architecture.md#versioned-assets)). A new set of versions is published only through a release manifest that passed the offline evaluation gate ([DATA-56, DATA-57](../rules/data-and-ml.md#models-and-artifacts)).
- No role-specific code exists yet, so renaming a role costs only document changes.

## Decision drivers

1. **Least privilege and separation of duties:** no role can both read customer data and change who has access to it.
2. **FR-06 and FR-08 can be demonstrated and tested** with real permission checks.
3. **One vocabulary** shared by the specification, the documents, the contracts, the code, and the UI.
4. **Small scope:** only what FR-08 and the specification need.

## Considered options

1. Keep `customer`, `staff`, and `supervisor`, without an admin role.
2. Rename `supervisor` to `manager`, and add an `admin` role limited to account management and version display.
3. Add an `admin` role that also changes settings and switches model or KB versions from a screen.
4. Make `admin` a superuser that can also do everything staff and managers do.

## Decision

We adopt option 2. The statements below are normative.

### Roles

1. There are exactly four roles: `customer`, `staff`, `manager`, and `admin`. Every account has exactly one role.
2. `manager` replaces `supervisor` and keeps all of its permissions. Contracts, code, UI text, and documents use `manager`. The word "supervisor" is not used for a role.
3. The roles have these duties:

   | Role | Stakeholder in the specification | Can | Cannot |
   |---|---|---|---|
   | `customer` | E-commerce customer | Browse the catalog; read their own orders, tickets, and sent replies; create a ticket on one of their orders | Read anything of another customer; see any AI output |
   | `staff` | Support staff, Tier 1 | Read a ticket in any state, read-only unless it is `open`; correct or confirm the intent of an open ticket; send replies where authority is not required; submit reply proposals; escalate | Send a reply where authority is required; list tickets awaiting approval, escalated, or closed; view reports; manage accounts |
   | `manager` | Support manager, Tier 2 | Everything `staff` can do on open tickets, except submitting proposals and escalating; list tickets in every state; send any reply, including where authority is required; view reports (FR-10) | Manage accounts |
   | `admin` | Administrator | List `staff`, `manager`, and `admin` accounts; change a role between `staff` and `manager`; deactivate and reactivate those accounts; view the versions in use | See customer accounts; read tickets, messages, drafts, orders, or reports; send replies; change any other role |

4. The full permission matrix per operation is defined in the [contracts v1 design](../design/contracts-v1.md#roles-and-permissions) and, once written, in the `backend` contract ([SEC-16](../rules/security-and-privacy.md#authentication-and-authorization)).

### Admin limits

1. `admin` operations live in their own namespace, `/v1/admin/`, and the admin screens live in their own area, `/admin`, in `frontend`.
2. Admin operations cover only internal accounts: `staff`, `manager`, and `admin`. Customer accounts are created only by the seed and are never listed, changed, or deactivated by an admin, so the admin never sees customer data.
3. A role change is allowed only from `staff` to `manager` or from `manager` to `staff`. The `admin` role cannot be changed, and no account can be given the `admin` role. Admin accounts exist only through the seed.
4. An admin cannot change their own role and cannot deactivate their own account. Because only an admin can deactivate an admin, at least one admin always stays active.
5. The last active `manager` cannot be demoted or deactivated, because tickets that require authority would have nobody to send their reply. The request fails with `422 invalid-request`.
6. A role change or a deactivation deletes all sessions of the account, so the change applies to its very next request. A deactivated account cannot sign in. Sign-in returns the same `401` as a wrong password ([ADR-0009](0009-demo-accounts-and-cookie-sessions.md), statement 8).
7. Records that name an account (decisions, replies, proposals, escalations) keep the account after a role change or a deactivation. History is never rewritten.
8. Every successful admin change is recorded in the audit log with the admin, the target account, the old and new values, and the time.
9. The account list shows the display name, role, and active status only. It does not show emails, password hashes, or session data.
10. "View the versions in use" shows the `release_id` and asset versions that `ai-service` reports, and the `backend` build version. Model, KB, prompt, and routing versions change only through a new release manifest and a redeploy, never from a screen.

### Seed and authentication

1. The seed creates at least one account per role, with passwords from settings ([ADR-0009](0009-demo-accounts-and-cookie-sessions.md), statement 1).
2. [ADR-0009](0009-demo-accounts-and-cookie-sessions.md) stays accepted. It defines the authentication mechanism, which this ADR does not change. This ADR replaces only the role names that ADR-0009 lists.

## Consequences

### Positive

- FR-08 is complete, with four roles that match the specification.
- Duties are separated: the admin manages access but cannot read customer data, and only managers decide cases that require authority.
- The safety checks of the release process cannot be bypassed from a screen.
- One word, `manager`, is used everywhere.

### Negative

- More operations in the `backend` contract, and one more area in `frontend`.
- Earlier accepted documents (ADR-0009) still say "supervisor". The glossary records the rename.
- The admin cannot fix a wrong release from a screen; a redeploy is needed.

### Follow-ups

- Contracts v1 design: the roles, the permission matrix, and the admin operations.
- Rules: SEC-15, UI-16, UI-19, and new admin rules. Glossary: `manager`, `admin`, and "supervisor" as a term not to use.
- Seed script: at least one account per role.

## Pros and cons of the options

### Keep three roles without an admin

- Good, because there is nothing more to build.
- Bad, because FR-08 lists four roles, and "supervisor" differs from the specification's wording.

### Rename to `manager` and add a limited `admin`

- Good, because it meets FR-08 with the smallest scope and keeps duties separate.
- Bad, because of the costs listed under Negative.

### Admin who changes settings and versions

- Good, because it matches the specification's wording literally.
- Bad, because a version switch from a screen bypasses the offline evaluation gate and the review of versioned assets.

### Superuser admin

- Good, because one account can demonstrate everything.
- Bad, because one role could both read customer data and grant itself access, which breaks least privilege, and permission tests would prove little.

## Validation

- The permission matrix is tested as a table: every operation, every role, allowed or rejected ([SEC-16](../rules/security-and-privacy.md#authentication-and-authorization)).
- Tests prove that an admin gets `403` on every `/v1/console/` and `/v1/shop/` operation.
- Tests prove that staff can read a ticket that is not `open`, with no allowed action, and cannot list such tickets.
- Tests prove that a role change or a deactivation makes the account's existing session fail with `401` on its next request.
- Tests prove that the last active manager cannot be demoted or deactivated, and that an admin cannot change their own role or deactivate themselves.
- Every successful admin change produces exactly one audit log entry.
- Tests prove that no admin operation returns or changes a customer account.
- Revisit when production authentication replaces demo accounts, or when a role needs a permission that this matrix does not allow.
