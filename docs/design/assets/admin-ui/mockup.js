/*
 * Admin UI mockups (design doc: docs/design/admin-ui.md).
 * Review material, not frontend code. Open mockup.html?screen=<name>; render.sh renders every screen.
 */

const ICONS = {
  checkCircle: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
  xCircle: '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
  user: '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
  logOut: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
  copy: '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  layers: '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
};

function icon(name, extraClass = "") {
  return `<svg class="icon ${extraClass}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
}

// ---------- One presentation per status (UI-12) ----------

const ROLE = {
  staff: { tone: "neutral", icon: "user", label: "Staff" },
  manager: { tone: "info", icon: "shield", label: "Manager" },
  admin: { tone: "neutral", icon: "shield", label: "Admin" },
};

const ACCOUNT_STATUS = {
  active: { tone: "success", icon: "checkCircle", label: "Active" },
  deactivated: { tone: "neutral", icon: "xCircle", label: "Deactivated" },
};

const AI_SERVICE_STATUS = {
  available: { tone: "success", icon: "checkCircle", label: "Available" },
  unavailable: { tone: "danger", icon: "xCircle", label: "Unavailable" },
};

function badge(p) {
  return `<span class="badge badge-${p.tone}">${icon(p.icon, "icon-sm")}${p.label}</span>`;
}

// ---------- Sample data (synthetic-dev-only) ----------

const ADMIN = { id: "acc-0001", name: "An Tran" };

const ACCOUNTS = [
  { id: "acc-0001", name: "An Tran", role: "admin", active: true },
  { id: "acc-0002", name: "Hoa Pham", role: "manager", active: true },
  { id: "acc-0003", name: "Mai Nguyen", role: "staff", active: true },
  { id: "acc-0004", name: "Minh Le", role: "staff", active: true },
  { id: "acc-0005", name: "Quang Vo", role: "staff", active: false },
];

const VERSIONS = [
  ["Release", "release-2026-11-01"],
  ["Model artifact", "intent-model 1.0.0"],
  ["KB", "kb 2026-10-30"],
  ["Document-to-intent mapping", "doc-intent-map 3"],
  ["Prompts", "draft-prompt 2"],
  ["Routing configuration", "routing 4"],
  ["Retrieval index", "index 2026-10-30"],
];

// ---------- Building blocks ----------

function adminBar(active) {
  const link = (key, iconName, label) => `<a class="${active === key ? "active" : ""}">${icon(iconName)}${label}</a>`;
  return `<header class="appbar">
    <div class="brand">SupportIQ <span>Admin</span></div>
    <nav>${link("accounts", "users", "Accounts")}${link("versions", "layers", "Versions")}</nav>
    <div class="user">${icon("user")}<span><b>${ADMIN.name}</b> · Admin</span>
      <button class="btn btn-ghost btn-sm">${icon("logOut", "icon-sm")}Sign out</button></div>
  </header>`;
}

function mockLabel(text) {
  return `<div class="mock-label">Mockup · ${text} · Sample data (synthetic-dev-only)</div>`;
}

function page(active, inner, label, overlay = "") {
  return `<div class="app">${adminBar(active)}<div class="page"><main class="admin-main">${inner}</main></div>${overlay}${mockLabel(label)}</div>`;
}

function accountActions(a) {
  if (a.id === ADMIN.id) return `<span class="note">You cannot change your own account</span>`;
  const status = a.active
    ? `<button class="btn btn-sm">Deactivate</button>`
    : `<button class="btn btn-sm">Reactivate</button>`;
  if (a.role === "admin") return `<span class="note">The admin role cannot be changed</span> ${status}`;
  const target = a.role === "staff" ? "manager" : "staff";
  return `<button class="btn btn-sm">Make ${target}</button>${status}`;
}

function accountsTable() {
  const rows = ACCOUNTS
    .map((a) => `<tr>
      <td><div class="strong">${a.name}${a.id === ADMIN.id ? ' <span class="muted">(you)</span>' : ""}</div></td>
      <td>${badge(ROLE[a.role])}</td>
      <td>${badge(ACCOUNT_STATUS[a.active ? "active" : "deactivated"])}</td>
      <td class="actions">${accountActions(a)}</td>
    </tr>`)
    .join("");
  return `<section class="panel"><table class="accounts">
    <thead><tr><th scope="col">Account</th><th scope="col">Role</th><th scope="col">Status</th><th scope="col"><span class="muted">Actions</span></th></tr></thead>
    <tbody>${rows}</tbody>
  </table></section>`;
}

function accountsPage(banner = "") {
  return `<h1 class="page-title">Accounts<span class="trail muted">Internal accounts only. Customer accounts are never listed.</span></h1>${banner}${accountsTable()}`;
}

function dialog(title, body, confirm) {
  return `<div class="scrim"><div class="dialog" role="dialog" aria-modal="true" aria-label="${title}">
    <h2>${title}</h2>
    <p>${body}</p>
    <div class="dialog-actions"><button class="btn">Cancel</button>${confirm}</div>
  </div></div>`;
}

function versionsPage(available) {
  const rows = VERSIONS
    .map(([k, v]) => `<dt>${k}</dt><dd>${available ? `<span class="mono">${v}</span>` : '<span class="muted">Unknown</span>'}</dd>`)
    .join("");
  const banner = available
    ? ""
    : `<div class="banner banner-danger">${icon("xCircle")}<div><b>ai-service cannot be reached.</b> Its versions are unknown. Reload this page later.</div></div>`;
  return `<h1 class="page-title">Versions in use<span class="trail muted">Read-only. Versions change only through the release process.</span></h1>
    ${banner}
    <section class="panel">
      <div class="panel-head">ai-service<span class="trail">${badge(AI_SERVICE_STATUS[available ? "available" : "unavailable"])}</span></div>
      <dl class="versions">${rows}</dl>
    </section>
    <section class="panel">
      <div class="panel-head">backend</div>
      <dl class="versions"><dt>Build</dt><dd><span class="mono">backend 0.1.0</span></dd></dl>
    </section>`;
}

// ---------- Screens ----------

const SCREENS = {
  "admin-accounts": () => page("accounts", accountsPage(), "Accounts"),
  "admin-confirm-role": () => page("accounts", accountsPage(), "Confirm a role change",
    dialog("Make Mai Nguyen a manager?", "Mai Nguyen will be able to send replies on tickets that require authority and to view reports. Mai Nguyen will be signed out of every session.",
      `<button class="btn btn-primary">Make manager</button>`)),
  "admin-confirm-deactivate": () => page("accounts", accountsPage(), "Confirm a deactivation",
    dialog("Deactivate Minh Le?", "Minh Le will be signed out of every session and cannot sign in until an admin reactivates the account.",
      `<button class="btn btn-danger">Deactivate</button>`)),
  "admin-last-manager": () => page("accounts",
    accountsPage(`<div class="banner banner-danger">${icon("alert")}<div><b>Hoa Pham was not deactivated.</b> This change would leave no active manager. Make another account a manager first.<div class="row small muted">Details: trace 7c41d2a9 ${icon("copy", "icon-sm")}</div></div></div>`),
    "A change refused: the last active manager"),
  "admin-versions": () => page("versions", versionsPage(true), "Versions in use"),
  "admin-versions-unavailable": () => page("versions", versionsPage(false), "Versions in use, ai-service unavailable"),
};

const screen = new URLSearchParams(window.location.search).get("screen") ?? "admin-accounts";
document.body.innerHTML = (SCREENS[screen] ?? SCREENS["admin-accounts"])();
