/*
 * Shop UI mockups (design doc: docs/design/shop-ui.md).
 * Review material, not frontend code. Open mockup.html?screen=<name>; render.sh renders every screen.
 * Screens whose name ends in "-mobile" are rendered inside a 360 px frame.
 */

const ICONS = {
  chevronRight: '<path d="m9 18 6-6-6-6"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  checkCircle: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
  xCircle: '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  circleDot: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="1"/>',
  send: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
  user: '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
  package: '<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/><path d="M12 22V12"/><path d="M3.3 7 12 12l8.7-5"/>',
  message: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  logOut: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
  shoppingBag: '<path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/>',
  grid: '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
  lifeBuoy: '<circle cx="12" cy="12" r="10"/><path d="m4.93 4.93 4.24 4.24"/><path d="m14.83 9.17 4.24-4.24"/><path d="m14.83 14.83 4.24 4.24"/><path d="m9.17 14.83-4.24 4.24"/><circle cx="12" cy="12" r="4"/>',
  lock: '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  key: '<path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"/><circle cx="16.5" cy="7.5" r=".5" fill="currentColor"/>',
};

function icon(name, extraClass = "") {
  return `<svg class="icon ${extraClass}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
}

// ---------- One presentation per status (UI-12) ----------

const ORDER_STATUS = {
  placed: { tone: "neutral", icon: "circleDot", label: "Placed" },
  processing: { tone: "info", icon: "clock", label: "Processing" },
  shipped: { tone: "info", icon: "package", label: "Shipped" },
  delivered: { tone: "success", icon: "checkCircle", label: "Delivered" },
  cancelled: { tone: "neutral", icon: "xCircle", label: "Cancelled" },
};

const SHIPMENT_STATUS = {
  not_shipped: { tone: "neutral", icon: "circleDot", label: "Not shipped" },
  in_transit: { tone: "info", icon: "package", label: "In transit" },
  delivered: { tone: "success", icon: "checkCircle", label: "Delivered" },
  delayed: { tone: "warning", icon: "clock", label: "Delayed" },
  lost: { tone: "danger", icon: "alert", label: "Lost" },
};

const REFUND_STATUS = {
  none: { tone: "neutral", icon: "circleDot", label: "No refund" },
  requested: { tone: "info", icon: "clock", label: "Refund requested" },
  under_review: { tone: "info", icon: "clock", label: "Refund under review" },
  approved: { tone: "success", icon: "checkCircle", label: "Refund approved" },
  rejected: { tone: "danger", icon: "xCircle", label: "Refund rejected" },
  paid: { tone: "success", icon: "checkCircle", label: "Refund paid" },
};

const TICKET_STATUS = {
  received: { tone: "info", icon: "clock", label: "Received" },
  replied: { tone: "success", icon: "checkCircle", label: "Replied" },
};

function badge(p) {
  return `<span class="badge badge-${p.tone}">${icon(p.icon, "icon-sm")}${p.label}</span>`;
}

// ---------- Sample data (synthetic-dev-only) ----------

const CUSTOMER = "Linh Tran";

const ORDERS = [
  { id: "ORD-20990", placed: "28 Oct 2026", order: "shipped", shipment: ["in_transit", "Due 7 Nov 2026"], refund: ["none", ""], total: "$42.50", lines: [{ name: "Desk lamp", qty: 1 }, { name: "Notebook set", qty: 2 }] },
  { id: "ORD-20955", placed: "12 Oct 2026", order: "delivered", shipment: ["delivered", "16 Oct 2026"], refund: ["none", ""], total: "$64.00", lines: [{ name: "Running shoes", qty: 1 }] },
  { id: "ORD-20931", placed: "2 Oct 2026", order: "delivered", shipment: ["delivered", "6 Oct 2026"], refund: ["under_review", "Requested 14 Oct 2026"], total: "$89.00", lines: [{ name: "Wireless headphones", qty: 1 }] },
];
const ORDER = ORDERS[2];

const PRODUCTS = [
  ["Wireless headphones", "Audio", "$89.00"], ["Running shoes", "Sport", "$64.00"], ["Desk lamp", "Home", "$24.50"],
  ["Notebook set", "Stationery", "$9.00"], ["Blender", "Kitchen", "$55.00"], ["Travel mug", "Kitchen", "$12.00"],
];

const REPLIED = {
  id: "TCK-1042", order: "ORD-20931", status: "replied", sent: "3 weeks ago",
  message: "Hi, I sent back the headphones from order ORD-20931 almost two weeks ago and I still haven't got my money back. Can you check what is happening with my refund?",
  reply: { sent: "3 weeks ago", body: "Thank you for your patience. Your refund request for order ORD-20931 was received on 14 October and is under review. You can follow the refund status on this order." },
};

const RECEIVED = {
  id: "TCK-1051", order: "ORD-20990", status: "received", sent: "2 hours ago",
  message: "Where is my parcel? The tracking page has said in transit for five days.",
};

const JUST_SENT = {
  id: "TCK-1063", order: "ORD-20931", status: "received", sent: "Just now",
  message: "Can I also return the charging cable that came with the headphones?",
};

// ---------- Building blocks ----------

function shopBar(active, isMenuOpen = false) {
  const link = (key, iconName, label) => `<a class="${active === key ? "active" : ""}">${icon(iconName)}${label}</a>`;
  return `<header class="shopbar">
    <div class="brand">${icon("shoppingBag")}Demo Shop</div>
    <nav>${link("products", "grid", "Products")}${link("orders", "package", "My orders")}${link("support", "lifeBuoy", "Support")}</nav>
    <div class="user"><button class="account-trigger${isMenuOpen ? " open" : ""}">${icon("user")}<span><b>${CUSTOMER}</b> · Customer</span>${icon("chevronDown", "icon-sm")}</button></div>
  </header>${isMenuOpen ? accountMenu() : ""}`;
}

// The account menu of the account management design, drawn open.
function accountMenu() {
  return `<div class="account-menu" role="menu">
    <div class="menu-heading"><b>${CUSTOMER}</b><span class="muted">Customer</span></div>
    <hr>
    <div class="menu-entry focused" role="menuitem">${icon("key")}Change password</div>
    <div class="menu-entry" role="menuitem">${icon("logOut")}Sign out</div>
  </div>`;
}

function mockLabel(text) {
  return `<div class="mock-label">Mockup · ${text} · Sample data (synthetic-dev-only)</div>`;
}

function page(active, inner, label, overlay = "", isMenuOpen = false) {
  return `<div class="shop-app">${shopBar(active, isMenuOpen)}<main class="shop-main">${inner}</main>${overlay}${mockLabel(label)}</div>`;
}

function lineList(lines) {
  return lines.map((l) => `${l.name}${l.qty > 1 ? ` × ${l.qty}` : ""}`).join(", ");
}

function orderSummary(o) {
  const cell = (label, p, when) => `<div class="status-cell"><span class="label">${label}</span>${badge(p)}<span class="when">${when}</span></div>`;
  const lines = o.lines
    .map((l) => `<div class="line"><span class="thumb">${icon("package")}</span><div><div class="name">${l.name}</div><div class="qty small">Quantity ${l.qty}</div></div></div>`)
    .join("");
  return `<section class="card">
    <div class="card-body"><div class="status-grid">
      ${cell("Order", ORDER_STATUS[o.order], `Placed ${o.placed}`)}
      ${cell("Shipment", SHIPMENT_STATUS[o.shipment[0]], o.shipment[1])}
      ${cell("Refund", REFUND_STATUS[o.refund[0]], o.refund[1] || "Not requested")}
    </div></div>
    <div class="card-body">${lines}<div class="total"><span>Total</span><span>${o.total}</span></div></div>
  </section>`;
}

function threadItem(t) {
  const reply = t.reply
    ? `<div class="bubble-row from-support"><div class="bubble bubble-reply"><div class="who"><b>Reply from support</b><span>· ${t.reply.sent}</span></div>${t.reply.body}</div></div>`
    : `<div class="waiting">${icon("clock", "icon-sm")}No reply yet. A person from our support team replies here.</div>`;
  return `<div class="thread-item" id="ticket-${t.id}">
    <div class="thread-meta"><span class="mono muted">${t.id}</span>${badge(TICKET_STATUS[t.status])}</div>
    <div class="bubble-row from-customer"><div class="bubble bubble-customer"><div class="who"><b>You</b><span>· ${t.sent}</span></div>${t.message}</div></div>
    ${reply}
  </div>`;
}

function composer({ text = "" } = {}) {
  const hasText = text.length > 0;
  return `<div class="composer" id="contact">
    <label class="field-label" for="message">Write to support about this order</label>
    <div class="textarea ${hasText ? "filled" : ""}" id="message">${hasText ? text : "Describe your question."}</div>
    <div class="form-foot">
      <span class="count">${text.length} / 2,000 characters</span>
      <span class="help">${icon("info", "icon-sm")}Each message gets one reply from a person on our support team.</span>
      <span class="end"><button class="btn btn-primary" ${hasText ? "" : "disabled"}>${icon("send", "icon-sm")}Send message</button></span>
    </div>
  </div>`;
}

function supportCard(tickets, composerOptions) {
  const thread = tickets.length ? `<div class="card-body thread">${tickets.map(threadItem).join("")}</div>` : "";
  return `<section class="card">
    <div class="card-head">${icon("lifeBuoy")}Support for this order</div>
    ${thread}
    <div class="card-body">${composer(composerOptions)}</div>
  </section>`;
}

function orderHead() {
  return `<div class="crumbs"><a>My orders</a>${icon("chevronRight", "icon-sm")}<span class="mono">${ORDER.id}</span></div>
    <div class="page-head"><h1>Order <span class="mono" style="font-size: inherit">${ORDER.id}</span></h1><span class="meta">Placed ${ORDER.placed}</span>
      <span class="trail"><button class="btn">${icon("message", "icon-sm")}Contact support</button></span></div>`;
}

// Lists use cursor pagination (CON-14), so there is no page count: Show more loads the next page.
function showMore(label) {
  return `<div class="pager"><button class="btn">${icon("chevronDown", "icon-sm")}${label}</button></div>`;
}

function ordersList() {
  const rows = ORDERS
    .map((o) => `<div class="list-row"><div class="main">
      <div class="row wrap"><span class="strong">Order <span class="mono">${o.id}</span></span><span class="muted small">Placed ${o.placed}</span></div>
      <div class="excerpt muted">${lineList(o.lines)}</div>
      <div class="row wrap"><span class="pair"><span class="muted small">Order</span>${badge(ORDER_STATUS[o.order])}</span><span class="pair"><span class="muted small">Shipment</span>${badge(SHIPMENT_STATUS[o.shipment[0]])}</span>${o.refund[0] === "none" ? "" : badge(REFUND_STATUS[o.refund[0]])}</div>
    </div><span class="price">${o.total}</span>${icon("chevronRight", "go")}</div>`)
    .join("");
  return `<div class="page-head"><h1>My orders</h1></div><section class="card">${rows}</section>`;
}

function supportList() {
  const rows = [RECEIVED, REPLIED]
    .map((t) => `<div class="list-row"><div class="main">
      <div class="excerpt">${t.message}</div>
      <div class="sub"><span class="mono">${t.id}</span><span>· Order <span class="mono">${t.order}</span></span><span>· ${t.sent}</span></div>
    </div>${badge(TICKET_STATUS[t.status])}${icon("chevronRight", "go")}</div>`)
    .join("");
  return `<div class="page-head"><h1>Support</h1></div>
    <div class="help">${icon("info", "icon-sm")}Your messages to support, newest first. Each one opens on the page of its order.</div>
    <section class="card">${rows}</section>`;
}

function productsGrid() {
  const cards = PRODUCTS
    .map(([name, category, price]) => `<div class="product-card"><div class="product-image">${icon("package")}</div><div class="product-body"><div class="name">${name}</div><div class="muted small">${category}</div><div class="strong">${price}</div></div></div>`)
    .join("");
  return `<div class="page-head"><h1>Products</h1><span class="meta">A read-only catalog for the demo</span></div><div class="product-grid">${cards}</div>${showMore("Show more products")}`;
}

function productDetail() {
  return `<div class="crumbs"><a>Products</a>${icon("chevronRight", "icon-sm")}<span>Wireless headphones</span></div>
    <section class="card product-detail">
      <div class="product-image large">${icon("package")}</div>
      <div class="stack">
        <h1 class="product-title">Wireless headphones</h1>
        <span class="muted">Audio</span>
        <span class="price-large">$89.00</span>
        <p class="description">Over-ear headphones with a long battery life and a charging cable. This text is sample data.</p>
        <div class="help">${icon("info", "icon-sm")}The demo shop has no cart. Questions about an order go through My orders.</div>
      </div>
    </section>`;
}

function contactPanel() {
  return `<section class="contact-panel" role="dialog" aria-label="Contact support">
    <div class="card-head">${icon("message")}Contact support<span class="trail"><button class="btn btn-ghost btn-sm" aria-label="Close">${icon("x", "icon-sm")}</button></span></div>
    <div class="card-body stack-8">
      <label class="field-label">Which order is this about?</label>
      <div class="select"><span><span class="mono">${ORDER.id}</span> · Wireless headphones</span>${icon("chevronDown", "icon-sm")}</div>
      <label class="field-label">Your message</label>
      <div class="textarea small-area">Describe your question.</div>
      <div class="form-foot"><span class="count">0 / 2,000</span><span class="end"><button class="btn btn-primary" disabled>${icon("send", "icon-sm")}Send message</button></span></div>
      <div class="help">${icon("info", "icon-sm")}Each message is about one of your orders. The reply appears on that order's page.</div>
    </div>
  </section>`;
}

// ---------- Screens ----------

const ORDER_PAGE = () => `${orderHead()}${orderSummary(ORDER)}${supportCard([REPLIED])}`;

const SCREENS = {
  "products": () => page("products", productsGrid(), "Products"),
  "product": () => page("products", productDetail(), "Product"),
  "orders": () => page("orders", ordersList(), "My orders"),
  "order": () => page("orders", ORDER_PAGE(), "Order with its support tickets and the message box"),
  "order-sent": () => page("orders",
    `<div class="banner banner-success">${icon("checkCircle")}<div><b>Message sent.</b> A person from our support team replies here.</div></div>${supportCard([REPLIED, JUST_SENT])}`,
    "Order after sending a message, scrolled to its tickets"),
  "support": () => page("support", supportList(), "Support"),
  "order-loading": () => page("orders",
    `<div class="crumbs"><a>My orders</a></div><span class="skeleton w-60"></span><section class="card"><div class="card-body stack-8"><span class="skeleton w-90"></span><span class="skeleton w-80"></span><span class="skeleton w-60"></span></div></section><section class="card"><div class="card-body stack-8"><span class="skeleton w-100"></span><span class="skeleton w-80"></span></div></section>`,
    "State · loading"),
  "order-not-found": () => page("orders",
    `<section class="card"><div class="card-body"><div class="empty-state">${icon("search")}<b>This order was not found</b><span class="muted">It may not exist, or it belongs to another account.</span><button class="btn">Back to My orders</button></div></div></section>`,
    "State · not found (404)"),
  "permission-denied": () => `<div class="shop-app"><header class="shopbar"><div class="brand">${icon("shoppingBag")}Demo Shop</div></header><main class="shop-main"><section class="card"><div class="card-body"><div class="empty-state">${icon("lock")}<b>The shop is for customer accounts</b><span class="muted">You are signed in with a support or admin account. Sign out, then sign in with a customer account.</span><button class="btn">${icon("logOut", "icon-sm")}Sign out</button><span class="row small muted">Details: trace 9e2f61c0</span></div></div></section></main>${mockLabel("State · permission denied (403)")}</div>`,
  "orders-mobile": () => page("orders", ordersList(), "My orders, phone width"),
  "order-mobile": () => page("orders", ORDER_PAGE(), "Order, phone width"),
  "account-menu-mobile": () => page("orders", ordersList(), "Account menu open, phone width", "", true),
  "proposal-contact-panel": () => page("products", productsGrid(), "Proposal, not decided · Contact support panel with an order picker", contactPanel()),
};

const params = new URLSearchParams(window.location.search);
const screen = params.get("screen") ?? "order";
if (screen.endsWith("-mobile") && !params.has("frame")) {
  document.body.className = "phone-frame";
  document.body.innerHTML = `<iframe title="Phone width" scrolling="no" width="360" height="1240" src="mockup.html?screen=${screen}&frame=1"></iframe>`;
} else {
  document.body.innerHTML = (SCREENS[screen] ?? SCREENS.order)();
}
