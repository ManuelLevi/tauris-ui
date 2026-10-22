// tauris-ui table: a dense data table, as in a desktop app: 25px rows under a
// header that stays, columns sorted ▲▼ by a click on their header and widened
// by dragging its edge, rows in groups (a colour square, a name and a count;
// with `collapsible`, a +/- box), a row selected and moved with the keys (or
// several, with `multiple`), typing a name to jump to it, a name edited in
// place (F2), a checkbox column, a row's own buttons, and a flash for a row
// just added. Plain JavaScript: no build step, no dependencies. In a Tauri app
// the plugin injects this file with its stylesheet (web/table.css), added the
// first time a page uses it.
//
//   const table = TaurisTable.mount(document.querySelector("#tasks"), {
//     columns: [
//       { key: "done", label: "", width: 28, check: true, canToggle: t => t.blocked ? "Waiting on the brief." : true, onToggle: (t, on) => mark(t, on) },
//       { key: "name", label: "Task", edit: true },
//       { key: "due", label: "Due", width: 90, align: "right", value: t => t.dueDate },
//       { actions: [{ id: "edit", icon: "✎", title: "Edit", onClick: t => edit(t) }] },
//     ],
//     rows: tasks,                                  // each { id, group?, ... }
//     groups: projects.map(p => ({ id: p.id, label: p.name, color: p.color })),
//     onOpen: (t, { cmd }) => edit(t),              // Enter, a double click (cmd: ⌘↩, a ⌘-click)
//     onEdit: (t, key, value) => rename(t, value),  // a throw (or text) refuses it: the field stays
//     onContextMenu: (t, at) => TaurisMenu.open(menuFor(t), at),
//   });
//
// The app owns its rows: setRows() with new ones draws them again (the
// selection, the scroll and a name being edited stay). Keys, on the table:
// ↑ ↓ move, Home End and ⌘↑ ⌘↓ go to the first and last, Page Up and Down by
// a page, Enter opens (⌘↩ the other way), F2 edits, Space ticks the checkbox
// column, the menu key or ⇧F10 opens the row's menu, a letter jumps to the
// next row whose name starts with what was typed. With collapsible groups, ←
// and → close and open them. `onKey` takes any key first. Drag to reorder:
// TaurisReorder.attach(table.scroller, { rows: ".ttb-row", ... }).

(() => {
  "use strict";
  if (window.TaurisTable) return;

  // Filled in by the plugin; left as is when the file is loaded on its own.
  const CSS = "__TAURIS_TABLE_CSS__";
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
  const plain = e => !e.metaKey && !e.ctrlKey && !e.altKey && !e.shiftKey;

  const LABELS = {
    // a letter typed that no row's name starts with: (typed) => text
    noneStarts: typed => `Nothing starts with “${typed}”.`,
    // a button that copied its text, for a moment
    copied: "Copied",
    // ⌘C on rows: (count) => text
    copiedRows: n => (n === 1 ? "Copied 1 row." : `Copied ${n} rows.`),
    // the clipboard refused
    copyFailed: "Could not copy.",
    // a group with no rows
    emptyGroup: "Nothing here.",
    // the table with no rows at all
    empty: "Nothing yet.",
    // state: "loading"
    loading: "Loading…",
    // a group's count, after its name: (rows) => text
    count: n => String(n),
    // an edit's maxLength reached: (n) => text
    maxLength: n => `At most ${n} characters.`,
    // a group's +/- box, for a screen reader
    expand: "Expand",
    collapse: "Collapse",
    // a column's edge, for a screen reader
    resize: label => `${label} width`,
  };

  const DEFAULTS = {
    // [{ key, label, width?, align?, render?, text?, value?, compare?, sortable?, title?, className?,
    //    short?, edit?, check?, canToggle?, onToggle?, actions? }]
    columns: [],
    // [{ id, group?, dim?, ...fields }]: the rows, in the order the app keeps them
    rows: [],
    // [{ id, label, color?, detail?, empty?, expanded? }]: rows with that `group` go under it, in this order
    groups: null,
    // groups open and close (a +/- box, ← →, Enter or Space on a selected group)
    collapsible: false,
    // groups can be selected (the keys go through them), even when they do not close
    selectableGroups: false,
    // buttons on a group's row, shown on hover and selection: [{ id, icon, title, onClick(group), danger? }]
    groupActions: null,
    // (row) => true: the row stays after the others, whichever way the table is sorted (locked, no website)
    last: null,
    // { key, up }: the column sorted, or null for the rows in the order given
    sort: null,
    // false: no header sorts
    sortable: true,
    // false: no column's edge can be dragged
    resizable: true,
    selected: null,
    // ⌘-click and Shift-click select several rows, ⌘A every row shown, ⇧↑ ⇧↓ extend
    multiple: false,
    // ⌘C copies the selected rows as text (tab-separated: a spreadsheet takes them)
    copy: false,
    // the column whose text typing matches (default the first)
    typeKey: null,
    // how long after a key the next one still adds to the name being typed
    typeAheadMs: 700,
    // (row) => class names for the row (overdue, locked, a drop target)
    rowClass: null,
    // null; "loading"; or { error: text }: said in place of the rows
    state: null,
    // keeps the columns' widths, the sort and the closed groups in the browser's storage under this key
    storageKey: null,
    // the table's name, for a screen reader
    label: "",
    labels: {},
    // false: the page brings its own stylesheet
    styles: true,
    // (row | null, { how, rows }): the selection changed; rows: every selected row
    onSelect: null,
    // (row, { how, cmd }): Enter or a double click; cmd: ⌘↩, or a ⌘-click (without `multiple`)
    onOpen: null,
    // (row, key, value): a cell edited in place; a throw (or text, or false) refuses it, and it stays open
    onEdit: null,
    // (row | null, { x, y, how }): a right click or the menu key; null on the empty space
    onContextMenu: null,
    // ({ key, up } | null): a header was clicked
    onSort: null,
    // ({ widths }): a column's edge was dragged
    onResize: null,
    // (event, row | null, group | null) => true when the app took the key (Delete)
    onKey: null,
    // (group, { how, cmd }): a double click on a group's row (or Enter on it, when groups do not close)
    onGroupOpen: null,
    // (group, open, { how }): a group opened or closed by the person
    onGroupToggle: null,
    // (group, { x, y, how }): a right click or the menu key on a group's row
    onGroupContextMenu: null,
    // (text, kind): what the table has to say ("Nothing starts with “q”.", a refusal)
    onMessage: null,
  };

  let uid = 0;
  const say = (label, ...args) => (typeof label === "function" ? label(...args) : String(label ?? ""));
  const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
  const fold = text => String(text ?? "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
  const keyTime = e => e.timeStamp || performance.now();
  const CSS_ESCAPE = v => (window.CSS?.escape ? window.CSS.escape(v) : String(v).replace(/["\\]/g, "\\$&"));
  const TICK = "<svg viewBox='0 0 16 16' aria-hidden='true'><path d='M3 8.5 6.5 12 13 4.5' fill='none' stroke='currentColor' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/></svg>";

  function el(tag, cls, attrs = {}, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    for (const [k, v] of Object.entries(attrs)) if (v != null) node.setAttribute(k, String(v));
    if (text != null) node.textContent = String(text);
    return node;
  }
  // An icon: text (an emoji), or markup starting with "<" (the app's own svg).
  function icon(node, value) {
    const v = String(value ?? "");
    if (v.trim().startsWith("<")) node.innerHTML = v;
    else node.textContent = v;
  }

  function mount(root, options = {}) {
    if (!(root instanceof HTMLElement)) throw new Error("TaurisTable.mount needs the element to draw the table in");
    if (root.__taurisTable) throw new Error("TaurisTable.mount: this element already has a table; call destroy() first");
    root.__taurisTable = true;
    // An option given as undefined keeps its default.
    const given = changes => Object.fromEntries(Object.entries(changes ?? {}).filter(([, v]) => v !== undefined));
    const opt = { ...DEFAULTS, ...given(options) };
    if (opt.styles) addStyles();
    const L = () => ({ ...LABELS, ...(opt.labels || {}) });
    const id = `ttb-${++uid}`;
    const life = new AbortController();
    const signal = life.signal;
    const call = (fn, ...args) => {
      if (typeof fn !== "function" || signal.aborted) return undefined;
      try {
        return fn(...args);
      } catch (e) {
        console.error("[tauris-ui table] a callback failed:", e);
        return undefined;
      }
    };
    const message = (text, kind = "info") => {
      if (!text) return;
      live.textContent = text;
      call(opt.onMessage, text, kind);
    };

    // ---------- the parts ----------

    const addedClass = !root.classList.contains("ttb");
    root.classList.add("ttb");
    const scroller = el("div", "ttb-list", { role: "grid", tabindex: "0", id: `${id}-grid` });
    const table = el("table", "ttb-table", { role: "presentation" });
    const cols = el("colgroup");
    const head = el("thead", "", { role: "rowgroup" });
    const headRow = el("tr", "ttb-headrow", { role: "row" });
    head.append(headRow);
    const body = el("tbody", "", { role: "rowgroup" });
    table.append(cols, head, body);
    const empty = el("p", "ttb-empty");
    scroller.append(table, empty);
    const live = el("span", "ttb-live", { role: "status" });
    root.replaceChildren(scroller, live);

    // ---------- state ----------

    let rows = [];
    let shown = []; // the rows in the order drawn
    let items = []; // what the keys go through: { group } and { row }, as drawn
    let byId = new Map();
    let sel = opt.selected == null ? null : String(opt.selected); // the row with the focus
    let selGroup = null; // a group's row with the focus instead (collapsible groups)
    const picked = new Set(); // every selected row (multiple)
    let anchor = null;
    let sort = opt.sort && opt.sort.key != null ? { key: opt.sort.key, up: opt.sort.up !== false } : null;
    const widths = new Map(); // column index -> width dragged to
    const closed = new Set(); // groups closed
    const knownGroups = new Set();
    let editing = null; // { key, ci, draft }
    let typed = "";
    let typedAt = 0;
    let typedTimer = 0;
    const flashing = new Map(); // id -> timer
    const copiedAt = new Map(); // "row|action" -> timer

    const keyOf = v => String(v);
    if (sel != null) picked.add(sel);
    const stored = (() => {
      if (!opt.storageKey) return null;
      try {
        const data = JSON.parse(localStorage.getItem(String(opt.storageKey)) || "null");
        return data && typeof data === "object" ? data : null;
      } catch {
        return null;
      }
    })();
    if (stored) {
      if (Array.isArray(stored.widths)) stored.widths.forEach((w, i) => { if (Number.isFinite(w) && w > 0) widths.set(i, w); });
      if (stored.sort && stored.sort.key != null) sort = { key: stored.sort.key, up: stored.sort.up !== false };
      else if (stored.sort === null) sort = null;
      for (const g of Array.isArray(stored.closed) ? stored.closed : []) closed.add(String(g));
      for (const g of Array.isArray(stored.known) ? stored.known : []) knownGroups.add(String(g));
    }
    function keep() {
      if (!opt.storageKey) return;
      try {
        const list = columns().map((_, i) => widths.get(i) ?? null);
        localStorage.setItem(String(opt.storageKey), JSON.stringify({ widths: list, sort, closed: [...closed], known: [...knownGroups] }));
      } catch {
        // storage blocked (a private window): kept for this page only
      }
    }

    const columns = () => (Array.isArray(opt.columns) ? opt.columns : []);
    const textOf = (row, col) => {
      if (!col) return "";
      if (typeof col.text === "function") return String(call(col.text, row) ?? "");
      const v = col.key != null ? row[col.key] : "";
      return v == null ? "" : String(v);
    };
    const typeColumn = () => columns().find(c => c.key === opt.typeKey) ?? columns().find(c => !c.actions && !c.check) ?? null;
    const rowId = key => `${id}-r-${String(key).replace(/[^\w-]/g, ch => `_${ch.codePointAt(0)}`)}`;
    const groupId = key => `${id}-g-${String(key).replace(/[^\w-]/g, ch => `_${ch.codePointAt(0)}`)}`;
    const current = () => (sel != null ? byId.get(sel) ?? null : null);
    const groupById = key => (Array.isArray(opt.groups) ? opt.groups.find(g => keyOf(g.id) === key) ?? null : null);
    const collapsible = () => opt.collapsible === true && Array.isArray(opt.groups);
    const groupsSelectable = () => (opt.selectableGroups === true || opt.collapsible === true) && Array.isArray(opt.groups);
    const pickedRows = () => shown.filter(r => picked.has(keyOf(r.id)));

    function compare(col) {
      if (typeof col.compare === "function") return (a, b) => call(col.compare, a, b, sort ? sort.up : true) ?? 0;
      const value = row => (typeof col.value === "function" ? call(col.value, row) : col.key != null ? row[col.key] : null);
      return (a, b) => {
        const x = value(a);
        const y = value(b);
        if (x == null || x === "") return y == null || y === "" ? 0 : 1;
        if (y == null || y === "") return -1;
        if (typeof x === "number" && typeof y === "number") return x - y;
        if (typeof x === "boolean" && typeof y === "boolean") return Number(x) - Number(y);
        if (x instanceof Date && y instanceof Date) return x - y;
        return collator.compare(String(x), String(y));
      };
    }
    // The rows as they show: sorted (a stable sort: ties keep the app's order), then in groups.
    function arrange() {
      let list = rows.slice();
      const col = sort ? columns().find(c => c.key === sort.key && !c.actions) : null;
      if (col) {
        const by = compare(col);
        list = list.map((r, i) => [r, i]).sort(([a, i], [b, j]) => (by(a, b) * (sort.up ? 1 : -1)) || i - j).map(([r]) => r);
      }
      // Rows that stay last, either way (in their order among themselves).
      if (typeof opt.last === "function") {
        const lastOnes = list.filter(r => call(opt.last, r) === true);
        if (lastOnes.length) list = list.filter(r => !lastOnes.includes(r)).concat(lastOnes);
      }
      if (!Array.isArray(opt.groups)) return { list, parts: null };
      const parts = opt.groups.map(g => ({ group: g, rows: [] }));
      const at = new Map(opt.groups.map((g, i) => [keyOf(g.id), i]));
      const loose = [];
      for (const r of list) {
        const i = r.group == null ? undefined : at.get(keyOf(r.group));
        if (i === undefined) loose.push(r);
        else parts[i].rows.push(r);
      }
      if (loose.length) parts.push({ group: null, rows: loose });
      return { list: parts.flatMap(p => p.rows), parts };
    }
    const isOpen = g => !collapsible() || !closed.has(keyOf(g.id));

    // ---------- drawing ----------

    const colWidth = (c, i) => widths.get(i) ?? (c.width != null ? c.width : c.actions ? Math.max(1, c.actions.length) * 24 + 8 : null);
    function drawHead() {
      cols.replaceChildren(...columns().map((c, i) => {
        const col = el("col", c.actions ? "ttb-col-acts" : "");
        const w = colWidth(c, i);
        if (w != null) col.style.width = typeof w === "number" ? `${w}px` : String(w);
        return col;
      }));
      headRow.replaceChildren(...columns().map((c, i) => {
        const th = el("th", `ttb-th${c.align ? ` ttb-${c.align}` : ""}`, { role: "columnheader", scope: "col" });
        if (opt.resizable !== false && !c.actions && i < columns().length - 1) th.append(grip(i, c));
        if (c.actions || c.check) {
          th.setAttribute("aria-label", c.label ?? "");
          return th;
        }
        const on = sort && sort.key === c.key;
        const sortable = opt.sortable && c.sortable !== false && c.key != null;
        th.setAttribute("aria-sort", on ? (sort.up ? "ascending" : "descending") : "none");
        if (!sortable) {
          th.prepend(document.createTextNode(String(c.label ?? "")));
          th.removeAttribute("aria-sort");
          return th;
        }
        const btn = el("button", "ttb-sort", { type: "button", tabindex: "-1" });
        btn.append(el("span", "ttb-th-label", {}, c.label ?? ""));
        if (on) btn.append(el("span", "ttb-arrow", { "aria-hidden": "true" }, sort.up ? "▲" : "▼"));
        btn.addEventListener("click", () => setSort(on ? { key: c.key, up: !sort.up } : { key: c.key, up: true }, true));
        th.prepend(btn);
        return th;
      }));
    }

    // A column's right edge: dragged, the column follows (kept under storageKey).
    function grip(i, c) {
      const g = el("span", "ttb-grip", { role: "separator", "aria-orientation": "vertical", "aria-label": say(L().resize, c.label ?? "") });
      g.addEventListener("pointerdown", e => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        const th = g.parentElement;
        const startX = e.clientX;
        const startW = th.getBoundingClientRect().width;
        const ends = new AbortController();
        const both = AbortSignal.any ? AbortSignal.any([signal, ends.signal]) : ends.signal;
        root.classList.add("ttb-resizing");
        window.addEventListener("pointermove", ev => {
          widths.set(i, Math.max(c.minWidth ?? 40, Math.round(startW + ev.clientX - startX)));
          const col = cols.children[i];
          if (col) col.style.width = `${widths.get(i)}px`;
        }, { signal: both });
        const stop = () => {
          if (ends.signal.aborted) return;
          ends.abort();
          root.classList.remove("ttb-resizing");
          keep();
          fitShort();
          call(opt.onResize, { widths: columns().map((_, j) => widths.get(j) ?? null) });
        };
        window.addEventListener("pointerup", stop, { signal: both });
        window.addEventListener("pointercancel", stop, { signal: both });
      }, { signal });
      g.addEventListener("click", e => e.stopPropagation(), { signal });
      return g;
    }

    function cellFor(row, c, ci) {
      const td = el("td", `ttb-cell${c.align ? ` ttb-${c.align}` : ""}${c.className ? ` ${c.className}` : ""}`, { role: "gridcell" });
      td.dataset.col = String(ci);
      if (c.actions) {
        td.classList.add("ttb-acts");
        c.actions.forEach((a, ai) => td.append(actionButton(row, a, ci, ai)));
        return td;
      }
      if (c.check) {
        td.classList.add("ttb-check-cell");
        const box = el("input", "ttb-check", { type: "checkbox", tabindex: "-1", "aria-label": `${c.label || ""}${c.label ? ": " : ""}${textOf(row, typeColumn())}` });
        box.checked = Boolean(typeof c.value === "function" ? call(c.value, row) : row[c.key]);
        if (box.checked) box.setAttribute("checked", "");
        // Blocked: it looks and reads so, its reason the tooltip; a press still says why.
        const may = typeof c.canToggle === "function" ? call(c.canToggle, row) : true;
        if (may !== true && may !== undefined) {
          box.setAttribute("aria-disabled", "true");
          if (typeof may === "string" && may) box.title = may;
        }
        box.addEventListener("click", e => {
          e.preventDefault();
          e.stopPropagation();
          // The column as it is now (a kept cell's listener was bound at an earlier draw).
          toggleCheck(row, columns()[ci] ?? c, "mouse");
        }, { signal });
        td.append(box);
        return td;
      }
      // A name being edited: its field, with what was typed (it survives a redraw).
      if (editing && editing.key === keyOf(row.id) && editing.ci === ci) {
        td.classList.add("ttb-editing");
        const input = el("input", "ttb-edit", { type: "text", "aria-label": c.label ?? "" });
        if (Number.isFinite(c.maxLength) && c.maxLength > 0) input.maxLength = c.maxLength;
        input.value = editing.draft;
        input.addEventListener("input", () => {
          if (!editing) return;
          editing.draft = input.value;
          // At its limit: said once (the field takes no more).
          if (input.maxLength > 0 && input.value.length >= input.maxLength && !editing.toldMax) {
            editing.toldMax = true;
            message(say(L().maxLength, input.maxLength), "error");
          }
        }, { signal });
        input.addEventListener("keydown", e => {
          e.stopPropagation();
          if (e.isComposing) return;
          if (e.key === "Enter") {
            e.preventDefault();
            commitEdit();
          } else if (e.key === "Escape") {
            e.preventDefault();
            cancelEdit();
          }
        }, { signal });
        input.addEventListener("blur", () => { if (editing && editing.input === input && !editing.saving) commitEdit(true); }, { signal });
        editing.input = input;
        td.append(input);
        return td;
      }
      if (c.edit) td.classList.add("ttb-editable");
      const out = typeof c.render === "function" ? call(c.render, row, td) : textOf(row, c);
      if (out instanceof Node) td.append(out);
      else if (out != null && out !== td) td.textContent = String(out);
      const tip = typeof c.title === "function" ? call(c.title, row) : c.title === true ? td.textContent : null;
      if (tip) td.title = String(tip);
      if (typeof c.short === "function") {
        td.dataset.full = td.textContent;
        td.dataset.short = String(call(c.short, row) ?? "");
      }
      return td;
    }

    // The action as it is now: a kept cell's button was made at an earlier draw.
    const actionNow = (ci, ai, a) => {
      const acts = columns()[ci]?.actions;
      if (!Array.isArray(acts)) return a;
      return acts.find(x => x && (x.id ?? x.title) === (a.id ?? a.title)) ?? acts[ai] ?? a;
    };
    function actionButton(row, a, ci, ai) {
      const key = `${keyOf(row.id)}|${a.id ?? a.title}`;
      const pressed = typeof a.pressed === "function" ? Boolean(call(a.pressed, row)) : null;
      const label = String(a.title ?? "");
      const name = textOf(row, typeColumn());
      // Off, with why: its tooltip, and said when it is pressed.
      const off = typeof a.disabled === "function" ? call(a.disabled, row) : a.disabled;
      const why = typeof off === "string" ? off : "";
      const btn = el("button", "ttb-ib", { type: "button", tabindex: "-1", title: why || label, "aria-label": name ? `${label}: ${name}` : label });
      if (a.id != null) btn.dataset.act = String(a.id);
      if (pressed !== null) btn.setAttribute("aria-pressed", String(pressed));
      if (off) btn.setAttribute("aria-disabled", "true");
      if (a.danger) btn.classList.add("ttb-danger");
      const done = copiedAt.has(key);
      if (done) {
        btn.classList.add("ttb-copied");
        btn.title = say(L().copied);
      }
      icon(btn, done ? TICK : a.icon ?? label.slice(0, 1));
      btn.addEventListener("click", async e => {
        e.stopPropagation();
        const r = byId.get(keyOf(row.id)) ?? row;
        const act = actionNow(ci, ai, a);
        const offNow = typeof act.disabled === "function" ? call(act.disabled, r) : act.disabled;
        if (offNow) return message(typeof offNow === "string" ? offNow : "", "error");
        if (typeof act.copy === "function") {
          const text = String(call(act.copy, r) ?? "");
          const wrote = navigator.clipboard?.writeText ? await navigator.clipboard.writeText(text).then(() => true, () => false) : false;
          if (!wrote) return message(say(L().copyFailed), "error");
          clearTimeout(copiedAt.get(key));
          copiedAt.set(key, setTimeout(() => {
            copiedAt.delete(key);
            if (!signal.aborted) draw();
          }, 1200));
          message(say(L().copied), "ok");
          draw();
        }
        call(act.onClick, r, { how: e.detail === 0 ? "keyboard" : "mouse" });
        return undefined;
      }, { signal });
      btn.addEventListener("dblclick", e => e.stopPropagation(), { signal });
      return btn;
    }

    function rowFor(row) {
      const key = keyOf(row.id);
      const tr = el("tr", "ttb-row", { role: "row", id: rowId(key), "aria-selected": String(picked.has(key)) });
      tr.dataset.id = key;
      if (row.group != null) tr.dataset.group = keyOf(row.group);
      if (flashing.has(key)) tr.classList.add("ttb-flash");
      if (row.dim) tr.classList.add("ttb-dim");
      if (key === sel) tr.classList.add("ttb-focus");
      const extra = typeof opt.rowClass === "function" ? call(opt.rowClass, row) : null;
      if (extra) for (const c of String(extra).split(/\s+/).filter(Boolean)) tr.classList.add(c);
      columns().forEach((c, ci) => tr.append(cellFor(row, c, ci)));
      return tr;
    }

    function groupRow(part) {
      const g = part.group;
      const key = keyOf(g.id);
      const tr = el("tr", "ttb-group", { role: "row", id: groupId(key) });
      tr.dataset.group = key;
      const td = el("td", "", { role: "gridcell", colspan: String(Math.max(1, columns().length)) });
      if (groupsSelectable()) tr.setAttribute("aria-selected", String(selGroup === key));
      // A group with no rows has nothing to open: no box.
      if (collapsible() && part.rows.length) {
        const open = isOpen(g);
        tr.setAttribute("aria-expanded", String(open));
        const box = el("span", "ttb-box", { "aria-hidden": "true", title: say(open ? L().collapse : L().expand) });
        box.textContent = open ? "−" : "+";
        td.append(box);
      }
      const chip = el("span", "ttb-chip", { "aria-hidden": "true" });
      if (g.color) tr.style.setProperty("--ttb-c", String(g.color));
      const name = el("span", "ttb-group-label", {}, g.label ?? "");
      const detail = el("span", "ttb-group-detail", {}, g.detail != null ? g.detail : say(L().count, part.rows.length));
      td.append(chip, name, detail);
      if (Array.isArray(opt.groupActions) && opt.groupActions.length) {
        const acts = el("span", "ttb-group-acts");
        opt.groupActions.forEach((a, ai) => {
          const btn = el("button", `ttb-ib${a.danger ? " ttb-danger" : ""}`, { type: "button", tabindex: "-1", title: String(a.title ?? ""), "aria-label": `${a.title ?? ""}: ${g.label ?? ""}` });
          if (a.id != null) btn.dataset.act = String(a.id);
          icon(btn, a.icon ?? String(a.title ?? "").slice(0, 1));
          btn.addEventListener("click", e => {
            e.stopPropagation();
            // The group's actions as they are now (a kept row's button was made at an earlier draw).
            const now = (Array.isArray(opt.groupActions) ? opt.groupActions : []);
            const act = now.find(x => x && (x.id ?? x.title) === (a.id ?? a.title)) ?? now[ai] ?? a;
            call(act.onClick, groupById(key) ?? g, { how: e.detail === 0 ? "keyboard" : "mouse" });
          }, { signal });
          btn.addEventListener("dblclick", e => e.stopPropagation(), { signal });
          acts.append(btn);
        });
        td.append(acts);
      }
      tr.append(td);
      return tr;
    }

    function draw() {
      const top = scroller.scrollTop;
      const hadEdit = editing?.input && document.activeElement === editing.input;
      const { list, parts } = arrange();
      byId = new Map(rows.map(r => [keyOf(r.id), r]));
      if (sel != null && !byId.has(sel)) sel = null;
      for (const k of [...picked]) if (!byId.has(k)) picked.delete(k);
      if (editing && !byId.has(editing.key)) editing = null;
      if (Array.isArray(opt.groups)) {
        for (const g of opt.groups) {
          const k = keyOf(g.id);
          if (!knownGroups.has(k)) {
            knownGroups.add(k);
            if (g.expanded === false) closed.add(k);
          }
        }
        if (selGroup != null && !groupById(selGroup)) selGroup = null;
      }
      const out = [];
      items = [];
      shown = [];
      if (parts) {
        for (const part of parts) {
          if (part.group) {
            out.push(groupRow(part));
            if (groupsSelectable()) items.push({ group: part.group });
          }
          const open = !part.group || isOpen(part.group);
          if (!open) continue;
          if (!part.rows.length && part.group) {
            const none = el("tr", "ttb-none", { role: "row" });
            none.append(el("td", "", { role: "gridcell", colspan: String(Math.max(1, columns().length)) }, part.group.empty ?? say(L().emptyGroup)));
            out.push(none);
          }
          for (const r of part.rows) {
            out.push(rowFor(r));
            items.push({ row: r });
            shown.push(r);
          }
        }
      } else {
        for (const r of list) {
          out.push(rowFor(r));
          items.push({ row: r });
          shown.push(r);
        }
      }
      // A state in place of the rows: loading, or what went wrong.
      const state = opt.state;
      const error = state && typeof state === "object" && state.error != null ? String(state.error) : null;
      place(state ? [] : out);
      empty.hidden = !state && rows.length > 0;
      empty.classList.toggle("ttb-error", Boolean(error));
      empty.setAttribute("role", error ? "alert" : "status");
      empty.textContent = error ?? (state === "loading" ? say(L().loading) : say(L().empty));
      scroller.setAttribute("aria-label", String(opt.label ?? ""));
      scroller.setAttribute("aria-rowcount", String(shown.length + 1));
      scroller.setAttribute("aria-multiselectable", opt.multiple ? "true" : "false");
      const active = selGroup != null ? groupId(selGroup) : sel != null ? rowId(sel) : null;
      if (active) scroller.setAttribute("aria-activedescendant", active);
      else scroller.removeAttribute("aria-activedescendant");
      scroller.scrollTop = top;
      fitShort();
      if (hadEdit && editing?.input) {
        editing.input.focus({ preventScroll: true });
        const n = editing.input.value.length;
        editing.input.setSelectionRange(n, n);
      }
    }

    // A cell with a short form ("€1.2M") shows it when its whole text ("€1,234,567") does not fit.
    // Inside a cell the app drew, a part marked data-short="€6.0k" does the same (its date stays).
    function fitShort() {
      for (const td of body.querySelectorAll("td[data-short]")) {
        if (!td.dataset.short) continue;
        td.textContent = td.dataset.full;
        if (td.scrollWidth > td.clientWidth + 1) {
          td.textContent = td.dataset.short;
          if (!td.title) td.title = td.dataset.full;
        }
      }
      for (const part of body.querySelectorAll("td [data-short]")) {
        if (part.dataset.full === undefined) part.dataset.full = part.textContent;
        part.textContent = part.dataset.full;
        const td = part.closest("td");
        if (td && td.scrollWidth > td.clientWidth + 1) {
          part.textContent = part.dataset.short;
          if (!part.title) part.title = part.dataset.full;
        }
      }
    }
    const fits = new ResizeObserver(() => fitShort());
    fits.observe(scroller);

    // The rows drawn again keep their elements where their id stays, and only the cells that
    // changed are new: a press's click still lands where it was pressed, :hover and a flash go on.
    function place(next) {
      const kept = new Map();
      for (const tr of body.children) {
        const k = tr.classList.contains("ttb-row") ? `r:${tr.dataset.id}` : tr.classList.contains("ttb-group") ? `g:${tr.dataset.group}` : null;
        if (k) kept.set(k, tr);
      }
      const final = next.map(tr => {
        const k = tr.classList.contains("ttb-row") ? `r:${tr.dataset.id}` : tr.classList.contains("ttb-group") ? `g:${tr.dataset.group}` : null;
        const old = k ? kept.get(k) : null;
        if (!old) return tr;
        kept.delete(k);
        morph(old, tr);
        return old;
      });
      final.forEach((tr, i) => { if (body.children[i] !== tr) body.insertBefore(tr, body.children[i] ?? null); });
      while (body.children.length > final.length) body.lastElementChild.remove();
    }
    function morph(old, tr) {
      for (const a of [...old.attributes]) if (!tr.hasAttribute(a.name)) old.removeAttribute(a.name);
      for (const a of [...tr.attributes]) if (old.getAttribute(a.name) !== a.value) old.setAttribute(a.name, a.value);
      const n = Math.max(old.children.length, tr.children.length);
      for (let i = n - 1; i >= 0; i--) {
        const was = old.children[i];
        const now = tr.children[i];
        if (!now) was.remove();
        else if (!was) old.append(now);
        // A cell edited in place is always the new one (its field is the one being typed in).
        else if (now.classList.contains("ttb-editing") || was.classList.contains("ttb-editing") || was.outerHTML !== now.outerHTML) old.replaceChild(now, was);
      }
    }

    // ---------- selection ----------

    function paintSelection() {
      for (const tr of body.rows) {
        if (tr.classList.contains("ttb-row")) {
          tr.setAttribute("aria-selected", String(picked.has(tr.dataset.id)));
          tr.classList.toggle("ttb-focus", tr.dataset.id === sel && selGroup == null);
        } else if (tr.classList.contains("ttb-group") && groupsSelectable()) {
          tr.setAttribute("aria-selected", String(selGroup === tr.dataset.group));
        }
      }
      const active = selGroup != null ? groupId(selGroup) : sel != null ? rowId(sel) : null;
      if (active) scroller.setAttribute("aria-activedescendant", active);
      else scroller.removeAttribute("aria-activedescendant");
    }
    function tellSelect(how) {
      call(opt.onSelect, current(), { how, rows: pickedRows() });
    }
    // One row selected (and the focus there).
    function select(key, how = "api", scroll = true) {
      const next = key == null ? null : keyOf(key);
      if (next != null && !byId.has(next)) return;
      const changed = next !== sel || picked.size !== (next == null ? 0 : 1) || selGroup != null;
      sel = next;
      selGroup = null;
      picked.clear();
      if (next != null) picked.add(next);
      anchor = next;
      paintSelection();
      if (scroll && sel != null) reveal(rowId(sel));
      if (changed && how !== "api") tellSelect(how);
    }
    function selectGroup(key, how) {
      selGroup = key;
      sel = null;
      picked.clear();
      paintSelection();
      reveal(groupId(key));
      if (how !== "api") tellSelect(how);
    }
    // From the anchor to `key` (Shift), or one more or less (⌘), with `multiple`.
    function extend(key, how) {
      const ids = shown.map(r => keyOf(r.id));
      const a = ids.indexOf(anchor ?? sel ?? key);
      const b = ids.indexOf(key);
      if (a < 0 || b < 0) return select(key, how);
      picked.clear();
      for (const k of ids.slice(Math.min(a, b), Math.max(a, b) + 1)) picked.add(k);
      sel = key;
      selGroup = null;
      paintSelection();
      reveal(rowId(key));
      tellSelect(how);
      return undefined;
    }
    function toggleOne(key, how) {
      if (picked.has(key)) picked.delete(key);
      else picked.add(key);
      sel = key;
      anchor = key;
      selGroup = null;
      paintSelection();
      tellSelect(how);
    }
    // Into view, under the header that stays.
    function reveal(elId) {
      const tr = document.getElementById(elId);
      if (!tr || !body.contains(tr)) return;
      const headH = head.getBoundingClientRect().height;
      const top = tr.offsetTop;
      if (top - headH < scroller.scrollTop) scroller.scrollTop = Math.max(0, top - headH);
      else if (top + tr.offsetHeight > scroller.scrollTop + scroller.clientHeight) scroller.scrollTop = top + tr.offsetHeight - scroller.clientHeight;
    }

    function setSort(next, byPerson) {
      sort = next && next.key != null ? { key: next.key, up: next.up !== false } : null;
      keep();
      drawHead();
      draw();
      if (sel != null) reveal(rowId(sel));
      if (byPerson) call(opt.onSort, sort ? { ...sort } : null);
    }

    function setGroupOpen(key, open, how) {
      const g = groupById(key);
      if (!g || !collapsible() || isOpen(g) === open) return;
      if (open) closed.delete(key);
      else closed.add(key);
      keep();
      // A row with the focus inside a group that closes: the group takes it.
      if (!open && sel != null && keyOf(byId.get(sel)?.group) === key) {
        sel = null;
        picked.clear();
        selGroup = key;
      }
      draw();
      call(opt.onGroupToggle, g, open, { how });
    }

    // ---------- the checkbox column, editing in place ----------

    function toggleCheck(row, c, how) {
      const r = byId.get(keyOf(row.id)) ?? row;
      const now = Boolean(typeof c.value === "function" ? call(c.value, r) : r[c.key]);
      const may = typeof c.canToggle === "function" ? call(c.canToggle, r) : true;
      if (may !== true && may !== undefined) {
        message(typeof may === "string" ? may : "", "error");
        return;
      }
      call(c.onToggle, r, !now, { how });
    }

    const editColumn = () => columns().findIndex(c => c.edit && !c.actions && !c.check);
    function beginEdit(key, ci = editColumn()) {
      const row = byId.get(keyOf(key));
      const c = columns()[ci];
      if (!row || !c || !c.edit || typeof opt.onEdit !== "function") return false;
      editing = { key: keyOf(key), ci, draft: textOf(row, c) };
      draw();
      editing?.input?.focus({ preventScroll: true });
      editing?.input?.select();
      return true;
    }
    function cancelEdit() {
      editing = null;
      draw();
      scroller.focus({ preventScroll: true });
    }
    async function commitEdit(blurred = false) {
      const ed = editing;
      if (!ed || ed.saving) return;
      const row = byId.get(ed.key);
      const c = columns()[ed.ci];
      if (!row || !c) return cancelEdit();
      if (ed.draft === textOf(row, c)) {
        editing = null;
        draw();
        if (!blurred) scroller.focus({ preventScroll: true });
        return;
      }
      ed.saving = true;
      let refused = null;
      try {
        const answer = await opt.onEdit(row, c.key, ed.draft);
        if (answer === false) refused = "";
        else if (typeof answer === "string") refused = answer;
      } catch (e) {
        refused = String(e?.message ?? e ?? "");
      }
      ed.saving = false;
      if (editing !== ed || signal.aborted) return;
      if (refused !== null) {
        // Refused: the field stays, with what was typed, and the keys there.
        if (refused) message(refused, "error");
        editing.input?.focus({ preventScroll: true });
        return;
      }
      editing = null;
      draw();
      if (!blurred) scroller.focus({ preventScroll: true });
    }

    async function copyRows() {
      const list = opt.multiple ? pickedRows() : current() ? [current()] : [];
      if (!list.length) return;
      const cs = columns().filter(c => !c.actions && (c.key != null || typeof c.text === "function"));
      const text = list.map(r => cs.map(c => (c.check ? String(Boolean(r[c.key])) : textOf(r, c)).replace(/[\t\n]/g, " ")).join("\t")).join("\n");
      const wrote = navigator.clipboard?.writeText ? await navigator.clipboard.writeText(text).then(() => true, () => false) : false;
      message(wrote ? say(L().copiedRows, list.length) : say(L().copyFailed), wrote ? "ok" : "error");
    }

    // ---------- the mouse ----------

    const rowOf = t => (t instanceof Element ? t.closest("tr.ttb-row") : null);
    const groupOf = t => (t instanceof Element ? t.closest("tr.ttb-group") : null);
    let wasSelected = null; // a press on the row that was already the selected one (a slow second click edits)
    let editTimer = 0;

    scroller.addEventListener("mousedown", e => {
      if (e.button !== 0 && e.button !== 2) return;
      if (e.target instanceof Element && e.target.closest("thead, .ttb-edit")) return;
      clearTimeout(editTimer);
      const tr = rowOf(e.target);
      const g = groupOf(e.target);
      wasSelected = tr && tr.dataset.id === sel && picked.size === 1 && e.detail === 1 ? sel : null;
      // A shift-click or a double click selects, never text.
      if (tr && (e.shiftKey || e.detail > 1)) e.preventDefault();
      if (tr) {
        const key = tr.dataset.id;
        if (e.button === 0 && opt.multiple && cmd(e)) toggleOne(key, "mouse");
        else if (e.button === 0 && opt.multiple && e.shiftKey) extend(key, "mouse");
        // ⌘-click without `multiple`: opens the other way (its click), the selection staying where it was.
        else if (e.button === 0 && !opt.multiple && cmd(e)) e.preventDefault();
        else if (!(e.button === 2 && picked.has(key))) select(key, "mouse", false);
      } else if (g && groupsSelectable()) {
        if (!(e.target instanceof Element && e.target.closest(".ttb-ib"))) e.preventDefault();
        selectGroup(g.dataset.group, "mouse");
        if (e.button === 0 && collapsible() && e.target instanceof Element && e.target.closest(".ttb-box")) {
          const k = g.dataset.group;
          setGroupOpen(k, !isOpen(groupById(k)), "mouse");
        }
      } else if (!g) {
        select(null, "mouse", false);
      }
      // A click on the row's own buttons keeps the keys on the table.
      if (e.target instanceof Element && e.target.closest(".ttb-ib, .ttb-check")) e.preventDefault();
      if (document.activeElement !== scroller && !(editing?.input && document.activeElement === editing.input)) scroller.focus({ preventScroll: true });
    }, { signal });

    scroller.addEventListener("click", e => {
      const tr = rowOf(e.target);
      if (!tr || e.button !== 0) return;
      // ⌘-click (Ctrl-click): the app's other way to open, when rows are picked one at a time.
      if (!opt.multiple && cmd(e) && !e.shiftKey) {
        const r = byId.get(tr.dataset.id);
        if (r) call(opt.onOpen, r, { how: "mouse", cmd: true });
        return;
      }
      // A click on the selected row's editable cell, then a pause: edit it (as Finder renames).
      const cell = e.target instanceof Element ? e.target.closest("td.ttb-editable") : null;
      if (cell && wasSelected === tr.dataset.id && e.detail === 1 && plain(e)) {
        const key = tr.dataset.id;
        const ci = Number(cell.dataset.col);
        editTimer = setTimeout(() => { if (sel === key && !editing) beginEdit(key, ci); }, 500);
      }
    }, { signal });

    scroller.addEventListener("dblclick", e => {
      clearTimeout(editTimer);
      if (e.target instanceof Element && e.target.closest(".ttb-edit, .ttb-check")) return;
      const tr = rowOf(e.target);
      if (tr) {
        const r = byId.get(tr.dataset.id);
        if (r) call(opt.onOpen, r, { how: "mouse", cmd: cmd(e) });
        return;
      }
      const g = groupOf(e.target);
      if (g && !(e.target instanceof Element && e.target.closest(".ttb-box"))) {
        const group = groupById(g.dataset.group);
        if (group) call(opt.onGroupOpen, group, { how: "mouse", cmd: cmd(e) });
      }
    }, { signal });

    scroller.addEventListener("contextmenu", e => {
      if (e.target instanceof Element && e.target.closest("thead, .ttb-edit")) return;
      const g = groupOf(e.target);
      if (g) {
        const group = groupById(g.dataset.group);
        if (group && typeof opt.onGroupContextMenu === "function") {
          e.preventDefault();
          call(opt.onGroupContextMenu, group, { x: e.clientX, y: e.clientY, how: "mouse" });
        }
        return;
      }
      if (typeof opt.onContextMenu !== "function") return;
      e.preventDefault();
      const tr = rowOf(e.target);
      if (tr && !picked.has(tr.dataset.id)) select(tr.dataset.id, "mouse", false);
      call(opt.onContextMenu, tr ? byId.get(tr.dataset.id) ?? null : null, { x: e.clientX, y: e.clientY, how: "mouse" });
    }, { signal });

    // ---------- the keys ----------

    function pageStep() {
      const first = body.querySelector("tr.ttb-row");
      const h = first ? first.getBoundingClientRect().height : 25;
      return Math.max(1, Math.floor((scroller.clientHeight - head.getBoundingClientRect().height) / h) - 1);
    }
    const itemIndex = () => items.findIndex(it => (it.group ? selGroup === keyOf(it.group.id) : selGroup == null && keyOf(it.row.id) === sel));
    function goItem(j, how, extending) {
      if (!items.length) return;
      const it = items[Math.max(0, Math.min(items.length - 1, j))];
      if (it.group) return selectGroup(keyOf(it.group.id), how);
      if (extending && opt.multiple) return extend(keyOf(it.row.id), how);
      return select(keyOf(it.row.id), how);
    }

    // A rename waiting for its pause ends with any key, a scroll, or the window losing focus (as in Finder).
    const noRename = () => clearTimeout(editTimer);
    scroller.addEventListener("scroll", noRename, { signal, passive: true });
    window.addEventListener("blur", noRename, { signal });

    scroller.addEventListener("keydown", e => {
      noRename();
      if (e.target !== scroller || e.isComposing) return;
      const row = current();
      const group = selGroup != null ? groupById(selGroup) : null;
      if (call(opt.onKey, e, row, group) === true) {
        e.preventDefault();
        return;
      }
      const i = itemIndex();
      const go = (j, extending = false) => {
        e.preventDefault();
        goItem(j, "keyboard", extending);
      };
      if ((e.key === "ArrowDown" || e.key === "ArrowUp") && !e.altKey) {
        if (cmd(e) && !e.shiftKey) return go(e.key === "ArrowUp" ? 0 : items.length - 1);
        if (e.metaKey || e.ctrlKey) return undefined;
        return go(i < 0 ? (e.key === "ArrowDown" ? 0 : items.length - 1) : i + (e.key === "ArrowDown" ? 1 : -1), e.shiftKey);
      }
      if ((e.key === "Home" || e.key === "End") && !e.altKey && !e.metaKey && !e.ctrlKey) return go(e.key === "Home" ? 0 : items.length - 1, e.shiftKey);
      if ((e.key === "PageDown" || e.key === "PageUp") && plain(e)) {
        const step = pageStep() * (e.key === "PageDown" ? 1 : -1);
        return go(i < 0 ? (step > 0 ? 0 : items.length - 1) : i + step);
      }
      // Groups: ← closes (on a row, goes to its group), → opens (then into it).
      if (collapsible() && (e.key === "ArrowLeft" || e.key === "ArrowRight") && plain(e)) {
        e.preventDefault();
        if (group) {
          const k = keyOf(group.id);
          if (e.key === "ArrowLeft") setGroupOpen(k, false, "keyboard");
          else if (!isOpen(group)) setGroupOpen(k, true, "keyboard");
          else goItem(i + 1, "keyboard");
        } else if (row && e.key === "ArrowLeft" && row.group != null && groupById(keyOf(row.group))) {
          selectGroup(keyOf(row.group), "keyboard");
        }
        return undefined;
      }
      if ((e.key === "Enter" || e.key === " ") && group && plain(e)) {
        e.preventDefault();
        if (e.repeat) return undefined;
        if (collapsible()) setGroupOpen(keyOf(group.id), !isOpen(group), "keyboard");
        else if (e.key === "Enter") call(opt.onGroupOpen, group, { how: "keyboard", cmd: false });
        return undefined;
      }
      if (e.key === "Enter" && !e.altKey && !e.shiftKey) {
        if (!row) return undefined;
        e.preventDefault();
        call(opt.onOpen, row, { how: "keyboard", cmd: cmd(e) });
        return undefined;
      }
      if (e.key === "F2" && plain(e) && row) {
        if (beginEdit(keyOf(row.id))) e.preventDefault();
        return undefined;
      }
      if (e.key === " " && plain(e) && row) {
        const c = columns().find(x => x.check);
        if (c && typed === "") {
          e.preventDefault();
          if (!e.repeat) toggleCheck(row, c, "keyboard");
          return undefined;
        }
      }
      if (cmd(e) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "a" && opt.multiple) {
        e.preventDefault();
        picked.clear();
        for (const r of shown) picked.add(keyOf(r.id));
        if (sel == null && shown[0]) sel = keyOf(shown[0].id);
        selGroup = null;
        paintSelection();
        tellSelect("keyboard");
        return undefined;
      }
      if (cmd(e) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "c" && opt.copy) {
        e.preventDefault();
        copyRows();
        return undefined;
      }
      if (e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey)) {
        e.preventDefault();
        const at = document.getElementById(selGroup != null ? groupId(selGroup) : sel != null ? rowId(sel) : "") ?? head;
        const box = at.getBoundingClientRect();
        const where = { x: box.left + 12, y: box.bottom, how: "keyboard" };
        if (group) call(opt.onGroupContextMenu, group, where);
        else call(opt.onContextMenu, row, where);
        return undefined;
      }
      // Typing: the next row whose name starts with what was typed.
      if (e.key.length !== 1 || e.metaKey || e.ctrlKey || e.altKey) {
        if (e.key.length !== 1 && !["Shift", "CapsLock", "Dead", "AltGraph", "Compose", "Process", "Unidentified"].includes(e.key)) typed = "";
        return undefined;
      }
      const now = keyTime(e);
      const going = typed !== "" && now - typedAt < opt.typeAheadMs;
      if (e.key === " " && !going) return undefined;
      e.preventDefault();
      typed = (going ? typed : "") + e.key.toLowerCase();
      typedAt = now;
      const col = typeColumn();
      const same = [...typed].every(ch => ch === typed[0]);
      const at = sel != null ? shown.findIndex(r => keyOf(r.id) === sel) : -1;
      // A whole name typed is looked for from the top; one letter again and again steps on.
      const from = typed.length > 1 && !same ? 0 : at + 1;
      const order = shown.slice(from).concat(shown.slice(0, from));
      const hit = order.find(r => fold(textOf(r, col)).startsWith(fold(same ? typed[0] : typed)));
      if (hit) select(keyOf(hit.id), "keyboard");
      else if (shown.length) message(say(L().noneStarts, typed), "error");
      return undefined;
    }, { signal });
    // The typing ends a moment after the last key (Space ticks again).
    scroller.addEventListener("keyup", () => {
      clearTimeout(typedTimer);
      typedTimer = setTimeout(() => { typed = ""; }, opt.typeAheadMs);
    }, { signal });

    // ---------- start ----------

    rows = Array.isArray(opt.rows) ? opt.rows.slice() : [];
    drawHead();
    draw();

    return {
      /** Replaces the rows (the app's list is the truth); the selection, the scroll and an edit stay. */
      setRows(next) {
        rows = Array.isArray(next) ? next.slice() : [];
        draw();
      },
      /** The rows as the table has them, in the app's order. */
      rows() {
        return rows.slice();
      },
      /** The rows in the order they show (sorted, in groups, closed groups' left out). */
      shown() {
        return shown.slice();
      },
      /** Changes options: columns, rows, groups, sort, selected, state, labels, the on… functions. */
      update(changes = {}) {
        changes = given(changes);
        Object.assign(opt, changes);
        if ("rows" in changes) rows = Array.isArray(changes.rows) ? changes.rows.slice() : [];
        if ("sort" in changes) {
          sort = changes.sort && changes.sort.key != null ? { key: changes.sort.key, up: changes.sort.up !== false } : null;
          keep();
        }
        drawHead();
        draw();
        if ("selected" in changes) select(changes.selected, "api");
      },
      /** Selects a row by id (null: none), and brings it into view; an array selects several (multiple). */
      select(key) {
        if (Array.isArray(key) && opt.multiple) {
          picked.clear();
          for (const k of key) if (byId.has(keyOf(k))) picked.add(keyOf(k));
          sel = key.length ? keyOf(key[0]) : null;
          selGroup = null;
          anchor = sel;
          paintSelection();
          if (sel != null) reveal(rowId(sel));
          return;
        }
        select(Array.isArray(key) ? key[0] ?? null : key, "api");
      },
      /** The selected row with the focus, or null. */
      selected() {
        return current();
      },
      /** Every selected row, as they show. */
      selection() {
        return pickedRows();
      },
      /** The selected group (collapsible groups), or null. */
      selectedGroup() {
        return selGroup != null ? groupById(selGroup) : null;
      },
      /** Opens or closes a group; onGroupToggle is not called. */
      expand(groupKey) {
        const k = keyOf(groupKey);
        if (!closed.delete(k)) return;
        keep();
        draw();
      },
      collapse(groupKey) {
        const k = keyOf(groupKey);
        if (closed.has(k)) return;
        closed.add(k);
        keep();
        draw();
      },
      isExpanded(groupKey) {
        return !closed.has(keyOf(groupKey));
      },
      /** Edits a row's cell in place (its first column with edit: true, or `key`'s). */
      edit(rowKey, colKey) {
        const ci = colKey == null ? editColumn() : columns().findIndex(c => c.key === colKey);
        return beginEdit(rowKey, ci);
      },
      /** The column sorted, or null. */
      get sort() {
        return sort ? { ...sort } : null;
      },
      /** The columns' widths dragged to (null: as given). */
      widths() {
        return columns().map((_, i) => widths.get(i) ?? null);
      },
      /** A row just added: selected, in view, and flashed so the eye finds it. */
      flash(key) {
        const k = keyOf(key);
        if (!byId.has(k)) return;
        clearTimeout(flashing.get(k));
        flashing.set(k, setTimeout(() => {
          flashing.delete(k);
          document.getElementById(rowId(k))?.classList.remove("ttb-flash");
        }, 1400));
        select(k, "api");
        const tr = document.getElementById(rowId(k));
        if (tr) {
          tr.classList.remove("ttb-flash");
          void tr.offsetWidth;
          tr.classList.add("ttb-flash");
        }
      },
      /** The keys go to the table. */
      focus() {
        scroller.focus({ preventScroll: true });
      },
      /** The element that scrolls the rows (for TaurisReorder.attach). */
      get scroller() {
        return scroller;
      },
      /** Removes it. */
      destroy() {
        life.abort();
        fits.disconnect();
        clearTimeout(editTimer);
        clearTimeout(typedTimer);
        for (const t of flashing.values()) clearTimeout(t);
        for (const t of copiedAt.values()) clearTimeout(t);
        root.replaceChildren();
        if (addedClass) root.classList.remove("ttb", "ttb-resizing");
        delete root.__taurisTable;
      },
    };
  }

  window.TaurisTable = { mount };
})();
