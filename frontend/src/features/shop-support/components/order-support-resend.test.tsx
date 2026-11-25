import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { createShopTicketRoute } from "@/test/backend-routes";
import { exampleAnswer, type FakeBackend } from "@/test/fake-backend";
import { BOX_NAME, openOrderSupport, sendMessage } from "@/test/order-support-screen";
import { testSettings } from "@/test/render-app";

/**
 * Read the key of each message that reached `backend`.
 *
 * @param backend - The fake backend.
 * @returns The keys, in the order of the requests.
 */
function readKeys(backend: FakeBackend): readonly (string | null)[] {
  return backend
    .requestsTo(createShopTicketRoute)
    .map((request) => request.headers.get("Idempotency-Key"));
}

describe("OrderSupportSection, the key of a message that is sent again", () => {
  it("reuses the key when the same text is sent again after a failure", async () => {
    const { user, backend } = openOrderSupport({
      creates: [{ kind: "network_error" }, exampleAnswer(201, "createShopTicket", "created")],
    });

    await sendMessage(user, "Is it shipped?");
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Message sent.");
    const [first, second] = readKeys(backend);
    expect(first).toBeTruthy();
    expect(second).toBe(first);
  });

  it("uses a new key when the text changed after a failure", async () => {
    const { user, backend } = openOrderSupport({
      creates: [{ kind: "network_error" }, exampleAnswer(201, "createShopTicket", "created")],
    });

    await sendMessage(user, "Is it shipped?");
    await screen.findByRole("alert");
    await user.type(screen.getByRole("textbox", { name: BOX_NAME }), " Today?");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Message sent.");
    const [first, second] = readKeys(backend);
    expect(second).not.toBe(first);
  });

  it("reuses the key when the text changed and came back to the same text", async () => {
    const { user, backend } = openOrderSupport({
      creates: [{ kind: "network_error" }, exampleAnswer(201, "createShopTicket", "created")],
    });

    await sendMessage(user, "Hello");
    await screen.findByRole("alert");
    const box = screen.getByRole("textbox", { name: BOX_NAME });
    await user.type(box, "!{Backspace}");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Message sent.");
    const [first, second] = readKeys(backend);
    expect(second).toBe(first);
  });

  it("uses a new key for the same text after a success: it is a new message", async () => {
    const { user, backend } = openOrderSupport({
      creates: [
        { kind: "network_error" },
        exampleAnswer(201, "createShopTicket", "created"),
        exampleAnswer(201, "createShopTicket", "created"),
      ],
    });

    await sendMessage(user, "Hello");
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByRole("status");
    await sendMessage(user, "Hello");
    await waitFor(() => {
      expect(backend.requestsTo(createShopTicketRoute)).toHaveLength(3);
    });

    const [first, second, third] = readKeys(backend);
    expect(second).toBe(first);
    expect(third).not.toBe(first);
  });
});

describe("OrderSupportSection, a send with an unknown outcome", () => {
  it.each([
    ["a lost connection", { kind: "network_error" } as const],
    ["a 502 from the ingress", { kind: "ingress", status: 502 } as const],
    ["a 504 from the ingress", { kind: "ingress", status: 504 } as const],
    ["a 201 without a body", { kind: "body", status: 201, body: null } as const],
    ["a 201 with an empty body", { kind: "body", status: 201, body: {} } as const],
  ])("says that the message may have arrived after %s", async (_case, answer) => {
    const { user } = openOrderSupport({ creates: [answer] });

    await sendMessage(user, "Is it shipped?");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your message may have arrived. We could not confirm it. Sending the same text again is safe: support gets it once.",
    );
    expect(screen.queryByText(/was not sent/)).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: BOX_NAME })).toHaveValue("Is it shipped?");
  });

  it("says that the message may have arrived after a timeout", async () => {
    const { user } = openOrderSupport({
      creates: [{ kind: "no_answer" }],
      settings: { ...testSettings, requestTimeoutMs: 1 },
    });

    await sendMessage(user, "Is it shipped?");

    expect(await screen.findByRole("alert")).toHaveTextContent("Your message may have arrived.");
  });

  it.each([
    ["503", exampleAnswer(503, "problems", "not-ready")],
    ["429", { kind: "ingress", status: 429 } as const],
    ["500", exampleAnswer(500, "problems", "internal-error")],
  ])("still says so when the retry after a lost connection gets a %s", async (_case, answer) => {
    const { user } = openOrderSupport({
      creates: [{ kind: "network_error" }, answer],
      settings: { ...testSettings, requestRetryMaxCount: 1 },
    });

    await sendMessage(user, "Is it shipped?");

    expect(await screen.findByRole("alert")).toHaveTextContent("Your message may have arrived.");
  });

  it("shows the trace ID of the last answer when it is a Problem Details body (UI-25)", async () => {
    const { user } = openOrderSupport({
      creates: [{ kind: "network_error" }, exampleAnswer(503, "problems", "not-ready")],
      settings: { ...testSettings, requestRetryMaxCount: 1 },
    });

    await sendMessage(user, "Is it shipped?");

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Your message may have arrived.");
    expect(within(banner).getByText("1c80319c0af7651916cd43dd8448eb21")).toBeVisible();
  });

  it("says that it was not sent when the retry is refused: backend remembers a success", async () => {
    const { user } = openOrderSupport({
      creates: [{ kind: "network_error" }, exampleAnswer(422, "problems", "invalid-request")],
      settings: { ...testSettings, requestRetryMaxCount: 1 },
    });

    await sendMessage(user, "Is it shipped?");

    expect(await screen.findByRole("alert")).toHaveTextContent("Your message was not sent.");
  });

  it("still says so when the customer sends the same text again and backend is busy", async () => {
    const { user, backend } = openOrderSupport({
      creates: [{ kind: "network_error" }, exampleAnswer(503, "problems", "not-ready")],
    });

    await sendMessage(user, "Is it shipped?");
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => {
      expect(backend.requestsTo(createShopTicketRoute)).toHaveLength(2);
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Your message may have arrived.");
    expect(screen.queryByText(/was not sent/)).not.toBeInTheDocument();
  });

  it("says that it was not sent when the text changed, because that is a new message", async () => {
    const { user } = openOrderSupport({
      creates: [{ kind: "network_error" }, exampleAnswer(503, "problems", "not-ready")],
    });

    await sendMessage(user, "Is it shipped?");
    await screen.findByRole("alert");
    await user.type(screen.getByRole("textbox", { name: BOX_NAME }), " Today?");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Your message was not sent.");
    });
  });
});
