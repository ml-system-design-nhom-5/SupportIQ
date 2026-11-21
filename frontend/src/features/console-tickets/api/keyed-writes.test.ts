import { describe, expect, it } from "vitest";

import { chooseIdempotencyKey } from "@/features/console-tickets/api/keyed-writes";
import { buildEscalationRequest } from "@/features/console-tickets/model/escalation-form";
import {
  acknowledgeWarning,
  createComposerState,
  rejectDraft,
  startEditing,
} from "@/features/console-tickets/model/reply-composer";
import { buildSendReplyRequest } from "@/features/console-tickets/model/reply-request";
import { DRAFT_READY_SUGGESTION_ID, readComposerTicket } from "@/test/console-screen";

const draftReady = readComposerTicket("draft-ready");
const opened = createComposerState(DRAFT_READY_SUGGESTION_ID);
const acknowledged = acknowledgeWarning(opened, { warningId: "w1", isAcknowledged: true });
const rejected = { ...rejectDraft(opened), body: "My own reply." };

/**
 * Choose the key of a request after a failed one.
 *
 * @param failedRequest - The request that failed with the key `k1`.
 * @param request - The request to send now.
 * @returns The key that the request gets.
 */
function chooseAfterFailure<Request>(failedRequest: Request, request: Request): string {
  return chooseIdempotencyKey(
    request,
    { isError: true, variables: { request: failedRequest, idempotencyKey: "k1" } },
    () => "k2",
  );
}

describe("chooseIdempotencyKey (TS-29, ERR-16)", () => {
  it("reuses the key of the same reply sent again after a failure", () => {
    const reply = buildSendReplyRequest(draftReady, acknowledged);

    expect(chooseAfterFailure(reply, buildSendReplyRequest(draftReady, acknowledged))).toBe("k1");
  });

  it.each([
    ["another text", startEditing(acknowledged, "x")],
    ["another acknowledgement", opened],
  ])("gets a new key for a reply with %s", (_case, state) => {
    expect(
      chooseAfterFailure(
        buildSendReplyRequest(draftReady, acknowledged),
        buildSendReplyRequest(draftReady, state),
      ),
    ).toBe("k2");
  });

  it("gets a new key for a rejection with other reason codes", () => {
    const first = buildSendReplyRequest(draftReady, {
      ...rejected,
      reasonCodes: new Set(["wrong_intent"]),
    });
    const second = buildSendReplyRequest(draftReady, {
      ...rejected,
      reasonCodes: new Set(["kb_gap"]),
    });

    expect(chooseAfterFailure(first, second)).toBe("k2");
  });
});

describe("chooseIdempotencyKey of an escalation and of a first request", () => {
  it("gets a new key for an escalation with other reasons or another suggestion", () => {
    const first = buildEscalationRequest({ reasonCodes: new Set(["kb_gap"]), note: "" }, "s1");

    expect(
      chooseAfterFailure(
        first,
        buildEscalationRequest({ reasonCodes: new Set(["kb_gap"]), note: "" }, "s1"),
      ),
    ).toBe("k1");
    expect(
      chooseAfterFailure(
        first,
        buildEscalationRequest({ reasonCodes: new Set(["other"]), note: "A note." }, "s1"),
      ),
    ).toBe("k2");
    expect(
      chooseAfterFailure(
        first,
        buildEscalationRequest({ reasonCodes: new Set(["kb_gap"]), note: "" }, "s2"),
      ),
    ).toBe("k2");
  });

  it("gets a new key when the last request succeeded or none was sent", () => {
    const reply = buildSendReplyRequest(draftReady, acknowledged);

    expect(chooseIdempotencyKey(reply, { isError: false, variables: undefined }, () => "k2")).toBe(
      "k2",
    );
  });
});
