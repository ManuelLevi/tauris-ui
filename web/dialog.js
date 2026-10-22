// tauris-ui dialogs: a question, a form in the Swing layout, a review of the
// changes before they are saved, and two ready sheets (Keyboard Shortcuts,
// About); also titled border panels for a page. Plain JavaScript: no build
// step, no dependencies. In a Tauri app the plugin injects this file with its
// stylesheet (web/dialog.css), which is added the first time a page uses it.
//
//   if (await TaurisDialog.confirm({ title: "Delete “Atlas”?", message: "Its files go too.", ok: "Delete", danger: true })) ...
//   const values = await TaurisDialog.form({
//     title: "New Project", ok: "Create",
//     fields: [{ name: "name", label: "Name", placeholder: "Northwind Launch", required: true }, ...],
//     submit: async values => { await save(values); },      // a throw shows its message, and keeps the dialog open
//   });                                                       // the values, or null when cancelled
//
// A dialog sits over the page (below the tab strip), the rest of the page out
// of reach until it closes, and the focus goes back where it was. Esc and ⌘.
// are Cancel; Enter is the default button; Tab goes round inside it. A
// question starts on Cancel, so Enter never deletes by accident; a form
// starts in its first field, its text selected. `native: true` on a question
// asks with the system's alert instead (in a Tauri app with the plugin's
// "files" feature and the dialog plugin; elsewhere, in the page).
//
// `window: true` on a form, a review or a sheet opens it in a native window of
// its own, attached to this one. That window loads the app's page too: the
// page starts with `if (TaurisDialog.inWindow)` and there only defines its own
// field types (`TaurisDialog.defineField`); the dialog draws itself. The app's
// checks and its save (validate, review, submit) run here, in the window that
// asked; values cross as JSON.

(() => {
  "use strict";
  if (window.TaurisDialog) return;

  // Filled in by the plugin; left as is when the file is loaded on its own.
  const CSS = "__TAURIS_DIALOG_CSS__";
  let stylesAdded = false;
  function addStyles() {
    if (stylesAdded || CSS.startsWith("__TAURIS")) return;
    stylesAdded = true;
    // A constructed sheet is not blocked by a page's style-src policy.
    try {
      const sheet = new CSSStyleSheet();
      sheet.replaceSync(CSS);
      document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
    } catch {
      const style = document.createElement("style");
      style.textContent = CSS;
      document.head.append(style);
    }
  }

  const MAC = /mac|iphone|ipad/i.test(navigator.userAgentData?.platform || navigator.platform || navigator.userAgent || "");
  const cmd = e => (MAC ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey);

  const LABELS = {
    ok: "OK",
    cancel: "Cancel",
    close: "Close",
    save: "Save",
    back: "Back",
    done: "Done",
    review: "Save Changes",
    required: label => `${label} is needed.`,
    changed: "changed",
    either: "or",
    shortcuts: "Keyboard Shortcuts",
    show: "Show",
    hide: "Hide",
    generate: "Generate",
    before: "before",
    after: "after",
    failed: "Could not do it",
  };

  let uid = 0;
  function el(tag, className, attrs = {}, ...children) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    for (const [key, value] of Object.entries(attrs)) if (value != null && value !== false) node.setAttribute(key, value === true ? "" : value);
    node.append(...children.flat().filter(c => c != null && c !== false));
    return node;
  }
  const say = (label, ...values) => String(typeof label === "function" ? label(...values) : label);
  const words = given => ({ ...LABELS, ...(given || {}) });
  // Markup starting with "<" (an svg), or text.
  function markup(node, value) {
    if (typeof value === "string" && value.trimStart().startsWith("<")) node.innerHTML = value;
    else if (value != null) node.textContent = String(value);
    return node;
  }
  // A refusal as the form shows it: text, or { field, text }.
  const refusalOf = e => (e && typeof e === "object" && "field" in e ? { field: e.field, text: String(e.text ?? e.message ?? "") } : String(e?.message ?? e));

  const X_SVG = '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M2 2l6 6M8 2l-6 6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';
  const EYE_SVG = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8z" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="2" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>';

  // ---------- windows of their own ----------

  const tauri = () => window.__TAURI__?.core;
  const plugin = (name, args) => tauri().invoke(`plugin:tauris-ui|${name}`, args);
  /** This page is a dialog's window (opened with window: true). */
  const IN_WINDOW = location.hash === "#tauris-dialog";
  const WINDOW_EVENT = "tauris-ui:dialog-window";
  // What the dialog windows say, by window (here, in the window that asked); in a dialog window, what its asker says.
  const heard = new Map();
  const before = window.__taurisUiDeliver;
  Object.defineProperty(window, "__taurisUiDeliver", {
    configurable: true,
    value: (name, payload) => {
      if (name !== WINDOW_EVENT) return typeof before === "function" ? before(name, payload) : undefined;
      heard.get(String(payload?.label))?.(payload?.message ?? {});
      return undefined;
    },
  });

  // The app's own field types, by name: in a dialog's window too, where the app's page defines them again.
  const types = new Map();
  function defineField(type, render) {
    if (typeof type !== "string" || !type || typeof render !== "function") throw new Error("TaurisDialog.defineField needs a type name and a render function");
    types.set(type, render);
  }

  // A form, a review or a sheet in a window of its own: the window's label, or null (then it shows in the page).
  async function openWindow(kind, options, title, width) {
    if (!tauri() || IN_WINDOW) return null;
    // Data only: the functions stay here, and are asked through messages.
    const spec = {
      kind,
      options: JSON.parse(JSON.stringify({ ...options, window: undefined })),
      has: { validate: typeof options.validate === "function", review: typeof options.review === "function", submit: typeof options.submit === "function" },
    };
    try {
      const label = await plugin("dialog_window_open", { spec: JSON.stringify(spec), title: String(title ?? ""), width: Number(width) || 440 });
      return typeof label === "string" ? label : null;
    } catch (e) {
      console.warn("[tauris-ui dialog] no window of its own, so in the page:", e);
      return null;
    }
  }

  // Here, while a dialog's window is open: the page is out of reach, and a click brings the dialog forward.
  // The dialog windows waited for, the last on top: a question asked meanwhile (a confirm in
  // a submit) shows in the top one.
  const windowWaits = [];
  const questions = new Map(); // id -> resolve, for questions shown in a dialog's window
  let questionIds = 0;

  function waitForWindow(label, onMessage) {
    const back = rememberFocus();
    const shield = el("div", "tdl-shield");
    const quieted = [...document.body.children].filter(n => !n.inert && !n.matches("script, style"));
    for (const n of quieted) n.inert = true;
    document.body.append(shield);
    shield.addEventListener("mousedown", e => {
      e.preventDefault();
      plugin("dialog_window_reply", { label, message: { type: "focus" } }).catch(() => {});
    });
    open.push(shield);
    windowWaits.push(label);
    return new Promise(resolve => {
      let done = false;
      const finish = value => {
        if (done) return;
        done = true;
        heard.delete(label);
        windowWaits.splice(windowWaits.indexOf(label), 1);
        shield.remove();
        for (const n of quieted) n.inert = false;
        open.splice(open.indexOf(shield), 1);
        // After the window is key again.
        requestAnimationFrame(back);
        resolve(value);
      };
      const reply = (id, answer) => plugin("dialog_window_reply", { label, message: { type: "answer", id, ...answer } }).catch(() => {});
      // TaurisDialog.close(): the window closes, the dialog ends as cancelled.
      shield.abort = () => {
        plugin("dialog_window_reply", { label, message: { type: "close" } }).catch(() => {});
        finish(null);
      };
      heard.set(label, async msg => {
        if (msg.type === "closed") return finish(null);
        if (msg.type === "done") return finish(msg.value ?? null);
        if (msg.type === "answered") {
          questions.get(msg.id)?.(msg.yes === true);
          questions.delete(msg.id);
          return undefined;
        }
        if (msg.type === "ask") {
          try {
            reply(msg.id, { result: (await onMessage(msg.what, msg.value)) ?? null });
          } catch (e) {
            reply(msg.id, { error: refusalOf(e) });
          }
        }
        return undefined;
      });
    });
  }

  // In a dialog's window: asks the window that asked, and waits for its answer.
  let asked = 0;
  const answers = new Map();
  function ask(what, value) {
    const id = ++asked;
    return new Promise((resolve, reject) => {
      answers.set(id, { resolve, reject });
      plugin("dialog_window_send", { message: { type: "ask", id, what, value } }).catch(reject);
    });
  }
  function tellDone(value) {
    return plugin("dialog_window_send", { message: { type: "done", value: value ?? null } }).catch(() => {}).then(() => plugin("dialog_window_close").catch(() => {}));
  }

  // Where the keyboard was, to give it back when a dialog closes: the element,
  // or (a row's own small button that has gone) the nearest list it was in.
  function rememberFocus() {
    const at = document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : null;
    if (!at) return () => {};
    const up = [];
    for (let n = at.parentElement; n && n !== document.body; n = n.parentElement) if (n.hasAttribute("tabindex")) up.push(n);
    return () => {
      const to = at.isConnected && !at.closest("[inert]") ? at : up.find(n => n.isConnected);
      if (to && document.activeElement !== to) to.focus({ preventScroll: true });
    };
  }

  // ---------- the frame every dialog shares ----------

  const open = []; // the dialogs open, the last on top

  // A dialog: its title bar, its body, its button row. `onCancel` is Esc, ⌘., ✕
  // and a press on the veil; the caller closes it with the returned close().
  function frame({ title, role = "dialog", wide = false, width, onCancel, className = "" }) {
    addStyles();
    const id = `tdl-${++uid}`;
    const back = rememberFocus();
    const heading = el("h2", "tdl-title", { id: `${id}-t` }, String(title ?? ""));
    const x = el("div", "tdl-x", { role: "button", tabindex: "-1", "aria-label": LABELS.close });
    x.innerHTML = X_SVG;
    const head = el("div", "tdl-head", {}, heading, x);
    const body = el("div", "tdl-body");
    const buttons = el("div", "tdl-buttons");
    const box = el("div", `tdl${wide ? " tdl-wide" : ""}${className ? " " + className : ""}`, { role, "aria-modal": "true", "aria-labelledby": heading.id, tabindex: "-1" },
      head, body, buttons);
    if (width) box.style.setProperty("--tdl-w", `${Number(width)}px`);
    const veil = el("div", `tdl-veil${open.length ? " tdl-over" : ""}`, {}, box);
    const sizesWindow = IN_WINDOW && !open.length;
    // The rest of the page (and a dialog under this one) is out of reach, for a screen reader too.
    const quieted = [...document.body.children].filter(n => n !== veil && !n.inert && !n.matches("script, style, .tmn-menu"));
    for (const n of quieted) n.inert = true;
    document.body.append(veil);
    const life = new AbortController();
    const signal = life.signal;
    const state = { veil, box, body, buttons, heading, life, closed: false };
    open.push(state);
    const cancel = () => { if (!state.closed) onCancel?.(); };
    x.addEventListener("click", cancel, { signal });
    veil.addEventListener("mousedown", e => { if (e.target === veil) { e.preventDefault(); cancel(); } }, { signal });
    box.addEventListener("keydown", e => {
      if (e.key === "Escape" || (cmd(e) && e.key === ".")) {
        if (e.isComposing) return;
        e.preventDefault();
        e.stopPropagation();
        cancel();
      } else if (e.key === "Tab") {
        // Round and round inside it.
        const stops = [...box.querySelectorAll("input, select, textarea, [tabindex='0'], a[href]")]
          .filter(n => !n.disabled && n.getClientRects().length && !n.closest("[hidden]"));
        if (!stops.length) return e.preventDefault();
        const at = stops.indexOf(document.activeElement);
        if (e.shiftKey && (at <= 0)) { e.preventDefault(); stops[stops.length - 1].focus(); }
        else if (!e.shiftKey && at === stops.length - 1) { e.preventDefault(); stops[0].focus(); }
      }
    }, { signal });
    // In its own window: the window is its size (and follows it as a refusal or a review shows).
    if (sizesWindow) {
      let queued = false;
      const fit = () => {
        queued = false;
        if (state.closed) return;
        const r = box.getBoundingClientRect();
        plugin("dialog_window_ready", { width: Math.ceil(r.width), height: Math.ceil(r.height), pageW: window.innerWidth, pageH: window.innerHeight })
          .catch(e => console.error("[tauris-ui dialog] cannot size its window:", e));
      };
      const seen = new ResizeObserver(() => {
        if (queued) return;
        queued = true;
        requestAnimationFrame(fit);
      });
      seen.observe(box);
      signal.addEventListener("abort", () => seen.disconnect());
    }
    state.close = () => {
      if (state.closed) return;
      state.closed = true;
      life.abort();
      veil.remove();
      for (const n of quieted) n.inert = false;
      open.splice(open.indexOf(state), 1);
      back();
    };
    return state;
  }

  // A button of a dialog's row (not a <button>: an app's `button { ... }` rule leaves it alone).
  function button(label, { primary = false, danger = false, onPress } = {}) {
    const b = el("div", `tdl-btn${primary ? " tdl-primary" : ""}${danger ? " tdl-danger" : ""}`, { role: "button", tabindex: "0" }, String(label));
    const press = () => { if (b.getAttribute("aria-disabled") !== "true") onPress?.(); };
    b.addEventListener("click", press);
    b.addEventListener("keydown", e => {
      if ((e.key === "Enter" || e.key === " ") && !e.repeat) {
        e.preventDefault();
        e.stopPropagation();
        press();
      }
    });
    return b;
  }

  // ---------- a question ----------

  async function confirm(options = {}) {
    // Asked while a dialog's own window is open (its submit asking "Future date?"): asked there.
    const label = windowWaits[windowWaits.length - 1];
    if (label && !IN_WINDOW) {
      const id = ++questionIds;
      const yes = await new Promise(resolve => {
        questions.set(id, resolve);
        const { run, ...data } = options;
        plugin("dialog_window_reply", { label, message: { type: "confirm", id, options: JSON.parse(JSON.stringify(data)) } })
          .catch(() => { questions.delete(id); resolve(null); });
      });
      if (yes === null) return confirmHere(options);
      if (!yes || typeof options.run !== "function") return yes;
      await options.run();
      return true;
    }
    return confirmHere(options);
  }

  async function confirmHere(options = {}) {
    const w = words(options.labels);
    const ok = String(options.ok ?? w.ok);
    const cancel = String(options.cancel ?? w.cancel);
    const run = typeof options.run === "function" ? options.run : null;
    if (options.native && tauri()) {
      let yes = null;
      try {
        yes = await plugin("ask", { title: String(options.title ?? ""), message: String(options.message ?? ""), ok, cancel, warning: options.danger === true });
      } catch {
        // no system alert here (the files feature or the dialog plugin is missing): asked in the page
      }
      if (typeof yes === "boolean") {
        if (!yes || !run) return yes;
        try {
          await run();
          return true;
        } catch (e) {
          // The alert is gone: why it could not be done is a notice of its own.
          const text = refusalOf(e);
          await plugin("ask", { title: String(options.failedTitle ?? w.failed), message: typeof text === "string" ? text : text.text, ok: String(w.ok), cancel: "", warning: true }).catch(() => {});
          return false;
        }
      }
    }
    return new Promise(resolve => {
      let state = null;
      let busy = false;
      const end = yes => { state.close(); resolve(yes); };
      state = frame({ title: options.title, role: "alertdialog", width: options.width, onCancel: () => { if (!busy) end(false); }, className: "tdl-question" });
      state.abort = () => end(false);
      const text = el("div", "tdl-message", { id: `${state.heading.id}-m` });
      for (const para of String(options.message ?? "").split(/\n{2,}/)) if (para.trim()) text.append(el("p", "", {}, para.trim()));
      state.box.setAttribute("aria-describedby", text.id);
      // Why the action could not be done: the dialog stays, the reason on its kept line.
      const refusal = el("div", "tdl-line tdl-question-line", {}, el("span", "tdl-line-error", { role: "alert" }));
      state.body.append(text);
      if (run) state.body.append(refusal);
      const no = button(cancel, { onPress: () => { if (!busy) end(false); } });
      const yes = button(ok, {
        primary: !options.danger,
        danger: options.danger === true,
        onPress: async () => {
          if (busy) return;
          if (!run) return end(true);
          busy = true;
          state.box.classList.add("tdl-busy");
          for (const b of [yes, no]) b.setAttribute("aria-disabled", "true");
          try {
            await run();
          } catch (e) {
            busy = false;
            state.box.classList.remove("tdl-busy");
            for (const b of [yes, no]) b.setAttribute("aria-disabled", "false");
            const r = refusalOf(e);
            refusal.firstChild.textContent = typeof r === "string" ? r : r.text;
            refusal.classList.add("tdl-refused");
            no.focus({ preventScroll: true });
            return undefined;
          }
          return end(true);
        },
      });
      state.buttons.append(el("span", "tdl-spacer"), no, yes);
      // Starts on Cancel: Enter there is "no", never a delete by accident.
      no.focus({ preventScroll: true });
    });
  }

  // ---------- a form ----------

  const TEXTLIKE = new Set(["text", "password", "number", "email", "url", "tel", "search", "date", "time"]);

  // A password the person never has to think of: letters, digits and a few signs, from the system's randomness.
  function newPassword(length) {
    const set = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789-_.!@#%+=";
    const n = Math.max(8, Math.min(128, Number(length) || 20));
    const bytes = new Uint32Array(n);
    crypto.getRandomValues(bytes);
    return [...bytes].map(b => set[b % set.length]).join("");
  }

  function fieldControl(f, id, w) {
    const type = String(f.type ?? "text");
    let control;
    let handle = null;
    let wrap = null;
    // A field's own render, or a type the app defined (never in place of one of the form's own).
    const own = TEXTLIKE.has(type) || type === "textarea" || type === "select" || type === "checkbox";
    const custom = typeof f.render === "function" ? f.render : own ? null : types.get(type);
    if (custom) {
      // The app's own widget, in the form's layout: it gives its value (and takes the focus) when asked.
      control = el("div", "tdl-custom", { id, role: "group", "aria-label": String(f.label ?? f.name) });
      try {
        handle = custom(control, f) ?? null;
      } catch (e) {
        console.error(`[tauris-ui dialog] the "${type}" field failed to draw:`, e);
      }
      return { control, handle, wrap: control };
    }
    if (type === "textarea") {
      control = el("textarea", "tdl-input", { id, rows: String(f.rows ?? 3), placeholder: f.placeholder ?? null });
      control.value = f.value == null ? "" : String(f.value);
    } else if (type === "select") {
      control = el("select", "tdl-input", { id });
      for (const o of Array.isArray(f.options) ? f.options : []) {
        const option = typeof o === "object" && o ? o : { value: o, label: o };
        control.append(el("option", "", { value: String(option.value) }, String(option.label ?? option.value)));
      }
      if (f.value != null) control.value = String(f.value);
    } else if (type === "checkbox") {
      control = el("input", "tdl-check", { id, type: "checkbox" });
      control.checked = f.value === true;
    } else {
      control = el("input", "tdl-input", {
        id, type: TEXTLIKE.has(type) ? type : "text", placeholder: f.placeholder ?? null, autocomplete: f.autocomplete ?? (type === "password" ? "new-password" : "off"),
        spellcheck: type === "text" ? "false" : null, min: f.min ?? null, max: f.max ?? null, step: f.step ?? null,
        inputmode: f.inputmode ?? null,
      });
      control.value = f.value == null ? "" : String(f.value);
    }
    if (f.disabled) control.disabled = true;
    if (f.required) control.setAttribute("aria-required", "true");
    // A password: Show to read it, Generate to make one.
    if (type === "password" && (f.reveal || f.generate)) {
      wrap = el("span", "tdl-pw", {}, control);
      if (f.reveal) {
        const eye = el("div", "tdl-pw-btn", { role: "button", tabindex: "0", "aria-pressed": "false", "aria-label": say(w.show), title: say(w.show) });
        eye.innerHTML = EYE_SVG;
        const toggle = () => {
          const shown = control.type === "password";
          control.type = shown ? "text" : "password";
          eye.setAttribute("aria-pressed", String(shown));
          eye.title = say(shown ? w.hide : w.show);
          eye.setAttribute("aria-label", eye.title);
        };
        eye.addEventListener("click", toggle);
        eye.addEventListener("keydown", e => { if ((e.key === "Enter" || e.key === " ") && !e.repeat) { e.preventDefault(); e.stopPropagation(); toggle(); } });
        wrap.append(eye);
        wrap.__show = () => { if (control.type === "password") toggle(); };
      }
      if (f.generate) {
        const gen = el("div", "tdl-pw-gen", { role: "button", tabindex: "0" }, say(w.generate));
        const make = () => {
          control.value = typeof f.generate === "function" ? String(f.generate() ?? "") : newPassword(f.generate === true ? 20 : f.generate);
          wrap.__show?.();
          control.dispatchEvent(new Event("input", { bubbles: true }));
          control.focus();
          control.select();
        };
        gen.addEventListener("click", make);
        gen.addEventListener("keydown", e => { if ((e.key === "Enter" || e.key === " ") && !e.repeat) { e.preventDefault(); e.stopPropagation(); make(); } });
        wrap.append(gen);
      }
    }
    return { control, handle, wrap: wrap ?? control };
  }

  function valueOf(f, entry) {
    if (entry.handle) return typeof entry.handle.value === "function" ? entry.handle.value() : null;
    const control = entry.control;
    if (f.type === "checkbox") return control.checked;
    if (f.type === "number") return control.value === "" ? null : Number(control.value);
    return control.value;
  }
  const isEmpty = v => v == null || v === false || (typeof v === "string" && !v.trim()) || (Array.isArray(v) && !v.length);

  // The review: "Field: old → new", old struck through; without `before`, only that it changed;
  // a picture's change as its two pictures.
  function reviewRows(rows, w) {
    const table = el("table", "tdl-review-rows");
    const tbody = el("tbody");
    for (const c of rows) {
      const row = el("tr", "", { "data-field": String(c.field) });
      row.append(el("th", "", { scope: "row" }, `${c.field}:`));
      const cell = el("td");
      const picture = (src, which) => (src ? el("img", "tdl-thumb", { src: String(src), alt: `${c.field}, ${say(which)}` }) : el("span", "tdl-thumb tdl-thumb-none", {}, "—"));
      if (c.beforeImage !== undefined || c.afterImage !== undefined) {
        cell.append(picture(c.beforeImage, w.before), el("span", "tdl-arrow", { "aria-hidden": "true" }, " → "), picture(c.afterImage, w.after));
      } else if (c.before === undefined) {
        cell.append(el("span", "tdl-now", {}, c.after == null ? say(w.changed) : String(c.after)));
      } else {
        cell.append(el("span", "tdl-was", {}, String(c.before === "" ? "—" : c.before)), el("span", "tdl-arrow", { "aria-hidden": "true" }, " → "),
          el("span", "tdl-now", {}, String(c.after === "" ? "—" : c.after)));
      }
      row.append(cell);
      tbody.append(row);
    }
    table.append(tbody);
    return table;
  }

  async function form(options = {}) {
    // In a window of its own: only fields the window can draw (a one-off render stays in the page).
    const inline = (Array.isArray(options.fields) ? options.fields : []).some(f => f && typeof f.render === "function");
    if (options.window && !inline) {
      const width = options.width ?? (options.wide ? 560 : 440);
      const label = await openWindow("form", options, options.title, width);
      if (label) {
        return waitForWindow(label, async (what, value) => {
          if (what === "validate") return typeof options.validate === "function" ? (await options.validate(value)) ?? null : null;
          if (what === "review") return typeof options.review === "function" ? (await options.review(value)) ?? null : null;
          if (what === "submit" && typeof options.submit === "function") await options.submit(value);
          return null;
        });
      }
    }
    return formHere(options);
  }

  function formHere(options = {}) {
    const w = words(options.labels);
    const fields = (Array.isArray(options.fields) ? options.fields : []).filter(f => f && f.name != null);
    return new Promise(resolve => {
      let state = null;
      let busy = false;
      let reviewing = null; // the values waiting for "Save Changes"
      const handles = [];
      const end = values => {
        for (const h of handles) {
          try {
            h.destroy?.();
          } catch (e) {
            console.error("[tauris-ui dialog] a field's destroy() failed:", e);
          }
        }
        state.close();
        resolve(values);
      };
      const cancel = () => {
        if (busy) return;
        // During a review, Esc goes back to the fields.
        if (reviewing) return showFields();
        end(null);
      };
      state = frame({ title: options.title, wide: options.wide === true, width: options.width, onCancel: cancel, className: "tdl-form" });
      state.abort = () => end(null);
      const grid = el("div", "tdl-fields");
      const controls = new Map();
      // Several inputs on one line ({ type: "row", label, fields }): one label, the inputs side by side.
      const rowOf = f => {
        const cell = el("div", "tdl-cell");
        const line = el("div", "tdl-inline");
        for (const sub of (Array.isArray(f.fields) ? f.fields : []).filter(x => x && x.name != null)) {
          const id = `${state.heading.id}-${String(sub.name).replace(/[^\w-]/g, "_")}`;
          const entry = fieldControl(sub, id, w);
          if (entry.handle) handles.push(entry.handle);
          controls.set(String(sub.name), { f: sub, ...entry });
          if (sub.label) line.append(el("label", "tdl-sub-label", { for: entry.handle ? null : id }, String(sub.label)));
          line.append(sub.type === "checkbox" ? el("label", "tdl-check-label", {}, entry.control) : entry.wrap);
        }
        cell.append(line, el("div", "tdl-tip", { role: "alert", hidden: true }));
        if (f.hint) cell.append(el("div", "tdl-hint", {}, String(f.hint)));
        grid.append(el("span", "tdl-label", {}, f.label ? `${f.label}:` : ""), cell);
      };
      for (const f of fields) {
        if (f.type === "row") {
          rowOf(f);
          continue;
        }
        const id = `${state.heading.id}-${String(f.name).replace(/[^\w-]/g, "_")}`;
        const entry = fieldControl(f, id, w);
        if (entry.handle) handles.push(entry.handle);
        controls.set(String(f.name), { f, ...entry });
        const label = el("label", `tdl-label${f.type === "textarea" || entry.handle ? " tdl-top" : ""}`, { for: entry.handle ? null : id }, f.type === "checkbox" ? "" : `${f.label ?? f.name}:`);
        const cell = el("div", "tdl-cell");
        if (f.type === "checkbox") cell.append(el("label", "tdl-check-label", {}, entry.control, el("span", "", {}, String(f.label ?? f.name))));
        else cell.append(entry.wrap);
        // A field's own refusal: a balloon under it.
        const tip = el("div", "tdl-tip", { id: `${id}-tip`, role: "alert", hidden: true });
        cell.append(tip);
        if (f.hint) {
          const hint = el("div", "tdl-hint", { id: `${id}-hint` }, String(f.hint));
          cell.append(hint);
          entry.control.setAttribute("aria-describedby", hint.id);
        }
        grid.append(label, cell);
      }
      // One kept line for refusals: the dialog never changes height; the hint gives way to a refusal.
      const hint = el("span", "tdl-line-hint", {}, options.hint ? String(options.hint) : "");
      const refusal = el("span", "tdl-line-error", { role: "alert" });
      const line = el("div", "tdl-line", {}, hint, refusal);
      const page = el("div", "tdl-page", {}, grid, line);
      const review = el("div", "tdl-review", { role: "group", hidden: true });
      state.body.append(page, review);

      const left = el("span", "tdl-left");
      const no = button(String(options.cancel ?? w.cancel), { onPress: cancel });
      const yes = button(String(options.ok ?? w.ok), { primary: true, danger: options.danger === true, onPress: () => go() });
      state.buttons.append(left, el("span", "tdl-spacer"), no, yes);

      const values = () => Object.fromEntries([...controls].map(([name, entry]) => [name, valueOf(entry.f, entry)]));
      const focusEntry = entry => {
        if (entry.handle) {
          if (typeof entry.handle.focus === "function") entry.handle.focus();
          else entry.control.querySelector("input, select, textarea, [tabindex='0'], button")?.focus();
          return;
        }
        entry.control.focus();
        entry.control.select?.();
      };
      function clear() {
        refusal.textContent = "";
        line.classList.remove("tdl-refused");
        for (const { control } of controls.values()) {
          control.removeAttribute("aria-invalid");
          const tip = control.closest(".tdl-cell").querySelector(".tdl-tip");
          tip.hidden = true;
          tip.textContent = "";
        }
      }
      // A refusal: about a field (a balloon under it, the field marked and given the keys), or the whole form (the line).
      function refuse(r) {
        clear();
        const text = typeof r === "string" ? r : String(r?.text ?? r?.message ?? r ?? "");
        const name = typeof r === "object" && r ? r.field : null;
        const at = name != null ? controls.get(String(name)) : null;
        if (at) {
          const tip = at.control.closest(".tdl-cell").querySelector(".tdl-tip");
          tip.textContent = text;
          tip.hidden = false;
          at.control.setAttribute("aria-invalid", "true");
          // A part of the app's own field (an objective's date): it shows where, and takes the keys there.
          const part = typeof r === "object" && r ? r.part : null;
          if (part != null && at.handle) {
            at.handle.refuse?.(part, text);
            if (typeof at.handle.focus === "function") at.handle.focus(part);
          } else {
            focusEntry(at);
          }
        } else {
          refusal.textContent = text;
          line.classList.add("tdl-refused");
        }
      }
      function setBusy(on) {
        busy = on;
        state.box.classList.toggle("tdl-busy", on);
        for (const b of [yes, no]) b.setAttribute("aria-disabled", String(on));
      }
      function showFields() {
        reviewing = null;
        review.hidden = true;
        page.hidden = false;
        state.heading.textContent = String(options.title ?? "");
        yes.textContent = String(options.ok ?? w.ok);
        no.textContent = String(options.cancel ?? w.cancel);
        focusFirst();
      }
      function showReview(rows, v) {
        reviewing = v;
        review.replaceChildren(el("p", "tdl-review-title", {}, String(options.reviewTitle ?? w.review)), reviewRows(rows, w),
          options.reviewNote ? el("p", "tdl-review-note", {}, String(options.reviewNote)) : null);
        // The fields' height is kept for a short review: the dialog does not jump.
        review.style.minHeight = `${Math.min(page.offsetHeight, 240)}px`;
        page.hidden = true;
        review.hidden = false;
        yes.textContent = String(options.saveLabel ?? w.save);
        no.textContent = String(w.back);
        yes.focus({ preventScroll: true });
      }
      async function go() {
        if (busy) return;
        const v = reviewing ?? values();
        if (!reviewing) {
          // Needed fields first, then the app's own checks (which may take a moment: the app is asked).
          for (const [name, entry] of controls) {
            const { f } = entry;
            if (f.required && !f.disabled && isEmpty(valueOf(f, entry))) {
              return refuse({ field: name, text: say(f.requiredText ?? w.required, String(f.label ?? name)) });
            }
          }
          setBusy(true);
          let refused = null;
          let rows = null;
          try {
            refused = typeof options.validate === "function" ? await options.validate(v) : null;
            if (!refused) rows = typeof options.review === "function" ? await options.review(v) : null;
          } catch (e) {
            refused = refusalOf(e);
          }
          setBusy(false);
          if (refused) return refuse(refused);
          if (Array.isArray(rows) && rows.length) return showReview(rows, v);
        }
        if (typeof options.submit === "function") {
          setBusy(true);
          try {
            await options.submit(v);
          } catch (e) {
            setBusy(false);
            if (reviewing) showFields();
            return refuse(refusalOf(e));
          }
          setBusy(false);
        }
        end(v);
      }
      function focusFirst() {
        // The first text field, its text selected, ready to retype; else the default button.
        const first = [...controls.values()].find(c => !c.control.disabled && c.f.type !== "checkbox");
        if (first) {
          focusEntry(first);
        } else {
          yes.focus({ preventScroll: true });
        }
      }
      // Enter in a field is the default button (⌘↩ in a text area); typing clears a refusal.
      state.box.addEventListener("keydown", e => {
        if (e.key !== "Enter" || e.isComposing || e.repeat) return;
        const t = e.target;
        const area = t instanceof HTMLTextAreaElement;
        if (t instanceof HTMLElement && (t.classList.contains("tdl-btn") || t.closest(".tdl-pw-btn, .tdl-pw-gen"))) return;
        // The app's own widget keeps its Enter (a picker choosing), unless ⌘↩.
        if (t instanceof HTMLElement && t.closest(".tdl-custom") && !cmd(e)) return;
        if (area && !cmd(e)) return;
        if (t instanceof HTMLSelectElement && !cmd(e)) return;
        e.preventDefault();
        go();
      }, { signal: state.life.signal });
      state.box.addEventListener("input", () => { if (refusal.textContent || state.box.querySelector(".tdl-tip:not([hidden])")) clear(); }, { signal: state.life.signal });
      if (typeof options.left === "function") {
        try {
          options.left(left);
        } catch (e) {
          console.error("[tauris-ui dialog] left() failed:", e);
        }
      }
      state.form = { refuse, values };
      focusFirst();
      // A form that opens refused (New Task at the limit): the reason at once, its button off.
      if (options.okDisabled) yes.setAttribute("aria-disabled", "true");
      if (options.refusal) refuse(options.refusal);
    });
  }

  // ---------- a review on its own ----------

  async function review(options = {}) {
    if (options.window) {
      const label = await openWindow("review", options, options.title ?? words(options.labels).review, options.width ?? 440);
      if (label) return (await waitForWindow(label, () => null)) === true;
    }
    return reviewHere(options);
  }

  function reviewHere(options = {}) {
    const w = words(options.labels);
    return new Promise(resolve => {
      let state = null;
      const end = yes => { state.close(); resolve(yes); };
      state = frame({ title: options.title ?? w.review, width: options.width, onCancel: () => end(false), className: "tdl-form" });
      state.abort = () => end(false);
      const box = el("div", "tdl-review", { role: "group", "aria-label": String(options.title ?? w.review) },
        options.message ? el("p", "tdl-review-title", {}, String(options.message)) : null,
        reviewRows(Array.isArray(options.rows) ? options.rows : [], w),
        options.note ? el("p", "tdl-review-note", {}, String(options.note)) : null);
      state.body.append(box);
      const no = button(String(options.cancel ?? w.cancel), { onPress: () => end(false) });
      const yes = button(String(options.ok ?? w.save), { primary: true, onPress: () => end(true) });
      state.buttons.append(el("span", "tdl-spacer"), no, yes);
      yes.focus({ preventScroll: true });
    });
  }

  // ---------- the sheets ----------

  // Keys drawn as keycaps: "⌘K" is one key; ["⌘[", "⌘]"] with either: true reads "⌘[ or ⌘]".
  function keycaps(keys, either, w) {
    const out = el("span", "tdl-keys");
    (Array.isArray(keys) ? keys : [keys]).forEach((k, i) => {
      if (i) out.append(el("span", "tdl-or", {}, either ? ` ${w.either} ` : " "));
      out.append(el("kbd", "tdl-key", {}, String(k)));
    });
    return out;
  }

  async function shortcuts(options = {}) {
    if (options.window) {
      const label = await openWindow("shortcuts", options, options.title ?? words(options.labels).shortcuts, options.width ?? 700);
      if (label) return void (await waitForWindow(label, () => null));
    }
    return shortcutsHere(options);
  }

  function shortcutsHere(options = {}) {
    const w = words(options.labels);
    return new Promise(resolve => {
      let state = null;
      const end = () => { state.close(); resolve(); };
      state = frame({ title: options.title ?? w.shortcuts, wide: true, width: options.width ?? 700, onCancel: end, className: "tdl-sheet" });
      state.abort = end;
      const groups = (Array.isArray(options.groups) ? options.groups : []).map(g => {
        const rows = el("dl", "tdl-shortcut-rows");
        for (const item of Array.isArray(g.items) ? g.items : []) rows.append(el("dt", "", {}, String(item.label ?? "")), el("dd", "", {}, keycaps(item.keys, item.either === true, w)));
        return el("section", "tdl-shortcut-group", { "aria-label": String(g.title ?? "") }, el("h3", "", {}, String(g.title ?? "")), rows);
      });
      // In columns of about the same height (a group never breaks across them).
      const columns = Math.max(1, Math.min(Number(options.columns) || 3, groups.length));
      const cols = Array.from({ length: columns }, () => el("div", "tdl-column"));
      const sizes = (Array.isArray(options.groups) ? options.groups : []).map(g => 1 + (Array.isArray(g.items) ? g.items.length : 0));
      const heights = new Array(columns).fill(0);
      groups.forEach((g, i) => {
        const shortest = heights.indexOf(Math.min(...heights));
        cols[shortest].append(g);
        heights[shortest] += sizes[i];
      });
      state.body.append(el("div", "tdl-columns", { style: null }, cols));
      state.body.querySelector(".tdl-columns").style.setProperty("--tdl-columns", String(columns));
      const done = button(String(options.done ?? w.done), { primary: true, onPress: end });
      state.buttons.append(el("span", "tdl-spacer"), done);
      done.focus({ preventScroll: true });
    });
  }

  async function about(options = {}) {
    if (options.window) {
      const label = await openWindow("about", options, options.title ?? `About ${options.name ?? ""}`.trim(), options.width ?? 420);
      if (label) return void (await waitForWindow(label, () => null));
    }
    return aboutHere(options);
  }

  function aboutHere(options = {}) {
    const w = words(options.labels);
    return new Promise(resolve => {
      let state = null;
      const end = () => { state.close(); resolve(); };
      state = frame({ title: options.title ?? `About ${options.name ?? ""}`.trim(), width: options.width ?? 420, onCancel: end, className: "tdl-about" });
      state.abort = end;
      const mark = el("div", "tdl-mark", { "aria-hidden": "true" });
      if (typeof options.mark === "string" && /^(data:|https?:|\/|\.)/.test(options.mark)) mark.append(el("img", "", { src: options.mark, alt: "" }));
      else markup(mark, options.mark);
      // The values can be selected and copied (a version, a server's address).
      const rows = el("dl", "tdl-about-rows");
      for (const [k, v] of Array.isArray(options.rows) ? options.rows : []) rows.append(el("dt", "", {}, String(k)), el("dd", "tauris-selectable", {}, String(v ?? "")));
      state.body.append(el("div", "tdl-about-head", {}, mark, el("div", "", {}, el("p", "tdl-about-name", {}, String(options.name ?? "")),
        options.description ? el("p", "tdl-about-text tauris-selectable", {}, String(options.description)) : null)), rows);
      const done = button(String(options.done ?? w.done), { primary: true, onPress: end });
      state.buttons.append(el("span", "tdl-spacer"), done);
      done.focus({ preventScroll: true });
    });
  }

  // ---------- titled border panels ----------

  // A box with its title on its top line (Swing's TitledBorder): the title, a dim
  // count and the panel's buttons share that line. The element's own content stays.
  function panel(element, options = {}) {
    if (!(element instanceof HTMLElement)) throw new Error("TaurisDialog.panel needs the element to frame");
    addStyles();
    element.classList.add("tdl-panel");
    let head = element.querySelector(":scope > .tdl-panel-head");
    if (!head) {
      head = el("div", "tdl-panel-head");
      element.prepend(head);
    }
    const draw = (o = options) => {
      const title = el("span", "tdl-panel-title", { role: "heading", "aria-level": String(o.level ?? 3) }, String(o.title ?? ""));
      const parts = [title];
      if (o.count != null && o.count !== "") parts.push(el("span", "tdl-panel-count", {}, `· ${o.count}`));
      for (const a of Array.isArray(o.actions) ? o.actions : []) {
        if (!a) continue;
        const b = el("div", "tdl-panel-action", { role: "button", tabindex: a.disabled ? "-1" : "0", "aria-disabled": a.disabled ? "true" : null, title: a.title ?? null }, String(a.label ?? ""));
        const press = () => { if (!a.disabled) a.action?.(); };
        b.addEventListener("click", press);
        b.addEventListener("keydown", e => { if ((e.key === "Enter" || e.key === " ") && !e.repeat) { e.preventDefault(); press(); } });
        parts.push(b);
      }
      head.replaceChildren(...parts);
      element.setAttribute("role", element.getAttribute("role") ?? "region");
      element.setAttribute("aria-label", String(o.title ?? ""));
    };
    draw();
    return {
      /** Changes the title, the count or the buttons. */
      update(changes = {}) { options = { ...options, ...changes }; draw(options); },
      /** Takes the frame away (the element's own content stays). */
      destroy() { head.remove(); element.classList.remove("tdl-panel"); },
    };
  }

  // ---------- in a dialog's window: draw what was asked for ----------

  async function serveWindow() {
    document.documentElement.classList.add("tdl-in-window");
    addStyles();
    heard.set("self", async msg => {
      // The window that asked: a question during its save, or close (TaurisDialog.close()).
      if (msg.type === "close") return void plugin("dialog_window_close").catch(() => {});
      if (msg.type === "confirm") {
        const yes = await confirmHere(msg.options ?? {});
        return void plugin("dialog_window_send", { message: { type: "answered", id: msg.id, yes } }).catch(() => {});
      }
      if (msg.type !== "answer") return;
      const waiting = answers.get(msg.id);
      if (!waiting) return;
      answers.delete(msg.id);
      if (msg.error != null) waiting.reject(msg.error);
      else waiting.resolve(msg.result);
    });
    let spec = null;
    try {
      spec = JSON.parse(await plugin("dialog_window_spec"));
    } catch (e) {
      console.error("[tauris-ui dialog] this window has no dialog to show:", e);
      return;
    }
    if (!spec || !spec.options) return;
    const o = spec.options;
    if (spec.kind === "form") {
      const values = await formHere({
        ...o,
        validate: spec.has.validate ? v => ask("validate", v) : undefined,
        review: spec.has.review ? v => ask("review", v) : undefined,
        submit: spec.has.submit ? v => ask("submit", v) : undefined,
      });
      return tellDone(values);
    }
    if (spec.kind === "review") return tellDone(await reviewHere(o));
    if (spec.kind === "shortcuts") return tellDone(await shortcutsHere(o));
    if (spec.kind === "about") return tellDone(await aboutHere(o));
    return tellDone(null);
  }
  if (IN_WINDOW && tauri()) {
    // The asker's answers come to this window under its own label: heard as "self".
    const own = window.__taurisUiDeliver;
    Object.defineProperty(window, "__taurisUiDeliver", {
      configurable: true,
      value: (name, payload) => {
        if (name === WINDOW_EVENT) return heard.get("self")?.(payload?.message ?? {});
        return own(name, payload);
      },
    });
    // After the app's page has run (and defined its field types).
    if (document.readyState === "complete") queueMicrotask(serveWindow);
    else window.addEventListener("load", () => serveWindow(), { once: true });
  }

  window.TaurisDialog = {
    confirm,
    form,
    review,
    shortcuts,
    about,
    panel,
    defineField,
    /** Closes whatever dialog is open (a session that ends): each ends as cancelled. */
    close() {
      for (const d of [...open].reverse()) d.abort?.();
    },
    /** This page is a dialog's window: the app only defines its field types here. */
    inWindow: IN_WINDOW,
    /** Whether a dialog is open (the app may hold its own keys while one is). */
    get isOpen() { return open.length > 0; },
  };
})();
