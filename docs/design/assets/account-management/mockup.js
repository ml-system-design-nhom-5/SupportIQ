/*
 * Account management mockups (design doc: docs/design/account-management.md).
 * Review material, not frontend code. Open mockup.html?screen=<name>; render.sh renders every screen.
 * Tokens and primitives come from ../console-ui/mockup.css. The admin dialogs are in ../admin-ui/.
 */

const ICONS = {
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  user: '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
  logOut: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  eye: '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
  key: '<path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"/><circle cx="16.5" cy="7.5" r=".5" fill="currentColor"/>',
};

function icon(name, extraClass = "") {
  return `<svg class="icon ${extraClass}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
}

// ---------- Sample data (synthetic-dev-only) ----------

const STAFF = { name: "Mai Nguyen", role: "Staff" };

// ---------- Building blocks ----------

function mockLabel(text) {
  return `<div class="mock-label">Mockup · ${text} · Sample data (synthetic-dev-only)</div>`;
}

function consoleBar(isMenuOpen) {
  return `<header class="appbar">
    <div class="brand">SupportIQ <span>Console</span></div>
    <nav><a class="active">${icon("inbox")}Tickets</a></nav>
    <div class="user"><span class="account-trigger${isMenuOpen ? " open" : ""}">${icon("user")}<span><b>${STAFF.name}</b> · ${STAFF.role}</span>${icon("chevronDown", "icon-sm")}</span></div>
  </header>`;
}

// The account menu, as Radix DropdownMenu shows it open with the focus on its first item.
function accountMenu() {
  return `<div class="account-menu" role="menu">
    <div class="menu-heading"><b>${STAFF.name}</b><span class="muted">${STAFF.role}</span></div>
    <hr>
    <div class="menu-entry focused" role="menuitem">${icon("key")}Change password</div>
    <div class="menu-entry" role="menuitem">${icon("logOut")}Sign out</div>
  </div>`;
}

function passwordField(label, { error, dots = "•••••••••••••" } = {}) {
  const help = error === undefined ? "" : `<span class="field-error">${icon("alert", "icon-sm")}${error}</span>`;
  return `<label class="field"><span class="small strong">${label}</span>
    <span class="input${error === undefined ? "" : " input-invalid"}"><span>${dots}</span><span class="toggle" title="Show password">${icon("eye")}</span></span>
    ${help}</label>`;
}

function changePasswordPage({ currentError } = {}) {
  return `<div class="app"><div class="page"><div class="center">
    <section class="panel form-panel">
      <div class="brand">SupportIQ</div>
      <h1>Change password</h1>
      ${passwordField("Current password", { error: currentError, dots: currentError === undefined ? "•••••••••••••" : "" })}
      ${passwordField("New password", { dots: "••••••••••••••••" })}
      ${passwordField("Confirm new password", { dots: "••••••••••••••••" })}
      <div class="field"><span class="checkbox"><i class="on">${icon("check")}</i>Sign out of my other sessions</span>
        <span class="field-hint">This browser stays signed in.</span></div>
      <div class="form-actions"><button class="btn">Cancel</button><button class="btn btn-primary">Change password</button></div>
    </section>
  </div></div>`;
}

// ---------- Screens ----------

const SCREENS = {
  "account-menu": () => `<div class="app">${consoleBar(true)}<div class="page"><div class="center"><div class="empty-state">${icon("inbox")}<b>Select a ticket</b><span class="muted">Tickets wait in the inbox, oldest first.</span></div></div></div>${accountMenu()}${mockLabel("Account menu open, every area")}</div>`,
  "change-password": () => `${changePasswordPage()}${mockLabel("/change-password, opened from the account menu")}</div>`,
  "change-password-error": () => `${changePasswordPage({ currentError: "The current password is not correct." })}${mockLabel("/change-password after 422 current_password_incorrect")}</div>`,
};

const screen = new URLSearchParams(window.location.search).get("screen") ?? "change-password";
document.body.innerHTML = (SCREENS[screen] ?? SCREENS["change-password"])();
