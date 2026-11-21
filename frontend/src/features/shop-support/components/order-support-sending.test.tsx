import { act, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { createShopTicketRoute, listShopTicketsRoute } from "@/test/backend-routes";
import { exampleAnswer, holdAnswer } from "@/test/fake-backend";
import { BOX_NAME, openOrderSupport, sendMessage } from "@/test/order-support-screen";
import { testSettings } from "@/test/render-app";

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

describe("OrderSupportSection, sending", () => {
  it("sends the message with a new Idempotency-Key, empties the box, and shows the ticket", async () => {
    const { user, backend } = openOrderSupport({
      tickets: [exampleAnswer(200, "listShopTickets", "empty"), { kind: "no_answer" }],
    });

    await sendMessage(user, "When will it be paid?");

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Message sent. A person from our support team replies here.",
    );
    const [request] = backend.requestsTo(createShopTicketRoute);
    expect(request?.body).toEqual({ order_id: "ORD-20931", message: "When will it be paid?" });
    expect(request?.headers.get("Idempotency-Key")).toMatch(uuidPattern);
    expect(screen.getByRole("textbox", { name: BOX_NAME })).toHaveValue("");
    expect(await screen.findByText("Received")).toBeVisible();
  });

  it("loads the ticket lists again after sending, so the list shows what backend holds", async () => {
    const { user, backend } = openOrderSupport({
      tickets: [
        exampleAnswer(200, "listShopTickets", "empty"),
        exampleAnswer(200, "listShopTickets", "last-page"),
      ],
    });

    await sendMessage(user, "When will it be paid?");

    expect(await screen.findByText("Reply from support")).toBeVisible();
    expect(backend.requestsTo(listShopTicketsRoute)).toHaveLength(2);
  });

  it("keeps one entry when the list already holds the new ticket", async () => {
    const { user } = openOrderSupport();

    await sendMessage(user, "When will it be paid?");

    await screen.findByRole("status");
    const list = screen.getByRole("list", { name: "Tickets about this order" });
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((item) => item.id),
    ).toEqual(["ticket-TCK-1017", "ticket-TCK-1042"]);
  });

  it("keeps the text unchanged while it is sent, so nothing typed is lost", async () => {
    const { user } = openOrderSupport({ creates: [{ kind: "no_answer" }] });

    await sendMessage(user, "Is it shipped?");
    const box = screen.getByRole("textbox", { name: BOX_NAME });
    await user.type(box, " More text");

    expect(box).toHaveAttribute("readonly");
    expect(box).toHaveValue("Is it shipped?");
  });

  it("sends one request when Send message is double-clicked", async () => {
    const { user, backend } = openOrderSupport({ creates: [{ kind: "no_answer" }] });
    await user.type(await screen.findByRole("textbox", { name: BOX_NAME }), "Hello");

    await user.dblClick(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByRole("button", { name: "Sending…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(backend.requestsTo(createShopTicketRoute)).toHaveLength(1);
  });

  it("uses a new key for each Send message", async () => {
    const { user, backend } = openOrderSupport();

    await sendMessage(user, "First");
    await screen.findByRole("status");
    await sendMessage(user, "Second");
    await waitFor(() => {
      expect(backend.requestsTo(createShopTicketRoute)).toHaveLength(2);
    });

    const keys = backend
      .requestsTo(createShopTicketRoute)
      .map((request) => request.headers.get("Idempotency-Key"));
    expect(new Set(keys).size).toBe(2);
  });

  it("retries a failed send automatically with the same key (TS-29)", async () => {
    const { user, backend } = openOrderSupport({
      creates: [
        exampleAnswer(503, "problems", "not-ready"),
        exampleAnswer(201, "createShopTicket", "created"),
      ],
      settings: { ...testSettings, requestRetryMaxCount: 2 },
    });

    await sendMessage(user, "Hello");

    expect(await screen.findByRole("status")).toHaveTextContent("Message sent.");
    const keys = backend
      .requestsTo(createShopTicketRoute)
      .map((request) => request.headers.get("Idempotency-Key"));
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });
});

describe("OrderSupportSection, failed sends keep the text", () => {
  it.each([
    ["503", exampleAnswer(503, "problems", "not-ready"), "The service is not available right now."],
    ["422", exampleAnswer(422, "problems", "invalid-request"), "The request was not accepted."],
    ["404", exampleAnswer(404, "problems", "not-found"), "This order was not found."],
    ["403", exampleAnswer(403, "problems", "forbidden-origin"), "Your account is not allowed"],
    ["413", { kind: "ingress", status: 413 } as const, "The request is too large."],
    ["500", exampleAnswer(500, "problems", "internal-error"), "Something went wrong."],
    ["ingress 503", { kind: "ingress", status: 503 } as const, "The service is not available"],
  ])("explains a %s and keeps the text in the box", async (_case, answer, message) => {
    const { user, backend } = openOrderSupport({ creates: [answer] });

    await sendMessage(user, "Tôi chưa nhận được tiền hoàn 🙏");

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Your message was not sent.");
    expect(banner).toHaveTextContent(message);
    expect(screen.getByRole("textbox", { name: BOX_NAME })).toHaveValue(
      "Tôi chưa nhận được tiền hoàn 🙏",
    );
    expect(backend.requestsTo(createShopTicketRoute)).toHaveLength(1);
  });

  it("opens sign-in with a return path when the session ended (401)", async () => {
    const { user, router } = openOrderSupport({
      creates: [exampleAnswer(401, "problems", "unauthenticated")],
    });

    await sendMessage(user, "Hello");

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sign-in");
    });
    expect(new URLSearchParams(router.state.location.search).get("returnTo")).toBe(
      "/shop/orders/ORD-20931",
    );
  });
});

describe("OrderSupportSection, the focus after sending (UI-30)", () => {
  it("moves the focus to the message box after a success", async () => {
    const { user } = openOrderSupport();

    await sendMessage(user, "Hello");

    await screen.findByRole("status");
    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: BOX_NAME })).toHaveFocus();
    });
  });

  it("moves the focus to the message box after a failure", async () => {
    const { user } = openOrderSupport({
      creates: [exampleAnswer(422, "problems", "invalid-request")],
    });

    await sendMessage(user, "Hello");

    await screen.findByRole("alert");
    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: BOX_NAME })).toHaveFocus();
    });
  });

  it("leaves the focus alone when the customer moved on while it was sent", async () => {
    const created = holdAnswer(exampleAnswer(201, "createShopTicket", "created"));
    const { user } = openOrderSupport({ creates: [created.answer] });
    const link = await screen.findByRole("link", { name: "Wireless headphones" });
    await sendMessage(user, "Hello");
    await screen.findByRole("button", { name: "Sending…" });

    act(() => {
      link.focus();
    });
    created.release();

    await screen.findByRole("status");
    await screen.findByRole("button", { name: "Send message" });
    // Moving the pointer waits for the browser's task queue, so the effect of the end of sending ran.
    await user.hover(link);
    expect(link).toHaveFocus();
  });
});

describe("OrderSupportSection, message length (MessageText)", () => {
  it("allows exactly 2,000 characters and refuses 2,001", async () => {
    const { user } = openOrderSupport();
    const box = await screen.findByRole("textbox", { name: BOX_NAME });

    await user.click(box);
    await user.paste("x".repeat(2000));
    expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled();
    await user.paste("y");

    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    expect(screen.getByText(/2,001 \/ 2,000 characters/)).toBeVisible();
  });

  it("counts an emoji as one character, as the contract does", async () => {
    const { user } = openOrderSupport();

    await user.type(await screen.findByRole("textbox", { name: BOX_NAME }), "😊");

    expect(screen.getByText("1 / 2,000 characters")).toBeVisible();
  });
});
