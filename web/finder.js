// tauris-ui finder: find anything (⌘K), a panel at the top of the window, as
// Spotlight or Xcode's Open Quickly. Plain JavaScript: no build step, no
// dependencies. In a Tauri app the plugin injects this file with its stylesheet
// (web/finder.css), which is added the first time a page uses it.
//
//   const finder = TaurisFinder.mount({
//     items: () => projects.map(p => ({ id: p.id, kind: "project", label: p.name, detail: `${p.open} open tasks` })),
//     kinds: [{ id: "project", label: "Projects", limit: 5 }, { id: "doc", label: "Documents" }],
//     onPick: item => show(item),
//   });
//
// Everything searched is in memory, so the results follow every key. Only an
// item's label and its `more` texts are searched: what the app leaves out
// (a password, a note) is never found. A query's words each match the label
// (whole, at its start, at a word's start, inside, as initials: "rp" finds
// Revenue Pipeline, or as scattered letters at word starts) or one of the
// `more` texts (letters together, at half weight). Results come in groups by
// kind, the group with the best match first, each group cut at its `limit`.
// With nothing typed, it shows what was picked last (`recent`), then the
// latest items (by `when`).
//
// Keys: ⌘K or ⌘L (Ctrl elsewhere) opens it, anywhere in the page; ↑ ↓ (or
// ⌃N ⌃P) move, ⌘↑ ⌘↓ go to the first and last, Page Up and Down by a page,
// Tab to the next group; Enter picks; Esc closes and puts the focus back.
//
// As a command line: `extra(query)` adds results made from what is typed
// ('New Task "call ana"…'), after the matches; `onKey(item, e)` hears the other
// keys on the chosen result (⌘C, ⌘E, ⌘⌫, Space in an empty field); an item's
// `actions` show those keys in the strip, its `shortcut` on its right.

(() => {
  "use strict";
  if (window.TaurisFinder) return;

  // Filled in by the plugin; left as is when the file is loaded on its own.
  const CSS = "__TAURIS_FINDER_CSS__";
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
    find: "Find",
    placeholder: "Find anything",
    results: "Results",
    recent: "Recent",
    latest: "Latest",
    // how many of a group are shown: (shown, total)
    some: (shown, total) => `${shown} of ${total}`,
    noMatch: query => `Nothing matches “${query}”`,
    noMatchHint: "Try fewer letters, or another word.",
    nothing: "Nothing to find yet.",
    choose: "to choose",
    open: "to open",
    close: "to close",
    // what ⌘↩ (or a ⌘-click) does, shown in the key strip when set ("New Tab"); onPick hears { cmd: true }
    openAlt: "",
    // the heading of extra(query)'s results that have no kind
    actions: "Actions",
  };

  const DEFAULTS = {
    // [{ id, label, kind?, detail?, more?: [text], icon?, color?, dim?, when? }], or a function making
    // them each time the panel opens (so it shows the app's state as it is then)
    items: [],
    // the groups, in their usual order: [{ id, label, icon?, limit?, bias? }]; a kind not listed comes last
    kinds: [],
    // the most rows a group shows (a kind's own limit wins)
    limit: 6,
    // ⌘K and ⌘L (Ctrl elsewhere) open it, anywhere in the page
    shortcut: true,
    // remembers what was picked, shown first with nothing typed (in the browser's storage under this key)
    storageKey: null,
    labels: {},
    styles: true,
    onPick: null, // (item, { how: "keyboard" | "mouse", cmd }): cmd is ⌘↩ or a ⌘-click (Ctrl elsewhere)
    onContextMenu: null, // (item, { x, y, how }): a right click, or the menu key, on a result
    // (item, e) => true (handled: the panel stays), "close" (handled, and it closes as on a pick) or false:
    // the keys the panel and its field do not use, on the chosen result
    onKey: null,
    // (query) => [items]: results made from what is typed, after the matches, in their own group
    extra: null,
    onOpen: null,
    onClose: null, // ({ picked })
  };

  const SEARCH_SVG = '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M10.4 10.4L14 14" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';

  let uid = 0;
  function el(tag, className, attrs = {}, ...children) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    for (const [key, value] of Object.entries(attrs)) if (value != null) node.setAttribute(key, value);
    node.append(...children.flat().filter(c => c != null));
    return node;
  }
  const say = (label, ...values) => String(typeof label === "function" ? label(...values) : label);

  // ---------- matching ----------

  const foldCache = new Map();
  // Lower case without accents, one character for one, so a match's place maps back.
  function fold(s) {
    let out = "";
    for (const c of String(s)) {
      let f = foldCache.get(c);
      if (f === undefined) {
        f = c.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
        if (f.length !== c.length) f = c.length === 1 ? (f[0] ?? c) : c;
        foldCache.set(c, f);
      }
      out += f;
    }
    return out;
  }
  const isWordChar = c => /[\p{L}\p{N}]/u.test(c);
  function wordStart(orig, t, i) {
    if (i === 0) return true;
    if (!isWordChar(t[i - 1])) return true;
    // camelCase and digits after letters start a word too
    const a = orig[i - 1], b = orig[i];
    return (a === a.toLowerCase() && b !== b.toLowerCase()) || (/\d/.test(b) && !/\d/.test(a));
  }

  // How well one word of the query matches a text: whole, its start, a word's
  // start, inside, initials, scattered. `strict`: its letters must sit together.
  function matchWord(q, orig, t, strict = false) {
    if (!q) return null;
    const at = t.indexOf(q);
    if (at === 0) return { score: (t.length === q.length ? 1000 : 900) - Math.min(t.length, 60) * 0.5, ranges: [[0, q.length]] };
    if (at > 0) {
      for (let i = at; i !== -1; i = t.indexOf(q, i + 1)) {
        if (wordStart(orig, t, i)) return { score: 760 - Math.min(i, 80), ranges: [[i, i + q.length]] };
      }
      return { score: 420 - Math.min(at, 80), ranges: [[at, at + q.length]] };
    }
    if (strict || q.length < 2 || t.length > 240) return null;
    // Initials and word heads: "rp" finds Revenue Pipeline, "revpip" too.
    {
      const ranges = [];
      let i = 0, ok = true;
      for (let k = 0; k < q.length; k++) {
        const last = ranges[ranges.length - 1];
        if (last && last[1] < t.length && t[last[1]] === q[k]) { last[1] += 1; continue; }
        let j = i;
        while (j < t.length && !(t[j] === q[k] && wordStart(orig, t, j))) j++;
        if (j >= t.length) { ok = false; break; }
        ranges.push([j, j + 1]);
        i = j + 1;
      }
      if (ok) return { score: 640 - ranges.length * 8 - Math.min(ranges[0][0], 40), ranges };
    }
    // Scattered letters in a few runs: the first starts a word, each later one starts
    // a word or sits in the first word ("stpe" finds Stripe); anything looser is noise.
    if (q.length < 3) return null;
    let firstEnd = 0;
    while (firstEnd < t.length && isWordChar(t[firstEnd])) firstEnd++;
    const ranges = [];
    let i = 0;
    for (let k = 0; k < q.length; k++) {
      const last = ranges[ranges.length - 1];
      if (last && last[1] < t.length && t[last[1]] === q[k]) { last[1] += 1; i = last[1]; continue; }
      let j = i;
      while (j < t.length && !(t[j] === q[k] && ((ranges.length && j < firstEnd) || wordStart(orig, t, j)))) j++;
      if (j >= t.length) return null;
      ranges.push([j, j + 1]);
      i = j + 1;
    }
    if (ranges.length > Math.max(2, Math.ceil(q.length / 3))) return null;
    const span = ranges[ranges.length - 1][1] - ranges[0][0];
    return { score: Math.max(1, 160 - ranges.length * 10 - Math.min(span - q.length, 60) - Math.min(ranges[0][0], 30)), ranges, loose: true };
  }

  function merge(r) {
    const s = [...r].sort((a, b) => a[0] - b[0]);
    const out = [];
    for (const x of s) {
      const l = out[out.length - 1];
      if (l && x[0] <= l[1]) l[1] = Math.max(l[1], x[1]);
      else out.push([x[0], x[1]]);
    }
    return out;
  }

  // Every word of the query must match the label or a `more` text; the score ranks them.
  function search(index, query, bias) {
    const qf = fold(query.trim()).replace(/\s+/g, " ");
    if (!qf) return [];
    const words = qf.split(" ");
    const out = [];
    for (const e of index) {
      let score = 0;
      let loose = false;
      const ranges = [];
      const snips = new Map();
      let ok = true;
      for (const w of words) {
        const h = matchWord(w, e.label, e.labelF, e.strict);
        // A match with its letters together anywhere beats a scattered one, whatever its weight.
        const rank = (x, weight) => x.score * weight - (x.loose ? 10000 : 0);
        let best = h ? rank(h, 1) : -Infinity;
        let inLabel = !!h;
        let from = null;
        for (const m of e.more) {
          const hm = matchWord(w, m.o, m.f, true);
          if (hm && rank(hm, 0.5) > best) { best = rank(hm, 0.5); inLabel = false; from = { m, h: hm }; }
        }
        if (best === -Infinity) { ok = false; break; }
        if (h && inLabel) ranges.push(...h.ranges);
        if (from) snips.set(from.m, [...(snips.get(from.m) ?? []), ...from.h.ranges]);
        if (best < 0) { loose = true; best += 10000; }
        score += best;
      }
      if (!ok) continue;
      // The whole phrase at the start of the label beats the same words scattered.
      if (words.length > 1 && e.labelF.startsWith(qf)) score += 300;
      score = score / words.length + (bias.get(e.kind) ?? 0) - (e.item.dim ? 60 : 0) - (loose ? 2000 : 0);
      const [sm, sr] = [...snips.entries()][0] ?? [];
      out.push({ e, score, ranges: merge(ranges), snip: sm && sr ? { text: sm.o, ranges: merge(sr) } : null });
    }
    return out;
  }

  // A text with its matches marked; a long one cut to a window around the first match.
  function marked(text, ranges, max = 110) {
    const lead = Math.round(max / 4);
    let from = 0;
    if (text.length > max && ranges.length && ranges[0][0] > lead + 12) from = Math.max(0, Math.min(ranges[0][0] - lead, text.length - max));
    const to = Math.min(text.length, from + max);
    const parts = [];
    if (from > 0) parts.push("…");
    let i = from;
    for (const [a0, b0] of ranges) {
      const a = Math.max(a0, from), b = Math.min(b0, to);
      if (b <= a) continue;
      if (a > i) parts.push(text.slice(i, a));
      parts.push(el("mark", "", {}, text.slice(a, b)));
      i = b;
    }
    if (i < to) parts.push(text.slice(i, to));
    if (to < text.length) parts.push("…");
    return parts;
  }

  // ---------- the panel ----------

  let current = null; // the open finder (one at a time)
  const MODIFIERS = new Set(["Shift", "Meta", "Control", "Alt", "AltGraph", "CapsLock", "Fn", "OS"]);

  function mount(options = {}) {
    const given = changes => Object.fromEntries(Object.entries(changes ?? {}).filter(([, v]) => v !== undefined));
    const opt = { ...DEFAULTS, ...given(options) };
    if (opt.styles) addStyles();
    const L = () => ({ ...LABELS, ...(opt.labels || {}) });
    const id = `tfd-${++uid}`;
    const life = new AbortController();
    const signal = life.signal;
    const call = (fn, ...args) => {
      if (typeof fn !== "function" || signal.aborted) return;
      try {
        fn(...args);
      } catch (e) {
        console.error("[tauris-ui finder] a callback failed:", e);
      }
    };

    let host = null;      // the veil over the window, while open
    let input = null;
    let list = null;
    let count = null;
    let index = [];       // the items as searched
    let flat = [];        // the rows shown, in order
    let at = 0;           // the row chosen
    let back = null;      // where the focus was before
    let pointer = null;   // where the mouse was (a row it rests on is chosen only when it moves)
    let enterHint = null; // the strip's "↵ to open"
    let ownKeys = null;   // the strip's keys of the chosen result

    const kindsOf = () => (Array.isArray(opt.kinds) ? opt.kinds : []).filter(k => k && k.id != null);
    const keyOf = item => `${item.kind ?? ""}:${item.id}`;

    function buildIndex() {
      let items = [];
      try {
        items = typeof opt.items === "function" ? opt.items() : opt.items;
      } catch (e) {
        console.error("[tauris-ui finder] items() failed:", e);
      }
      index = (Array.isArray(items) ? items : []).filter(i => i && i.id != null).map(item => {
        const label = String(item.label ?? "");
        const more = (Array.isArray(item.more) ? item.more : []).filter(t => t != null && String(t).trim())
          .map(t => { const o = String(t).replace(/\s+/g, " ").trim(); return { o, f: fold(o) }; });
        const kind = item.kind == null ? "" : String(item.kind);
        // Long text (a log entry, a sentence): its letters must sit together, or "rp" finds half of it.
        const strict = item.strict ?? kindsOf().find(k => String(k.id) === kind)?.strict ?? false;
        return { item, kind, label, labelF: fold(label), more, strict: strict === true };
      });
    }

    function readRecent() {
      if (!opt.storageKey) return [];
      try {
        const v = JSON.parse(localStorage.getItem(String(opt.storageKey)) || "[]");
        return Array.isArray(v) ? v.filter(x => typeof x === "string") : [];
      } catch {
        return [];
      }
    }
    function keepRecent(item) {
      if (!opt.storageKey) return;
      const list = [keyOf(item), ...readRecent().filter(k => k !== keyOf(item))].slice(0, 12);
      try {
        localStorage.setItem(String(opt.storageKey), JSON.stringify(list));
      } catch {
        // recents are a convenience
      }
    }

    function groups(query) {
      const words = L();
      const kinds = kindsOf();
      const order = new Map(kinds.map((k, i) => [String(k.id), i]));
      const limitOf = kind => Number(kinds.find(k => String(k.id) === kind)?.limit) || opt.limit;
      const titleOf = kind => String(kinds.find(k => String(k.id) === kind)?.label ?? kind);
      if (!query.trim()) {
        const byKey = new Map(index.map(e => [keyOf(e.item), e]));
        const recent = readRecent().map(k => byKey.get(k)).filter(Boolean).slice(0, 6);
        const seen = new Set(recent.map(e => keyOf(e.item)));
        const latest = index.filter(e => e.item.when != null && !e.item.dim && !seen.has(keyOf(e.item)))
          .sort((a, b) => String(b.item.when).localeCompare(String(a.item.when))).slice(0, recent.length ? 5 : 8);
        const out = [];
        if (recent.length) out.push({ key: "recent", title: String(words.recent), rows: recent.map(e => ({ e, ranges: [] })), total: recent.length });
        if (latest.length) out.push({ key: "latest", title: String(words.latest), rows: latest.map(e => ({ e, ranges: [] })), total: latest.length });
        return [...out, ...extraGroups(query)];
      }
      const bias = new Map(kinds.map(k => [String(k.id), Number(k.bias) || 0]));
      const by = new Map();
      for (const h of search(index, query, bias)) {
        if (!by.has(h.e.kind)) by.set(h.e.kind, []);
        by.get(h.e.kind).push(h);
      }
      const out = [];
      for (const [kind, rows] of by) {
        rows.sort((a, b) => b.score - a.score || String(b.e.item.when ?? "").localeCompare(String(a.e.item.when ?? "")) || a.e.label.localeCompare(b.e.label));
        out.push({ key: kind, title: titleOf(kind), rows: rows.slice(0, limitOf(kind)), total: rows.length });
      }
      // The group with the best match first; equal groups keep their usual order.
      const rank = kind => (order.has(kind) ? order.get(kind) : kinds.length);
      return [...out.sort((a, b) => b.rows[0].score - a.rows[0].score || rank(a.key) - rank(b.key)), ...extraGroups(query)];
    }

    // extra(query)'s results: in the order given, a group for each kind, after everything else.
    function extraGroups(query) {
      if (typeof opt.extra !== "function") return [];
      let items = [];
      try {
        items = opt.extra(query);
      } catch (e) {
        console.error("[tauris-ui finder] extra() failed:", e);
      }
      const kinds = kindsOf();
      const by = new Map();
      for (const item of Array.isArray(items) ? items : []) {
        if (!item || item.id == null) continue;
        const kind = item.kind == null ? "" : String(item.kind);
        const label = String(item.label ?? "");
        if (!by.has(kind)) by.set(kind, []);
        by.get(kind).push({ e: { item, kind, label, labelF: fold(label), more: [], strict: false, extra: true }, ranges: [] });
      }
      return [...by].map(([kind, rows]) => ({
        key: `extra:${kind}`,
        title: kind ? String(kinds.find(k => String(k.id) === kind)?.label ?? kind) : String(L().actions),
        rows, total: rows.length, extra: true,
      }));
    }

    function iconOf(item) {
      const value = item.icon ?? kindsOf().find(k => String(k.id) === String(item.kind ?? ""))?.icon;
      const node = el("span", "tfd-icon", { "aria-hidden": "true" });
      if (typeof value === "string" && value.trimStart().startsWith("<")) node.innerHTML = value;
      else if (value != null) node.textContent = String(value);
      return node;
    }

    function draw() {
      const words = L();
      const query = input.value;
      const gs = groups(query);
      flat = gs.flatMap(g => g.rows);
      at = Math.min(at, Math.max(0, flat.length - 1));
      list.replaceChildren();
      let n = 0;
      for (const g of gs) {
        const head = el("div", "tfd-group-head", { "aria-hidden": "true" }, el("span", "", {}, g.title),
          g.total > g.rows.length ? el("span", "tfd-some", {}, say(words.some, g.rows.length, g.total)) : null);
        const group = el("div", "tfd-group", { role: "group", "aria-label": g.title }, head);
        for (const r of g.rows) {
          const me = n++;
          const item = r.e.item;
          const row = el("div", "tfd-row" + (item.dim ? " tfd-dim" : ""), { id: `${id}-o${me}`, role: "option", "data-i": String(me), "aria-selected": String(me === at) });
          const name = el("span", "tfd-label", {}, ...marked(r.e.label || "—", r.ranges));
          name.__full = r.e.label;
          const meta = el("span", "tfd-detail");
          if (item.color) {
            const chip = el("i", "tfd-chip", { "aria-hidden": "true" });
            chip.style.setProperty("--tfd-chip", String(item.color));
            meta.append(chip);
          }
          // The text that matched, when the label does not show every word.
          if (r.snip && !r.ranges.length) meta.append(el("span", "tfd-snip", {}, ...marked(r.snip.text, r.snip.ranges, 44)));
          if (item.detail != null && String(item.detail) !== "") meta.append(el("span", "tfd-detail-text", { title: String(item.detail) }, String(item.detail)));
          row.append(iconOf(item), name, meta);
          if (item.shortcut != null && String(item.shortcut) !== "") row.append(el("kbd", "tfd-shortcut", {}, String(item.shortcut)));
          group.append(row);
        }
        list.append(group);
      }
      if (!flat.length) {
        const q = query.trim();
        list.append(el("div", "tfd-empty", { role: "presentation" },
          el("b", "", {}, q ? say(words.noMatch, q) : String(words.nothing)),
          q ? el("span", "", {}, String(words.noMatchHint)) : null));
      }
      // A label cut short ("…") is whole in its tooltip.
      for (const label of list.querySelectorAll(".tfd-label")) {
        if (label.scrollWidth > label.clientWidth + 1 || label.textContent !== label.__full) label.parentElement.title = label.__full;
      }
      const total = gs.filter(g => !g.extra).reduce((sum, g) => sum + g.total, 0);
      count.textContent = query.trim() ? String(total) : "";
      input.setAttribute("aria-expanded", String(flat.length > 0));
      paint(true);
    }

    function paint(scroll) {
      for (const row of list.querySelectorAll(".tfd-row")) row.setAttribute("aria-selected", String(Number(row.dataset.i) === at));
      // The chosen result's own keys in the strip ("⌘C Copy"); one for ↵ names what Enter does to it ("Run").
      const actions = (Array.isArray(flat[at]?.e.item.actions) ? flat[at].e.item.actions : []).filter(a => a && a.key != null && a.label != null);
      const enter = actions.find(a => String(a.key) === "↵");
      enterHint.lastChild.textContent = ` ${enter ? enter.label : L().open}`;
      ownKeys.replaceChildren(...actions.filter(a => a !== enter).map(a => el("span", "", {}, el("kbd", "", {}, String(a.key)), ` ${a.label}`)));
      const row = list.querySelector(`.tfd-row[data-i="${at}"]`);
      if (row) {
        input.setAttribute("aria-activedescendant", row.id);
        if (scroll) {
          // A group's first row brings its heading into view with it; the first row shows the list from the top.
          if (at === 0) list.scrollTop = 0;
          else if (row.previousElementSibling?.classList.contains("tfd-group-head")) row.previousElementSibling.scrollIntoView({ block: "nearest" });
          row.scrollIntoView({ block: "nearest" });
        }
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    const move = to => {
      if (!flat.length) return;
      at = Math.max(0, Math.min(flat.length - 1, to));
      paint(true);
    };
    const pageSize = () => {
      const row = list.querySelector(".tfd-row");
      return Math.max(1, Math.floor(list.clientHeight / (row?.offsetHeight || 24)) - 1);
    };

    // The keys the field keeps, as any text field: typing (Space too, but in an empty field or with ⌥),
    // deleting, moving in the text, and its edit shortcuts (⌘C only with text selected).
    function forField(e) {
      const k = e.key;
      const c = cmd(e);
      const other = MAC ? e.ctrlKey : e.metaKey;
      if (e.code === "Space" || k === " ") return !c && !other && !e.altKey && input.value !== "";
      if (!c && !other && k.length === 1) return true;
      if ((k === "Backspace" || k === "Delete") && !c && !other) return true;
      if (k === "ArrowLeft" || k === "ArrowRight" || k === "Home" || k === "End") return true;
      if (c && !e.altKey && ["a", "x", "v", "z"].includes(k.toLowerCase())) return true;
      if (c && !e.altKey && !e.shiftKey && k.toLowerCase() === "c" && input.selectionStart !== input.selectionEnd) return true;
      // ⌃ and a letter move and edit in the text on a Mac (⌃A ⌃E ⌃K ⌃D), as in every field.
      return MAC && e.ctrlKey && !e.metaKey && k.length === 1;
    }

    function pick(i, how, alt = false) {
      const r = flat[i];
      if (!r) return;
      // What extra() made from the query is not a place to come back to.
      if (!r.e.extra) keepRecent(r.e.item);
      close(true);
      call(opt.onPick, r.e.item, { how, cmd: alt });
    }

    function open(text = "") {
      if (signal.aborted) return;
      if (host) {
        // Open already: the field takes the keys, its text selected, to type a new search at once.
        if (text) { input.value = String(text); at = 0; draw(); }
        input.focus();
        input.select();
        return;
      }
      leaving?.();
      if (current && current !== api) current.close();
      current = api;
      window.TaurisMenu?.close?.();
      const words = L();
      back = document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : null;
      buildIndex();
      at = 0;
      pointer = null;
      input = el("input", "tfd-input", {
        type: "text", spellcheck: "false", autocomplete: "off", autocorrect: "off", autocapitalize: "off",
        role: "combobox", "aria-autocomplete": "list", "aria-controls": `${id}-list`, "aria-expanded": "false",
        "aria-label": String(words.find), placeholder: String(words.placeholder),
      });
      input.value = String(text ?? "");
      count = el("span", "tfd-count", { "aria-hidden": "true" });
      const field = el("div", "tfd-field", {}, el("span", "tfd-search", { "aria-hidden": "true" }), input, count, el("kbd", "tfd-esc", { "aria-hidden": "true" }, "esc"));
      field.firstChild.innerHTML = SEARCH_SVG;
      list = el("div", "tfd-list", { id: `${id}-list`, role: "listbox", "aria-label": String(words.results), tabindex: "-1" });
      enterHint = el("span", "", {}, el("kbd", "", {}, "↵"), ` ${words.open}`);
      ownKeys = el("span", "tfd-own-keys");
      const keys = el("div", "tfd-keys", { "aria-hidden": "true" },
        el("span", "", {}, el("kbd", "", {}, "↑"), el("kbd", "", {}, "↓"), ` ${words.choose}`),
        enterHint,
        words.openAlt ? el("span", "", {}, el("kbd", "", {}, MAC ? "⌘↵" : "Ctrl+↵"), ` ${words.openAlt}`) : null,
        ownKeys,
        el("span", "", {}, el("kbd", "", {}, "esc"), ` ${words.close}`));
      const panel = el("div", "tfd", { role: "dialog", "aria-label": String(words.find), "aria-modal": "true" }, field, list, keys);
      host = el("div", "tfd-host", {}, panel);
      document.body.append(host);
      const here = new AbortController();
      const on = (node, type, fn, o = {}) => node.addEventListener(type, fn, { signal: here.signal, ...o });
      host.__tfdLife = here;

      on(input, "input", () => { at = 0; draw(); });
      on(panel, "keydown", e => {
        if (e.isComposing || e.keyCode === 229) return;
        const n = flat.length;
        if (e.key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          close(false);
        } else if (e.key === "ArrowDown" || (e.key === "n" && e.ctrlKey && !e.metaKey)) {
          e.preventDefault();
          move(cmd(e) ? n - 1 : at + 1);
        } else if (e.key === "ArrowUp" || (e.key === "p" && e.ctrlKey && !e.metaKey)) {
          e.preventDefault();
          move(cmd(e) ? 0 : at - 1);
        } else if (e.key === "PageDown") {
          e.preventDefault();
          move(at + pageSize());
        } else if (e.key === "PageUp") {
          e.preventDefault();
          move(at - pageSize());
        } else if (e.key === "Tab" && !e.metaKey && !e.ctrlKey && !e.altKey) {
          // Tab and ⇧Tab go from group to group (the keys stay in the panel).
          e.preventDefault();
          const firsts = [...list.querySelectorAll(".tfd-group")].map(g => Number(g.querySelector(".tfd-row")?.dataset.i)).filter(Number.isFinite);
          if (!firsts.length) return;
          const now = firsts.filter(f => f <= at).length - 1;
          move(firsts[(now + (e.shiftKey ? -1 : 1) + firsts.length) % firsts.length]);
        } else if (e.key === "Enter" && ((cmd(e) && !e.shiftKey && !e.altKey) || (!e.shiftKey && !e.altKey && !e.ctrlKey && !e.metaKey))) {
          // Plain, or with ⌘ alone (the app's other way to open: a new tab); with other keys, the app's (onKey).
          e.preventDefault();
          if (!e.repeat) pick(at, "keyboard", cmd(e));
        } else if ((e.key === "ContextMenu" || (e.shiftKey && e.key === "F10")) && typeof opt.onContextMenu === "function") {
          const row = list.querySelector(`.tfd-row[data-i="${at}"]`);
          if (!row || !flat[at]) return;
          e.preventDefault();
          const r = row.getBoundingClientRect();
          call(opt.onContextMenu, flat[at].e.item, { x: r.left + 24, y: r.bottom, how: "keyboard" });
        } else if (flat[at] && typeof opt.onKey === "function" && !MODIFIERS.has(e.key) && !forField(e)) {
          // Any other key, on the chosen result: the app's (⌘C copies it, ⌘E edits it).
          let r = false;
          try {
            r = opt.onKey(flat[at].e.item, e);
          } catch (err) {
            console.error("[tauris-ui finder] onKey failed:", err);
          }
          if (r !== true && r !== "close") return;
          e.preventDefault();
          e.stopPropagation();
          if (r === "close") close(true);
        } else if (e.key === "Enter") {
          e.preventDefault();
        }
      });
      // The mouse: a row it rests on is chosen when it moves (not when the list moves under it).
      on(list, "pointermove", e => {
        if (pointer && Math.abs(e.clientX - pointer.x) < 1 && Math.abs(e.clientY - pointer.y) < 1) return;
        pointer = { x: e.clientX, y: e.clientY };
        const row = e.target instanceof Element ? e.target.closest(".tfd-row") : null;
        if (row && Number(row.dataset.i) !== at) {
          at = Number(row.dataset.i);
          paint(false);
        }
      });
      on(list, "mousedown", e => e.preventDefault()); // the keys stay in the field
      on(list, "click", e => {
        const row = e.target instanceof Element ? e.target.closest(".tfd-row") : null;
        if (row) pick(Number(row.dataset.i), "mouse", cmd(e));
      });
      on(list, "contextmenu", e => {
        const row = e.target instanceof Element ? e.target.closest(".tfd-row") : null;
        if (!row || typeof opt.onContextMenu !== "function") return;
        e.preventDefault();
        at = Number(row.dataset.i);
        paint(false);
        call(opt.onContextMenu, flat[at].e.item, { x: e.clientX, y: e.clientY, how: "mouse" });
      });
      // A press beside the panel closes it.
      on(host, "mousedown", e => {
        if (e.target === host) {
          e.preventDefault();
          close(false);
        }
      });
      // The focus going elsewhere (a click in another frame, a menu of the app's that closed it) closes it too.
      on(document, "focusin", e => {
        if (host && !host.contains(e.target) && !e.target.closest?.(".tmn-menu")) close(false, false);
      });
      draw();
      input.focus({ preventScroll: true });
      call(opt.onOpen);
    }

    // A panel on its way out (a short fade), removed at once if another opens.
    let leaving = null;
    function close(picked, refocus = true) {
      if (!host) return;
      host.__tfdLife.abort();
      const gone = host;
      gone.classList.add("tfd-leaving");
      const remove = () => { gone.remove(); if (leaving === remove) leaving = null; };
      leaving = remove;
      setTimeout(remove, matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 90);
      host = null;
      input = list = count = enterHint = ownKeys = null;
      flat = [];
      if (current === api) current = null;
      // The focus goes back where it was (a pick: before onPick, which may move it on).
      if (refocus && back?.isConnected) back.focus({ preventScroll: true });
      back = null;
      call(opt.onClose, { picked });
    }

    if (opt.shortcut) {
      document.addEventListener("keydown", e => {
        if (!cmd(e) || e.altKey || e.shiftKey || e.repeat) return;
        const k = e.key.toLowerCase();
        if (k !== "k" && k !== "l") return;
        e.preventDefault();
        open();
      }, { signal });
    }

    const api = {
      /** Opens it (with this text in the field), or brings the keys back to it. */
      open(text) { open(text); },
      /** Closes it; the focus goes back where it was. */
      close() { close(false); },
      /** Whether it is open. */
      get isOpen() { return host !== null; },
      /** Changes options: items, kinds, limit, labels, the on… functions. An open panel shows them. */
      update(changes = {}) {
        Object.assign(opt, given(changes));
        if (host) { buildIndex(); draw(); }
      },
      /** Removes it and its shortcut. */
      destroy() {
        if (signal.aborted) return;
        close(false);
        leaving?.();
        life.abort();
      },
    };
    return api;
  }

  window.TaurisFinder = { mount, close: () => current?.close() };
})();
