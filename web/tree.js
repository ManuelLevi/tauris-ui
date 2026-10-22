// tauris-ui tree view and configuration editor. Plain JavaScript: no build
// step, no dependencies. In a Tauri app the plugin injects this file with its
// stylesheet (web/tree.css), which is added on the first mount. Elsewhere (the
// demo page) load web/tree.css with a <link>.
//
//   const tree = TaurisTree.mount(document.getElementById("files"), { data });
//   tree.on("select", ({ node }) => { ... });
//
// A node is { id, label, children?, icon?, values?, editor?, readOnly?, expanded? }.
// With `columns`, the first column holds the tree and each other column shows
// node.values[column.key]. A column with `editable: true` edits those values in
// place. Only the rows in view are drawn, so thousands of rows stay fast.
//
// With `sortable: true` (or a first `sort`), a click on a column's header
// sorts by it and a second click turns it round. Rows sort among their
// siblings, so groups stay groups: numbers as numbers, text as people read it
// ("Brian 49" before "Brian 169"), empty values last both ways.
//
// The look is the classic Qt / Windows tree: compact rows, small +/- boxes and
// dotted connector lines. The lines follow one checkerboard across all rows,
// so they join without a seam and meet the middle pixel of every box.

(() => {
  "use strict";
  if (window.TaurisTree) return;

  // Filled in by the plugin; left as is when the file is loaded on its own.
  const CSS = "__TAURIS_TREE_CSS__";
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

  // Built-in icons, 16 x 16. Strokes sit on half pixels so 1px lines stay
  // sharp. tv-i-fill takes a light tint of the icon's colour, tv-i-line its
  // outline; the colours are --tv-icon-* in tree.css.
  const svg = (name, body) =>
    `<svg class="tv-svg tv-svg-${name}" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">${body}</svg>`;
  const PAGE = "M3.5 1.5h6l3 3v10h-9z";
  const FOLDER = "M2.5 2.5h3.5l1 1h6.5a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z";
  const page = marks => `<path class="tv-i-fill" d="${PAGE}"/><path class="tv-i-line" d="${PAGE}M9.5 1.5v3h3${marks}"/>`;
  const ICONS = {
    folder: svg("folder", `<path class="tv-i-fill" d="${FOLDER}"/><path class="tv-i-line" d="${FOLDER}M1.5 5.5h13"/>`),
    "folder-open": svg("folder",
      '<path class="tv-i-line" d="M1.5 13.5v-10a1 1 0 0 1 1-1h3.5l1 1h5.5a1 1 0 0 1 1 1v3"/>' +
      '<path class="tv-i-fill tv-i-strong" d="M1.5 13.5l2-6h11.5l-2 6z"/><path class="tv-i-line" d="M1.5 13.5l2-6h11.5l-2 6z"/>'),
    file: svg("file", page("")),
    code: svg("code", page("M6.5 7.5 5 9l1.5 1.5M9.5 7.5 11 9l-1.5 1.5")),
    doc: svg("doc", page("M5.5 7.5h5M5.5 9.5h5M5.5 11.5h3")),
    data: svg("data", page("M5.5 7.5h1M7.5 7.5h3M5.5 9.5h1M7.5 9.5h3M5.5 11.5h1M7.5 11.5h2")),
    image: svg("image",
      '<path class="tv-i-fill" d="M2.5 2.5h11a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z"/>' +
      '<path class="tv-i-line" d="M2.5 2.5h11a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1zM2 12l3.5-3.5 2.5 2.5 2-2 4 4"/>' +
      '<circle class="tv-i-dot" cx="10.5" cy="6" r="1.25"/>'),
    package: svg("package",
      '<path class="tv-i-fill" d="M1.5 2.5h13v3h-13zM2.5 5.5h11v8h-11z"/>' +
      '<path class="tv-i-line" d="M1.5 2.5h13v3h-13zM2.5 5.5v7a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-7M6.5 8.5h3"/>'),
    lock: svg("lock",
      '<path class="tv-i-fill" d="M3.5 7.5h9v7h-9z"/>' +
      '<path class="tv-i-line" d="M5.5 7.5v-2a2.5 2.5 0 0 1 5 0v2M3.5 7.5h9v6a1 1 0 0 1-1 1h-7a1 1 0 0 1-1-1zM8 10v2"/>'),
  };

  const DEFAULTS = {
    // the nodes: { id, label, children?, icon?, values?, editor?, readOnly?, expanded? }
    data: [],
    // null for a plain tree, or [{ label, width, key?, minWidth?, editable?, align?, className? }].
    // The first column holds the tree; the others show node.values[key].
    // The last column stretches to the right edge.
    columns: null,
    // the tree's accessible name
    label: "Tree",
    // dotted connector lines (false: +/- boxes only)
    lines: true,
    // in a table (columns), rows that only group others in a band of their own, their names bold
    // (a settings editor's sections); off, every row looks the same, as in a desktop outline
    bandGroups: false,
    // more icons by name, as svg markup: { name: "<svg ...>" }. A node's
    // `icon` names one of these or a built-in: folder, file, code, doc, data,
    // image, package, lock. Any other name becomes the class tv-icon-<name>.
    icons: {},
    // rows drawn above and below the visible ones
    overscan: 8,
    // ⌘-click (Ctrl-click) and Shift-click select several rows; ⌘A selects every row shown.
    // Off by default: a settings tree selects one row.
    multiple: false,
    // a click on a column's header sorts by it, a second click turns it
    // round; a column with `sortable: false` never sorts. null: on when
    // `sort` is given.
    sortable: null,
    // the first order: { key, up }. key is a column's key ("label" for the
    // first column unless it has a key of its own); up: true is A to Z.
    sort: null,
    // add the stylesheet (false: bring your own)
    styles: true,
    // the column headers (false: none; a tree in a sidebar)
    header: true,
    // the first column takes the room the others leave, so the tree fits its
    // width and never scrolls sideways (a tree in a sidebar)
    fit: false,
  };

  const HEX = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;
  const MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
  // Keys that do not end a name being typed: Shift and the like, and an accent's first key.
  const KEEP_TYPED = new Set(["Shift", "Control", "Alt", "Meta", "CapsLock", "Dead", "AltGraph", "Compose", "Process", "Unidentified"]);
  const has = (obj, k) => obj != null && Object.prototype.hasOwnProperty.call(obj, k);
  const hasKids = n => Array.isArray(n.children) && n.children.length > 0;
  const keyOf = id => String(id);
  const labelOf = n => String(n.label ?? n.id);

  function el(tag, className, attrs = {}, ...children) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    for (const [k, v] of Object.entries(attrs)) if (v != null) node.setAttribute(k, v);
    node.append(...children.flat().filter(c => c != null));
    return node;
  }

  // A colour typed by hand: #abc or #aabbcc, returned as #aabbcc (or null).
  function normalHex(text) {
    const s = String(text).trim();
    const m = HEX.exec(s.startsWith("#") ? s : "#" + s);
    if (!m) return null;
    const h = m[1].length === 3 ? [...m[1]].map(c => c + c).join("") : m[1];
    return "#" + h.toLowerCase();
  }

  function mount(root, options = {}) {
    if (!(root instanceof HTMLElement)) throw new Error("TaurisTree.mount needs the element to draw the tree in");
    if (root.__taurisTree) throw new Error("TaurisTree.mount: this element already has a tree; call destroy() first");
    // An option given as undefined keeps its default.
    const opt = { ...DEFAULTS, ...Object.fromEntries(Object.entries(options).filter(([, v]) => v !== undefined)) };
    if (opt.styles) addStyles();
    const icons = { ...ICONS, ...(opt.icons || {}) };
    const cols = Array.isArray(opt.columns) && opt.columns.length
      ? opt.columns.map((c, i) => ({
        key: c.key ?? null,
        label: c.label ?? "",
        width: c.width ?? (i === 0 ? 240 : 120),
        minWidth: c.minWidth ?? 40,
        editable: Boolean(c.editable) && i > 0,
        align: c.align ?? null,
        className: c.className ?? "",
        editor: c.editor ?? null,
        // what sorting calls the column, and how it sorts
        id: c.key ?? (i === 0 ? "label" : typeof c.sortValue === "function" || typeof c.compare === "function" ? `column${i}` : null),
        sortable: c.sortable !== false,
        sortValue: typeof c.sortValue === "function" ? c.sortValue : null,
        compare: typeof c.compare === "function" ? c.compare : null,
      }))
      : null;
    const widths = cols ? cols.map(c => Math.max(c.minWidth, c.width)) : [];
    // A plain tree sorts by its labels.
    const sortCols = cols ?? [{ id: "label", label: "", sortable: true, sortValue: null, compare: null }];
    const canSort = c => Boolean(c && c.sortable && c.id !== null);
    const headersSort = cols !== null && (options.sortable === true || (options.sortable !== false && options.sort != null));
    const clickable = c => headersSort && canSort(c);

    const life = new AbortController();
    const signal = life.signal;
    const listeners = new Map();
    const on = (event, fn) => {
      if (!listeners.has(event)) listeners.set(event, new Set());
      listeners.get(event).add(fn);
      return () => listeners.get(event)?.delete(fn);
    };
    const emit = (event, payload) => listeners.get(event)?.forEach(fn => {
      try { fn(payload); } catch (err) { console.error(`[tauris-ui tree] a "${event}" listener failed`, err); }
    });
    // How the selection is being made, for "select": the person's mouse or keys, or the app ("api").
    let selectHow = "api";
    const as = (how, fn) => (...args) => {
      const was = selectHow;
      selectHow = how;
      try {
        return fn(...args);
      } finally {
        selectHow = was;
      }
    };

    // ---------- the frame ----------
    // .tv (the element given) > .tv-scroll > [.tv-head] + .tv-body (role tree).
    // The header sits inside the scroller (sticky), so it scrolls sideways with the rows.

    root.__taurisTree = true;
    root.classList.add("tv");
    if (cols) root.classList.add("tv-columns");
    if (!opt.lines) root.classList.add("tv-nolines");
    if (opt.bandGroups) root.classList.add("tv-band-groups");
    const scroller = el("div", "tv-scroll");
    // Hidden from screen readers only when nothing in it can be used (no sorting, one column).
    const head = cols && opt.header !== false ? el("div", "tv-head", { "aria-hidden": cols.some(clickable) || cols.length > 1 ? null : "true" }, cols.map(headCell)) : null;
    // tabindex -1: it holds the focus while it shows no rows (a filter that matches nothing).
    const body = el("div", "tv-body", { role: "tree", tabindex: "-1", "aria-label": opt.label, "aria-multiselectable": opt.multiple ? "true" : null });
    if (head) scroller.append(head);
    scroller.append(body);
    root.append(scroller);

    // ---------- state ----------

    let data = [];
    let nodes = new Map();    // key -> node
    let parents = new Map();  // key -> parent key, or null at the top
    const expanded = new Set();
    const seen = new Set(); // every id the tree has had, for expanded: true
    let rows = [];            // the visible rows, top to bottom
    let index = new Map();    // key -> row number
    let selectedKey = null;   // the selected row with the focus
    const picked = new Set(); // every selected row (selectedKey among them)
    let anchorKey = null;     // where a Shift-click range starts
    let focusKey = null;      // the row in the Tab order (roving tabindex)
    let gen = 0;              // grows when row contents change; drawn rows refill when theirs is older
    const pool = new Map();   // key -> drawn row element
    let frame = 0;
    // Past what a browser can scroll (33 million pixels in Chromium and WebKit,
    // fewer elsewhere) the body stays this tall, and its scroll position is
    // spread over all the rows: `ratio` row pixels to a scrolled one.
    const MAX_BODY = 15e6;
    let ratio = 1;
    let shift = 0;     // how much higher than i * rowH the drawn rows sit (0 unless spread)
    let viewAt = 0;    // where the view's top is among the rows, in row pixels
    let setTop = null; // the scrollTop this code set, while it stands
    let wheelSpread = false;
    // Where the view is among the rows: the scroll position, spread; one this
    // code set stands as it was meant (scrollTop keeps whole pixels).
    function viewTop() {
      const s = scroller.scrollTop;
      if (setTop === null || Math.abs(s - setTop) >= 1) {
        setTop = null;
        viewAt = s * ratio;
      }
      return viewAt;
    }
    function scrollToRow(at) {
      const viewH = Math.max(0, scroller.clientHeight - headH);
      viewAt = Math.max(0, Math.min(at, rows.length * rowH - viewH));
      setTop = ratio === 1 ? null : viewAt / ratio;
      scroller.scrollTop = viewAt / ratio;
    }
    let editing = null;
    let sortBy = null;        // { ci, up }: the column sorted by; null keeps the data's order
    let sorted = new Map();   // parent key (null at the top) -> its children in that order
    {
      const ci = opt.sort ? sortCols.findIndex(c => c.id === opt.sort.key && canSort(c)) : -1;
      if (ci >= 0) sortBy = { ci, up: opt.sort.up !== false };
    }

    // Sizes come from tree.css; see measure().
    let rowH = 18, indent = 16, box = 9, mid = 9, lineX = 8, headH = 0;

    function measure() {
      const cs = getComputedStyle(root);
      const px = (name, fallback) => {
        const v = parseFloat(cs.getPropertyValue(name));
        return Number.isFinite(v) && v > 0 ? Math.round(v) : fallback;
      };
      rowH = px("--tv-row-h", 18);
      indent = px("--tv-indent", 16);
      box = px("--tv-box", 9);
      // The pixel row of the horizontal line and the pixel column of the
      // vertical one. The box is centred on both.
      mid = Math.floor(rowH / 2);
      lineX = Math.floor(indent / 2);
      root.style.setProperty("--tv-mid", `${mid}px`);
      root.style.setProperty("--tv-lx", `${lineX}px`);
      headH = head ? head.offsetHeight : 0;
    }

    function applyWidths() {
      if (!cols) return;
      widths.forEach((w, i) => root.style.setProperty(`--tv-c${i}`, `${w}px`));
      head?.querySelectorAll('[role="separator"]').forEach(s => {
        const w = widths[[...head.children].indexOf(s)];
        s.setAttribute("aria-valuenow", String(w));
        s.setAttribute("aria-valuemax", String(Math.max(4000, w)));
        s.setAttribute("aria-valuetext", `${w} pixels`);
      });
      root.style.setProperty("--tv-total", `${widths.reduce((a, b) => a + b, 0)}px`);
    }

    let dataCalls = 0;
    function setData(list) {
      // An edit in progress goes on, on the new list's node, when that node is
      // still there and editable (an app that refreshes its data while the
      // person types does not end their edit); otherwise it ends.
      const call = ++dataCalls;
      let keepRow = null;
      if (editing) {
        const ed = editing;
        // The node in the new list, and whether every folder above it is open
        // (an edit in a row that will not show cannot go on).
        let shows = true;
        const find = (items, open) => {
          for (const n of Array.isArray(items) ? items : []) {
            if (keyOf(n.id) === ed.key) {
              shows = open;
              return n;
            }
            const k = keyOf(n.id);
            const opens = open && (expanded.has(k) || (n.expanded === true && !seen.has(k)));
            const deeper = hasKids(n) ? find(n.children, opens) : null;
            if (deeper) return deeper;
          }
          return null;
        };
        const incoming = find(list, true);
        if (incoming && shows && !incoming.readOnly && ed.col.key != null && has(incoming.values, ed.col.key)) {
          // A field nobody has typed in yet shows the new value; what was typed stays.
          const fresh = incoming.values[ed.col.key];
          if (!ed.touched && !Object.is(fresh, ed.start)) {
            showValue(ed, fresh);
            ed.start = fresh;
          }
          ed.node = incoming;
          keepRow = pool.get(ed.key) ?? null;
        } else {
          // The edit ends; a value typed goes into the new list's node (if there is one), and is said for it.
          const typed = incoming && ed.touched ? editedValue(ed) : { ok: false };
          finishEdit(false, false);
          if (typed.ok && ed.col.key != null && !Object.is(typed.value, ed.start)) {
            (incoming.values ??= {})[ed.col.key] = typed.value;
            queueMicrotask(() => { if (!signal.aborted) emit("change", { node: incoming, column: ed.col.key, value: typed.value }); });
          }
          if (call !== dataCalls) return;
        }
      }
      const hadFocus = body.contains(document.activeElement);
      // A checkbox reached with Tab keeps the focus through the new data.
      const checkHad = document.activeElement?.closest?.(".tv-cell[role=checkbox]");
      const checkAt = checkHad ? { key: checkHad.closest(".tv-row")?.dataset.key, ci: Number(checkHad.dataset.col) } : null;
      const hadKey = selectedKey;
      const hadPicked = picked.size;
      const hadAt = selectedKey !== null ? index.get(selectedKey) : undefined;
      data = Array.isArray(list) ? list : [];
      nodes = new Map();
      parents = new Map();
      const clashes = [];
      const walk = (items, parent) => {
        for (const n of items) {
          const k = keyOf(n.id);
          if (n.id === undefined || n.id === null || nodes.has(k)) clashes.push(String(n.id));
          nodes.set(k, n);
          parents.set(k, parent);
          // expanded: true opens a node the first time it comes; after that the
          // person decides, even if the node leaves a list for a while (a search).
          if (n.expanded === true && !seen.has(k)) expanded.add(k);
          seen.add(k);
          if (hasKids(n)) walk(n.children, k);
        }
      };
      walk(data, null);
      if (clashes.length) {
        console.warn(`[tauris-ui tree] every node needs its own id; repeated or missing: ${clashes.slice(0, 5).join(", ")}${clashes.length > 5 ? ", ..." : ""}`);
      }
      sorted = new Map(); // the order stays; the rows are sorted again
      if (selectedKey !== null && !nodes.has(selectedKey)) selectedKey = null;
      for (const k of [...picked]) if (!nodes.has(k)) picked.delete(k);
      const dropped = selectedKey !== hadKey || picked.size !== hadPicked;
      if (focusKey !== null && !nodes.has(focusKey)) focusKey = selectedKey;
      // The rows may be in a new order: draw them all again (but the row being
      // edited, which keeps its field and the focus).
      for (const [k, node] of pool) if (!(keepRow && k === editing?.key)) node.remove();
      pool.clear();
      if (keepRow && editing) {
        pool.set(editing.key, keepRow);
        keepRow.__gen = -1; // its other cells are drawn again once the edit ends
      }
      measure();
      let moved = rebuild();
      // The only selected row is gone: the row now in its place takes the
      // selection and the focus, as in a file manager.
      if (hadKey !== null && selectedKey === null && !picked.size && rows.length) {
        const row = rows[Math.min(hadAt ?? 0, rows.length - 1)];
        anchorKey = focusKey = row.key;
        pick([row.key], row.key);
        reveal(index.get(row.key));
        render();
        moved = true;
        emitSelect();
      }
      if (dropped && !moved) emitSelect();
      // The focus stays in the tree: on the tree itself while it shows nothing,
      // then on the first row when rows come back.
      if (hadFocus && !editing) {
        if (!rows.length) {
          body.focus({ preventScroll: true });
        } else {
          if (focusKey === null || !index.has(focusKey)) {
            focusKey = rows[0].key;
            render();
          }
          focusRow();
          if (checkAt && index.has(checkAt.key)) goToCell(checkAt.key, checkAt.ci);
        }
      }
      requestAnimationFrame(checkHeight);
    }

    // Only the rows in view are drawn, which needs an element with a height.
    // Without one the element grows to hold every row: say so, once.
    let warnedHeight = false;
    function checkHeight() {
      if (warnedHeight || signal.aborted || rows.length < 200) return;
      if (scroller.scrollHeight <= scroller.clientHeight + 1) {
        warnedHeight = true;
        console.warn("[tauris-ui tree] the tree's element has no height, so all " + rows.length +
          " rows are drawn; give it a height (or flex: 1 inside a parent with one)");
      }
    }

    // The visible rows, with what each needs for its connector lines.
    function flatten() {
      rows = [];
      const walk = (all, depth, parent) => {
        const items = ordered(all, parent ? parent.key : null);
        items.forEach((n, i) => {
          const k = keyOf(n.id);
          const kids = hasKids(n);
          const row = {
            key: k, node: n, depth, parent, kids,
            open: kids && expanded.has(k),
            hasNext: i < items.length - 1,
            first: depth === 0 && i === 0,
            pos: i + 1, size: items.length,
          };
          rows.push(row);
          if (row.open) walk(n.children, depth + 1, row);
        });
      };
      walk(data, 0, null);
      index = new Map(rows.map((r, i) => [r.key, i]));
    }

    // ---------- sorting ----------
    // Siblings are sorted, once per order: the result is kept until the data
    // or the order changes. An edit does not move its row (it would jump away
    // under the editor); the next sort or setData puts it in its place.

    const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

    // What a node is sorted by: a number, a text, or null (empty, always last).
    function sortValueOf(n, c, ci) {
      let v = c.sortValue ? c.sortValue(n) : ci === 0 ? labelOf(n) : n.values?.[c.key];
      if (!c.sortValue && ci > 0 && c.editable && v != null) {
        const spec = editorOf(n, c);
        if (spec.type === "select") v = choices(spec).find(o => o.value === v)?.label ?? v;
      }
      if (v instanceof Date) v = v.getTime();
      if (typeof v === "boolean") v = v ? 1 : 0;
      if (typeof v === "number") return Number.isFinite(v) ? v : null;
      if (v == null) return null;
      const text = String(v).trim();
      return text === "" ? null : text;
    }

    function ordered(items, parentKey) {
      if (!sortBy || items.length < 2) return items;
      const done = sorted.get(parentKey);
      if (done) return done;
      const c = sortCols[sortBy.ci];
      const dir = sortBy.up ? 1 : -1;
      let out;
      if (c.compare) {
        // Empty values go last both ways here too.
        const keyed = items.map((n, i) => ({ n, i, empty: sortValueOf(n, c, sortBy.ci) === null }));
        keyed.sort((a, b) => (a.empty !== b.empty ? (a.empty ? 1 : -1) : dir * c.compare(a.n, b.n) || a.i - b.i));
        out = keyed.map(x => x.n);
      } else {
        const keyed = items.map((n, i) => ({ n, i, v: sortValueOf(n, c, sortBy.ci) }));
        keyed.sort((a, b) => {
          if (a.v === null || b.v === null) return a.v === b.v ? a.i - b.i : a.v === null ? 1 : -1;
          const numA = typeof a.v === "number";
          const numB = typeof b.v === "number";
          const r = numA && numB ? a.v - b.v : numA ? -1 : numB ? 1 : collator.compare(a.v, b.v);
          return r * dir || a.i - b.i;
        });
        out = keyed.map(x => x.n);
      }
      sorted.set(parentKey, out);
      return out;
    }

    // A new order: rows are drawn again; selection and focus stay on their nodes.
    // `again`: sorts even when the order is the one in place (rows edited since stay where they were until then).
    function applySort(next, announce = true, again = false) {
      const same = next === sortBy || (next && sortBy && next.ci === sortBy.ci && next.up === sortBy.up);
      if (same && !again) return;
      if (same) announce = false;
      finishEdit(true, false);
      const hadFocus = body.contains(document.activeElement);
      sortBy = next;
      sorted = new Map();
      for (const node of pool.values()) node.remove();
      pool.clear();
      rebuild();
      const k = selectedKey ?? focusKey;
      if (k !== null && index.has(k)) {
        reveal(index.get(k));
        render();
      }
      if (hadFocus) focusRow();
      paintHead();
      if (announce) emit("sort", sorting());
    }

    const sorting = () => (sortBy ? { key: sortCols[sortBy.ci].id, up: sortBy.up } : null);

    function visibleAncestor(k) {
      while (k !== null && !index.has(k)) k = parents.get(k) ?? null;
      return k;
    }

    // After the shape changed: a hidden selection moves up to the row that
    // hid it, as in Windows and Qt.
    function rebuild() {
      const hadFocus = body.contains(document.activeElement);
      flatten();
      gen++;
      let moved = false;
      // Rows hidden by closing their parent are no longer selected.
      for (const k of [...picked]) {
        if (!index.has(k)) {
          picked.delete(k);
          moved = true;
        }
      }
      if (selectedKey !== null && !index.has(selectedKey)) {
        selectedKey = visibleAncestor(selectedKey);
        if (selectedKey !== null) picked.add(selectedKey);
        moved = true;
      }
      // The row with the focus is gone but others are still selected: the first of them takes it.
      if (selectedKey === null && picked.size) {
        selectedKey = rows.find(r => picked.has(r.key))?.key ?? null;
        moved = true;
      }
      if (focusKey === null || !index.has(focusKey)) {
        focusKey = visibleAncestor(focusKey) ?? selectedKey ?? rows[0]?.key ?? null;
      }
      render();
      if (hadFocus && !body.contains(document.activeElement)) focusRow();
      if (moved) emitSelect();
      return moved;
    }

    // ---------- drawing ----------

    function schedule() {
      if (!frame) frame = requestAnimationFrame(render);
    }

    let rendering = false;
    function render() {
      rendering = true;
      try {
        drawRows();
      } finally {
        rendering = false;
      }
    }
    function drawRows() {
      cancelAnimationFrame(frame);
      frame = 0;
      const viewH = Math.max(0, scroller.clientHeight - headH);
      const total = rows.length * rowH;
      const bodyH = Math.min(total, MAX_BODY);
      ratio = total > MAX_BODY ? Math.max(1, total - viewH) / Math.max(1, MAX_BODY - viewH) : 1;
      if (ratio === 1) setTop = null;
      // Rows spread over the scroll: the wheel moves by row pixels, as it does
      // otherwise (listened to only then: it holds the scrolling up a little).
      if (ratio > 1 && !wheelSpread) {
        wheelSpread = true;
        scroller.addEventListener("wheel", e => {
          if (ratio === 1 || e.ctrlKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
          e.preventDefault();
          scrollToRow(viewTop() + e.deltaY * (e.deltaMode === 1 ? rowH : e.deltaMode === 2 ? scroller.clientHeight - headH : 1));
        }, { signal, passive: false });
      }
      body.style.height = `${bodyH}px`;
      const top = viewTop();
      shift = Math.round(top - scroller.scrollTop);
      const from = Math.max(0, Math.floor(top / rowH) - opt.overscan);
      const to = Math.min(rows.length, Math.ceil((top + viewH) / rowH) + opt.overscan);
      const want = [];
      for (let i = from; i < to; i++) want.push(i);
      // The focused row and the row being edited stay drawn even when scrolled
      // away, so keyboard focus and an open editor are never lost.
      for (const k of [focusKey, editing?.key]) {
        const i = k === null || k === undefined ? undefined : index.get(k);
        if (i !== undefined && (i < from || i >= to) && !want.includes(i)) want.push(i);
      }
      want.sort((a, b) => a - b);
      const keep = new Set(want.map(i => rows[i].key));
      for (const [k, node] of pool) {
        if (!keep.has(k)) {
          node.remove();
          pool.delete(k);
        }
      }
      // Drawn rows stay in top-to-bottom order; new rows go in between, and
      // a drawn row is never moved (moving the focused one would drop focus).
      let next = body.firstElementChild;
      for (const i of want) {
        const row = rows[i];
        let node = pool.get(row.key);
        if (node) {
          next = node.nextElementSibling;
        } else {
          node = el("div", "tv-row", { role: "treeitem" });
          node.dataset.key = row.key;
          body.insertBefore(node, next);
          pool.set(row.key, node);
        }
        if (node.__gen !== gen && !(editing && editing.key === row.key)) fill(node, row);
        place(node, row, i);
      }
    }

    // Where a row sits and its state: cheap, done on every draw.
    function place(node, row, i) {
      // A row kept drawn far from the view (it has the focus) waits above the
      // body, where it takes no room, when the rows are spread.
      const y = i * rowH - shift;
      node.style.top = `${shift && (y < -rowH || y > MAX_BODY) ? -2 * rowH : y}px`;
      node.style.setProperty("--tv-depth", String(row.depth));
      // With an odd row height every other row starts on an odd pixel; the
      // dot pattern shifts by one there so the checkerboard stays unbroken.
      node.style.setProperty("--tv-ph", `${((y % 2) + 2) % 2}px`);
      node.setAttribute("aria-level", String(row.depth + 1));
      node.setAttribute("aria-setsize", String(row.size));
      node.setAttribute("aria-posinset", String(row.pos));
      if (row.kids) node.setAttribute("aria-expanded", String(row.open));
      else node.removeAttribute("aria-expanded");
      node.setAttribute("aria-selected", String(picked.has(row.key)));
      node.classList.toggle("tv-many", picked.size > 1);
      node.tabIndex = row.key === focusKey ? 0 : -1;
    }

    // A row's contents: lines, box, icon, label and cells.
    function fill(node, row) {
      const n = row.node;
      const branch = el("span", "tv-indent", {}, row.kids ? el("span", "tv-box") : null);
      branch.style.setProperty("--tv-g", guides(row));
      const main = el("div", "tv-cell tv-main", {}, branch, iconOf(n, row.open), el("span", "tv-label", {}, labelOf(n)));
      if (cols) {
        main.dataset.col = "0";
        main.style.width = "var(--tv-c0)";
        if (cols[0].className) main.className += " " + cols[0].className;
        node.replaceChildren(main, ...cols.slice(1).map((c, j) => valueCell(n, c, j + 1)));
      } else {
        node.replaceChildren(main);
      }
      // Screen readers hear the row as "Label, Column: value, ...".
      if (cols) {
        const said = cols.slice(1).filter(c => has(n.values, c.key)).map(c => `${c.label}: ${spoken(n, c)}`);
        node.setAttribute("aria-label", [labelOf(n), ...said].join(", "));
      }
      node.classList.toggle("tv-parent", row.kids);
      node.classList.toggle("tv-group", row.kids && n.values == null);
      const check = checkboxColumn(row);
      if (check > 0) node.setAttribute("aria-checked", String(Boolean(n.values[cols[check].key])));
      else node.removeAttribute("aria-checked");
      node.__gen = gen;
    }

    // The connector lines of one row, as background layers of .tv-indent's
    // ::before. tree.css masks them with a checkerboard, which makes them
    // dotted. A line stops at the box edge, so the box needs no fill.
    function guides(row) {
      const line = "linear-gradient(var(--tv-line),var(--tv-line))";
      const layers = [];
      for (let a = row.parent; a; a = a.parent) {
        if (a.hasNext) layers.push(`${line} ${a.depth * indent + lineX}px 0/1px 100% no-repeat`);
      }
      const x = row.depth * indent + lineX;
      const half = (box - 1) / 2;
      const upTo = row.kids ? mid - half : mid + 1;
      const downFrom = row.kids ? mid + half + 1 : mid;
      if (!row.first && upTo > 0) layers.push(`${line} ${x}px 0/1px ${upTo}px no-repeat`);
      if (row.hasNext) layers.push(`${line} ${x}px ${downFrom}px/1px ${rowH - downFrom}px no-repeat`);
      const stubFrom = row.kids ? x + half + 1 : x;
      const stubTo = (row.depth + 1) * indent;
      if (stubTo > stubFrom) layers.push(`${line} ${stubFrom}px ${mid}px/${stubTo - stubFrom}px 1px no-repeat`);
      return layers.join(",");
    }

    function iconOf(n, open) {
      if (typeof n.icon !== "string" || !n.icon) return null;
      const name = n.icon === "folder" && open ? "folder-open" : n.icon;
      const span = el("span", "tv-icon", { "aria-hidden": "true" });
      if (has(icons, name)) span.innerHTML = icons[name]; // the library's or the app's own markup, never node data
      else span.classList.add(`tv-icon-${name.toLowerCase().replace(/[^a-z0-9-]/g, "")}`);
      return span;
    }

    // ---------- value cells and editors ----------

    // A cell's editor: the node's for that column (editor: { level: ... }),
    // else the column's, else the node's one editor; one that does not fit the
    // value (a checkbox for text, a choice for a boolean) is not used.
    function editorOf(n, c) {
      const asSpec = spec => (typeof spec === "string" ? { type: spec }
        : spec && typeof spec === "object" && typeof spec.type === "string" ? spec : null);
      const v = n.values?.[c.key];
      const byColumn = n.editor && typeof n.editor === "object" && typeof n.editor.type !== "string" && c.key != null
        ? asSpec(n.editor[c.key]) : null;
      const fits = spec => spec && (typeof v === "boolean") === (spec.type === "checkbox");
      const spec = [byColumn, asSpec(c.editor), asSpec(n.editor)].find(fits);
      if (spec) return spec;
      if (typeof v === "boolean") return { type: "checkbox" };
      if (typeof v === "number") return { type: "number" };
      return { type: "text" };
    }

    const choices = spec => (Array.isArray(spec.options) ? spec.options : [])
      .map(o => (o !== null && typeof o === "object" ? { value: o.value, label: String(o.label ?? o.value) } : { value: o, label: String(o) }));

    function canEdit(row, ci) {
      if (!cols || ci < 1 || ci >= cols.length || !row) return false;
      const c = cols[ci];
      return c.editable && !row.node.readOnly && has(row.node.values, c.key);
    }

    function firstEditable(row) {
      if (!cols) return -1;
      for (let ci = 1; ci < cols.length; ci++) if (canEdit(row, ci)) return ci;
      return -1;
    }

    function checkboxColumn(row) {
      const ci = firstEditable(row);
      return ci > 0 && editorOf(row.node, cols[ci]).type === "checkbox" ? ci : -1;
    }

    // The row's next (step 1) or previous (-1) editable value after column ci; -1 past the end.
    function nextEditable(row, ci, step) {
      for (let next = ci + step; next > 0 && next < cols.length; next += step) if (canEdit(row, next)) return next;
      return -1;
    }

    const isCheck = (row, ci) => editorOf(row.node, cols[ci]).type === "checkbox";

    // Goes to an editable value: a field opens; a checkbox takes the focus,
    // for Space to flip it (and Tab to go on).
    // A column off to the side comes into view (rows scroll up and down by reveal).
    function showCell(cell) {
      const box = scroller.getBoundingClientRect();
      const right = box.left + scroller.clientWidth; // a scrollbar is not room
      const at = cell.getBoundingClientRect();
      if (at.right > right) scroller.scrollLeft += Math.min(at.right - right, at.left - box.left);
      if (at.left < box.left) scroller.scrollLeft -= box.left - at.left;
    }

    function goToCell(k, ci) {
      const row = rows[index.get(k)];
      if (!canEdit(row, ci)) return false;
      if (!isCheck(row, ci)) return beginEdit(k, ci);
      finishEdit(true, false);
      reveal(index.get(k));
      render();
      const cell = cellOf(k, ci);
      if (!cell) return false;
      cell.tabIndex = -1;
      cell.focus({ preventScroll: true });
      showCell(cell);
      return true;
    }

    function valueCell(n, c, ci) {
      const cell = el("div", `tv-cell${c.className ? " " + c.className : ""}${c.align === "right" ? " tv-right" : c.align === "center" ? " tv-center" : ""}`);
      cell.dataset.col = String(ci);
      cell.style.width = `var(--tv-c${ci})`;
      if (!has(n.values, c.key)) return cell;
      const v = n.values[c.key];
      if (!c.editable) {
        cell.append(el("span", "tv-text", {}, v == null ? "" : String(v)));
        return cell;
      }
      // A read-only value shows as an editable one does (a choice's label, a
      // box, a swatch), only it cannot change.
      const fixed = Boolean(n.readOnly);
      const spec = editorOf(n, c);
      cell.classList.add(fixed ? "tv-readonly" : "tv-editable", `tv-kind-${spec.type}`);
      if (spec.type === "checkbox") {
        // Reached with Tab from the row's other values; Space flips it.
        if (!fixed) {
          cell.setAttribute("role", "checkbox");
          cell.setAttribute("aria-checked", String(Boolean(v)));
          cell.setAttribute("aria-label", `${labelOf(n)}, ${c.label}`);
        }
        cell.append(el("span", `tv-check${v ? " tv-on" : ""}`, { "aria-hidden": "true" }));
      } else if (spec.type === "color") {
        const swatch = el("span", "tv-swatch", { "aria-hidden": "true" });
        if (HEX.test(String(v))) swatch.style.setProperty("--tv-swatch", String(v));
        cell.append(swatch, el("span", "tv-text", {}, String(v ?? "")));
      } else if (spec.type === "select") {
        const choice = choices(spec).find(o => o.value === v);
        cell.append(el("span", "tv-text", {}, choice ? choice.label : String(v ?? "")));
        if (!fixed) cell.append(el("span", "tv-caret", { "aria-hidden": "true" }));
      } else {
        cell.append(el("span", "tv-text", {}, v == null ? "" : String(v)));
      }
      return cell;
    }

    function spoken(n, c) {
      const v = n.values[c.key];
      if (typeof v === "boolean") return v ? "on" : "off";
      const spec = c.editable ? editorOf(n, c) : null; // (read-only too: it shows the same way)
      if (spec?.type === "select") return choices(spec).find(o => o.value === v)?.label ?? String(v ?? "");
      return v == null ? "" : String(v);
    }

    function cellOf(k, ci) {
      return pool.get(k)?.querySelector(`.tv-cell[data-col="${ci}"]`) ?? null;
    }

    // Saves a new value in the node, redraws and tells the app.
    function commit(n, c, value) {
      if (Object.is(n.values[c.key], value)) return;
      n.values[c.key] = value;
      gen++;
      render();
      emit("change", { node: n, column: c.key, value });
    }

    // Opens the editor of a cell inside its row (the row keeps its height).
    // A checkbox flips at once; a colour opens the system picker when its
    // swatch is clicked, or a hex field otherwise.
    function beginEdit(k, ci, target = null) {
      finishEdit(true, false);
      const i = index.get(k);
      const row = i === undefined ? null : rows[i];
      if (!canEdit(row, ci)) return false;
      const n = row.node;
      const c = cols[ci];
      const spec = editorOf(n, c);
      const v = n.values[c.key];
      if (spec.type === "checkbox") {
        commit(n, c, !v);
        return true;
      }
      reveal(i);
      render();
      const cell = cellOf(k, ci);
      if (!cell) return false;
      if (spec.type === "color" && target && target.closest(".tv-swatch")) {
        openPicker(cell, n, c, v);
        return true;
      }
      let input;
      if (spec.type === "select") {
        const list = choices(spec);
        input = el("select", "tv-editor", { "aria-label": `${labelOf(n)}, ${c.label}` }, list.map((o, j) => el("option", null, { value: String(j) }, o.label)));
        input.selectedIndex = list.findIndex(o => o.value === v);
        input.addEventListener("change", () => finishEdit(true), { signal });
      } else {
        const number = spec.type === "number";
        input = el("input", "tv-editor", {
          type: number ? "number" : "text", spellcheck: "false", autocomplete: "off", "aria-label": `${labelOf(n)}, ${c.label}`,
          min: number ? spec.min : null, max: number ? spec.max : null, step: number ? (spec.step ?? "any") : null,
        });
        input.value = v == null ? "" : String(v);
        // The wheel over a number field scrolls the tree; Chromium would change the number.
        if (number) {
          input.addEventListener("wheel", e => {
            e.preventDefault();
            scrollToRow(viewTop() + e.deltaY * (e.deltaMode === 1 ? rowH : 1));
          }, { passive: false, signal });
        }
      }
      input.addEventListener("keydown", e => {
        e.stopPropagation();
        // Enter and Escape confirm or cancel an input method's text then, not the value.
        if (e.isComposing || e.keyCode === 229) return;
        if (e.key === "Tab") {
          // Tab and Shift+Tab save and go to the row's next (or previous)
          // editable value; past the last one, back to the row.
          e.preventDefault();
          finishEdit(true, false);
          const next = nextEditable(rows[index.get(k)], ci, e.shiftKey ? -1 : 1);
          if (next < 0 || !goToCell(k, next)) focusRow();
        } else if (e.key === "Enter") {
          e.preventDefault();
          finishEdit(true);
        } else if (e.key === "Escape") {
          e.preventDefault();
          finishEdit(false);
        }
      }, { signal });
      // Clicking elsewhere saves; switching to another app does not (the field is there on coming back).
      input.addEventListener("blur", () => {
        if (!document.hasFocus()) return;
        // While rows are being drawn (its row taken out), after the drawing.
        if (rendering) queueMicrotask(() => finishEdit(true, false));
        else finishEdit(true, false);
      }, { signal });
      cell.classList.add("tv-editing");
      cell.append(input);
      editing = { key: k, ci, input, spec, node: n, col: c, start: v, touched: false };
      const ed = editing;
      input.addEventListener(input.tagName === "SELECT" ? "change" : "input", () => { ed.touched = true; }, { signal });
      input.focus({ preventScroll: true });
      showCell(cell);
      if (input.tagName === "INPUT") input.select();
      if (input.tagName === "SELECT" && typeof input.showPicker === "function") {
        try { input.showPicker(); } catch { /* no user gesture: the list opens on the next click */ }
      }
      return true;
    }

    // Puts a value in an open editor.
    function showValue(ed, value) {
      if (ed.spec.type === "select") ed.input.selectedIndex = choices(ed.spec).findIndex(o => o.value === value);
      else ed.input.value = value == null ? "" : String(value);
    }

    // What the editor holds, as the type the value has: { ok, value }.
    function editedValue(ed) {
      const { input, spec } = ed;
      // Nothing changed in the field: the value stays what it was (a number shown
      // in a text field stays a number, "#5B8CFF" is not rewritten).
      if (spec.type !== "select" && input.value === (ed.start == null ? "" : String(ed.start))) return { ok: true, value: ed.start };
      if (spec.type === "select") {
        const list = choices(spec);
        const j = input.selectedIndex;
        return j >= 0 && j < list.length ? { ok: true, value: list[j].value } : { ok: false };
      }
      if (spec.type === "number") {
        const text = input.value.trim();
        const num = Number(text);
        if (text === "" || !Number.isFinite(num)) return { ok: false };
        let value = num;
        // On a step from min (or 0): 12.5 is 13 for a step of 1.
        if (typeof spec.step === "number" && spec.step > 0) {
          const base = typeof spec.min === "number" ? spec.min : 0;
          value = Number((base + Math.round((value - base) / spec.step) * spec.step).toFixed(10));
        }
        if (typeof spec.min === "number" && value < spec.min) value = spec.min;
        if (typeof spec.max === "number" && value > spec.max) value = spec.max;
        return { ok: true, value };
      }
      if (spec.type === "color") {
        const hex = normalHex(input.value);
        return hex ? { ok: true, value: hex } : { ok: false };
      }
      return { ok: true, value: input.value };
    }

    // Closes the open editor; keeps its value when `save` is true and the
    // value is valid. Focus goes back to the row unless it went elsewhere.
    function finishEdit(save, refocus = true) {
      const ed = editing;
      if (!ed) return;
      editing = null; // first, so a blur fired by the removal does nothing
      const result = save ? editedValue(ed) : { ok: false };
      const hadFocus = document.activeElement === ed.input;
      ed.input.parentElement?.classList.remove("tv-editing");
      ed.input.remove();
      // Drawn again either way: a row kept through setData shows its new data.
      if (result.ok && !Object.is(ed.node.values?.[ed.col.key], result.value)) commit(ed.node, ed.col, result.value);
      else render();
      // The editor had the focus: it goes back to the row (whatever closed the
      // editor: Enter, setData, a sort, a folder closing), never to the page.
      if (hadFocus) focusRow();
    }

    function openPicker(cell, n, c, v) {
      cell.querySelector(".tv-picker")?.remove();
      const picker = el("input", "tv-picker", { type: "color", tabindex: "-1", "aria-hidden": "true" });
      picker.value = normalHex(v ?? "") ?? "#000000";
      cell.append(picker);
      // The swatch follows the picker live; the value is saved when it closes.
      picker.addEventListener("input", () => cell.querySelector(".tv-swatch")?.style.setProperty("--tv-swatch", picker.value), { signal });
      picker.addEventListener("change", () => {
        const value = picker.value;
        picker.remove();
        commit(n, c, value);
      }, { signal });
      if (typeof picker.showPicker === "function") {
        try { picker.showPicker(); } catch { picker.click(); }
      } else {
        picker.click();
      }
    }

    // ---------- focus, selection, expansion ----------

    function focusRow() {
      const node = pool.get(focusKey);
      node?.focus({ preventScroll: true });
      // Taking the focus from an editor saved it, and the app's answer to that
      // "change" may have drawn the rows again: the row as it is now.
      const now = pool.get(focusKey);
      if (now && now !== node) now.focus({ preventScroll: true });
    }

    function reveal(i) {
      const viewH = scroller.clientHeight - headH;
      const y = i * rowH;
      const top = viewTop();
      if (y < top) scrollToRow(y);
      else if (y + rowH > top + viewH) scrollToRow(Math.max(0, y + rowH - viewH));
    }

    // "select": the row with the focus, and every selected row, top to bottom.
    function emitSelect() {
      const all = rows.filter(r => picked.has(r.key)).map(r => r.node);
      emit("select", { node: selectedKey === null ? null : nodes.get(selectedKey) ?? null, nodes: all, how: selectHow });
    }

    // The selection becomes these keys, with `key` selected and focused.
    function pick(keys, key) {
      const next = new Set(keys);
      const changed = key !== selectedKey || next.size !== picked.size || [...next].some(k => !picked.has(k));
      picked.clear();
      for (const k of next) picked.add(k);
      selectedKey = key;
      return changed;
    }

    // Adds the row with the focus to the selection, or takes it out (Space with `multiple`).
    function toggleFocused() {
      const keys = new Set(picked);
      if (keys.has(focusKey)) keys.delete(focusKey);
      else keys.add(focusKey);
      anchorKey = focusKey;
      let next = keys.has(focusKey) ? focusKey : selectedKey;
      if (next !== null && !keys.has(next)) next = rows.find(r => keys.has(r.key))?.key ?? null;
      if (pick(keys, next)) {
        render();
        emitSelect();
      }
    }

    // The visible rows from the anchor to `key`.
    function span(key) {
      const a = index.get(anchorKey ?? key);
      const b = index.get(key);
      if (a === undefined || b === undefined) return [key];
      return rows.slice(Math.min(a, b), Math.max(a, b) + 1).map(r => r.key);
    }

    // Moves focus and selection to row i (selection follows focus). With
    // `extend` (Shift), the selection runs from the anchor to that row.
    function go(i, extend = false) {
      const row = rows[Math.max(0, Math.min(i, rows.length - 1))];
      if (!row) return;
      focusKey = row.key;
      let changed;
      if (extend && opt.multiple) {
        changed = pick(span(row.key), row.key);
      } else {
        anchorKey = row.key;
        changed = pick([row.key], row.key);
      }
      reveal(index.get(row.key));
      render();
      focusRow();
      if (changed) emitSelect();
    }

    // Opens or closes the given keys; one toggle event per row that changed.
    function setOpen(keys, open) {
      const changed = [];
      for (const k of keys) {
        const n = nodes.get(k);
        if (!n || !hasKids(n) || expanded.has(k) === open) continue;
        if (open) expanded.add(k);
        else expanded.delete(k);
        changed.push(n);
      }
      if (!changed.length) return;
      // An editor stays open unless its row is being hidden (a folder above it closing).
      const hides = k => { for (let p = parents.get(k); p != null; p = parents.get(p)) if (!expanded.has(p)) return true; return false; };
      if (editing && hides(editing.key)) finishEdit(true, false);
      rebuild();
      for (const n of changed) emit("toggle", { node: n, expanded: open });
    }

    const toggle = k => setOpen([k], !expanded.has(k));

    function descendants(n, out = []) {
      if (hasKids(n)) for (const c of n.children) {
        out.push(keyOf(c.id));
        descendants(c, out);
      }
      return out;
    }

    // ---------- keyboard ----------
    // Windows / Qt keys. Selection follows focus; one row is in the Tab order.

    let typed = "";
    let typedAt = 0;
    // When the key was pressed, not when it was handled: a page busy drawing the
    // last match does not cut short a name typed quickly (0 in an engine that leaves it out).
    const keyTime = e => e.timeStamp || performance.now();
    function typeAhead(ch, at, now) {
      typed = now - typedAt > 700 ? ch : typed + ch;
      typedAt = now;
      // One letter again and again steps through the rows that start with it.
      const same = [...typed].every(c => c === typed[0]);
      const needle = (same ? typed[0] : typed).toLowerCase();
      const from = typed.length === 1 || same ? at + 1 : at;
      for (let j = 0; j < rows.length; j++) {
        const i = (from + j) % rows.length;
        if (labelOf(rows[i].node).toLowerCase().startsWith(needle)) return go(i);
      }
    }

    // The focus put on a row by something else (VoiceOver's cursor, the app's own
    // row.focus()): that row is the one the keys act on, selected as a key would.
    let pressedAt = -Infinity; // a press focuses its row itself (or, a right click, leaves it alone)
    body.addEventListener("pointerdown", () => { pressedAt = performance.now(); }, { capture: true, signal });
    body.addEventListener("focusin", as("keyboard", e => {
      if (performance.now() - pressedAt < 500) return;
      const rowEl = e.target instanceof Element && e.target.classList.contains("tv-row") ? e.target : null;
      const k = rowEl?.dataset.key;
      if (k == null || k === focusKey || !index.has(k) || editing) return;
      go(index.get(k));
    }), { signal });

    body.addEventListener("keydown", as("keyboard", e => {
      if (e.target.closest(".tv-editor, .tv-picker")) return;
      // A checkbox reached with Tab: Space flips it, Tab goes on, Enter or Escape back to the row.
      const check = e.target.closest?.(".tv-cell[role=checkbox]");
      if (check && check === document.activeElement && [" ", "Tab", "Enter", "Escape"].includes(e.key)) {
        const k = check.closest(".tv-row")?.dataset.key;
        const ci = Number(check.dataset.col);
        const row = k == null ? null : rows[index.get(k)];
        if (!row) return;
        e.preventDefault();
        e.stopPropagation();
        if (e.key === " ") {
          if (!e.repeat && canEdit(row, ci)) {
            commit(row.node, cols[ci], !row.node.values[cols[ci].key]);
            const again = cellOf(k, ci);
            if (again) {
              again.tabIndex = -1;
              again.focus({ preventScroll: true });
            }
          }
        } else if (e.key === "Tab") {
          const next = nextEditable(row, ci, e.shiftKey ? -1 : 1);
          if (next < 0 || !goToCell(k, next)) focusRow();
        } else {
          focusRow();
        }
        return;
      }
      // Any other key there is the row's (the arrows move on from it).
      if (check && check === document.activeElement && !KEEP_TYPED.has(e.key)) focusRow();
      // Any key but a letter (or Shift and the like, or an accent's first key) ends what was being typed.
      if (e.key.length !== 1 && !KEEP_TYPED.has(e.key)) typed = "";
      const at = index.get(focusKey);
      if (at === undefined) return;
      // The menu key or ⇧F10: the app's menu, under the row with the focus.
      if ((e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey && !e.altKey && !e.ctrlKey && !e.metaKey)) && listeners.get("contextmenu")?.size) {
        const rowEl = pool.get(focusKey);
        const node = nodes.get(focusKey);
        if (rowEl && node) {
          e.preventDefault();
          const r = rowEl.getBoundingClientRect();
          emit("contextmenu", { node, x: r.left + 12, y: r.bottom, how: "keyboard" });
        }
        return;
      }
      const toggleKey = MAC ? e.metaKey : e.ctrlKey;
      // ⌘A (Ctrl+A): every row shown; never the page's own Select All.
      if (toggleKey && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "a") {
        e.preventDefault();
        if (opt.multiple && pick(rows.map(r => r.key), selectedKey ?? focusKey)) {
          render();
          emitSelect();
        }
        return;
      }
      // ⌘ (Ctrl) with the arrows moves the focus alone; with Space it selects or unselects that row.
      if (opt.multiple && toggleKey && !e.altKey && !e.shiftKey) {
        const page = Math.max(1, Math.floor((scroller.clientHeight - headH) / rowH) - 1);
        const moves = { ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: rows.length - 1, PageDown: at + page, PageUp: at - page };
        if (e.key in moves) {
          e.preventDefault();
          const row = rows[Math.max(0, Math.min(moves[e.key], rows.length - 1))];
          focusKey = row.key;
          reveal(index.get(row.key));
          render();
          focusRow();
          return;
        }
        if (e.key === " ") {
          e.preventDefault();
          toggleFocused();
          return;
        }
      }
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      const row = rows[at];
      const page = Math.max(1, Math.floor((scroller.clientHeight - headH) / rowH) - 1);
      const handled = () => e.preventDefault();
      const ext = e.shiftKey;
      switch (e.key) {
        case "ArrowDown": handled(); go(at + 1, ext); break;
        case "ArrowUp": handled(); go(at - 1, ext); break;
        case "PageDown": handled(); go(at + page, ext); break;
        case "PageUp": handled(); go(at - page, ext); break;
        case "Home": handled(); go(0, ext); break;
        case "End": handled(); go(rows.length - 1, ext); break;
        case "ArrowRight":
          handled();
          if (row.kids && !row.open) setOpen([row.key], true);
          else if (row.kids) go(at + 1);
          break;
        case "ArrowLeft":
          handled();
          if (row.kids && row.open) setOpen([row.key], false);
          else if (row.parent) go(index.get(row.parent.key));
          break;
        case "+":
        case "-":
        case "*":
          handled();
          // Inside a name being typed ("src-tauri"), part of it.
          if (typed && keyTime(e) - typedAt < 700) typeAhead(e.key, at, keyTime(e));
          else if (e.key === "+") setOpen([row.key], true);
          else if (e.key === "-") setOpen([row.key], false);
          else setOpen([row.key, ...descendants(row.node)], true);
          break;
        case "Enter": {
          handled();
          const ci = firstEditable(row);
          if (ci > 0) goToCell(row.key, ci);
          else emit("activate", { node: row.node });
          break;
        }
        case "F2": {
          handled();
          const ci = firstEditable(row);
          if (ci > 0) goToCell(row.key, ci);
          break;
        }
        case " ": {
          handled();
          // A space in the middle of typing a name is part of it ("open at login").
          if (typed && keyTime(e) - typedAt < 700) {
            typeAhead(" ", at, keyTime(e));
            break;
          }
          const ci = checkboxColumn(row);
          if (opt.multiple && ci <= 0) {
            toggleFocused();
            break;
          }
          if (selectedKey !== row.key) go(at);
          if (ci > 0) beginEdit(row.key, ci);
          break;
        }
        default:
          if (e.key.length === 1 && e.key.trim()) {
            handled();
            typeAhead(e.key, at, keyTime(e));
          }
      }
    }), { signal });

    // ---------- mouse ----------
    // Selection happens on press, as in desktop trees. The press is held back
    // from the browser so focus and text selection stay under our control.

    body.addEventListener("mousedown", as("mouse", e => {
      // A right click (Control-click on a Mac) leaves the selection to the app's own menu.
      // A right click (Control-click on a Mac) leaves the selection and the
      // focus to the app's own menu: the browser does not move the focus either.
      if (e.button !== 0 || (MAC && e.ctrlKey)) {
        if (e.target.closest(".tv-row")) e.preventDefault();
        return;
      }
      if (e.target.closest(".tv-editor, .tv-picker")) return;
      // An edit open elsewhere is saved first: the app's answer to its "change"
      // may draw the rows again, and the press then acts on them as they are
      // (the row pressed is found again by its key).
      const pressed = e.target.closest(".tv-row");
      if (editing) finishEdit(true, false);
      const rowEl = pressed ? pool.get(pressed.dataset.key) ?? pressed : null;
      if (!rowEl) {
        if (e.target === body) {
          e.preventDefault();
          focusRow();
        }
        return;
      }
      e.preventDefault();
      const k = rowEl.dataset.key;
      const i = index.get(k);
      if (i === undefined) return;
      const row = rows[i];
      // The +/- box, or anywhere in its slot: open or close, keep the selection.
      const branch = rowEl.querySelector(".tv-indent");
      const x = e.clientX - branch.getBoundingClientRect().left;
      if (row.kids && x >= row.depth * indent && x < (row.depth + 1) * indent) {
        toggle(k);
        focusRow();
        return;
      }
      const toggleKey = MAC ? e.metaKey : e.ctrlKey;
      if (opt.multiple && (toggleKey || e.shiftKey)) {
        // ⌘-click adds or takes out one row; Shift-click selects the rows from the anchor.
        let keys;
        if (toggleKey) {
          keys = new Set(picked);
          if (keys.has(k)) keys.delete(k);
          else keys.add(k);
          anchorKey = k;
        } else {
          keys = span(k);
        }
        const kept = new Set(keys);
        // Taking out the row with the focus moves the focus to the nearest selected row.
        let next = kept.has(k) ? k : null;
        if (next === null) {
          let gap = Infinity;
          for (const key of kept) {
            const d = Math.abs((index.get(key) ?? Infinity) - i);
            if (d < gap) {
              gap = d;
              next = key;
            }
          }
        }
        focusKey = next ?? k;
        const changed = pick(kept, next);
        render();
        focusRow();
        if (changed) emitSelect();
        return;
      }
      go(i);
      const cell = e.target.closest(".tv-cell[data-col]");
      const ci = cell ? Number(cell.dataset.col) : -1;
      if (!canEdit(row, ci)) return;
      // A checkbox flips only when its box is pressed.
      if (editorOf(row.node, cols[ci]).type === "checkbox" && !e.target.closest(".tv-check")) return;
      beginEdit(k, ci, e.target);
    }), { signal });

    // A right click on a row: "contextmenu", where to open the app's own menu (the
    // selection stays as it is). With a listener, the browser's own menu stays shut.
    body.addEventListener("contextmenu", e => {
      if (!listeners.get("contextmenu")?.size) return;
      const rowEl = e.target instanceof Element ? e.target.closest(".tv-row") : null;
      if (!rowEl || e.target.closest(".tv-editor, .tv-picker")) return;
      const node = nodes.get(rowEl.dataset.key);
      if (!node) return;
      e.preventDefault();
      emit("contextmenu", { node, x: e.clientX, y: e.clientY, how: "mouse" });
    }, { signal });

    body.addEventListener("dblclick", e => {
      const rowEl = e.target.closest(".tv-row");
      if (!rowEl || e.target.closest(".tv-editor, .tv-picker, .tv-editable")) return;
      const i = index.get(rowEl.dataset.key);
      if (i === undefined) return;
      const row = rows[i];
      const x = e.clientX - rowEl.querySelector(".tv-indent").getBoundingClientRect().left;
      if (x < (row.depth + 1) * indent) return; // the box's own presses did the work
      if (row.kids) toggle(row.key);
      emit("activate", { node: row.node });
    }, { signal });

    scroller.addEventListener("scroll", schedule, { signal, passive: true });
    // A press on the empty space below the last row (not on a scrollbar): the
    // focus stays in the tree, on its row, and an open edit is saved.
    scroller.addEventListener("mousedown", e => {
      if (e.target !== scroller || e.button !== 0) return;
      const box = scroller.getBoundingClientRect();
      if (e.clientX - box.left > scroller.clientWidth || e.clientY - box.top > scroller.clientHeight) return;
      e.preventDefault();
      if (editing) finishEdit(true, false);
      focusRow();
    }, { signal });
    // fit: the first column takes the room the others leave (never less than its minWidth).
    function fitWidths() {
      if (!cols || !opt.fit || !scroller.clientWidth) return;
      const others = widths.slice(1).reduce((a, b) => a + b, 0);
      const w = Math.max(cols[0].minWidth, Math.floor(scroller.clientWidth - others));
      if (w === widths[0]) return;
      widths[0] = w;
      applyWidths();
    }
    // A tree mounted while hidden measured nothing: measure again once it shows.
    const resized = new ResizeObserver(() => {
      measure();
      fitWidths();
      schedule();
    });
    resized.observe(scroller);

    // ---------- column header ----------

    function headCell(c, i) {
      const cell = el("div", `tv-hcell${c.align === "right" ? " tv-right" : c.align === "center" ? " tv-center" : ""}`, {}, el("span", "tv-htext", {}, c.label));
      cell.style.width = `var(--tv-c${i})`;
      if (clickable(c)) {
        // The header is a button: a click sorts, a second click turns it round.
        cell.classList.add("tv-sortable");
        cell.setAttribute("role", "button");
        cell.tabIndex = 0;
        cell.append(el("span", "tv-arrow", { "aria-hidden": "true" }));
        const press = () => applySort({ ci: i, up: sortBy?.ci === i ? !sortBy.up : true });
        let spaceDown = false;
        cell.addEventListener("click", e => {
          if (!e.target.closest(".tv-grip")) press();
        }, { signal });
        cell.addEventListener("keydown", e => {
          if (e.altKey || e.ctrlKey || e.metaKey) return;
          if (e.key === "Enter") {
            e.preventDefault();
            if (!e.repeat) press();
          } else if (e.key === " ") {
            e.preventDefault();
            spaceDown = true;
          }
        }, { signal });
        cell.addEventListener("keyup", e => {
          if (e.key !== " ") return;
          const was = spaceDown;
          spaceDown = false;
          if (was) press();
        }, { signal });
        cell.addEventListener("blur", () => { spaceDown = false; }, { signal });
      }
      if (i < cols.length - 1) {
        const grip = el("span", "tv-grip", { "aria-hidden": "true" });
        grip.addEventListener("pointerdown", e => startResize(e, i, grip), { signal });
        cell.append(grip);
        // The keyboard resizes too: Alt+← / Alt+→ on a header that sorts; on one
        // that does not, the header is the column's edge, and ← / → move it.
        const edge = !clickable(c);
        if (edge) {
          cell.setAttribute("role", "separator");
          cell.setAttribute("aria-orientation", "vertical");
          cell.setAttribute("aria-label", `${c.label}, width`);
          cell.setAttribute("aria-valuemin", String(c.minWidth));
          cell.setAttribute("aria-valuemax", String(Math.max(4000, widths[i])));
          cell.setAttribute("aria-valuenow", String(widths[i]));
          cell.setAttribute("aria-valuetext", `${widths[i]} pixels`);
          cell.tabIndex = 0;
        }
        cell.addEventListener("keydown", e => {
          if (e.ctrlKey || e.metaKey || (e.key !== "ArrowLeft" && e.key !== "ArrowRight") || !(e.altKey || edge)) return;
          e.preventDefault();
          const was = widths[i];
          widths[i] = Math.max(cols[i].minWidth, widths[i] + (e.key === "ArrowLeft" ? -10 : 10));
          applyWidths();
          if (widths[i] !== was) widthChanged(i);
        }, { signal });
      }
      return cell;
    }

    // The ▲ / ▼ and what a screen reader hears. (aria-sort belongs to tables;
    // a tree's header says its order in the button's name.)
    function paintHead() {
      if (!head) return;
      [...head.children].forEach((cell, i) => {
        if (!cell.classList.contains("tv-sortable")) return;
        const on = sortBy?.ci === i;
        cell.querySelector(".tv-arrow").textContent = on ? (sortBy.up ? "▲" : "▼") : "";
        cell.classList.toggle("tv-sorted", on);
        cell.setAttribute("aria-label", on ? `${cols[i].label}, sorted ${sortBy.up ? "ascending" : "descending"}` : `Sort by ${cols[i].label}`);
      });
    }

    // The person made a column wider or narrower: the app hears it, to keep it.
    function widthChanged(i) {
      emit("resize", { column: cols[i].key ?? null, index: i, width: widths[i], widths: widths.slice() });
    }

    // Dragging a column's right edge: one variable changes, header and rows follow.
    function startResize(e, i, grip) {
      if (e.button !== 0) return;
      e.preventDefault();
      const startX = e.clientX;
      const startW = widths[i];
      grip.setPointerCapture(e.pointerId);
      root.classList.add("tv-resizing");
      grip.classList.add("tv-grip-on");
      const drag = new AbortController();
      // WebKit sends both pointerup and lostpointercapture: end the drag once.
      const stop = () => {
        if (drag.signal.aborted) return;
        drag.abort();
        root.classList.remove("tv-resizing");
        grip.classList.remove("tv-grip-on");
        if (widths[i] !== startW) widthChanged(i);
      };
      const both = AbortSignal.any ? AbortSignal.any([signal, drag.signal]) : drag.signal;
      grip.addEventListener("pointermove", ev => {
        widths[i] = Math.max(cols[i].minWidth, Math.round(startW + ev.clientX - startX));
        applyWidths();
      }, { signal: both });
      grip.addEventListener("pointerup", stop, { signal: both });
      grip.addEventListener("lostpointercapture", stop, { signal: both });
    }

    // ---------- start ----------

    applyWidths();
    fitWidths();
    paintHead();
    setData(opt.data);

    return {
      /** Replaces every node. Open rows and the selection are kept where their ids still exist. */
      setData,
      /** Opens a row (its parents stay as they are). */
      expand(id) { setOpen([keyOf(id)], true); },
      /** Closes a row. */
      collapse(id) { setOpen([keyOf(id)], false); },
      /** Opens or closes a row. */
      toggle(id) { toggle(keyOf(id)); },
      expandAll() { setOpen([...nodes.keys()], true); },
      collapseAll() {
        setOpen([...expanded], false);
        expanded.clear(); // folders not in the list now come back closed too
      },
      /** Selects a row, opening its parents and scrolling it into view. null clears the selection. */
      select(id) {
        if (id === null || id === undefined) {
          if (selectedKey === null && !picked.size) return;
          pick([], null);
          render();
          emitSelect();
          return;
        }
        if (Array.isArray(id)) {
          // Several rows (with `multiple`): the first gets the focus. Their parents open.
          const keys = id.map(keyOf).filter(k => nodes.has(k));
          if (!keys.length) return; // as select() with an id the tree does not have
          const list = opt.multiple ? keys : keys.slice(0, 1);
          const hadFocus = body.contains(document.activeElement);
          const closed = [];
          for (const k of list) for (let q = parents.get(k); q !== null && q !== undefined; q = parents.get(q)) if (!expanded.has(q)) closed.push(q);
          setOpen(closed, true);
          anchorKey = list[0] ?? null;
          if (list[0] !== undefined) focusKey = list[0];
          const changed = pick(list, list[0] ?? null);
          if (list[0] !== undefined) reveal(index.get(list[0]));
          render();
          if (hadFocus) focusRow();
          if (changed) emitSelect();
          return;
        }
        const k = keyOf(id);
        if (!nodes.has(k)) return;
        const closed = [];
        for (let p = parents.get(k); p !== null && p !== undefined; p = parents.get(p)) if (!expanded.has(p)) closed.push(p);
        setOpen(closed, true);
        const hadFocus = body.contains(document.activeElement);
        focusKey = k;
        anchorKey = k;
        const changed = pick([k], k);
        reveal(index.get(k));
        render();
        if (hadFocus) focusRow();
        if (changed) emitSelect();
      },
      /** The selected node with the focus, or null. */
      selected() { return selectedKey === null ? null : nodes.get(selectedKey) ?? null; },
      /** Every selected node, top to bottom (one at most without `multiple`). */
      selection() { return rows.filter(r => picked.has(r.key)).map(r => r.node); },
      /** Selects every row shown (with `multiple`). */
      selectAll() {
        if (!opt.multiple) return;
        if (pick(rows.map(r => r.key), selectedKey ?? rows[0]?.key ?? null)) {
          render();
          emitSelect();
        }
      },
      /** The node with this id, or null. */
      get(id) { return nodes.get(keyOf(id)) ?? null; },
      /** Whether a row is open. */
      isExpanded(id) {
        const n = nodes.get(keyOf(id));
        return Boolean(n) && hasKids(n) && expanded.has(keyOf(id));
      },
      /** Opens the editor of a cell: (id, columnKey?) — the first editable column by default. */
      edit(id, column) {
        const k = keyOf(id);
        if (!nodes.has(k)) return false;
        // A row inside closed folders: they open, as select() opens them.
        const closed = [];
        for (let p = parents.get(k); p !== null && p !== undefined; p = parents.get(p)) if (!expanded.has(p)) closed.push(p);
        setOpen(closed, true);
        const i = index.get(k);
        if (i === undefined) return false;
        const ci = column === undefined ? firstEditable(rows[i]) : (cols ?? []).findIndex(c => c.key === column);
        if (!canEdit(rows[i], ci)) return false;
        // The row being edited is the selected one, so Escape and Tab come back to it.
        go(i);
        if (editorOf(rows[i].node, cols[ci]).type === "checkbox") return goToCell(k, ci);
        return beginEdit(k, ci);
      },
      /** Moves keyboard focus into the tree. */
      focus() { focusRow(); },
      /** Every column's width in pixels, as the person left them. */
      widths() { return widths.slice(); },
      /** Sets the columns' widths (pixels, in column order; null keeps one as it is). */
      setWidths(list) {
        if (!cols || !Array.isArray(list)) return;
        list.forEach((w, i) => {
          if (i < widths.length && Number.isFinite(w)) widths[i] = Math.max(cols[i].minWidth, Math.round(w));
        });
        applyWidths();
        fitWidths();
      },
      /** Sorts by a column's key ("label": the first column), up: true for A to Z. null: the data's
       * own order. Fires "sort". Returns false for a column that cannot sort. */
      sort(key, up = true) {
        if (key === null || key === undefined) {
          applySort(null, true, true);
          return true;
        }
        const ci = sortCols.findIndex(c => c.id === key && canSort(c));
        if (ci < 0) return false;
        applySort({ ci, up: up !== false }, true, true);
        return true;
      },
      /** The order now: { key, up }, or null for the data's own order. */
      sorting,
      on,
      destroy() {
        finishEdit(true, false); // what is being typed is kept, as setData keeps it
        life.abort();
        resized.disconnect();
        cancelAnimationFrame(frame);
        scroller.remove();
        pool.clear();
        root.classList.remove("tv", "tv-columns", "tv-nolines", "tv-resizing", "tv-band-groups");
        for (const name of ["--tv-mid", "--tv-lx", "--tv-total", ...widths.map((_, i) => `--tv-c${i}`)]) root.style.removeProperty(name);
        delete root.__taurisTree;
        listeners.clear();
      },
    };
  }

  window.TaurisTree = { mount };
})();
