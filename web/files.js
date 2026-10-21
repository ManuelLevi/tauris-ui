// tauris-ui files: a place's shared files as a dense, sortable table. Plain
// JavaScript: no build step, no dependencies. In a Tauri app the plugin
// injects this file with its stylesheet (web/files.css), which is added on the
// first mount. Elsewhere (the demo page) load web/files.css with a <link>.
//
//   const files = TaurisFiles.mount(element, {
//     title: "Health", files: [...],
//     onAdd: paths => invoke("upload", { paths }),    // dropped or picked; resolve with the new files
//     onOpen: file => invoke("open_file", { id: file.id }),
//     onDelete: file => invoke("delete_file", { id: file.id }),
//   });
//   files.setFiles(next);                             // whenever the app's list changes
//
// A file is { id, name, size?, added?, by?, type?, kind? }. The app keeps the
// files wherever it likes (a server, a folder): the component shows them and
// hands every action to the app. Only the actions the app gives appear.
//
// Dropping files on the window adds them (Tauri's drag-and-drop events, read
// through window.__TAURI__); "Add files…" opens the system's picker through
// the plugin. Both end in onAdd(paths). A folder cannot be told from a file
// here: the app refuses folders where it reads the paths (in Rust,
// tauris_ui::files::inspect says why in a sentence), and the component shows
// that sentence.

(() => {
  "use strict";
  if (window.TaurisFiles) return;

  // Filled in by the plugin; left as is when the file is loaded on its own.
  const CSS = "__TAURIS_FILES_CSS__";
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

  // Icons, 16 x 16 strokes (search: 12 x 12). currentColor, so they follow the text.
  const svg = (box, d) => `<svg viewBox="0 0 ${box} ${box}" aria-hidden="true" focusable="false">${d}</svg>`;
  const ICONS = {
    upload: svg(16, '<path d="M8 11V3.5M5 6.2L8 3.2l3 3M3 12.5h10"/>'),
    open: svg(16, '<path d="M9 3h4v4M13 3L7.5 8.5M11.5 9.5V13H3V4.5h3.5"/>'),
    saveAs: svg(16, '<path d="M8 3v7.5M5 7.8l3 3 3-3M3 12.8h10"/>'),
    rename: svg(16, '<path d="M10.5 2.5l3 3L6 13H3v-3z"/>'),
    delete: svg(16, '<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5"/>'),
    search: svg(12, '<circle cx="5" cy="5" r="3.4"/><path d="M7.5 7.5L10.5 10.5"/>'),
  };

  const MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");

  // Every word the component shows. Pass `labels` to change any of them.
  const LABELS = {
    type: "Type",
    name: "Name",
    size: "Size",
    added: "Added",
    by: "By",
    actions: "Actions",
    add: "Add files…",
    search: "Search files",
    open: "Open",
    saveAs: "Save a copy…",
    rename: "Rename",
    delete: "Delete",
    cancel: "Cancel",
    count: n => (n === 1 ? "1 file" : `${n.toLocaleString()} files`),
    list: place => `Files in ${place}. Arrow keys move, Enter opens.`,
    pickTitle: place => `Add files to ${place}`,
    emptyTitle: place => `No files in ${place} yet`,
    emptyText: "Drop files anywhere on this window, or add them.",
    noMatch: query => `No files match “${query}”.`,
    drop: place => `Drop to add to ${place}`,
    dropHint: "",
    adding: n => (n === 1 ? "Adding 1 file…" : `Adding ${n} files…`),
    addedFiles: (files, place) => (files.length === 1 ? `Added ${files[0].name} to ${place}.` : `Added ${files.length} files to ${place}.`),
    opening: file => `Opening ${file.name}…`,
    opened: file => `Opened ${file.name}.`,
    saved: file => `Saved a copy of ${file.name}.`,
    renamed: (file, name) => `Renamed ${file.name} to ${name}.`,
    nameNeeded: "Give the file a name.",
    confirmDelete: file => `Delete “${file.name}”? This cannot be undone.`,
    deleted: file => `Deleted ${file.name}.`,
    confirmDeleteMany: files => `Delete ${files.length} files? This cannot be undone.`,
    deletedMany: files => `Deleted ${files.length} files.`,
    openingMany: files => `Opening ${files.length} files…`,
    openedMany: files => `Opened ${files.length} files.`,
  };

  const COLUMNS = ["kind", "name", "size", "added", "by"];
  const SORTABLE = new Set(["name", "size", "added", "by"]);

  const DEFAULTS = {
    // the files: [{ id, name, size?, added?, by?, type?, kind? }]
    files: [],
    // the heading, and the place in "Drop to add to …" (unless `place` says otherwise)
    title: "Files",
    place: null,
    // a word before the count in the header ("Documents · 3 files · 2.1 MB")
    subtitle: "",
    // a colour chip before the heading (any CSS colour)
    color: null,
    // the columns, in order: kind, name, size, added, by (the actions come last)
    columns: COLUMNS,
    // the first order: { key: "name" | "size" | "added" | "by", up: true }
    sort: { key: "name", up: true },
    // the header with the heading, "Add files…" and the search field
    header: true,
    search: true,
    // where a drop adds files: "window" (anywhere on it), "element" (over the
    // component only) or "none"
    dropArea: "window",
    // ask before onDelete: true (the component asks), false (the app asks), or
    // a function (file) => the question. Several files at once are asked about
    // with labels.confirmDeleteMany.
    confirmDelete: true,
    // how a date shows in the Added column; the default is short ("21 Oct")
    formatDate: null,
    // the picker: (title) => Promise<string[]>; the default is the system's, through the plugin
    pick: null,
    labels: {},
    // the app's side; each is optional and may return a Promise
    onAdd: null, // (paths) => the added files
    onOpen: null, // (file)
    onSaveAs: null, // (file) => false when the person cancels
    onRename: null, // (file, name)
    onDelete: null, // (file)
    onSelect: null, // (file | null, files): the file with the focus, and every selected file
    // ⌘-click (Ctrl-click) and Shift-click select several files; ⌘A selects them all.
    // Off by default: an app turns it on when its own actions use selection().
    multiple: false,
    // the row's menu (right click, Shift+F10) opening and closing, as TaurisMenu's bar and buttons say it:
    // ({ label, how: "mouse" | "keyboard" }) and ({ label, chosen })
    onMenuOpen: null,
    onMenuClose: null,
    // (text, kind) with kind "info" | "ok" | "error"; without it, the component shows them itself
    onMessage: null,
    // add the stylesheet (false: bring your own)
    styles: true,
  };

  // ---------- helpers anyone can use ----------

  const KINDS = [
    ["PDF", t => t === "application/pdf", ["pdf"]],
    ["IMG", t => t.startsWith("image/"), ["png", "jpg", "jpeg", "gif", "webp", "heic", "heif", "svg", "tif", "tiff", "bmp", "avif"]],
    ["VID", t => t.startsWith("video/"), ["mp4", "mov", "m4v", "avi", "mkv", "webm"]],
    ["AUD", t => t.startsWith("audio/"), ["mp3", "m4a", "wav", "aac", "flac", "ogg"]],
    ["XLS", t => t.includes("spreadsheet") || t.includes("excel") || t === "text/csv" || t.includes("numbers"), ["xls", "xlsx", "csv", "numbers", "ods", "tsv"]],
    ["PPT", t => t.includes("presentation") || t.includes("powerpoint") || t.includes("keynote"), ["ppt", "pptx", "key", "odp"]],
    ["DOC", t => t.includes("word") || t === "application/rtf" || t.includes("pages") || t.includes("opendocument.text"), ["doc", "docx", "pages", "rtf", "odt"]],
    ["ZIP", t => t.includes("zip") || t.includes("compressed") || t.includes("x-tar") || t.includes("x-7z") || t.includes("rar"), ["zip", "gz", "tgz", "tar", "7z", "rar", "bz2", "xz"]],
    ["TXT", t => t.startsWith("text/"), ["txt", "md"]],
  ];

  const extOf = name => {
    const n = String(name ?? "");
    const dot = n.lastIndexOf(".");
    return dot > 0 && dot < n.length - 1 ? n.slice(dot + 1).toLowerCase() : "";
  };

  /** A short label for the kind of file (PDF, IMG, DOC, XLS…), from its type or extension. */
  function kindOf(file) {
    if (file?.kind) return String(file.kind).toUpperCase().slice(0, 4);
    const ext = extOf(file?.name);
    const t = String(file?.type ?? "").toLowerCase();
    for (const [kind, byType, exts] of KINDS) if ((t && byType(t)) || exts.includes(ext)) return kind;
    return ext ? ext.slice(0, 3).toUpperCase() : "FILE";
  }

  /** "0 KB", "240 KB", "2.4 MB", "1.2 GB". */
  function formatSize(bytes) {
    const n = Number(bytes);
    if (!Number.isFinite(n) || n < 0) return "—";
    if (n === 0) return "0 KB";
    const MB = 1024 * 1024;
    if (n < MB) return Math.max(1, Math.round(n / 1024)).toLocaleString("en-US") + " KB";
    if (n < 1024 * MB) return (n / MB).toLocaleString("en-US", { maximumFractionDigits: 1 }) + " MB";
    return (n / (1024 * MB)).toLocaleString("en-US", { maximumFractionDigits: 1 }) + " GB";
  }

  // A date from a Date, a number (ms) or a string: "2026-10-21", ISO, or
  // "2026-10-21 10:04:00.123Z" (PocketBase). A plain day is a local day.
  function dateOf(value) {
    if (value == null || value === "") return null;
    if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
    if (typeof value === "number") return Number.isFinite(value) ? new Date(value) : null;
    const s = String(value).trim();
    const day = /^(\d{4})-(\d\d)-(\d\d)$/.exec(s);
    if (day) return new Date(Number(day[1]), Number(day[2]) - 1, Number(day[3]));
    const d = new Date(s.replace(/^(\d{4}-\d\d-\d\d) /, "$1T"));
    return Number.isNaN(d.getTime()) ? null : d;
  }

  const shortDay = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });
  const shortDayYear = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "2-digit" });
  const longDate = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
  function formatDay(date) {
    return (date.getFullYear() === new Date().getFullYear() ? shortDay : shortDayYear).format(date);
  }

  function invoke(command, args) {
    const core = window.__TAURI__?.core;
    if (!core?.invoke) return Promise.reject(new Error("Native file dialogs need Tauri (app.withGlobalTauri) and the tauris-ui plugin."));
    return core.invoke(`plugin:tauris-ui|${command}`, args);
  }

  /** The system's picker: the paths the person chose, or [] if they cancel. */
  async function pick(options = {}) {
    const paths = await invoke("pick_files", { title: options.title ?? null, multiple: options.multiple !== false });
    return Array.isArray(paths) ? paths : [];
  }

  /** The system's save dialog, with a name filled in: the chosen path, or null if they cancel. */
  async function saveDialog(options = {}) {
    return (await invoke("save_dialog", { title: options.title ?? null, name: options.name ?? null })) ?? null;
  }

  const textOf = e => (e instanceof Error ? e.message : typeof e === "string" ? e : e && typeof e.message === "string" ? e.message : String(e));

  // ---------- the component ----------

  let uid = 0;

  function el(tag, className, attrs = {}, ...children) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    for (const [k, v] of Object.entries(attrs)) if (v != null) node.setAttribute(k, v);
    node.append(...children.flat().filter(c => c != null));
    return node;
  }

  function icon(name) {
    const span = el("span", "tf-icon", { "aria-hidden": "true" });
    span.innerHTML = ICONS[name];
    return span;
  }

  // Not a <button> (an app's plain button rule would restyle it): a span that
  // Enter and Space press, and aria-disabled turns off. Space presses on
  // release, and only the control it went down on: a Space that chose a
  // menu item must not also press the button that takes the focus next.
  function pressable(node, fn) {
    const off = () => node.getAttribute("aria-disabled") === "true";
    let spaceDown = false;
    node.addEventListener("click", e => {
      if (off()) return;
      fn(e);
    });
    node.addEventListener("keydown", e => {
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === "Enter") {
        e.preventDefault();
        e.stopPropagation();
        if (!e.repeat && !off()) fn(e);
      } else if (e.key === " ") {
        e.preventDefault();
        e.stopPropagation();
        spaceDown = true;
      }
    });
    node.addEventListener("keyup", e => {
      if (e.key !== " ") return;
      const pressed = spaceDown;
      spaceDown = false;
      if (!pressed || off()) return;
      e.preventDefault();
      fn(e);
    });
    node.addEventListener("blur", () => {
      spaceDown = false;
    });
    return node;
  }

  function mount(root, options = {}) {
    if (!(root instanceof HTMLElement)) throw new Error("TaurisFiles.mount needs the element to draw the files in");
    if (root.__taurisFiles) throw new Error("TaurisFiles.mount: this element already has files; call destroy() first");
    root.__taurisFiles = true;
    const opt = { ...DEFAULTS, ...options };
    if (opt.styles) addStyles();
    const id = `tf-${++uid}`;
    const life = new AbortController();
    const signal = life.signal;
    const L = () => ({ ...LABELS, ...(opt.labels || {}) });
    const say = (v, ...args) => (typeof v === "function" ? v(...args) : v);
    const place = () => String(opt.place ?? opt.title ?? "");

    let list = [];
    let sort = { key: SORTABLE.has(opt.sort?.key) ? opt.sort.key : "name", up: opt.sort?.up !== false };
    let query = "";
    let selId = null; // the file with the focus
    let sel = new Set(); // every selected file (selId among them)
    let anchor = null; // where a Shift-click range starts
    let shown = []; // the visible files, in order
    let rows = new Map(); // id -> row element
    let fresh = new Set();
    let freshTimer = 0;
    let queue = Promise.resolve();
    let busyText = null;
    let dropping = false;
    let dragFiles = false;
    let renaming = null; // { file, input, busy }
    let asking = null; // the delete question, while it is open
    let held = null; // a list given while renaming, drawn when it ends
    let messageTimer = 0;
    let rowMenuHandle = null;
    const deleting = new Set();
    let unlisten = null;

    const keyOf = v => String(v);
    const fileById = key => list.find(f => keyOf(f.id) === key) ?? null;

    // ---------- the parts ----------

    const addedClass = !root.classList.contains("tf");
    root.classList.add("tf");

    const chip = el("span", "tf-chip", { "aria-hidden": "true", hidden: "" });
    const title = el("span", "tf-title", { role: "heading", "aria-level": "2" });
    const sub = el("span", "tf-sub");
    const addBtn = pressable(el("span", "tf-btn tf-add", { role: "button", tabindex: "0" }), () => add());
    const addText = el("span");
    addBtn.append(icon("upload"), addText);
    const searchInput = el("input", "tf-q", { type: "search", id: `${id}-q`, autocomplete: "off", spellcheck: "false" });
    const searchBox = el("span", "tf-search", {}, icon("search"), searchInput);
    const head = el("div", "tf-head", {}, chip, title, sub, addBtn, el("span", "tf-grow"), searchBox);

    const headRow = el("div", "tf-row tf-headrow", { role: "row" });
    const table = el("div", "tf-table", { role: "presentation" },
      el("div", "tf-thead", { role: "rowgroup" }, headRow));
    const tbody = el("div", "tf-tbody", { role: "rowgroup" });
    table.append(tbody);
    const grid = el("div", "tf-list", { role: "grid", tabindex: "0", "aria-readonly": "true", "aria-multiselectable": String(opt.multiple === true) }, table);

    const emptyTitle = el("div", "tf-empty-title");
    const emptyText = el("div", "tf-empty-text");
    const emptyAdd = pressable(el("span", "tf-btn tf-primary", { role: "button", tabindex: "0" }), () => add());
    const empty = el("div", "tf-empty", { hidden: "" }, emptyTitle, emptyText, emptyAdd);
    const noMatch = el("div", "tf-nomatch", { role: "status", hidden: "" });
    const dropText = el("span", "tf-drop-title");
    const dropHint = el("span", "tf-drop-hint");
    const drop = el("div", "tf-drop", { "aria-hidden": "true", hidden: "" }, icon("upload"), dropText, dropHint);
    const seg = el("span", "tf-seg", { "aria-hidden": "true" });
    for (let i = 0; i < 20; i++) {
      const s = el("i");
      s.style.setProperty("--tf-i", String(i));
      seg.append(s);
    }
    const busyLabel = el("span");
    const busy = el("div", "tf-busy", { role: "status", hidden: "" }, seg, busyLabel);
    const askText = el("div", "tf-ask-text", { id: `${id}-ask` });
    const askNo = el("span", "tf-btn", { role: "button", tabindex: "0" });
    const askYes = el("span", "tf-btn tf-danger", { role: "button", tabindex: "0" });
    const askCard = el("div", "tf-ask", { role: "alertdialog", "aria-modal": "true", "aria-labelledby": `${id}-ask` },
      askText, el("div", "tf-ask-acts", {}, askNo, askYes));
    const veil = el("div", "tf-veil", { hidden: "" }, askCard);
    pressable(askYes, () => asking?.finish(true));
    pressable(askNo, () => asking?.finish(false));
    const panel = el("div", "tf-panel", {}, grid, empty, noMatch, drop, busy, veil);
    const status = el("div", "tf-status", { role: "status", "aria-live": "polite" });

    root.replaceChildren(head, panel, status);

    // ---------- messages ----------

    function message(text, kind = "info") {
      if (!text || signal.aborted) return;
      if (typeof opt.onMessage === "function") {
        opt.onMessage(text, kind);
        return;
      }
      status.textContent = text;
      status.dataset.kind = kind;
      clearTimeout(messageTimer);
      messageTimer = setTimeout(() => {
        status.textContent = "";
        delete status.dataset.kind;
      }, 6000);
    }

    // ---------- drawing ----------

    const columns = () => (Array.isArray(opt.columns) ? opt.columns.filter(c => COLUMNS.includes(c)) : COLUMNS);
    const actions = () => [
      ["open", opt.onOpen], ["saveAs", opt.onSaveAs], ["rename", opt.onRename], ["delete", opt.onDelete],
    ].filter(([, fn]) => typeof fn === "function").map(([name]) => name);

    function drawHead() {
      const words = L();
      const had = headRow.contains(document.activeElement) ? document.activeElement.closest(".tf-th")?.dataset.col : null;
      headRow.replaceChildren();
      for (const col of columns()) {
        const cell = el("div", `tf-th tf-c-${col}`, { role: "columnheader", "data-col": col });
        if (col === "kind") {
          cell.setAttribute("aria-label", words.type);
        } else {
          const on = sort.key === col;
          cell.setAttribute("aria-sort", on ? (sort.up ? "ascending" : "descending") : "none");
          const btn = pressable(el("span", "tf-sort", { role: "button", tabindex: "0" }, String(words[col])), () => sortBy(col));
          if (on) btn.append(el("span", "tf-arrow", { "aria-hidden": "true" }, sort.up ? "▲" : "▼"));
          cell.append(btn);
        }
        headRow.append(cell);
      }
      if (actions().length) headRow.append(el("div", "tf-th tf-c-acts", { role: "columnheader", "aria-label": words.actions }));
      if (had) headRow.querySelector(`[data-col="${had}"] .tf-sort`)?.focus({ preventScroll: true });
    }

    function sortBy(col) {
      if (!SORTABLE.has(col)) return;
      // A new column starts the way people look at it: names A to Z, the
      // biggest and newest first. The same column again turns it around.
      sort = sort.key === col ? { key: col, up: !sort.up } : { key: col, up: col === "name" || col === "by" };
      draw();
    }

    const collator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });

    function visible() {
      const q = query.trim().toLowerCase();
      const out = q ? list.filter(f => String(f.name ?? "").toLowerCase().includes(q)) : list.slice();
      const dir = sort.up ? 1 : -1;
      const byName = (a, b) => collator.compare(String(a.name ?? ""), String(b.name ?? ""));
      const time = new Map(out.map(f => [f, dateOf(f.added)?.getTime() ?? -Infinity]));
      const size = f => (Number.isFinite(Number(f.size)) ? Number(f.size) : -1);
      out.sort((a, b) => {
        let c;
        if (sort.key === "size") c = size(a) - size(b);
        else if (sort.key === "added") c = time.get(a) === time.get(b) ? 0 : time.get(a) < time.get(b) ? -1 : 1;
        else if (sort.key === "by") c = collator.compare(String(a.by ?? ""), String(b.by ?? ""));
        else return byName(a, b) * dir;
        return c * dir || byName(a, b);
      });
      return out;
    }

    function drawRow(file, index, cols, acts, words) {
      const key = keyOf(file.id);
      const row = el("div", "tf-row tf-file", { role: "row", id: `${id}-r${index}`, "aria-selected": "false" });
      row.__tfKey = key;
      for (const col of cols) {
        const cell = el("div", `tf-cell tf-c-${col}`, { role: "gridcell" });
        if (col === "kind") {
          const kind = kindOf(file);
          cell.append(el("span", "tf-kind", { "data-kind": kind }, kind));
        } else if (col === "name") {
          const name = String(file.name ?? "");
          cell.title = name;
          cell.append(el("span", "tf-name", {}, name));
        } else if (col === "size") {
          cell.textContent = file.size == null ? "—" : formatSize(file.size);
        } else if (col === "added") {
          const d = dateOf(file.added);
          cell.textContent = d ? (typeof opt.formatDate === "function" ? String(opt.formatDate(d, file)) : formatDay(d)) : "—";
          if (d) cell.title = longDate.format(d);
        } else if (col === "by") {
          cell.textContent = file.by ? String(file.by) : "—";
        }
        row.append(cell);
      }
      if (acts.length) {
        const box = el("span", "tf-acts");
        for (const act of acts) {
          const text = String(words[act]);
          const b = el("span", `tf-ib tf-ib-${act}`, { role: "button", tabindex: "-1", title: text, "aria-label": `${text}: ${file.name}`, "data-act": act });
          b.append(icon(act));
          box.append(b);
        }
        row.append(el("div", "tf-cell tf-c-acts", { role: "gridcell" }, box));
      }
      if (fresh.has(key)) row.classList.add("tf-fresh");
      return row;
    }

    const FIELDS = ["id", "name", "size", "added", "by", "type", "kind"];
    const signature = files => JSON.stringify(files.map(f => FIELDS.map(k => (f[k] instanceof Date ? f[k].getTime() : f[k] ?? null))));
    let drawn = null;

    function draw() {
      if (renaming || signal.aborted) return;
      drawn = signature(list);
      const words = L();
      const total = list.reduce((n, f) => n + (Number.isFinite(Number(f.size)) ? Number(f.size) : 0), 0);
      title.textContent = String(opt.title ?? "");
      if (opt.color) {
        chip.style.setProperty("--tf-chip", String(opt.color));
        chip.hidden = false;
      } else {
        chip.hidden = true;
      }
      const subtitle = opt.subtitle ? `${opt.subtitle} · ` : "";
      sub.textContent = subtitle + say(words.count, list.length) + (list.length ? ` · ${formatSize(total)}` : "");
      addText.textContent = String(words.add);
      emptyAdd.textContent = String(words.add);
      const canAdd = typeof opt.onAdd === "function";
      addBtn.hidden = !canAdd;
      emptyAdd.hidden = !canAdd;
      for (const b of [addBtn, emptyAdd]) b.setAttribute("aria-disabled", busyText ? "true" : "false");
      searchInput.placeholder = String(words.search);
      searchInput.setAttribute("aria-label", String(words.search));
      searchBox.hidden = !opt.search || list.length === 0;
      head.hidden = !opt.header;
      status.hidden = typeof opt.onMessage === "function";
      // A part that is not shown leaves no gap: the list takes its room.
      root.classList.toggle("tf-no-head", head.hidden);
      root.classList.toggle("tf-no-status", status.hidden);
      grid.setAttribute("aria-label", say(words.list, place()));
      grid.setAttribute("aria-multiselectable", String(several()));
      emptyTitle.textContent = say(words.emptyTitle, place());
      emptyText.textContent = say(words.emptyText, place());
      dropText.textContent = say(words.drop, place());
      dropHint.textContent = say(words.dropHint, place());
      dropHint.hidden = !dropHint.textContent;
      askNo.textContent = String(words.cancel);
      askYes.textContent = String(words.delete);

      // A selected file the app no longer has is not selected any more.
      const oldAt = selId != null ? shown.findIndex(f => keyOf(f.id) === selId) : -1;
      const hadSelection = sel.size > 0;
      const have = new Set(list.map(f => keyOf(f.id)));
      const lost = [...sel].filter(k => !have.has(k));
      const lostFocus = selId != null && !have.has(selId);
      if (lost.length || lostFocus) {
        for (const k of lost) sel.delete(k);
        if (lostFocus) selId = null;
        if (anchor != null && !have.has(anchor)) anchor = selId;
      }
      drawHead();
      shown = visible();
      const cols = columns();
      const acts = actions();
      rows = new Map();
      const frag = document.createDocumentFragment();
      shown.forEach((file, i) => {
        const row = drawRow(file, i, cols, acts, words);
        rows.set(row.__tfKey, row);
        frag.append(row);
      });
      tbody.replaceChildren(frag);
      root.classList.toggle("tf-has-acts", acts.length > 0);
      root.style.setProperty("--tf-acts-n", String(acts.length));
      grid.hidden = list.length === 0;
      empty.hidden = list.length !== 0;
      noMatch.hidden = !(list.length && !shown.length);
      noMatch.textContent = noMatch.hidden ? "" : say(words.noMatch, query.trim());
      // The only selected file is gone from the app's list: the file now in its
      // place takes the selection and the focus, as in a file manager (and the tree).
      if (hadSelection && !sel.size && oldAt >= 0 && shown.length && !list.some(f => keyOf(f.id) === selId)) {
        const k = keyOf(shown[Math.min(oldAt, shown.length - 1)].id);
        sel = new Set([k]);
        selId = anchor = k;
      }
      // The file with the focus hidden by a search: the focus goes to a selected file that is shown.
      if (selId != null && !rows.has(selId)) {
        const visible = shown.find(f => sel.has(keyOf(f.id)));
        if (visible) selId = keyOf(visible.id);
      }
      paintSelection(false);
      report();
    }

    function current() {
      return selId != null && rows.has(selId) ? fileById(selId) : null;
    }

    // The selected file the app should think of first: the one with the focus
    // when it is selected, otherwise the first selected file shown.
    function primary() {
      const file = current();
      if (file && sel.has(keyOf(file.id))) return file;
      return selection()[0] ?? null;
    }

    // The selected files that are shown, top to bottom (a search hides the others,
    // and nothing hidden is ever opened or deleted).
    function selection() {
      return shown.filter(f => sel.has(keyOf(f.id))).map(f => fileById(keyOf(f.id)) ?? f);
    }

    function paintSelection(scroll) {
      let active = null;
      for (const [key, row] of rows) {
        row.setAttribute("aria-selected", sel.has(key) ? "true" : "false");
        row.classList.toggle("tf-focused", key === selId);
        if (key === selId) active = row;
      }
      grid.classList.toggle("tf-many", sel.size > 1);
      if (active) {
        grid.setAttribute("aria-activedescendant", active.id);
        if (scroll) active.scrollIntoView({ block: "nearest" });
      } else {
        grid.removeAttribute("aria-activedescendant");
      }
    }

    // The selection becomes these keys, with the focus on `focus`.
    function setSelection(keys, focus, scroll = true) {
      if (signal.aborted) return;
      sel = new Set(keys);
      selId = focus;
      paintSelection(scroll);
      report();
    }

    // onSelect hears what the person can act on (the file with the focus and the
    // selected files shown) each time that changes, whatever changed it.
    let reported = "|";
    function report() {
      if (signal.aborted || typeof opt.onSelect !== "function") return;
      const file = primary();
      const files = selection();
      const now = `${file ? keyOf(file.id) : ""}|${files.map(f => keyOf(f.id)).join("\u0000")}`;
      if (now === reported) return;
      reported = now;
      opt.onSelect(file, files);
    }

    // One file alone (null: none).
    function select(key, scroll = true) {
      const k = key == null ? null : keyOf(key);
      anchor = k;
      setSelection(k == null ? [] : [k], k, scroll);
    }

    // The files from the anchor to `key`, as shown.
    function range(key) {
      const keys = shown.map(f => keyOf(f.id));
      const a = keys.indexOf(anchor ?? key);
      const b = keys.indexOf(key);
      if (a < 0 || b < 0) return [key];
      return keys.slice(Math.min(a, b), Math.max(a, b) + 1);
    }

    const several = () => opt.multiple === true;

    // The selected file nearest to `key` (in the order shown), for the focus to go to.
    function nearestSelected(keys, key) {
      const order = shown.map(f => keyOf(f.id));
      const at = order.indexOf(key);
      let best = null;
      let gap = Infinity;
      order.forEach((k, i) => {
        if (keys.has(k) && Math.abs(i - at) < gap) {
          best = k;
          gap = Math.abs(i - at);
        }
      });
      return best;
    }

    // Where the focus goes for a selection of every file shown: where it is, if shown.
    const focusAmongShown = () => (selId != null && rows.has(selId) ? selId : shown[0] ? keyOf(shown[0].id) : null);

    // ---------- the app's actions ----------

    // One add at a time: a second drop waits for the first to finish.
    function run(text, job) {
      const step = queue.then(async () => {
        setBusy(text);
        try {
          return await job();
        } finally {
          setBusy(null);
        }
      });
      queue = step.catch(() => {});
      return step;
    }

    function setBusy(text) {
      busyText = text || null;
      busy.hidden = !busyText;
      busyLabel.textContent = busyText ?? "";
      for (const b of [addBtn, emptyAdd]) b.setAttribute("aria-disabled", busyText ? "true" : "false");
    }

    async function addPaths(paths) {
      const items = (Array.isArray(paths) ? paths : []).map(String).filter(Boolean);
      if (!items.length || typeof opt.onAdd !== "function") return [];
      try {
        const out = await run(say(L().adding, items.length), () => opt.onAdd(items.slice()));
        const added = (Array.isArray(out) ? out : []).filter(f => f && f.id != null);
        if (!added.length || signal.aborted) return added;
        // The app may send its new list before or after this; until it does, the new files show.
        const have = new Set(list.map(f => keyOf(f.id)));
        const missing = added.filter(f => !have.has(keyOf(f.id)));
        if (missing.length) list = list.concat(missing);
        fresh = new Set(added.map(f => keyOf(f.id)));
        clearTimeout(freshTimer);
        freshTimer = setTimeout(() => {
          fresh = new Set();
          for (const row of rows.values()) row.classList.remove("tf-fresh");
        }, 1400);
        if (query && !added.some(f => String(f.name ?? "").toLowerCase().includes(query.trim().toLowerCase()))) {
          query = "";
          searchInput.value = "";
        }
        draw();
        // Every file just added is selected, the first one with the focus.
        anchor = keyOf(added[0].id);
        setSelection(added.map(f => keyOf(f.id)), anchor);
        message(say(L().addedFiles, added, place()), "ok");
        return added;
      } catch (e) {
        message(textOf(e), "error");
        return [];
      }
    }

    async function add() {
      if (typeof opt.onAdd !== "function" || busyText) return [];
      let paths;
      try {
        const titleText = say(L().pickTitle, place());
        paths = typeof opt.pick === "function" ? await opt.pick(titleText) : await pick({ title: titleText });
      } catch (e) {
        message(textOf(e), "error");
        return [];
      }
      return signal.aborted ? [] : addPaths(paths);
    }

    async function open(file) {
      if (!file || typeof opt.onOpen !== "function") return;
      message(say(L().opening, file), "info");
      try {
        await opt.onOpen(file);
        message(say(L().opened, file), "ok");
      } catch (e) {
        message(textOf(e), "error");
      }
    }

    // Several files open one after the other; the first refusal stops the rest.
    // The app's current object for each key, leaving out files that have gone.
    const fresh_ = keys => keys.map(k => fileById(k)).filter(Boolean);

    async function openMany(files) {
      if (files.length < 2) return open(files[0]);
      if (typeof opt.onOpen !== "function") return;
      message(say(L().openingMany, files), "info");
      for (const k of files.map(f => keyOf(f.id))) {
        const f = fileById(k);
        if (!f) continue; // gone meanwhile
        try {
          await opt.onOpen(f);
        } catch (e) {
          message(textOf(e), "error");
          return;
        }
        if (signal.aborted) return;
      }
      message(say(L().openedMany, files), "ok");
    }

    async function saveAs(file) {
      if (!file || typeof opt.onSaveAs !== "function") return;
      try {
        if ((await opt.onSaveAs(file)) !== false) message(say(L().saved, file), "ok");
      } catch (e) {
        message(textOf(e), "error");
      }
    }

    async function remove(file) {
      if (!file || typeof opt.onDelete !== "function") return;
      const key = keyOf(file.id);
      if (deleting.has(key)) return;
      const question = opt.confirmDelete === false ? null
        : typeof opt.confirmDelete === "function" ? opt.confirmDelete(file) : say(L().confirmDelete, file);
      if (question && !(await ask(String(question)))) return;
      if (deleting.has(key) || signal.aborted) return;
      // The app may have sent a new list while the question was open.
      file = fileById(key);
      if (!file) return;
      // The next row takes the selection, as in a file manager.
      const before = shown.slice();
      const at = Math.max(0, before.findIndex(f => keyOf(f.id) === key));
      const wasSelected = selId === key;
      deleting.add(key);
      try {
        await opt.onDelete(file);
      } catch (e) {
        message(textOf(e), "error");
        return;
      } finally {
        deleting.delete(key);
      }
      if (signal.aborted) return;
      list = list.filter(f => keyOf(f.id) !== key);
      if (wasSelected && (selId === key || selId === null)) {
        const left = new Set(list.map(f => keyOf(f.id)));
        const rest = before.filter(f => keyOf(f.id) !== key && left.has(keyOf(f.id)));
        const next = rest[Math.min(at, rest.length - 1)];
        const k = next ? keyOf(next.id) : null;
        sel = new Set(k == null ? [] : [k]);
        selId = anchor = k;
        draw();
        paintSelection(true);
      } else {
        draw();
      }
      message(say(L().deleted, file), "ok");
      if (!root.contains(document.activeElement) || document.activeElement === document.body) focusList();
    }

    // Several files: one question, then onDelete for each, one after the other.
    // The first refusal stops the rest; the ones already gone stay gone.
    async function removeMany(files) {
      files = files.filter(f => !deleting.has(keyOf(f.id)));
      if (files.length < 2) return remove(files[0]);
      if (typeof opt.onDelete !== "function") return;
      // Several files are asked about with labels.confirmDeleteMany, never with the
      // app's confirmDelete function: one written for a single file would name one
      // while several go.
      const question = opt.confirmDelete === false ? null : say(L().confirmDeleteMany, files);
      if (question && !(await ask(String(question)))) return;
      if (signal.aborted) return;
      // The app may have sent a new list while the question was open.
      files = fresh_(files.map(f => keyOf(f.id)));
      if (!files.length) return;
      const before = shown.slice();
      const keys = new Set(files.map(f => keyOf(f.id)));
      const last = Math.max(...before.map((f, i) => (keys.has(keyOf(f.id)) ? i : -1)));
      const gone = new Set();
      let failed = false;
      for (const f of files) {
        const k = keyOf(f.id);
        if (deleting.has(k)) continue;
        deleting.add(k);
        try {
          await opt.onDelete(f);
          gone.add(k);
        } catch (e) {
          message(textOf(e), "error");
          failed = true;
        } finally {
          deleting.delete(k);
        }
        if (failed || signal.aborted) break;
      }
      if (signal.aborted || !gone.size) return;
      list = list.filter(f => !gone.has(keyOf(f.id)));
      // The file after the last one deleted takes the selection, as in a file manager.
      const left = new Set(list.map(f => keyOf(f.id)));
      const next = before.slice(last + 1).find(f => left.has(keyOf(f.id)))
        ?? before.slice(0, Math.max(0, last)).reverse().find(f => left.has(keyOf(f.id)));
      const k = next ? keyOf(next.id) : null;
      sel = new Set(k == null ? [] : [k]);
      selId = anchor = k;
      draw();
      paintSelection(true);
      if (!failed) message(say(L().deletedMany, files.filter(f => gone.has(keyOf(f.id)))), "ok");
      if (!root.contains(document.activeElement) || document.activeElement === document.body) focusList();
    }

    // The delete question: a small card over the list, Cancel focused. The red
    // button deletes; Escape, Cancel or a click beside it keeps the file.
    function ask(question) {
      if (asking) asking.finish(false);
      return new Promise(resolve => {
        const back = document.activeElement;
        askText.textContent = question;
        veil.hidden = false;
        const done = new AbortController();
        const finish = (yes, refocus = true) => {
          if (asking !== state) return;
          asking = null;
          done.abort();
          veil.hidden = true;
          if (refocus && !signal.aborted) {
            if (back instanceof HTMLElement && back.isConnected && root.contains(back)) back.focus({ preventScroll: true });
            else focusList();
          }
          resolve(yes);
        };
        const state = { finish };
        asking = state;
        veil.addEventListener("pointerdown", e => {
          if (e.target === veil) finish(false);
        }, { signal: done.signal });
        // Going elsewhere in the window (the search field, a menu) is a no;
        // switching to another app is not.
        askCard.addEventListener("focusout", e => {
          if (askCard.contains(e.relatedTarget) || (e.relatedTarget == null && !document.hasFocus())) return;
          finish(false, false);
        }, { signal: done.signal });
        askCard.addEventListener("keydown", e => {
          if (e.key === "Escape") {
            e.preventDefault();
            e.stopPropagation();
            finish(false);
          } else if (e.key === "Tab") {
            e.preventDefault();
            (document.activeElement === askYes ? askNo : askYes).focus();
          }
        }, { signal: done.signal });
        // The safe answer has the focus: Tab reaches the red one.
        askNo.focus({ preventScroll: true });
      });
    }

    // ---------- renaming in place ----------

    function rename(file) {
      if (!file || typeof opt.onRename !== "function" || renaming) return;
      if (asking) asking.finish(false);
      const key = keyOf(file.id);
      if (!rows.has(key)) {
        query = "";
        searchInput.value = "";
        draw();
      }
      select(key);
      const row = rows.get(key);
      const cell = row?.querySelector(".tf-c-name");
      if (!cell) return;
      const name = String(file.name ?? "");
      const input = el("input", "tf-rename", { type: "text", value: name, spellcheck: "false", autocomplete: "off", "aria-label": `${L().rename}: ${name}` });
      input.value = name;
      cell.classList.add("tf-renaming");
      cell.replaceChildren(input);
      const state = { file, input, busy: false };
      renaming = state;
      input.focus({ preventScroll: true });
      // The name without its extension is selected, as in a file manager.
      const dot = name.lastIndexOf(".");
      input.setSelectionRange(0, dot > 0 ? dot : name.length);

      const end = () => {
        if (renaming !== state) return;
        renaming = null;
        if (held) {
          list = held;
          held = null;
        }
        // Back to the list, unless the person has gone to another field meanwhile.
        const stay = document.activeElement === input || document.activeElement === document.body || !document.activeElement;
        draw();
        if (stay) focusList();
      };
      const commit = async () => {
        if (renaming !== state || state.busy) return;
        const next = input.value.trim();
        if (next === name) return end();
        if (!next) {
          message(String(L().nameNeeded), "error");
          input.focus();
          return;
        }
        state.busy = true;
        input.readOnly = true;
        try {
          await opt.onRename(fileById(keyOf(file.id)) ?? file, next);
          if (signal.aborted) return;
        } catch (e) {
          state.busy = false;
          input.readOnly = false;
          message(textOf(e), "error");
          input.focus();
          input.select();
          return;
        }
        const k = keyOf(file.id);
        const swap = f => (keyOf(f.id) === k && f.name === name ? { ...f, name: next } : f);
        if (held) held = held.map(swap);
        else list = list.map(swap);
        message(say(L().renamed, file, next), "ok");
        end();
      };
      input.addEventListener("keydown", e => {
        e.stopPropagation();
        if (e.key === "Enter") {
          e.preventDefault();
          commit();
        } else if (e.key === "Escape") {
          e.preventDefault();
          end();
        }
      });
      // Clicking away saves, as in a file manager; switching to another app does not.
      input.addEventListener("blur", () => {
        if (renaming === state && !state.busy && document.hasFocus()) commit();
      });
      input.addEventListener("pointerdown", e => e.stopPropagation());
      input.addEventListener("dblclick", e => e.stopPropagation());
    }

    // ---------- the row menu ----------

    function rowMenu(file, at, keyboard) {
      if (!window.TaurisMenu || !file) return false;
      const words = L();
      const items = [];
      // On a row of a selection of several, the menu acts on all of them; saving a
      // copy and renaming take one file at a time.
      const keys = (sel.has(keyOf(file.id)) && selection().length > 1 ? selection() : [file]).map(f => keyOf(f.id));
      const one = keys.length === 1;
      const now = () => fresh_(keys); // the app may send a new list while the menu is open
      if (opt.onOpen) items.push({ label: words.open, shortcut: "↩", action: () => openMany(now()) });
      if (opt.onSaveAs) items.push({ label: words.saveAs, disabled: !one, action: () => saveAs(now()[0]) });
      if (opt.onRename) items.push({ label: words.rename, shortcut: "F2", disabled: !one, action: () => rename(now()[0]) });
      if (opt.onDelete) {
        if (items.length) items.push("-");
        items.push({ label: words.delete, shortcut: MAC ? "⌘⌫" : "Del", danger: true, action: () => removeMany(now()) });
      }
      if (!items.length) return false;
      const label = String(file.name ?? "");
      rowMenuHandle = window.TaurisMenu.open(items, at, {
        keyboard,
        label,
        returnTo: grid,
        onClose: info => {
          rowMenuHandle = null;
          if (!signal.aborted && typeof opt.onMenuClose === "function") opt.onMenuClose(info);
        },
      });
      if (typeof opt.onMenuOpen === "function") opt.onMenuOpen({ label, how: keyboard ? "keyboard" : "mouse" });
      return true;
    }

    // ---------- pointer and keyboard ----------

    function focusList() {
      if (!grid.hidden) grid.focus({ preventScroll: true });
      else if (!emptyAdd.hidden) emptyAdd.focus({ preventScroll: true });
    }

    const rowAt = target => {
      const row = target instanceof Element ? target.closest(".tf-file") : null;
      return row && tbody.contains(row) ? row : null;
    };

    tbody.addEventListener("pointerdown", e => {
      const row = rowAt(e.target);
      if (!row || e.button > 2) return;
      const k = row.__tfKey;
      const onButton = e.target.closest(".tf-ib") != null;
      const toggle = MAC ? e.metaKey : e.ctrlKey;
      const rightClick = e.button === 2 || (MAC && e.button === 0 && e.ctrlKey); // Control-click on a Mac
      if (!rightClick && several() && toggle && !onButton) {
        const next = new Set(sel);
        if (next.has(k)) next.delete(k);
        else next.add(k);
        anchor = k;
        setSelection(next, next.has(k) ? k : nearestSelected(next, k), false);
      } else if (!rightClick && several() && e.shiftKey && !onButton) {
        setSelection(range(k), k, false);
      } else if (rightClick && sel.has(k)) {
        // A right click on a selected file keeps the selection: its menu acts on all of them.
        setSelection(sel, k, false);
      } else {
        select(k, false);
      }
      e.preventDefault(); // no text selection; the focus stays on the list, even from a row's button
      grid.focus({ preventScroll: true });
    }, { signal });

    tbody.addEventListener("click", e => {
      const b = e.target instanceof Element ? e.target.closest(".tf-ib") : null;
      const row = rowAt(e.target);
      if (!b || !row) return;
      e.stopPropagation();
      const file = fileById(row.__tfKey);
      const act = b.dataset.act;
      if (act === "open") open(file);
      else if (act === "saveAs") saveAs(file);
      else if (act === "rename") rename(file);
      else if (act === "delete") remove(file);
    }, { signal });

    tbody.addEventListener("dblclick", e => {
      const row = rowAt(e.target);
      if (row && !e.target.closest(".tf-ib")) open(fileById(row.__tfKey));
    }, { signal });

    tbody.addEventListener("contextmenu", e => {
      const row = rowAt(e.target);
      if (!row) return;
      if (!sel.has(row.__tfKey)) select(row.__tfKey, false);
      if (rowMenu(fileById(row.__tfKey), { x: e.clientX, y: e.clientY }, false)) e.preventDefault();
    }, { signal });

    let typed = "";
    let typedAt = 0;
    grid.addEventListener("keydown", e => {
      const selectAll = (MAC ? e.metaKey : e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "a";
      if (selectAll && e.target !== grid && !(e.target instanceof HTMLInputElement)) e.preventDefault();
      if (e.target !== grid || e.isComposing || asking) return;
      const file = current();
      const i = file ? shown.indexOf(file) : -1;
      const page = Math.max(1, Math.floor(grid.clientHeight / (rows.values().next().value?.offsetHeight || 25)) - 1);
      // Shift extends the selection from the anchor, as in a file manager.
      const toggleKey = MAC ? e.metaKey : e.ctrlKey;
      const to = n => {
        e.preventDefault();
        if (!shown.length) return;
        const k = keyOf(shown[Math.max(0, Math.min(shown.length - 1, n))].id);
        if (e.shiftKey && several()) setSelection(range(k), k);
        else if (toggleKey && several()) setSelection(sel, k); // the focus moves; the selection stays
        else select(k);
      };
      const all = (MAC ? e.metaKey : e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "a";
      if (all) {
        // Inside the list ⌘A is never the page's own Select All.
        e.preventDefault();
        if (several()) setSelection(shown.map(f => keyOf(f.id)), focusAmongShown(), false);
      } else if (e.key === " " && !e.altKey && !e.shiftKey && several() && selId != null) {
        // Selects or unselects the file with the focus, keeping the others.
        e.preventDefault();
        const next = new Set(sel);
        if (next.has(selId)) next.delete(selId);
        else next.add(selId);
        anchor = selId;
        setSelection(next, selId);
      } else if (e.key === "ArrowDown") to(i < 0 ? 0 : i + 1);
      else if (e.key === "ArrowUp") to(i < 0 ? shown.length - 1 : i - 1);
      else if (e.key === "Home") to(0);
      else if (e.key === "End") to(shown.length - 1);
      else if (e.key === "PageDown") to(i < 0 ? page : i + page);
      else if (e.key === "PageUp") to(i < 0 ? 0 : i - page);
      // Enter, F2 and Delete act on the selected files, never on a file that only has the focus.
      else if (e.key === "Enter" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        if (selection().length) openMany(selection());
      } else if (e.key === "F2") {
        e.preventDefault();
        if (selection().length === 1) rename(selection()[0]);
      } else if (e.key === "Delete" || (e.key === "Backspace" && (e.metaKey || e.ctrlKey))) {
        e.preventDefault();
        if (selection().length) removeMany(selection());
      } else if (file && (e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey))) {
        // On a file that only has the focus, the menu selects it first, as a right click does.
        if (!sel.has(selId)) select(selId, false);
        const r = rows.get(keyOf(file.id))?.querySelector(".tf-c-name")?.getBoundingClientRect();
        if (r && rowMenu(file, { x: r.left + 12, y: r.bottom }, true)) e.preventDefault();
      } else if (e.key.length === 1 && e.key !== " " && !e.altKey && !e.ctrlKey && !e.metaKey) {
        // Typing jumps to the next file whose name starts with what was typed.
        const now = Date.now();
        typed = now - typedAt < 700 ? typed + e.key.toLowerCase() : e.key.toLowerCase();
        typedAt = now;
        const from = typed.length > 1 ? Math.max(i, 0) : i + 1;
        const order = shown.slice(from).concat(shown.slice(0, from));
        const hit = order.find(f => String(f.name ?? "").toLowerCase().startsWith(typed));
        if (hit) {
          e.preventDefault();
          select(hit.id);
        }
      }
    }, { signal });

    searchInput.addEventListener("input", () => {
      query = searchInput.value;
      draw();
    }, { signal });
    searchInput.addEventListener("keydown", e => {
      if (e.key === "ArrowDown" && shown.length) {
        e.preventDefault();
        if (!current()) select(shown[0].id);
        grid.focus({ preventScroll: true });
      } else if (e.key === "Escape" && searchInput.value) {
        e.preventDefault();
        e.stopPropagation();
        searchInput.value = "";
        query = "";
        draw();
      }
    }, { signal });
    // A click anywhere in the search box puts the caret in the field.
    searchBox.addEventListener("pointerdown", e => {
      if (e.target !== searchInput) {
        e.preventDefault();
        searchInput.focus();
      }
    }, { signal });

    // ---------- dropping files ----------

    function isShown() {
      return root.isConnected && root.getClientRects().length > 0;
    }

    function overMe(position) {
      if (opt.dropArea !== "element") return true;
      if (!position || !Number.isFinite(position.x) || !Number.isFinite(position.y)) return true;
      // Tauri reports physical pixels.
      const scale = window.devicePixelRatio || 1;
      const x = position.x / scale;
      const y = position.y / scale;
      const r = root.getBoundingClientRect();
      return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
    }

    function setDropping(on) {
      if (dropping === on) return;
      dropping = on;
      drop.hidden = !on;
      root.classList.toggle("tf-dropping", on);
    }

    function dragDrop(payload) {
      if (!payload || typeof payload !== "object") return;
      const type = payload.type;
      if (opt.dropArea === "none" || typeof opt.onAdd !== "function" || !isShown()) {
        setDropping(false);
        return;
      }
      if (type === "enter") {
        dragFiles = Array.isArray(payload.paths) ? payload.paths.length > 0 : true;
        setDropping(dragFiles && overMe(payload.position));
      } else if (type === "over") {
        setDropping(dragFiles && overMe(payload.position));
      } else if (type === "leave") {
        dragFiles = false;
        setDropping(false);
      } else if (type === "drop") {
        const inside = overMe(payload.position);
        dragFiles = false;
        setDropping(false);
        if (inside && Array.isArray(payload.paths) && payload.paths.length) addPaths(payload.paths);
      }
    }

    // Tauri's drag-and-drop events for this webview. The page's own listener
    // (getCurrentWebview().onDragDropEvent) when there is one; otherwise the
    // four events by name.
    async function listen() {
      const T = window.__TAURI__;
      if (!T) return;
      try {
        const webview = T.webview?.getCurrentWebview?.();
        if (webview && typeof webview.onDragDropEvent === "function") {
          const un = await webview.onDragDropEvent(e => dragDrop(e.payload));
          if (signal.aborted) un();
          else unlisten = un;
          return;
        }
        if (typeof T.event?.listen !== "function") return;
        const names = { "tauri://drag-enter": "enter", "tauri://drag-over": "over", "tauri://drag-drop": "drop", "tauri://drag-leave": "leave" };
        const offs = await Promise.all(Object.entries(names).map(([name, type]) =>
          T.event.listen(name, e => dragDrop({ ...(e.payload || {}), type }))));
        const all = () => offs.forEach(un => un?.());
        if (signal.aborted) all();
        else unlisten = all;
      } catch (e) {
        console.warn("TaurisFiles: cannot listen for dropped files:", e);
      }
    }

    // ---------- start ----------

    list = Array.isArray(opt.files) ? opt.files.slice() : [];
    draw();
    listen();

    return {
      /** Replaces the files (the app's list is the truth). */
      setFiles(files) {
        const next = Array.isArray(files) ? files.slice() : [];
        if (renaming) {
          held = next;
          return;
        }
        const same = signature(next) === drawn;
        list = next;
        // Nothing shown changed, but the objects are new: callbacks get the new ones.
        if (same) shown = shown.map(f => fileById(keyOf(f.id)) ?? f);
        else draw();
      },
      /** The files as the component has them now. */
      files() { return list.slice(); },
      /** Changes options: title, place, subtitle, color, labels, columns, the on… functions, files. */
      update(changes = {}) {
        Object.assign(opt, changes);
        // Turning off `multiple` keeps the file with the focus only.
        if (!several() && sel.size > 1) setSelection(selId == null ? [] : [selId], selId, false);
        if (changes.sort && SORTABLE.has(changes.sort.key)) sort = { key: changes.sort.key, up: changes.sort.up !== false };
        if (Array.isArray(changes.files)) {
          if (renaming) held = changes.files.slice();
          else list = changes.files.slice();
        }
        draw();
      },
      /** Selects one file by id (null: none), or several: an array of ids (the first gets the focus). */
      select(fileId) {
        if (Array.isArray(fileId)) {
          const keys = fileId.map(keyOf).filter(k => list.some(f => keyOf(f.id) === k)).slice(0, several() ? undefined : 1);
          anchor = keys[0] ?? null;
          setSelection(keys, keys[0] ?? null);
        } else {
          select(fileId == null ? null : fileId);
        }
      },
      /** Every selected file that is shown, top to bottom. */
      selection,
      /** Selects every file shown. */
      selectAll() {
        if (several()) setSelection(shown.map(f => keyOf(f.id)), focusAmongShown(), false);
      },
      /** The selected file with the focus, or else the first selected file; null when none is. */
      selected() { return primary(); },
      /** Opens the picker, then adds what was chosen (as "Add files…"). */
      add,
      /** Adds these paths, as if they were dropped. */
      addPaths,
      /** Opens a file with onOpen. */
      open(fileId) { return open(fileById(keyOf(fileId))); },
      /** Starts renaming a file in place. */
      rename(fileId) { rename(fileById(keyOf(fileId))); },
      /** Asks, then deletes a file with onDelete. */
      remove(fileId) { return remove(fileById(keyOf(fileId))); },
      /** Shows the search text (and only the files that match). */
      search(text) {
        query = String(text ?? "");
        searchInput.value = query;
        draw();
      },
      /** Feeds a drag-and-drop event: { type: "enter" | "over" | "drop" | "leave", paths?, position? }. */
      dragDrop,
      /** Shows the busy card with this text, or hides it (null). */
      busy(text) { setBusy(text); },
      /** Shows a message (through onMessage when there is one). */
      message,
      /** Moves keyboard focus to the list. */
      focus() { focusList(); },
      /** Moves keyboard focus to the search field. */
      focusSearch() {
        if (!searchBox.hidden) searchInput.focus();
      },
      /** Removes the component and its listeners; mount can then be called again. */
      destroy() {
        life.abort();
        rowMenuHandle?.close();
        unlisten?.();
        if (asking) asking.finish(false);
        clearTimeout(freshTimer);
        clearTimeout(messageTimer);
        root.replaceChildren();
        if (addedClass) root.classList.remove("tf");
        root.classList.remove("tf-dropping", "tf-has-acts", "tf-no-head", "tf-no-status");
        root.style.removeProperty("--tf-acts-n");
        delete root.__taurisFiles;
      },
    };
  }

  window.TaurisFiles = { mount, kindOf, formatSize, pick, saveDialog };
})();
