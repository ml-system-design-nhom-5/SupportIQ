# ADR-0019: One label for text in the placeholder syntax

- **Status:** Accepted
- **Date:** 2026-11-13
- **Deciders:** Project lead
- **Related:** [Requirements](../product/requirements.md) (FR-04, FR-09, NFR-11), [ADR-0010](0010-pseudonymization-and-egress-control.md) ([Placeholder syntax](0010-pseudonymization-and-egress-control.md#placeholder-syntax), [Restoring and sending](0010-pseudonymization-and-egress-control.md#restoring-and-sending)), [UI rules](../rules/ui.md#console-interaction) (UI-43), [security rules](../rules/security-and-privacy.md#pseudonymization) (SEC-38), [console UI design](../design/console-ui.md#draft-editing-and-citations)

## Context

This ADR amends one passage of [ADR-0010](0010-pseudonymization-and-egress-control.md). The project lead decided it on 2026-11-12.

- [ADR-0010, Restoring and sending](0010-pseudonymization-and-egress-control.md#restoring-and-sending), item 3, shows a restored `LITERAL` "highlighted with its own label". UI-43 named two labels: "Personal data hidden: replace before sending" for a mask or an unrestored pseudonym, and "Customer text in a reserved format: rephrase before sending" for a restored `LITERAL`.
- A `LITERAL` pseudonym replaces customer text that already matches the placeholder expression ([ADR-0010, Detection](0010-pseudonymization-and-egress-control.md#detection), step 1). After restoration, that text matches the expression again. A pseudonym missing from the map matches it too, and a customer who wrote `[EMAIL]` produces exactly the text of a mask.
- `getConsoleTicket` returns AI text with pseudonyms restored, and `backend` contract 1.2.0 has no field that marks which spans are restored `LITERAL`s. Text that staff type in the editor carries no such mark either. The console therefore cannot tell a restored `LITERAL` from an unrestored pseudonym or a mask by the text alone, so it cannot choose between the two labels correctly.
- The guardrail does not depend on the label: Send reply and Submit for approval are disabled while the editor contains text in the placeholder syntax (UI-43), and `sendReply` and `createReplyProposal` reject such a body with `422 invalid-request` ([ADR-0010, Restoring and sending](0010-pseudonymization-and-egress-control.md#restoring-and-sending), item 4; [SEC-38](../rules/security-and-privacy.md#pseudonymization)).

## Decision drivers

1. **Safety:** no placeholder reaches a customer (SEC-38).
2. **Correct information for staff:** a label states only what the console can know.
3. **Low complexity:** no contract change and no new mechanism.

## Considered options

1. Two labels, as ADR-0010 and UI-43 state.
2. Two labels, with `backend` marking each restored `LITERAL` in the ticket workspace so that the console can tell them apart.
3. One label for every text in the placeholder syntax.

## Decision

We adopt one label (option 3).

1. The console highlights every text that matches the placeholder expression ([ADR-0010, Placeholder syntax](0010-pseudonymization-and-egress-control.md#placeholder-syntax)) with one label: "Personal data or reserved text: replace before sending". This covers a mask, a pseudonym that `backend` could not restore, and a restored `LITERAL`, in the draft and in the editor. A restored `LITERAL` is still shown as the customer wrote it.
2. Send reply and Submit for approval stay disabled while the editor contains text in the placeholder syntax, and `sendReply` and `createReplyProposal` still reject such a body with `422 invalid-request` ([ADR-0010, Restoring and sending](0010-pseudonymization-and-egress-control.md#restoring-and-sending), item 4). The guardrail is unchanged.
3. This ADR replaces exactly one passage of ADR-0010: in [Restoring and sending](0010-pseudonymization-and-egress-control.md#restoring-and-sending), item 3, the words "highlighted with its own label" become "highlighted with the label of ADR-0019, statement 1". The rest of ADR-0010 still holds.

## Consequences

### Positive

- The label never claims more than the console knows, and staff get one instruction for every case. In each case they replace the text before sending, as before.
- `backend` contract 1.2.0 stays as it is.

### Negative

- The label no longer tells staff that a highlighted text was written by the customer. They read the customer message to see what it stood for.
- ADR-0010 stays Accepted with one passage that no longer holds. Readers rely on the note under the [index](README.md#index) to find this ADR.

### Follow-ups

- [UI-43](../rules/ui.md#console-interaction) names the single label, in the same PR as this ADR ([RULE-06](../rules/README.md#changing-a-rule)).
- The [console UI design](../design/console-ui.md#summary) records this decision in a revision.
- The mockup source `mockup.js` and the mockup `state-placeholder.png` of the console UI design show the single label.
- `frontend` defines the label once and uses it for every placeholder highlight.

## Pros and cons of the options

### Two labels, as ADR-0010 and UI-43 state

- Good, because staff would see that a highlighted text came from the customer.
- Bad, because the console cannot choose the label from the text alone, so it would show a wrong label, for example the label of a restored `LITERAL` for a mask, or the label of a mask for a customer who wrote `[EMAIL]`.

### Two labels, with `backend` marking each restored `LITERAL`

- Good, because each label would be correct.
- Bad, because it needs a change of `backend` contract 1.2.0 and of the restore function of the `pseudonymization` module, for a label that changes nothing in what staff must do.
- Bad, because text that staff type in the editor still carries no mark.

### One label for every text in the placeholder syntax

- Good, because it is correct for every text, needs no contract change, and leaves the guardrail as it is.
- Bad, because staff lose the hint that a text came from the customer.

## Validation

- Component test: a mask, an unrestored pseudonym, and a restored `LITERAL` in the draft and in the editor each carry the single label, and Send reply and Submit for approval are disabled in each case.
- Handler test: a reply or proposal body with each of the three still gets `422 invalid-request`.
- Revisit if `backend` gains a reason to mark restored `LITERAL`s in a contract, or if the NFR-11 usability study shows that the single label confuses staff.
