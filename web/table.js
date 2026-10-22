// tauris-ui table: a dense data table, as in a desktop app: 25px rows under a
// header that stays, columns sorted ▲▼ by a click on their header, rows in
// groups (a colour square, a name and a count), one row selected and moved
// with the keys, typing a name to jump to it, a row's own buttons, and a
// flash for a row just added. Plain JavaScript: no build step, no
// dependencies. In a Tauri app the plugin injects this file with its
// stylesheet (web/table.css), added the first time a page uses it.
//
//   const table = TaurisTable.mount(document.querySelector("#tasks"), {
//     columns: [
//       { key: "name", label: "Task" },
//       { key: "due", label: "Due", width: 90, align: "right", value: t => t.dueDate },
//       { key: "state", label: "Status", width: 110, render: t => TaurisGlance.status(t.kind, t.word) },
//       { actions: [{ id: "edit", icon: "✎", title: "Edit", onClick: t => edit(t) }] },
//     ],
//     rows: tasks,                                  // each { id, group?, ... }
//     groups: projects.map(p => ({ id: p.id, label: p.name, color: p.color })),
//     onOpen: t => edit(t),                         // Enter, a double click
//     onContextMenu: (t, at) => TaurisMenu.open(menuFor(t), at),
//   });
//
// The app owns its rows: setRows() with new ones draws them again (the
// selection and the scroll stay). Keys, on the table: ↑ ↓ move, Home End and
// ⌘↑ ⌘↓ go to the first and last, Page Up and Down by a page, Enter opens,
// the menu key or ⇧F10 opens the row's menu, a letter jumps to the next row
// whose name starts with what was typed. `onKey` takes the others (Space, F2,
// Delete) first. Drag to reorder: TaurisReorder.attach(table.scroller, …).

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
    // the clipboard refused
    copyFailed: "Could not copy.",
    // a group with no rows
    emptyGroup: "Nothing here.",
    // the table with no rows at all
    empty: "Nothing yet.",
    // a group's count, after its name: (rows) => text
    count: n => String(n),
  };

  const DEFAULTS = {
    // [{ key, label, width?, align?, render?, value?, compare?, sortable?, title?, className?, actions? }]
    columns: [],
    // [{ id, group?, ...fields }]: the rows, in the order the app keeps them
    rows: [],
    // [{ id, label, color?, detail? }]: rows with that `group` go under it, in this order
    groups: null,
    // { key, up }: the column sorted, or null for the rows in the order given
    sort: null,
    // false: no header sorts
    sortable: true,
    selected: null,
    // the column whose text typing matches (default the first)
    typeKey: null,
    // how long after a key the next one still adds to the name being typed
    typeAheadMs: 700,
    // the table's name, for a screen reader
    label: "",
    labels: {},
    // false: the page brings its own stylesheet
    styles: true,
    // (row | null, { how }): the selection changed
    onSelect: null,
    // (row, { how, cmd }): Enter or a double click
    onOpen: null,
    // (row | null, { x, y, how }): a right click or the menu key; null on the empty space
    onContextMenu: null,
    // ({ key, up } | null): a header was clicked
    onSort: null,
    // (event, row | null) => true when the app took the key (Space, F2, Delete)
    onKey: null,
    // (group, { how, cmd }): a double click on a group's row
    onGroupOpen: null,
    // (group, { x, y, how }): a right click on a group's row
    onGroupContextMenu: null,
    // (text, kind): what the table has to say ("Nothing starts with “q”.")
    onMessage: null,
  };

  let uid = 0;
  const say = (label, ...args) => (typeof label === "function" ? label(...args) : String(label ?? ""));
  const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
  const fold = text => String(text ?? "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
  const keyTime = e => e.timeStamp || performance.now();
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
    let byId = new Map();
    let sel = opt.selected == null ? null : String(opt.selected);
    let sort = opt.sort && opt.sort.key != null ? { key: opt.sort.key, up: opt.sort.up !== false } : null;
    let typed = "";
    let typedAt = 0;
    const flashing = new Map(); // id -> timer
    const copiedAt = new Map(); // "row|action" -> timer

    const keyOf = v => String(v);
    const columns = () => (Array.isArray(opt.columns) ? opt.columns : []);
    const textOf = (row, col) => {
      if (!col) return "";
      if (typeof col.text === "function") return String(call(col.text, row) ?? "");
      const v = col.key != null ? row[col.key] : "";
      return v == null ? "" : String(v);
    };
    const typeColumn = () => columns().find(c => c.key === opt.typeKey) ?? columns().find(c => !c.actions) ?? null;
    const rowId = key => `${id}-r-${String(key).replace(/[^\w-]/g, ch => `_${ch.codePointAt(0)}`)}`;
    const current = () => (sel != null ? byId.get(sel) ?? null : null);

    function compare(col) {
      if (typeof col.compare === "function") return (a, b) => call(col.compare, a, b) ?? 0;
      const value = row => (typeof col.value === "function" ? call(col.value, row) : col.key != null ? row[col.key] : null);
      return (a, b) => {
        const x = value(a);
        const y = value(b);
        if (x == null || x === "") return y == null || y === "" ? 0 : 1;
        if (y == null || y === "") return -1;
        if (typeof x === "number" && typeof y === "number") return x - y;
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

    // ---------- drawing ----------

    function drawHead() {
      cols.replaceChildren(...columns().map(c => {
        const col = el("col", c.actions ? "ttb-col-acts" : "");
        if (c.width != null) col.style.width = typeof c.width === "number" ? `${c.width}px` : String(c.width);
        else if (c.actions) col.style.width = `${Math.max(1, c.actions.length) * 24 + 8}px`;
        return col;
      }));
      headRow.replaceChildren(...columns().map(c => {
        const th = el("th", `ttb-th${c.align ? ` ttb-${c.align}` : ""}`, { role: "columnheader", scope: "col" });
        if (c.actions) {
          th.setAttribute("aria-label", c.label ?? "");
          return th;
        }
        const on = sort && sort.key === c.key;
        const sortable = opt.sortable && c.sortable !== false && c.key != null;
        th.setAttribute("aria-sort", on ? (sort.up ? "ascending" : "descending") : "none");
        if (!sortable) {
          th.textContent = String(c.label ?? "");
          th.removeAttribute("aria-sort");
          return th;
        }
        const btn = el("button", "ttb-sort", { type: "button", tabindex: "-1" });
        btn.append(el("span", "ttb-th-label", {}, c.label ?? ""));
        if (on) btn.append(el("span", "ttb-arrow", { "aria-hidden": "true" }, sort.up ? "▲" : "▼"));
        btn.addEventListener("click", () => setSort(on ? { key: c.key, up: !sort.up } : { key: c.key, up: true }, true));
        th.append(btn);
        return th;
      }));
    }

    function cellFor(row, c) {
      const td = el("td", `ttb-cell${c.align ? ` ttb-${c.align}` : ""}${c.className ? ` ${c.className}` : ""}`, { role: "gridcell" });
      if (c.actions) {
        td.classList.add("ttb-acts");
        for (const a of c.actions) td.append(actionButton(row, a));
        return td;
      }
      const out = typeof c.render === "function" ? call(c.render, row, td) : textOf(row, c);
      if (out instanceof Node) td.append(out);
      else if (out != null && out !== td) td.textContent = String(out);
      const tip = typeof c.title === "function" ? call(c.title, row) : c.title === true ? td.textContent : null;
      if (tip) td.title = String(tip);
      return td;
    }

    function actionButton(row, a) {
      const key = `${keyOf(row.id)}|${a.id ?? a.title}`;
      const pressed = typeof a.pressed === "function" ? Boolean(call(a.pressed, row)) : null;
      const label = String(a.title ?? "");
      const name = textOf(row, typeColumn());
      const btn = el("button", "ttb-ib", { type: "button", tabindex: "-1", title: label, "aria-label": name ? `${label}: ${name}` : label });
      if (a.id != null) btn.dataset.act = String(a.id);
      if (pressed !== null) btn.setAttribute("aria-pressed", String(pressed));
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
        if (typeof a.copy === "function") {
          const text = String(call(a.copy, r) ?? "");
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
        call(a.onClick, r, { how: e.detail === 0 ? "keyboard" : "mouse" });
      }, { signal });
      btn.addEventListener("dblclick", e => e.stopPropagation(), { signal });
      return btn;
    }

    function rowFor(row) {
      const key = keyOf(row.id);
      const tr = el("tr", "ttb-row", { role: "row", id: rowId(key), "aria-selected": String(key === sel) });
      tr.dataset.id = key;
      if (row.group != null) tr.dataset.group = keyOf(row.group);
      if (flashing.has(key)) tr.classList.add("ttb-flash");
      if (row.dim) tr.classList.add("ttb-dim");
      for (const c of columns()) tr.append(cellFor(row, c));
      return tr;
    }

    function groupRow(part) {
      const g = part.group;
      const tr = el("tr", "ttb-group", { role: "row" });
      tr.dataset.group = keyOf(g.id);
      const td = el("td", "", { role: "gridcell", colspan: String(Math.max(1, columns().length)) });
      const chip = el("span", "ttb-chip", { "aria-hidden": "true" });
      if (g.color) tr.style.setProperty("--ttb-c", String(g.color));
      const name = el("span", "ttb-group-label", {}, g.label ?? "");
      const detail = el("span", "ttb-group-detail", {}, g.detail != null ? g.detail : say(L().count, part.rows.length));
      td.append(chip, name, detail);
      tr.append(td);
      return tr;
    }

    function draw() {
      const top = scroller.scrollTop;
      const { list, parts } = arrange();
      shown = list;
      byId = new Map(rows.map(r => [keyOf(r.id), r]));
      if (sel != null && !byId.has(sel)) sel = null;
      const out = [];
      if (parts) {
        for (const part of parts) {
          if (part.group) out.push(groupRow(part));
          if (!part.rows.length && part.group) {
            const none = el("tr", "ttb-none", { role: "row" });
            none.append(el("td", "", { role: "gridcell", colspan: String(Math.max(1, columns().length)) }, part.group.empty ?? say(L().emptyGroup)));
            out.push(none);
          }
          for (const r of part.rows) out.push(rowFor(r));
        }
      } else {
        for (const r of list) out.push(rowFor(r));
      }
      body.replaceChildren(...out);
      empty.hidden = rows.length > 0;
      empty.textContent = say(L().empty);
      scroller.setAttribute("aria-label", String(opt.label ?? ""));
      scroller.setAttribute("aria-rowcount", String(shown.length + 1));
      if (sel != null) scroller.setAttribute("aria-activedescendant", rowId(sel));
      else scroller.removeAttribute("aria-activedescendant");
      scroller.scrollTop = top;
    }

    // ---------- selection ----------

    function select(key, how = "api", scroll = true) {
      const next = key == null ? null : keyOf(key);
      if (next != null && !byId.has(next)) return;
      const changed = next !== sel;
      sel = next;
      for (const tr of body.rows) if (tr.classList.contains("ttb-row")) tr.setAttribute("aria-selected", String(tr.dataset.id === sel));
      if (sel != null) scroller.setAttribute("aria-activedescendant", rowId(sel));
      else scroller.removeAttribute("aria-activedescendant");
      if (scroll && sel != null) reveal(sel);
      if (changed && how !== "api") call(opt.onSelect, current(), { how });
    }
    // Into view, under the header that stays.
    function reveal(key) {
      const tr = body.querySelector(`tr[data-id="${CSS_ESCAPE(key)}"]`);
      if (!tr) return;
      const headH = head.getBoundingClientRect().height;
      const top = tr.offsetTop;
      if (top - headH < scroller.scrollTop) scroller.scrollTop = Math.max(0, top - headH);
      else if (top + tr.offsetHeight > scroller.scrollTop + scroller.clientHeight) scroller.scrollTop = top + tr.offsetHeight - scroller.clientHeight;
    }
    const CSS_ESCAPE = v => (window.CSS?.escape ? window.CSS.escape(v) : String(v).replace(/["\\]/g, "\\$&"));

    function setSort(next, byPerson) {
      sort = next && next.key != null ? { key: next.key, up: next.up !== false } : null;
      drawHead();
      draw();
      if (sel != null) reveal(sel);
      if (byPerson) call(opt.onSort, sort ? { ...sort } : null);
    }

    // ---------- the mouse ----------

    const rowOf = t => (t instanceof Element ? t.closest("tr.ttb-row") : null);
    const groupOf = t => (t instanceof Element ? t.closest("tr.ttb-group") : null);
    const groupById = key => (Array.isArray(opt.groups) ? opt.groups.find(g => keyOf(g.id) === key) ?? null : null);

    scroller.addEventListener("mousedown", e => {
      if (e.button !== 0 && e.button !== 2) return;
      const tr = rowOf(e.target);
      if (e.target instanceof Element && e.target.closest("thead")) return;
      // A shift-click or a double click selects the row, never text.
      if (tr && (e.shiftKey || e.detail > 1)) e.preventDefault();
      if (tr) select(tr.dataset.id, "mouse", false);
      else if (!groupOf(e.target)) select(null, "mouse", false);
      // A click on the row's own buttons keeps the keys on the table.
      if (e.target instanceof Element && e.target.closest(".ttb-ib")) e.preventDefault();
      if (document.activeElement !== scroller) scroller.focus({ preventScroll: true });
    }, { signal });

    scroller.addEventListener("dblclick", e => {
      const tr = rowOf(e.target);
      if (tr) {
        const r = byId.get(tr.dataset.id);
        if (r) call(opt.onOpen, r, { how: "mouse", cmd: cmd(e) });
        return;
      }
      const g = groupOf(e.target);
      if (g) {
        const group = groupById(g.dataset.group);
        if (group) call(opt.onGroupOpen, group, { how: "mouse", cmd: cmd(e) });
      }
    }, { signal });

    scroller.addEventListener("contextmenu", e => {
      if (e.target instanceof Element && e.target.closest("thead")) return;
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
      if (tr) select(tr.dataset.id, "mouse", false);
      call(opt.onContextMenu, tr ? byId.get(tr.dataset.id) ?? null : null, { x: e.clientX, y: e.clientY, how: "mouse" });
    }, { signal });

    // ---------- the keys ----------

    const selectable = () => shown.map(r => keyOf(r.id));
    function pageStep() {
      const first = body.querySelector("tr.ttb-row");
      const h = first ? first.getBoundingClientRect().height : 25;
      return Math.max(1, Math.floor((scroller.clientHeight - head.getBoundingClientRect().height) / h) - 1);
    }

    scroller.addEventListener("keydown", e => {
      if (e.target !== scroller || e.isComposing) return;
      const row = current();
      if (call(opt.onKey, e, row) === true) {
        e.preventDefault();
        return;
      }
      const ids = selectable();
      const i = sel != null ? ids.indexOf(sel) : -1;
      const go = (j, how = "keyboard") => {
        if (!ids.length) return;
        e.preventDefault();
        select(ids[Math.max(0, Math.min(ids.length - 1, j))], how);
      };
      // (⌥⌘↑ ⌥⌘↓ are a reorder's: left to it.)
      if ((e.key === "ArrowDown" || e.key === "ArrowUp") && !e.altKey && !e.shiftKey) {
        if (cmd(e)) return go(e.key === "ArrowUp" ? 0 : ids.length - 1);
        if (e.metaKey || e.ctrlKey) return undefined;
        return go(i < 0 ? (e.key === "ArrowDown" ? 0 : ids.length - 1) : i + (e.key === "ArrowDown" ? 1 : -1));
      }
      if ((e.key === "Home" || e.key === "End") && plain(e)) return go(e.key === "Home" ? 0 : ids.length - 1);
      if ((e.key === "PageDown" || e.key === "PageUp") && plain(e)) {
        const step = pageStep() * (e.key === "PageDown" ? 1 : -1);
        return go(i < 0 ? (step > 0 ? 0 : ids.length - 1) : i + step);
      }
      if (e.key === "Enter" && !e.altKey && !e.shiftKey) {
        if (!row) return undefined;
        e.preventDefault();
        call(opt.onOpen, row, { how: "keyboard", cmd: cmd(e) });
        return undefined;
      }
      if (e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey)) {
        if (typeof opt.onContextMenu !== "function") return undefined;
        e.preventDefault();
        const tr = sel != null ? body.querySelector(`tr[data-id="${CSS_ESCAPE(sel)}"]`) : null;
        const box = (tr ?? head).getBoundingClientRect();
        call(opt.onContextMenu, row, { x: box.left + 12, y: box.bottom, how: "keyboard" });
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
      const same = [...typed].every(c => c === typed[0]);
      // A whole name typed is looked for from the top; one letter again and again steps on.
      const from = typed.length > 1 && !same ? 0 : i + 1;
      const order = shown.slice(from).concat(shown.slice(0, from));
      const hit = order.find(r => fold(textOf(r, col)).startsWith(fold(same ? typed[0] : typed)));
      if (hit) select(keyOf(hit.id), "keyboard");
      else if (shown.length) message(say(L().noneStarts, typed), "error");
      return undefined;
    }, { signal });

    // ---------- start ----------

    rows = Array.isArray(opt.rows) ? opt.rows.slice() : [];
    drawHead();
    draw();

    return {
      /** Replaces the rows (the app's list is the truth); the selection and the scroll stay. */
      setRows(next) {
        rows = Array.isArray(next) ? next.slice() : [];
        draw();
      },
      /** The rows as the table has them, in the app's order. */
      rows() {
        return rows.slice();
      },
      /** The rows in the order they show (sorted, in groups). */
      shown() {
        return shown.slice();
      },
      /** Changes options: columns, rows, groups, sort, selected, labels, label, typeKey, the on… functions. */
      update(changes = {}) {
        changes = given(changes);
        Object.assign(opt, changes);
        if ("rows" in changes) rows = Array.isArray(changes.rows) ? changes.rows.slice() : [];
        if ("sort" in changes) sort = changes.sort && changes.sort.key != null ? { key: changes.sort.key, up: changes.sort.up !== false } : null;
        drawHead();
        draw();
        if ("selected" in changes) select(changes.selected, "api");
      },
      /** Selects a row by id (null: none), and brings it into view. */
      select(key, how = "api") {
        if (rows.length && byId.size === 0) draw();
        select(key, how);
      },
      /** The selected row, or null. */
      selected() {
        return current();
      },
      /** The column sorted, or null. */
      get sort() {
        return sort ? { ...sort } : null;
      },
      /** A row just added: selected, in view, and flashed so the eye finds it. */
      flash(key) {
        const k = keyOf(key);
        if (!byId.has(k)) return;
        clearTimeout(flashing.get(k));
        flashing.set(k, setTimeout(() => {
          flashing.delete(k);
          body.querySelector(`tr[data-id="${CSS_ESCAPE(k)}"]`)?.classList.remove("ttb-flash");
        }, 1400));
        select(k, "api");
        const tr = body.querySelector(`tr[data-id="${CSS_ESCAPE(k)}"]`);
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
        for (const t of flashing.values()) clearTimeout(t);
        for (const t of copiedAt.values()) clearTimeout(t);
        root.replaceChildren();
        if (addedClass) root.classList.remove("ttb");
        delete root.__taurisTable;
      },
    };
  }

  window.TaurisTable = { mount };
})();
