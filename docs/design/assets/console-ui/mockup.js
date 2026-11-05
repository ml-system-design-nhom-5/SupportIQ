// Console UI mockups (design doc: docs/design/console-ui.md).
// Review material, not frontend code. mockup.html takes ?screen=<name>, and this script draws
// that screen from the sample data below.
// All names, IDs, messages, documents, and dates are sample data (synthetic-dev-only), not KB content.

const ICONS = {
  chevronRight: '<path d="m9 18 6-6-6-6"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  checkCircle: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
  xCircle: '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
  sparkles: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 3v4"/><path d="M17 5h4"/>',
  arrowUpCircle: '<circle cx="12" cy="12" r="10"/><path d="m16 12-4-4-4 4"/><path d="M12 16V8"/>',
  circleDot: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="1"/>',
  fileText: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
  pencil: '<path d="M21.17 6.81a1 1 0 0 0-3.99-3.99L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5z"/>',
  send: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
  user: '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
  package: '<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/><path d="M12 22V12"/><path d="M3.3 7 12 12l8.7-5"/>',
  message: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
  barChart: '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
  loader: '<path d="M21 12a9 9 0 1 1-6.22-8.56"/>',
  code: '<path d="m16 18 6-6-6-6"/><path d="m8 6-6 6 6 6"/>',
  logOut: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M8 16H3v5"/>',
  more: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
  copy: '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2"/>',
};

function icon(name, extraClass = "") {
  return `<svg class="icon ${extraClass}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
}

// ---------- One presentation per status (UI-12) ----------

const TICKET_STATUS = {
  open: { tone: "info", icon: "circleDot", label: "Open" },
  awaiting_approval: { tone: "warning", icon: "clock", label: "Awaiting approval" },
  escalated: { tone: "warning", icon: "arrowUpCircle", label: "Escalated" },
  closed: { tone: "success", icon: "checkCircle", label: "Closed" },
};

const DRAFT_STATUS = {
  pending: { tone: "info", icon: "loader", label: "Generating draft" },
  draft_ready: { tone: "ai", icon: "sparkles", label: "Draft ready" },
  abstained: { tone: "warning", icon: "alert", label: "AI abstained" },
  escalation_recommended: { tone: "warning", icon: "arrowUpCircle", label: "Escalation recommended" },
  unavailable: { tone: "danger", icon: "xCircle", label: "AI unavailable" },
  manual: { tone: "neutral", icon: "user", label: "Manual handling" },
};

const VALIDITY = {
  valid: { tone: "success", icon: "checkCircle", label: "In effect" },
  expired: { tone: "warning", icon: "clock", label: "Expired" },
  conflicting: { tone: "danger", icon: "alert", label: "Conflicting" },
};

function badge(p) {
  return `<span class="badge badge-${p.tone}">${icon(p.icon, "icon-sm")}${p.label}</span>`;
}

function confidence(band, percent) {
  const on = { high: 3, medium: 2, low: 1 }[band];
  const bars = [1, 2, 3].map((i) => `<i class="${i <= on ? "on" : ""}"></i>`).join("");
  const label = band[0].toUpperCase() + band.slice(1);
  return `<span class="confidence ${band}"><span class="bars">${bars}</span>${label} · ${percent}%</span>`;
}

// ---------- Sample data (synthetic-dev-only) ----------

const STAFF = { name: "Mai Nguyen", role: "Staff" };
const MANAGER = { name: "Hoa Pham", role: "Manager" };

const POLICY_SOURCES = [
  { num: 1, title: "Refund policy", id: "refund-policy", version: "v3", validity: "valid", period: "Since 1 Sep 2026" },
  { num: 2, title: "Returns policy", id: "returns-policy", version: "v2", validity: "valid", period: "Since 15 Jul 2026" },
  { num: null, title: "Shipping FAQ", id: "shipping-faq", version: "v4", validity: "expired", period: "Ended 30 Sep 2026" },
];

const DRAFT_PARAGRAPHS = [
  [{ text: "Thank you for your patience." }],
  [
    { text: "Your refund request for order ORD-20931 was received on 14 October and is currently under review.", cites: ["order"] },
    { text: "Refund requests are reviewed as described in our refund policy.", cites: [1] },
    { text: "If you have the tracking number for your return, please reply with it so we can confirm that the return has arrived.", cites: [2] },
  ],
];

const BASE = {
  user: STAFF,
  ticket: { id: "TCK-1042", status: "open", mode: "Assisted", customer: "Linh Tran", received: "18 min ago" },
  isAuthorityRequired: false,
  message: "Hi, I sent back the headphones from order ORD-20931 almost two weeks ago and I still haven't got my money back. Can you check what is happening with my refund?",
  order: {
    id: "ORD-20931",
    chip: "Delivered · Refund under review",
    facts: [["Order", "Delivered", "Placed 2 Oct"], ["Shipment", "Delivered", "6 Oct"], ["Refund", "Under review", "Requested 14 Oct"], ["Total", "$89.00", "1 item"]],
    items: "Wireless headphones × 1",
    address: "12 Sample Street, Hanoi",
  },
  intent: { name: "Refund status", band: "high", percent: 91, source: "Predicted" },
  candidates: [{ name: "Request refund", percent: 5 }, { name: "Return product", percent: 2 }],
  recommendation: "Reply with a draft",
  reasonChips: [],
  warnings: [{ label: "Missing information", text: "The request needs information that is in neither the message nor the order. See the note for staff." }],
  draft: { generated: "1 min ago", paragraphs: DRAFT_PARAGRAPHS },
  sources: POLICY_SOURCES,
  staffNote: "The refund has been under review since 14 October. No cited source states how long a review takes, so the draft gives no date. The customer has not given a return tracking number.",
  reply: "draft",
  actions: {
    edit: { label: "Edit draft", enabled: true },
    reject: { enabled: true },
    escalate: { enabled: true },
    more: { enabled: true },
    send: { label: "Send reply", enabled: false, icon: "send" },
    reason: "Acknowledge 1 warning to send the reply.",
  },
};

const ACTIONS_OFF = {
  edit: { label: "Edit draft", enabled: false },
  reject: { enabled: false },
  escalate: { enabled: false },
  more: { enabled: false },
  send: { label: "Send reply", enabled: false, icon: "send" },
};

const MANAGER_REVIEW = {
  user: MANAGER,
  rail: "awaiting_approval",
  ticket: { id: "TCK-1038", status: "awaiting_approval", mode: "Assisted", customer: "An Vo", received: "41 min ago" },
  isAuthorityRequired: true,
  message: "My blender from order ORD-20877 arrived with a cracked jug. I don't want a replacement, I want a full refund.",
  order: {
    id: "ORD-20877",
    chip: "Delivered · No refund requested",
    facts: [["Order", "Delivered", "Placed 20 Oct"], ["Shipment", "Delivered", "24 Oct"], ["Refund", "None", "Not requested"], ["Total", "$64.00", "1 item"]],
    items: "Blender × 1",
    address: "8 Example Lane, Da Nang",
  },
  intent: { name: "Request refund", band: "high", percent: 88, source: "Predicted" },
  candidates: [{ name: "Return product", percent: 6 }, { name: "Delivery issue", percent: 3 }],
  reasonChips: [{ icon: "shield", label: "Requires authority" }],
  warnings: [],
  proposal: {
    by: "Minh Le (staff)",
    submitted: "12 min ago",
    text: "Hi An, I'm sorry your blender arrived damaged. I have passed your refund request to a manager, who will decide on it and reply to you here.",
  },
  draft: {
    generated: "38 min ago",
    paragraphs: [
      [{ text: "I'm sorry the blender arrived with a cracked jug." }],
      [
        { text: "Refund requests for items that arrive damaged are handled under our refund policy.", cites: [1, 2] },
        { text: "A manager will review your request and reply to you on this ticket." },
      ],
    ],
  },
  sources: [
    { num: 1, title: "Refund policy", id: "refund-policy", version: "v3", validity: "valid", period: "Since 1 Sep 2026" },
    { num: 2, title: "Damaged items", id: "damaged-items", version: "v1", validity: "valid", period: "Since 1 Aug 2026" },
  ],
  staffNote: "The customer asks for a full refund for an item that arrived damaged. The draft holds supporting information only; the refund decision belongs to a manager.",
  reply: "proposal",
  actions: {
    edit: { label: "Edit proposal", enabled: true },
    reject: { enabled: false },
    escalate: { enabled: false },
    more: { enabled: false },
    send: { label: "Send reply", enabled: true, icon: "send" },
    reason: "Reject draft and Escalate ticket are not available while the ticket awaits approval.",
  },
};

const OPEN_INBOX = [
  { id: "TCK-1042", customer: "Linh Tran", excerpt: "Hi, I sent back the headphones from order ORD-20931 almost two weeks ago…", intent: ["Refund status", "high", 91], ai: "draft_ready", age: "18 min ago" },
  { id: "TCK-1043", customer: "Quang Do", excerpt: "Where is my parcel? The tracking page has said out for delivery since yesterday", intent: ["Track order", "high", 95], ai: "draft_ready", age: "15 min ago", opened: "Opened 4 min ago" },
  { id: "TCK-1044", customer: "Thu Ha", excerpt: "hi i want to talk to a real person pls", intent: ["Human agent", "high", 97], ai: "escalation_recommended", age: "12 min ago" },
  { id: "TCK-1045", customer: "Bao Tran", excerpt: "I want a refund for the shoes from order ORD-20955, they fall apart", intent: ["Request refund", "high", 84], ai: "draft_ready", authority: true, age: "9 min ago" },
  { id: "TCK-1046", customer: "Lan Anh", excerpt: "can u change the colour of my order", intent: ["Cancel order", "low", 41], ai: "abstained", age: "6 min ago" },
  { id: "TCK-1047", customer: "Khanh Vu", excerpt: "My order still hasn't arrived and it has been three weeks", intent: null, noIntent: "No analysis", ai: "unavailable", age: "3 min ago" },
  { id: "TCK-1048", customer: "Phuc Le", excerpt: "How much is shipping for order ORD-20990 if I add another item?", intent: ["Shipping costs", "high", 89], ai: "pending", age: "1 min ago" },
  { id: "TCK-1049", customer: "Mai Do", excerpt: "I need to return a jacket that does not fit", intent: null, noIntent: "No AI (manual)", ai: "manual", age: "Just now" },
  { id: "TCK-1050", customer: "Son Pham", excerpt: "Do you gift wrap orders for birthdays?", intent: ["Delivery options", "medium", 62], ai: "abstained", age: "Just now" },
];

const RAILS = {
  awaiting_approval: {
    title: "Awaiting approval",
    items: [
      { id: "TCK-1038", customer: "An Vo", excerpt: "My blender from order ORD-20877 arrived with a cracked jug…", intent: ["Request refund", "high", 88], authority: true, age: "41 min ago", status: "awaiting_approval" },
      { id: "TCK-1040", customer: "Tuan Ho", excerpt: "I returned the shoes but the refund is less than I paid", intent: ["Refund status", "medium", 66], authority: true, age: "27 min ago", status: "awaiting_approval" },
    ],
  },
  escalated: {
    title: "Escalated",
    items: [
      { id: "TCK-1036", customer: "Nam Dang", excerpt: "The app says my parcel was delivered but nobody here received it", intent: ["Delivery issue", "high", 86], age: "2 h ago", status: "escalated" },
    ],
  },
  closed: {
    title: "Closed",
    items: [
      { id: "TCK-1031", customer: "Vy Hoang", excerpt: "How long do refunds to a bank card take?", intent: ["Refund policy", "high", 93], age: "Yesterday", status: "closed" },
      { id: "TCK-1029", customer: "Duc Tran", excerpt: "Please cancel my order, I bought the wrong size", intent: ["Cancel order", "high", 90], age: "Yesterday", status: "closed" },
    ],
  },
};

const OTHER_ORDERS = [
  { id: "ORD-20874", status: "Shipped · In transit", selected: true },
  { id: "ORD-20655", status: "Delivered · No refund requested" },
];

// ---------- Shell ----------

function appBar(user, active = "tickets") {
  const reports = user.role === "Manager"
    ? `<a class="${active === "reports" ? "active" : ""}">${icon("barChart")}Reports</a>`
    : "";
  return `<header class="appbar">
    <div class="brand">SupportIQ <span>Console</span></div>
    <nav><a class="${active === "tickets" ? "active" : ""}">${icon("inbox")}Tickets</a>${reports}</nav>
    <div class="user">${icon("user")}<span><b>${user.name}</b> · ${user.role}</span>
      <button class="btn btn-ghost btn-sm">${icon("logOut", "icon-sm")}Sign out</button></div>
  </header>`;
}

function mockLabel(text) {
  return `<div class="mock-label">Mockup · ${text} · Sample data (synthetic-dev-only), not KB content</div>`;
}

// ---------- Inbox (left sidebar) ----------

function inboxItem(q, activeId) {
  const intent = q.intent
    ? `<div class="row small">${q.intent[0]}${confidence(q.intent[1], q.intent[2])}</div>`
    : `<div class="row small muted">${q.noIntent}</div>`;
  const status = q.status ? badge(TICKET_STATUS[q.status]) : badge(DRAFT_STATUS[q.ai]);
  const authority = q.authority ? `<span class="badge badge-warning">${icon("shield", "icon-sm")}Authority</span>` : "";
  const opened = q.opened ? `<div class="muted small row">${icon("user", "icon-sm")}${q.opened}</div>` : "";
  return `<div class="rail-item ${q.id === activeId ? "active" : ""}">
    <div class="row"><span class="mono">${q.id}</span><span class="muted small">${q.age}</span></div>
    <div class="strong">${q.customer}</div>
    <div class="excerpt small">${q.excerpt}</div>
    ${intent}
    <div class="row">${status}${authority}</div>
    ${opened}
  </div>`;
}

function inboxRail(railKey, activeId, { emptyText, hide } = {}) {
  const list = (railKey === "open" ? OPEN_INBOX : RAILS[railKey].items).filter((q) => q.id !== hide);
  const title = railKey === "open" ? "Open" : RAILS[railKey].title;
  const index = list.findIndex((q) => q.id === activeId);
  const start = Math.max(0, index - 4);
  const items = emptyText
    ? `<div class="rail-empty muted">${icon("inbox")}${emptyText}</div>`
    : list.slice(start, start + 6).map((q) => inboxItem(q, activeId)).join("");
  return `<aside class="rail">
    <div class="rail-head">${icon("inbox")}<button class="btn btn-sm">${title} ${icon("chevronDown", "icon-sm")}</button><span class="trail muted small">Oldest first</span></div>
    ${items}
  </aside>`;
}

// ---------- Ticket header and order chip ----------

function orderFacts(o) {
  return `<dl class="dl">
    ${o.facts.map(([k, v, sub]) => `<dt>${k}</dt><dd><b>${v}</b> <span class="muted">· ${sub}</span></dd>`).join("")}
    <dt>Items</dt><dd>${o.items}</dd>${o.address ? `<dt>Ship to</dt><dd>${o.address}</dd>` : ""}
  </dl>`;
}

function singleOrderPopover(o) {
  return `<div class="popover" role="dialog" aria-label="Order ${o.id}">
    <div class="panel-head">${icon("package")}Order <span class="mono">${o.id}</span><span class="trail muted small">From order records, not AI</span></div>
    <div class="panel-body">${orderFacts(o)}</div>
  </div>`;
}

function multiOrderPopover(o) {
  const rows = [{ id: o.id, status: o.chip, tag: "This ticket" }, ...OTHER_ORDERS]
    .map((r) => `<div class="order-row ${r.selected ? "selected" : ""}">
      <span class="mono">${r.id}</span>${r.tag ? `<span class="badge badge-neutral">${r.tag}</span>` : ""}
      <span class="muted small order-row-status">${r.status}</span>
    </div>`)
    .join("");
  const preview = {
    facts: [["Order", "Shipped", "Placed 20 Oct"], ["Shipment", "In transit", "Due 24 Oct"], ["Refund", "None", "Not requested"], ["Total", "$42.00", "1 item"]],
    items: "Running shoes × 1",
  };
  return `<div class="popover popover-orders" role="dialog" aria-label="Orders of this customer">
    <div class="panel-head">${icon("package")}Orders of this customer<span class="muted">3</span><span class="trail muted small">From order records, not AI</span></div>
    <div class="orders-split">
      <div class="orders-list">${rows}</div>
      <div class="orders-preview">
        <div class="orders-note">${icon("info", "icon-sm")}Not the order of this ticket. The AI did not use it.</div>
        ${orderFacts(preview)}
      </div>
    </div>
  </div>`;
}

function orderChip(s, { orderPopover }) {
  const o = s.order;
  const more = orderPopover === "multiple" ? `<span class="order-more">+2 orders</span>` : "";
  const popover = { single: singleOrderPopover, multiple: multiOrderPopover }[orderPopover]?.(o) ?? "";
  return `<span class="anchor"><button class="order-chip ${orderPopover ? "open" : ""}">${icon("package", "icon-sm")}<span class="mono">${o.id}</span><span>${o.chip}</span>${more}${icon("chevronDown", "icon-sm")}</button>${popover}</span>`;
}

function ticketHeader(s, opts) {
  const t = s.ticket;
  const modeIcon = t.mode === "Manual" ? "user" : "sparkles";
  return `<div class="ticket-header">
    <span class="title">Ticket <span class="mono">${t.id}</span></span>
    ${badge(TICKET_STATUS[t.status])}
    <span class="badge badge-neutral">${icon(modeIcon, "icon-sm")}${t.mode}</span>
    <span class="divider-v"></span>
    ${orderChip(s, opts)}
    <span class="meta"><span>${icon("user", "icon-sm")} ${t.customer}</span><span>Received ${t.received}</span></span>
  </div>`;
}

function banners(s) {
  const authority = s.isAuthorityRequired
    ? `<div class="banner banner-warning">${icon("shield")}<div><b>Authority required.</b> The AI output is supporting information only. A manager decides and sends the reply.</div></div>`
    : "";
  const extra = s.banner ? `<div class="banner banner-${s.banner.tone}">${icon(s.banner.icon)}<div>${s.banner.html}</div></div>` : "";
  return authority || extra ? `<div class="banner-wrap">${authority}${extra}</div>` : "";
}

// ---------- Middle column ----------

function messagePanel(s) {
  return `<section class="panel">
    <div class="panel-head">${icon("message")}Customer message</div>
    <div class="panel-body"><div class="message-text">${s.message}</div><div class="muted small">${s.ticket.customer} · ${s.ticket.received}</div></div>
  </section>`;
}

function intentStrip(s) {
  if (s.intentView === "none") return "";
  if (s.intentView === "skeleton") {
    return `<section class="panel"><div class="panel-body"><span class="skeleton w-60"></span></div></section>`;
  }
  if (s.intentView === "choose") {
    const rows = [{ name: s.intent.name, percent: s.intent.percent, band: s.intent.band }, ...s.candidates]
      .map((c) => `<div class="candidate"><span class="name">${c.name}</span>${c.band ? confidence(c.band, c.percent) : `<span class="muted small">${c.percent}%</span>`}<button class="btn btn-sm">Use this intent</button></div>`)
      .join("");
    return `<section class="panel panel-ai">
      <div class="panel-head">${icon("sparkles")}Choose an intent<span class="trail"><span class="badge badge-warning">${icon("alert", "icon-sm")}Low confidence</span></span></div>
      <div class="panel-body"><div class="candidates">${rows}</div></div>
    </section>`;
  }
  const isChosen = s.intent.source === "Chosen by staff";
  const alternatives = isChosen ? "" : s.candidates
    .map((c) => `<button class="btn btn-sm">${c.name}<span class="muted">${c.percent}%</span></button>`)
    .join("");
  const change = `<span class="row wrap"><span class="muted small">Not right? Use:</span>${alternatives}<button class="btn btn-sm btn-ghost">Other intent ${icon("chevronRight", "icon-sm")}</button></span>`;
  const conf = s.intent.band ? confidence(s.intent.band, s.intent.percent) : "";
  const tone = isChosen ? "badge-neutral" : "badge-ai";
  return `<section class="panel panel-ai">
    <div class="panel-body intent-strip">
      <span class="row strong">${icon("sparkles")}Intent</span>
      <span class="row"><span class="intent-name">${s.intent.name}</span>${conf}<span class="badge ${tone}">${s.intent.source}</span></span>
      ${change}
    </div>
  </section>`;
}

function citationMarker(cite) {
  return cite === "order"
    ? `<span class="cite cite-plain cite-order" aria-label="From order records, not AI">${icon("package", "icon-sm")}</span>`
    : `<span class="cite">${cite}</span>`;
}

function draftText(draft) {
  return draft.paragraphs
    .map((p) => `<p>${p.map((seg) => seg.text + (seg.cites || []).map(citationMarker).join("")).join(" ")}</p>`)
    .join("");
}

function warningsBlock(s) {
  if (!s.warnings.length) return "";
  const items = s.warnings
    .map((w) => `<div class="warning-item">${icon("alert")}<div class="text"><b>${w.label}</b><div class="small">${w.text}</div></div>
      <label class="checkbox"><i></i>I have checked this</label></div>`)
    .join("");
  return `<div class="panel-body"><p class="section-label">${s.warnings.length} warning to check before sending</p><div class="stack-8">${items}</div></div>`;
}

function actionBar(a, { menuOpen = false } = {}) {
  const dis = (on) => (on ? "" : "disabled");
  const retry = a.retry ? `<button class="btn">${icon("refresh", "icon-sm")}Try AI again</button>` : "";
  const menu = menuOpen
    ? `<div class="menu" role="menu"><div class="menu-item">${icon("clock", "icon-sm")}Submit for approval<span class="muted small">A manager sends the reply</span></div></div>`
    : "";
  const reason = a.reason ? `<span class="reason">${icon("info", "icon-sm")}${a.reason}</span>` : "";
  const more = a.more?.hidden
    ? ""
    : `<span class="anchor"><button class="btn" ${dis(a.more?.enabled)} aria-label="More actions">${icon("more", "icon-sm")}</button>${menu}</span>`;
  const submit = a.submit ? `<button class="btn" ${dis(a.submit.enabled)}>${icon("clock", "icon-sm")}Submit for approval</button>` : "";
  return `<div class="action-bar">
    ${reason}
    <div class="buttons">
      ${retry}
      ${a.edit?.hidden ? "" : `<button class="btn" ${dis(a.edit.enabled)}>${icon("pencil", "icon-sm")}${a.edit.label}</button>`}
      ${a.reject?.hidden ? "" : `<button class="btn" ${dis(a.reject.enabled)}>${icon("x", "icon-sm")}Reject draft</button>`}
      <button class="btn" ${dis(a.escalate.enabled)}>${icon("arrowUpCircle", "icon-sm")}Escalate ticket</button>
      ${submit}${more}
      <button class="btn btn-primary end" ${dis(a.send.enabled)}>${icon(a.send.icon, "icon-sm")}${a.send.label}</button>
    </div>
  </div>`;
}

function draftPanel(s, opts) {
  return `<section class="panel panel-ai fill">
    <div class="panel-head">${icon("sparkles")}AI draft<span class="trail">${badge(DRAFT_STATUS.draft_ready)}<span class="muted small">Generated ${s.draft.generated}</span></span></div>
    ${warningsBlock(s)}
    <div class="panel-body grow draft-text">${draftText(s.draft)}</div>
    ${actionBar(s.actions, opts)}
  </section>`;
}

function proposalPanel(s) {
  const p = s.proposal;
  return `<section class="panel fill">
    <div class="panel-head">${icon("clock")}Reply for approval<span class="trail muted small">${s.proposalHint ?? "Send it as proposed, or edit it first"}</span></div>
    <div class="panel-body grow"><div class="compare">
      <div class="compare-card editable"><div class="head">${icon("user", "icon-sm")}Staff proposal<span class="trail muted small">${p.by} · ${p.submitted}</span></div>
        <div class="draft-text"><p>${p.text}</p></div></div>
      <div class="compare-card ai"><div class="head">${icon("sparkles", "icon-sm")}AI draft<span class="trail"><span class="badge badge-ai">For comparison</span></span></div>
        <div class="draft-text">${draftText(s.draft)}</div></div>
    </div></div>
    ${actionBar(s.actions)}
  </section>`;
}

function skeletonPanel(s) {
  return `<section class="panel panel-ai fill">
    <div class="panel-head">${icon("sparkles")}AI draft<span class="trail">${badge(DRAFT_STATUS.pending)}</span></div>
    <div class="panel-body grow"><div class="stack-8"><span class="skeleton w-90"></span><span class="skeleton w-100"></span><span class="skeleton w-80"></span><span class="skeleton w-60"></span></div></div>
    ${actionBar(s.actions)}
  </section>`;
}

function outdatedPanel(s) {
  return `<section class="panel fill">
    <div class="panel-head">${icon("sparkles")}AI draft<span class="trail">${badge(DRAFT_STATUS.pending)}</span></div>
    <div class="panel-body"><div class="outdated"><span class="badge badge-neutral">Outdated</span><div class="draft-text">${draftText(s.draft)}</div></div></div>
    <div class="panel-body grow"><div class="stack-8"><span class="skeleton w-90"></span><span class="skeleton w-100"></span><span class="skeleton w-60"></span></div></div>
    ${actionBar(s.actions)}
  </section>`;
}

function editor(text, hint) {
  return `<div class="editor ${text ? "" : "editor-empty"}">${text || "Write the reply to the customer"}</div>${hint ? `<div class="muted small row">${icon("info", "icon-sm")}${hint}</div>` : ""}`;
}

function emptyPanel(s) {
  const reasons = (s.reasonLines ?? []).map((r) => `<div class="row">${badge(r)}</div>`).join("");
  return `<section class="panel fill">
    <div class="panel-head">${icon("pencil")}Reply<span class="trail">${s.replyBadge ? badge(s.replyBadge) : ""}</span></div>
    ${s.replyNote ? `<div class="panel-body small">${s.replyNote}</div>` : ""}
    <div class="panel-body grow stack-8">${reasons}${editor("", s.editorHint)}</div>
    ${actionBar(s.actions)}
  </section>`;
}

function noDraftPanel(s) {
  return `<section class="panel fill">
    <div class="panel-head">${icon("sparkles")}AI draft</div>
    <div class="panel-body grow empty-note muted">No draft is created until you choose an intent.</div>
    ${actionBar(s.actions)}
  </section>`;
}

function manualPanel(s) {
  const reminder = `<div class="reminder">${icon("shield")}<div><b>Refund decision or dispute?</b> Do not decide it here. Use Submit for approval, so a manager sends the reply.</div></div>`;
  return `<section class="panel fill">
    <div class="panel-head">${icon("user")}Manual handling<span class="trail">${s.replyBadge ? badge(s.replyBadge) : ""}</span></div>
    <div class="panel-body stack-8"><div class="small">${s.manualText}</div>${reminder}</div>
    <div class="panel-body grow">${editor("")}</div>
    ${actionBar(s.actions)}
  </section>`;
}

function editingPanel(s) {
  return `<section class="panel panel-ai fill">
    <div class="panel-head">${icon("pencil")}Edit draft<span class="trail"><span class="badge badge-ai">${icon("sparkles", "icon-sm")}Started from AI draft</span></span></div>
    ${warningsBlock(s)}
    <div class="panel-body grow stack-8">${editor(s.editorHtml, s.editorHint)}</div>
    ${actionBar(s.actions)}
  </section>`;
}

function rejectedPanel(s) {
  const chips = ["Wrong intent", "Wrong source", "Unsupported claim", "KB gap", "Missing case info", "Tone or clarity", "Case exception", "Other"]
    .map((c, i) => `<span class="chip ${i === 2 ? "chip-on" : ""}">${c}</span>`)
    .join("");
  return `<section class="panel fill">
    <div class="panel-head">${icon("x")}Draft rejected<span class="trail muted small">Your reason improves the AI after review</span></div>
    <div class="panel-body"><p class="section-label">Why did you reject it?</p><div class="row wrap">${chips}</div></div>
    <div class="panel-body"><div class="outdated"><span class="badge badge-neutral">Rejected</span><div class="draft-text">${draftText(s.draft)}</div></div></div>
    <div class="panel-body grow">${editor("")}</div>
    ${actionBar(s.actions)}
  </section>`;
}

function escalatedPanel(s) {
  const chips = s.escalation.reasons.map((r) => `<span class="chip">${r}</span>`).join("");
  return `<section class="panel fill">
    <div class="panel-head">${icon("arrowUpCircle")}Escalated by ${s.escalation.by}<span class="trail muted small">${s.escalation.when}</span></div>
    <div class="panel-body stack-8"><div class="row wrap">${chips}</div><div>${s.escalation.note}</div></div>
    <div class="panel-body grow stack-8">${editor("")}</div>
    ${actionBar(s.actions)}
  </section>`;
}

function closedPanel(s) {
  return `<section class="panel fill">
    <div class="panel-head">${icon("checkCircle")}Reply sent<span class="trail muted small">${s.sent.by} · ${s.sent.when}</span></div>
    <div class="panel-body grow draft-text"><p>${s.sent.text}</p></div>
    ${actionBar(s.actions)}
  </section>`;
}

function replyArea(s, opts) {
  const panels = {
    draft: draftPanel, proposal: proposalPanel, skeleton: skeletonPanel, outdated: outdatedPanel, empty: emptyPanel,
    noDraft: noDraftPanel, manual: manualPanel, editing: editingPanel, rejected: rejectedPanel, escalated: escalatedPanel, closed: closedPanel,
  };
  return panels[s.reply](s, opts);
}

// ---------- Right sidebar ----------

function recommendationPanel(s) {
  const reasons = s.reasonChips.length
    ? s.reasonChips.map((r) => `<span class="badge badge-warning">${icon(r.icon, "icon-sm")}${r.label}</span>`).join("")
    : `<span class="muted small">No escalation reason</span>`;
  return `<section class="panel panel-ai">
    <div class="panel-head">${icon("sparkles")}AI recommendation<span class="trail"><span class="badge badge-ai">AI suggestion</span></span></div>
    <div class="panel-body"><div class="row wrap"><span class="badge badge-ai">${icon("sparkles", "icon-sm")}${s.recommendation}</span>${reasons}</div></div>
  </section>`;
}

function staffNotePanel(s) {
  if (!s.staffNote) return "";
  return `<section class="panel">
    <div class="panel-head">${icon("info")}For staff only<span class="trail"><span class="badge badge-ai">AI note</span></span></div>
    <div class="panel-body"><div class="staff-note">${s.staffNote}</div></div>
  </section>`;
}

function sourcesPanel(s) {
  const items = s.sources.length
    ? s.sources
      .map((d) => {
        const num = d.num ? `<span class="cite">${d.num}</span>` : `<span class="cite cite-plain">–</span>`;
        const cited = d.num ? "" : `<span class="muted small">Not cited</span>`;
        return `<div class="source"><span class="num">${num}</span><div class="body">
        <div class="title">${d.title}</div>
        <div class="line"><span class="mono muted">${d.id} · ${d.version}</span>${badge(VALIDITY[d.validity])}<span class="muted small">${d.period}</span>${cited}</div>
      </div></div>`;
      })
      .join("")
    : `<div class="muted small">No document in effect supports this request.</div>`;
  return `<section class="panel">
    <div class="panel-head">${icon("fileText")}Sources<span class="trail muted small">Open a source to read the full version</span></div>
    <div class="panel-body">${items}</div>
  </section>`;
}

function devRow() {
  return `<div class="dev-row small">${icon("code", "icon-sm")}Developer details${icon("chevronRight", "icon-sm")}</div>`;
}

function aiSidebar(s) {
  return `${recommendationPanel(s)}${staffNotePanel(s)}${sourcesPanel(s)}${devRow()}`;
}

function unavailableSidebar() {
  return `<section class="panel">
    <div class="panel-head">${icon("xCircle")}AI recommendation<span class="trail">${badge(DRAFT_STATUS.unavailable)}</span></div>
    <div class="panel-body small">The AI could not process this ticket, so there is no analysis, draft, or source. Sign-in, ticket viewing, and manual replies keep working.</div>
  </section>${devRow()}`;
}

function manualSidebar() {
  return `<section class="panel">
    <div class="panel-head">${icon("user")}Manual handling</div>
    <div class="panel-body small">This ticket is handled without AI suggestions, so the AI panels stay empty.</div>
  </section>`;
}

function skeletonSidebar() {
  return `<section class="panel"><div class="panel-body"><div class="stack-8"><span class="skeleton w-60"></span><span class="skeleton w-90"></span></div></div></section>
    <section class="panel"><div class="panel-body"><div class="stack-8"><span class="skeleton w-80"></span><span class="skeleton w-100"></span><span class="skeleton w-60"></span></div></div></section>`;
}

const SIDEBARS = { ai: aiSidebar, unavailable: unavailableSidebar, manual: manualSidebar, skeleton: skeletonSidebar };

// ---------- Screens ----------

function workspace(overrides, label, opts = {}) {
  const s = { ...BASE, ...overrides };
  const rail = inboxRail(s.rail ?? "open", s.hideInRail ? null : s.ticket.id, { ...opts, hide: s.hideInRail ? s.ticket.id : null });
  const sidebar = SIDEBARS[s.sidebar ?? "ai"](s);
  return `<div class="app">${appBar(s.user)}<div class="shell">${rail}
    <div class="page">${ticketHeader(s, opts)}${banners(s)}
      <div class="workspace">
        <div class="col">${messagePanel(s)}${intentStrip(s)}${replyArea(s, opts)}</div>
        <div class="col">${sidebar}</div>
      </div></div></div>${opts.overlay ?? ""}${mockLabel(label)}</div>`;
}

function centered(user, railKey, activeId, inner, label, opts = {}) {
  return `<div class="app">${appBar(user)}<div class="shell">${inboxRail(railKey, activeId, opts)}
    <div class="page"><div class="center">${inner}</div></div></div>${mockLabel(label)}</div>`;
}

const AUTHORITY_DRAFT = {
  ticket: { id: "TCK-1045", status: "open", mode: "Assisted", customer: "Bao Tran", received: "9 min ago" },
  isAuthorityRequired: true,
  message: "I want a refund for the shoes from order ORD-20955, they fall apart after one week.",
  order: {
    id: "ORD-20955",
    chip: "Delivered · No refund requested",
    facts: [["Order", "Delivered", "Placed 8 Oct"], ["Shipment", "Delivered", "11 Oct"], ["Refund", "None", "Not requested"], ["Total", "$42.00", "1 item"]],
    items: "Running shoes × 1",
    address: "4 Example Road, Hue",
  },
  intent: { name: "Request refund", band: "high", percent: 84, source: "Predicted" },
  candidates: [{ name: "Return product", percent: 9 }, { name: "Delivery issue", percent: 3 }],
  reasonChips: [{ icon: "shield", label: "Requires authority" }],
  warnings: [],
  draft: {
    generated: "8 min ago",
    paragraphs: [
      [{ text: "I'm sorry the shoes did not last." }],
      [
        { text: "Items delivered within the return period can be returned under our returns policy.", cites: [1] },
        { text: "A manager will review your refund request and reply to you on this ticket." },
      ],
    ],
  },
  sources: [{ num: 1, title: "Returns policy", id: "returns-policy", version: "v2", validity: "valid", period: "Since 15 Jul 2026" }],
  staffNote: "The customer asks for a refund. The draft holds supporting information only; the refund decision belongs to a manager.",
};

const NO_ORDER_FACTS = {
  ticket: { id: "TCK-1047", status: "open", mode: "Assisted", customer: "Khanh Vu", received: "3 min ago" },
  message: "My order still hasn't arrived and it has been three weeks. Where is it?",
  order: {
    id: "ORD-20902",
    chip: "Shipped · Delayed",
    facts: [["Order", "Shipped", "Placed 6 Oct"], ["Shipment", "Delayed", "Due 12 Oct"], ["Refund", "None", "Not requested"], ["Total", "$120.00", "2 items"]],
    items: "Desk lamp × 2",
    address: "3 Sample Avenue, Hanoi",
  },
};

const SEND_DIALOG = `<div class="scrim"><div class="dialog" role="dialog" aria-label="Send reply">
  <h2>Send this reply to Linh Tran?</h2>
  <p class="muted">The customer sees it in the shop right away. A sent reply cannot be changed.</p>
  <div class="dialog-preview draft-text">Thank you for your patience. Your refund request for order ORD-20931 was received on 14 October and is currently under review.…</div>
  <div class="dialog-actions"><button class="btn">Keep editing</button><button class="btn btn-primary">${icon("send", "icon-sm")}Send reply</button></div>
</div></div>`;

const ESCALATE_DIALOG = `<div class="scrim"><div class="dialog" role="dialog" aria-label="Escalate ticket">
  <h2>Escalate ticket TCK-1042 to a manager?</h2>
  <p class="muted">Choose at least one reason. The ticket becomes read-only for you.</p>
  <div class="row wrap">
    <span class="chip">Wrong intent</span><span class="chip">Wrong source</span><span class="chip">Unsupported claim</span><span class="chip">KB gap</span>
    <span class="chip chip-on">Missing case info</span><span class="chip">Tone or clarity</span><span class="chip">Case exception</span><span class="chip">Other</span>
  </div>
  <label class="field"><span class="small strong">Note (required with Other)</span><span class="input">The customer has no return tracking number.</span></label>
  <div class="dialog-actions"><button class="btn">Cancel</button><button class="btn btn-primary">${icon("arrowUpCircle", "icon-sm")}Escalate ticket</button></div>
</div></div>`;

const CITATION_POPOVER = `<div class="popover popover-citation" role="tooltip">
  <div class="panel-head">${icon("fileText")}Refund policy<span class="trail"><span class="mono muted">refund-policy · v3</span></span></div>
  <div class="panel-body stack-8">
    <div class="row">${badge(VALIDITY.valid)}<span class="muted small">Since 1 Sep 2026</span></div>
    <div class="small">"A refund request is reviewed after the returned item is inspected."</div>
    <div class="row small muted">${icon("chevronRight", "icon-sm")}Activate the marker to read the full version</div>
  </div>
</div>`;

const ORDER_CITATION_POPOVER = `<div class="popover popover-citation popover-citation-order" role="tooltip">
  <div class="panel-head">${icon("package")}Order ORD-20931<span class="trail"><span class="muted small">From order records, not AI</span></span></div>
  <div class="panel-body stack-8">
    <div class="row small"><span class="muted">Refund requested</span><span>14 Oct 2026</span></div>
    <div class="row small"><span class="muted">Refund status</span><span>Under review</span></div>
    <div class="row small muted">${icon("chevronRight", "icon-sm")}Activate the marker to open the order details</div>
  </div>
</div>`;

const KB_SHEET = `<div class="scrim scrim-right"><aside class="sheet-panel" role="dialog" aria-label="KB document version">
  <div class="panel-head">${icon("fileText")}Refund policy<span class="trail"><button class="btn btn-sm btn-ghost" aria-label="Close">${icon("x", "icon-sm")}</button></span></div>
  <div class="panel-body stack-8">
    <div class="row wrap"><span class="mono muted">refund-policy · v3</span>${badge(VALIDITY.valid)}</div>
    <div class="muted small">In effect since 1 Sep 2026 · Owner: policy owner · Source: sample</div>
  </div>
  <div class="panel-body grow draft-text">
    <p>This is sample text. It is not KB content and not a policy.</p>
    <p class="highlight-block">A refund request is reviewed after the returned item is inspected.</p>
    <p>The document version opens here in full, so staff can check a citation against its source without leaving the ticket.</p>
  </div>
</aside></div>`;

function reportRow(label, value, target) {
  return `<tr><td>${label}</td><td class="num">${value}</td><td class="muted">${target ?? "No target"}</td></tr>`;
}

function reportTable(title, rows) {
  return `<section class="panel"><div class="panel-head">${title}</div>
    <table class="report"><thead><tr><th>Figure</th><th class="num">Value</th><th>Target</th></tr></thead><tbody>${rows.join("")}</tbody></table></section>`;
}

function reportsScreen() {
  return `<div class="app">${appBar(MANAGER, "reports")}<div class="page page-scroll"><div class="reports">
    <div class="row"><h1 class="page-title">Reports</h1><span class="trail row"><button class="btn btn-sm">1 Oct 2026 – 31 Oct 2026 ${icon("chevronDown", "icon-sm")}</button></span></div>
    <div class="report-grid">
      ${reportTable("Tickets", [reportRow("Created, assisted", "120 tickets"), reportRow("Created, manual", "32 tickets"), reportRow("Closed, assisted", "114 tickets"), reportRow("Closed, manual", "30 tickets")])}
      ${reportTable("Draft decisions", [reportRow("Approved", "52 replies · 46%"), reportRow("Edited", "47 replies · 41%"), reportRow("Rejected", "15 replies · 13%")])}
      ${reportTable("Speed", [reportRow("End-to-end latency p50", "3.6 s", "At most 4 s"), reportRow("End-to-end latency p95", "10.8 s", "At most 12 s"), reportRow("Handling time p50, assisted", "2 min 10 s"), reportRow("Handling time p50, manual", "3 min 05 s")])}
      ${reportTable("AI health and cost", [reportRow("AI error rate", "1.8%"), reportRow("LLM cost, total", "$4.20"), reportRow("LLM cost per suggestion", "$0.03")])}
      ${reportTable("Escalations by staff reason", [reportRow("Missing case info", "6 tickets"), reportRow("Case exception", "4 tickets"), reportRow("Wrong intent", "2 tickets")])}
      ${reportTable("AI outcomes", [reportRow("Draft ready", "98 suggestions"), reportRow("AI abstained", "14 suggestions"), reportRow("Escalation recommended", "6 suggestions"), reportRow("AI unavailable", "2 suggestions")])}
    </div>
  </div></div>${mockLabel("Reports, manager · sample figures, not results")}</div>`;
}

function signInScreen() {
  return `<div class="app"><div class="page"><div class="center">
    <section class="panel sign-in">
      <div class="brand">SupportIQ <span>Console</span></div>
      <label class="field"><span class="small strong">Login name</span><span class="input">staff-1</span></label>
      <label class="field"><span class="small strong">Password</span><span class="input">••••••••••</span></label>
      <div class="error-line small">${icon("alert", "icon-sm")}The login name or the password is not correct.</div>
      <button class="btn btn-primary">Sign in</button>
    </section>
  </div></div>${mockLabel("Sign in, after a failed attempt")}</div>`;
}

function tokenSheet() {
  const roles = [
    ["background", "#F4F4F5", "Page background"], ["surface", "#FFFFFF", "Panels"], ["surface-raised", "#FFFFFF", "Dialogs, popovers"],
    ["border", "#E4E4E7", "Dividers (decorative)"], ["border-strong", "#71717A", "Inputs, checkboxes · 4.8:1"], ["text", "#18181B", "Text · 17.7:1"],
    ["text-muted", "#52525B", "Secondary text · 7.7:1"], ["primary", "#1D4ED8", "Main action · 6.7:1"], ["focus-ring", "#2563EB", "Keyboard focus · 5.2:1"],
    ["success", "#15803D", "Grounded, sent · 5.0:1"], ["warning", "#B45309", "Needs attention · 5.0:1"], ["danger", "#B91C1C", "Blocked, failed · 6.5:1"],
    ["info", "#0369A1", "System information · 5.9:1"], ["ai", "#6D28D9", "AI content · 7.1:1"], ["*-subtle", "#FFFBEB", "Tinted backgrounds"],
  ]
    .map(([n, hex, use]) => `<div class="swatch"><span class="chipcolor" data-hex="${hex}"></span><div><div class="name">${n}</div><div class="mono muted">${hex}</div><div class="small muted">${use}</div></div></div>`)
    .join("");
  const types = [[30, "Page title"], [24, "Heading"], [20, "Screen title"], [18, "Section"], [16, "Shop body"], [14, "Console body"], [12, "Labels, meta"]]
    .map(([size, use]) => `<div class="type-row"><span class="k">${size} px</span><span class="type-sample" data-size="${size}">${use}</span></div>`)
    .join("");
  const spaces = [4, 8, 12, 16, 24, 32, 48, 64]
    .map((n) => `<div class="space-row"><span class="mono">${n}</span><i data-width="${n}"></i></div>`)
    .join("");
  const statusRows = [
    ["Ticket", Object.values(TICKET_STATUS)],
    ["AI draft", Object.values(DRAFT_STATUS)],
    ["Source validity", Object.values(VALIDITY)],
  ]
    .map(([k, list]) => `<span class="muted small">${k}</span><div class="row wrap">${list.map(badge).join("")}</div>`)
    .join("");
  const confidenceRow = `<span class="muted small">Confidence</span><div class="row">${confidence("high", 91)}${confidence("medium", 64)}${confidence("low", 41)}</div>`;
  const buttons = `<span class="muted small">Buttons</span><div class="row"><button class="btn btn-primary">${icon("send", "icon-sm")}Send reply</button><button class="btn">${icon("pencil", "icon-sm")}Edit draft</button><button class="btn" disabled>Escalate ticket</button><span class="cite">1</span><span class="badge badge-ai">${icon("sparkles", "icon-sm")}AI draft</span></div>`;
  return `<div class="app"><div class="sheet">
    <div><h2>Color roles (UI-06), contrast on surface</h2><div class="swatches">${roles}</div>
      <h2 class="spaced">Status presentations (UI-11, UI-12)</h2><div class="status-grid">${statusRows}${confidenceRow}${buttons}</div></div>
    <div><h2>Type scale (UI-08): Inter, JetBrains Mono for IDs</h2>${types}<div class="type-row"><span class="k">Mono 12</span><span class="mono">TCK-1042 · refund-policy · v3</span></div>
      <h2 class="spaced">Spacing (UI-07)</h2>${spaces}
      <h2 class="spaced">Radius 4 / 6 / 8 px · elevation 1 / 2 / 3 (UI-09)</h2>
      <div class="elev"><div class="e1">Level 1</div><div class="e2">Level 2</div><div class="e3">Level 3</div></div></div>
  </div>${mockLabel("Design tokens")}</div>`;
}

const SENDABLE = { ...BASE.actions, send: { label: "Send reply", enabled: true, icon: "send" }, reason: "" };

const SCREENS = {
  tokens: tokenSheet,
  reports: reportsScreen,
  "sign-in": signInScreen,

  "workspace-staff": () => workspace({}, "Workspace · staff, draft ready with a warning"),
  "workspace-manager": () => workspace(MANAGER_REVIEW, "Workspace · manager, reply proposal"),
  "order-single": () => workspace({}, "Order chip · a customer with one order", { orderPopover: "single" }),
  "order-multiple": () => workspace({}, "Order chip · a customer with several orders", { orderPopover: "multiple" }),
  "action-menu": () => workspace({}, "More menu · Submit for approval when authority is not required", { menuOpen: true }),

  "no-ticket-selected": () => centered(STAFF, "open", null, `<div class="empty-state">${icon("inbox")}<b>Select a ticket</b><span class="muted">Tickets wait in the inbox, oldest first.</span></div>`, "/console · no ticket selected"),
  "inbox-empty": () => centered(STAFF, "open", null, `<div class="empty-state">${icon("checkCircle")}<b>No open tickets</b><span class="muted">New tickets appear here on their own.</span></div>`, "/console · empty inbox", { emptyText: "No open tickets" }),
  "state-loading": () => workspace({ intentView: "skeleton", reply: "skeleton", sidebar: "skeleton", actions: { ...ACTIONS_OFF, reason: "Loading the ticket." } }, "State · loading"),
  "state-partial": () => workspace({
    ticket: { id: "TCK-1048", status: "open", mode: "Assisted", customer: "Phuc Le", received: "1 min ago" },
    message: "How much is shipping for order ORD-20990 if I add another item?",
    order: { ...BASE.order, id: "ORD-20990", chip: "Processing · No refund requested" },
    intent: { name: "Shipping costs", band: "high", percent: 89, source: "Predicted" },
    candidates: [{ name: "Delivery time", percent: 6 }, { name: "Track order", percent: 2 }],
    reply: "skeleton", staffNote: "", warnings: [],
    sources: [{ num: null, title: "Shipping FAQ", id: "shipping-faq", version: "v5", validity: "valid", period: "Since 1 Oct 2026" }],
    actions: { ...ACTIONS_OFF, reason: "The AI is still working on this ticket." },
  }, "State · partial, analysis shown and draft pending"),
  "state-choose-intent": () => workspace({
    ticket: { id: "TCK-1046", status: "open", mode: "Assisted", customer: "Lan Anh", received: "6 min ago" },
    message: "can u change the colour of my order",
    order: { ...BASE.order, id: "ORD-20961", chip: "Processing · No refund requested" },
    intentView: "choose",
    intent: { name: "Cancel order", band: "low", percent: 41, source: "Predicted" },
    candidates: [{ name: "Change order", percent: 33 }, { name: "Track order", percent: 11 }],
    reply: "noDraft", recommendation: "Choose an intent", reasonChips: [{ icon: "alert", label: "Low confidence" }], warnings: [], staffNote: "",
    sources: [{ num: null, title: "Order changes", id: "order-changes", version: "v2", validity: "valid", period: "Since 1 Sep 2026" }],
    actions: { ...ACTIONS_OFF, escalate: { enabled: true }, more: { enabled: true }, reason: "Choose an intent to get a draft." },
  }, "State · choose an intent (ESC-01)"),
  "state-abstained": () => workspace({
    ticket: { id: "TCK-1050", status: "open", mode: "Assisted", customer: "Son Pham", received: "Just now" },
    message: "Do you gift wrap orders for birthdays?",
    order: { ...BASE.order, id: "ORD-20995", chip: "Processing · No refund requested" },
    intent: { name: "Delivery options", band: "medium", percent: 62, source: "Predicted" },
    candidates: [{ name: "Shipping costs", percent: 12 }, { name: "Track order", percent: 7 }],
    reply: "empty", replyBadge: DRAFT_STATUS.abstained,
    replyNote: "The AI abstained: no document in effect supports this request.",
    recommendation: "Handle manually", reasonChips: [{ icon: "alert", label: "No valid document" }], warnings: [], staffNote: "", sources: [],
    actions: { ...ACTIONS_OFF, edit: { hidden: true }, reject: { hidden: true }, escalate: { enabled: true }, more: { enabled: true }, reason: "Write a reply to send it." },
  }, "State · AI abstained (ESC-02, ESC-04)"),
  "state-escalation-recommended": () => workspace({
    ticket: { id: "TCK-1044", status: "open", mode: "Assisted", customer: "Thu Ha", received: "12 min ago" },
    message: "hi i want to talk to a real person pls",
    order: { ...BASE.order, id: "ORD-20940", chip: "Delivered · No refund requested" },
    intent: { name: "Human agent", band: "high", percent: 97, source: "Predicted" },
    candidates: [{ name: "Delivery issue", percent: 1 }, { name: "Track order", percent: 1 }],
    reply: "empty", replyBadge: DRAFT_STATUS.escalation_recommended,
    replyNote: "The customer asked for a person. You decide whether a manager is needed.",
    recommendation: "Recommend escalation", reasonChips: [{ icon: "arrowUpCircle", label: "Human agent requested" }], warnings: [], sources: [],
    staffNote: "The customer asked to talk to a person and gave no other detail.",
    actions: { ...ACTIONS_OFF, edit: { hidden: true }, reject: { hidden: true }, escalate: { enabled: true }, more: { enabled: true }, reason: "Write a reply to send it, or escalate the ticket." },
  }, "State · escalation recommended (ESC-03)"),
  "state-intent-changed": () => workspace({
    intent: { name: "Request refund", source: "Chosen by staff" },
    reply: "outdated", warnings: [],
    actions: { ...ACTIONS_OFF, reason: "The AI is still working on this ticket." },
  }, "State · intent changed"),
  "state-ai-unavailable": () => workspace({
    ...NO_ORDER_FACTS, intentView: "none", reply: "manual", sidebar: "unavailable", replyBadge: DRAFT_STATUS.unavailable,
    manualText: "Manual-process instructions appear here. The team provides the text.",
    actions: { retry: true, edit: { hidden: true }, reject: { hidden: true }, escalate: { enabled: true }, more: { hidden: true }, submit: { enabled: false }, send: { label: "Send reply", enabled: false, icon: "send" }, reason: "Write a reply to send it or to submit it for approval." },
  }, "State · AI unavailable (ESC-05)"),
  "state-manual-mode": () => workspace({
    ticket: { id: "TCK-1049", status: "open", mode: "Manual", customer: "Mai Do", received: "Just now" },
    message: "I need to return a jacket that does not fit",
    order: { ...BASE.order, id: "ORD-20997", chip: "Delivered · No refund requested" },
    intentView: "none", reply: "manual", sidebar: "manual", replyBadge: DRAFT_STATUS.manual,
    manualText: "Manual-process instructions appear here. The team provides the text.",
    actions: { edit: { hidden: true }, reject: { hidden: true }, escalate: { enabled: true }, more: { hidden: true }, submit: { enabled: false }, send: { label: "Send reply", enabled: false, icon: "send" }, reason: "Write a reply to send it or to submit it for approval." },
  }, "State · manual mode"),
  "state-authority-required": () => workspace({
    ...AUTHORITY_DRAFT,
    actions: { edit: { label: "Edit draft", enabled: true }, reject: { enabled: true }, escalate: { enabled: true }, more: { hidden: true }, send: { label: "Submit for approval", enabled: true, icon: "clock" }, reason: "A manager sends the reply on this ticket." },
  }, "State · authority required, staff view"),
  "state-awaiting-approval-staff": () => workspace({
    ...AUTHORITY_DRAFT, ticket: { ...AUTHORITY_DRAFT.ticket, status: "awaiting_approval" }, reply: "proposal", hideInRail: true,
    proposal: { by: "Mai Nguyen (you)", submitted: "2 min ago", text: "Hi Bao, I'm sorry the shoes did not last. I have passed your refund request to a manager, who will decide on it and reply to you here." },
    proposalHint: "Waiting for a manager",
    actions: { ...ACTIONS_OFF, reason: "This ticket is read-only for you. A manager sends the reply." },
  }, "State · awaiting approval, staff read-only view"),
  "state-escalated": () => workspace({
    ...MANAGER_REVIEW, rail: "escalated", proposal: undefined, isAuthorityRequired: false, reply: "escalated",
    ticket: { id: "TCK-1036", status: "escalated", mode: "Assisted", customer: "Nam Dang", received: "2 h ago" },
    message: "The app says my parcel was delivered but nobody here received it.",
    order: { ...BASE.order, id: "ORD-20811", chip: "Delivered · No refund requested" },
    intent: { name: "Delivery issue", band: "high", percent: 86, source: "Predicted" },
    candidates: [{ name: "Track order", percent: 8 }, { name: "Request refund", percent: 3 }],
    reasonChips: [], staffNote: "The shipment shows as delivered. The customer says it never arrived.",
    escalation: { by: "Minh Le (staff)", when: "20 min ago", reasons: ["Missing case info"], note: "The customer says the parcel never arrived, and the order shows no signature." },
    actions: { edit: { hidden: true }, reject: { hidden: true }, escalate: { enabled: false }, more: { enabled: false }, send: { label: "Send reply", enabled: false, icon: "send" }, reason: "Write a reply to send it." },
  }, "State · escalated, manager view"),
  "state-closed": () => workspace({
    ...MANAGER_REVIEW, rail: "closed", proposal: undefined, isAuthorityRequired: false, reply: "closed",
    ticket: { id: "TCK-1031", status: "closed", mode: "Assisted", customer: "Vy Hoang", received: "Yesterday" },
    message: "How long do refunds to a bank card take?",
    order: { ...BASE.order, id: "ORD-20760", chip: "Delivered · Refund paid" },
    intent: { name: "Refund policy", band: "high", percent: 93, source: "Predicted" },
    candidates: [{ name: "Refund status", percent: 4 }, { name: "Request refund", percent: 2 }],
    reasonChips: [], staffNote: "",
    sent: { by: "Mai Nguyen (staff)", when: "Yesterday, 16:42", text: "Hi Vy, refunds to a bank card are processed as described in our refund policy. Your bank can take a few working days to show the money." },
    actions: { ...ACTIONS_OFF, reason: "This ticket is closed. A reply was already sent." },
  }, "State · closed"),
  "state-editing": () => workspace({
    reply: "editing",
    editorHtml: "Thank you for your patience.<br><br>Your refund request for order ORD-20931 was received on 14 October and is currently under review. Refund requests are reviewed as described in our refund policy. Please reply with the tracking number of your return.",
    editorHint: "Edited text is not checked against the sources.",
    actions: { ...SENDABLE, edit: { label: "Discard edits", enabled: true } },
  }, "State · editing a draft"),
  "state-rejected": () => workspace({
    reply: "rejected", warnings: [],
    actions: { edit: { hidden: true }, reject: { hidden: true }, escalate: { enabled: true }, more: { enabled: true }, send: { label: "Send reply", enabled: false, icon: "send" }, reason: "Write a reply to send it." },
  }, "State · draft rejected"),
  "state-placeholder": () => workspace({
    reply: "editing", warnings: [],
    editorHtml: 'We have sent the return label to <mark class="placeholder" title="Personal data hidden: replace before sending">[EMAIL]</mark>. Please reply with the tracking number of your return.',
    editorHint: "Personal data hidden: replace before sending.",
    actions: { ...BASE.actions, edit: { label: "Discard edits", enabled: true }, reason: "Replace the highlighted text to send the reply." },
  }, "State · placeholder in the editor"),
  "state-error": () => centered(STAFF, "open", "TCK-1042", `<div class="empty-state">${icon("alert")}<b>This ticket could not be loaded</b><span class="muted">Your connection may have dropped. Try again in a moment.</span><button class="btn btn-sm">Try again</button><span class="row small muted">Details: trace 4bf92f35 ${icon("copy", "icon-sm")}</span></div>`, "State · error, with a copyable trace ID"),
  "state-permission-denied": () => centered(STAFF, "open", null, `<div class="empty-state">${icon("shield")}<b>You cannot open this page</b><span class="muted">Your role does not allow it. Ask a manager if you need it.</span><span class="row small muted">Details: trace 7a1c03de ${icon("copy", "icon-sm")}</span></div>`, "State · permission denied"),

  "dialog-confirm-send": () => workspace({ warnings: [], actions: SENDABLE }, "Dialog · confirm Send reply", { overlay: SEND_DIALOG }),
  "dialog-escalate": () => workspace({ warnings: [], actions: SENDABLE }, "Dialog · Escalate ticket", { overlay: ESCALATE_DIALOG }),
  "citation-popover": () => workspace({ warnings: [], actions: SENDABLE }, "Citation marker · hover or focus", { overlay: CITATION_POPOVER }),
  "citation-order": () => workspace({ warnings: [], actions: SENDABLE }, "Order citation marker · hover or focus", { overlay: ORDER_CITATION_POPOVER }),
  "kb-document": () => workspace({ warnings: [], actions: SENDABLE }, "KB document version · side sheet", { overlay: KB_SHEET }),
};

const screen = new URLSearchParams(window.location.search).get("screen") ?? "workspace-staff";
document.body.innerHTML = SCREENS[screen]();

// The token sheet draws sample sizes from data attributes, so the markup above stays free of literals.
document.querySelectorAll("[data-hex]").forEach((el) => { el.style.background = el.dataset.hex; });
document.querySelectorAll("[data-size]").forEach((el) => { el.style.fontSize = `${el.dataset.size}px`; });
document.querySelectorAll("[data-width]").forEach((el) => { el.style.width = `${el.dataset.width * 3}px`; });
