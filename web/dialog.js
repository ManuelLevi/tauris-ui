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

  const X_SVG = '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M2 2l6 6M8 2l-6 6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';

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
    const veil = el("div", "tdl-veil", {}, box);
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
    const w = words(options.labels);
    const ok = String(options.ok ?? w.ok);
    const cancel = String(options.cancel ?? w.cancel);
    if (options.native && window.__TAURI__?.core) {
      try {
        const yes = await window.__TAURI__.core.invoke("plugin:tauris-ui|ask", {
          title: String(options.title ?? ""), message: String(options.message ?? ""), ok, cancel, warning: options.danger === true,
        });
        if (typeof yes === "boolean") return yes;
      } catch {
        // no system alert here (the files feature or the dialog plugin is missing): asked in the page
      }
    }
    return new Promise(resolve => {
      let state = null;
      const end = yes => { state.close(); resolve(yes); };
      state = frame({ title: options.title, role: "alertdialog", width: options.width, onCancel: () => end(false), className: "tdl-question" });
      const text = el("div", "tdl-message", { id: `${state.heading.id}-m` });
      for (const para of String(options.message ?? "").split(/\n{2,}/)) if (para.trim()) text.append(el("p", "", {}, para.trim()));
      state.box.setAttribute("aria-describedby", text.id);
      state.body.append(text);
      const no = button(cancel, { onPress: () => end(false) });
      const yes = button(ok, { primary: !options.danger, danger: options.danger === true, onPress: () => end(true) });
      state.buttons.append(el("span", "tdl-spacer"), no, yes);
      // Starts on Cancel: Enter there is "no", never a delete by accident.
      no.focus({ preventScroll: true });
    });
  }

  // ---------- a form ----------

  const TEXTLIKE = new Set(["text", "password", "number", "email", "url", "tel", "search", "date", "time"]);

  function fieldControl(f, id) {
    const type = String(f.type ?? "text");
    let control;
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
        id, type: TEXTLIKE.has(type) ? type : "text", placeholder: f.placeholder ?? null, autocomplete: f.autocomplete ?? "off",
        spellcheck: type === "text" ? "false" : null, min: f.min ?? null, max: f.max ?? null, step: f.step ?? null,
        inputmode: f.inputmode ?? null,
      });
      control.value = f.value == null ? "" : String(f.value);
    }
    if (f.disabled) control.disabled = true;
    if (f.required) control.setAttribute("aria-required", "true");
    return control;
  }

  function valueOf(f, control) {
    if (f.type === "checkbox") return control.checked;
    if (f.type === "number") return control.value === "" ? null : Number(control.value);
    return control.value;
  }

  // The review: "Field: old → new", old struck through; without `before`, only that it changed.
  function reviewRows(rows, w) {
    const table = el("table", "tdl-review-rows");
    const tbody = el("tbody");
    for (const c of rows) {
      const row = el("tr", "", { "data-field": String(c.field) });
      row.append(el("th", "", { scope: "row" }, `${c.field}:`));
      const cell = el("td");
      if (c.before === undefined) cell.append(el("span", "tdl-now", {}, c.after == null ? say(w.changed) : String(c.after)));
      else cell.append(el("span", "tdl-was", {}, String(c.before === "" ? "—" : c.before)), el("span", "tdl-arrow", { "aria-hidden": "true" }, " → "),
        el("span", "tdl-now", {}, String(c.after === "" ? "—" : c.after)));
      row.append(cell);
      tbody.append(row);
    }
    table.append(tbody);
    return table;
  }

  function form(options = {}) {
    const w = words(options.labels);
    const fields = (Array.isArray(options.fields) ? options.fields : []).filter(f => f && f.name != null);
    return new Promise(resolve => {
      let state = null;
      let busy = false;
      let reviewing = null; // the values waiting for "Save Changes"
      const end = values => { state.close(); resolve(values); };
      const cancel = () => {
        if (busy) return;
        // During a review, Esc goes back to the fields.
        if (reviewing) return showFields();
        end(null);
      };
      state = frame({ title: options.title, wide: options.wide === true, width: options.width, onCancel: cancel, className: "tdl-form" });
      const grid = el("div", "tdl-fields");
      const controls = new Map();
      for (const f of fields) {
        const id = `${state.heading.id}-${String(f.name).replace(/[^\w-]/g, "_")}`;
        const control = fieldControl(f, id);
        controls.set(String(f.name), { f, control });
        const label = el("label", `tdl-label${f.type === "textarea" ? " tdl-top" : ""}`, { for: id }, f.type === "checkbox" ? "" : `${f.label ?? f.name}:`);
        const cell = el("div", "tdl-cell");
        if (f.type === "checkbox") cell.append(el("label", "tdl-check-label", {}, control, el("span", "", {}, String(f.label ?? f.name))));
        else cell.append(control);
        // A field's own refusal: a balloon under it.
        const tip = el("div", "tdl-tip", { id: `${id}-tip`, role: "alert", hidden: true });
        cell.append(tip);
        if (f.hint) {
          const hint = el("div", "tdl-hint", { id: `${id}-hint` }, String(f.hint));
          cell.append(hint);
          control.setAttribute("aria-describedby", hint.id);
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

      const values = () => Object.fromEntries([...controls].map(([name, { f, control }]) => [name, valueOf(f, control)]));
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
          at.control.focus();
          at.control.select?.();
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
          // Needed fields first, then the app's own checks.
          for (const [name, { f, control }] of controls) {
            if (f.required && !f.disabled && (f.type === "checkbox" ? !control.checked : !String(control.value).trim())) {
              return refuse({ field: name, text: say(f.requiredText ?? w.required, String(f.label ?? name)) });
            }
          }
          let refused = null;
          try {
            refused = typeof options.validate === "function" ? options.validate(v) : null;
          } catch (e) {
            refused = e;
          }
          if (refused) return refuse(refused);
          const rows = typeof options.review === "function" ? options.review(v) : null;
          if (Array.isArray(rows) && rows.length) return showReview(rows, v);
        }
        if (typeof options.submit === "function") {
          setBusy(true);
          try {
            await options.submit(v);
          } catch (e) {
            setBusy(false);
            if (reviewing) showFields();
            return refuse(e && typeof e === "object" && "field" in e ? e : String(e?.message ?? e));
          }
          setBusy(false);
        }
        end(v);
      }
      function focusFirst() {
        // The first text field, its text selected, ready to retype; else the default button.
        const first = [...controls.values()].map(c => c.control).find(c => !c.disabled && c.type !== "checkbox");
        if (first) {
          first.focus({ preventScroll: true });
          if (first.value && first.select) first.select();
        } else {
          yes.focus({ preventScroll: true });
        }
      }
      // Enter in a field is the default button (⌘↩ in a text area); typing clears a refusal.
      state.box.addEventListener("keydown", e => {
        if (e.key !== "Enter" || e.isComposing || e.repeat) return;
        const t = e.target;
        const area = t instanceof HTMLTextAreaElement;
        if (t instanceof HTMLElement && t.classList.contains("tdl-btn")) return;
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
      focusFirst();
    });
  }

  // ---------- a review on its own ----------

  function review(options = {}) {
    const w = words(options.labels);
    return new Promise(resolve => {
      let state = null;
      const end = yes => { state.close(); resolve(yes); };
      state = frame({ title: options.title ?? w.review, width: options.width, onCancel: () => end(false), className: "tdl-form" });
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

  function shortcuts(options = {}) {
    const w = words(options.labels);
    return new Promise(resolve => {
      let state = null;
      const end = () => { state.close(); resolve(); };
      state = frame({ title: options.title ?? w.shortcuts, wide: true, width: options.width ?? 700, onCancel: end, className: "tdl-sheet" });
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

  function about(options = {}) {
    const w = words(options.labels);
    return new Promise(resolve => {
      let state = null;
      const end = () => { state.close(); resolve(); };
      state = frame({ title: options.title ?? `About ${options.name ?? ""}`.trim(), width: options.width ?? 420, onCancel: end, className: "tdl-about" });
      const mark = el("div", "tdl-mark", { "aria-hidden": "true" });
      if (typeof options.mark === "string" && /^(data:|https?:|\/|\.)/.test(options.mark)) mark.append(el("img", "", { src: options.mark, alt: "" }));
      else markup(mark, options.mark);
      const rows = el("dl", "tdl-about-rows");
      for (const [k, v] of Array.isArray(options.rows) ? options.rows : []) rows.append(el("dt", "", {}, String(k)), el("dd", "", {}, String(v ?? "")));
      state.body.append(el("div", "tdl-about-head", {}, mark, el("div", "", {}, el("p", "tdl-about-name", {}, String(options.name ?? "")),
        options.description ? el("p", "tdl-about-text", {}, String(options.description)) : null)), rows);
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

  window.TaurisDialog = {
    confirm,
    form,
    review,
    shortcuts,
    about,
    panel,
    /** Whether a dialog is open (the app may hold its own keys while one is). */
    get isOpen() { return open.length > 0; },
  };
})();
