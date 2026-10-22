// tauris-ui glance: small figures read at a glance, for a table's cells and a
// view's header: a sparkline, a status (a coloured dot and a word) and a
// capacity bar (how much of a limit is used, a segment each). Plain
// JavaScript: no build step, no dependencies. In a Tauri app the plugin
// injects this file with its stylesheet (web/glance.css), added the first
// time a page uses it.
//
//   cell.replaceChildren(TaurisGlance.sparkline([3, 5, 4, 8], { label: "Revenue, last 4 weeks" }));
//   cell.replaceChildren(TaurisGlance.status("warn", "Behind"));
//   header.append(TaurisGlance.capacity({ label: "Open tasks", max: 20, items: tasks.map(t => ({ title: t.name, color: t.color })) }));
//
// Each call makes a new element; to change one, make it again and put it in
// the old one's place. In a selected row ([aria-selected="true"]) a sparkline
// takes the row's text colour.

(() => {
  "use strict";
  if (window.TaurisGlance) return;

  // Filled in by the plugin; left as is when the file is loaded on its own.
  const CSS = "__TAURIS_GLANCE_CSS__";
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

  const SVG = "http://www.w3.org/2000/svg";
  const svg = (name, attrs = {}) => {
    const el = document.createElementNS(SVG, name);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
    return el;
  };
  // A number, a date (or its text), or a number's text; anything else is no value.
  const num = v => {
    if (typeof v === "number") return v;
    if (v instanceof Date) return v.getTime();
    if (typeof v !== "string" || v.trim() === "") return NaN;
    return Number.isNaN(Number(v)) ? Date.parse(v) : Number(v);
  };
  const fixed = v => (Math.round(v * 10) / 10).toString();

  // A point: a number (its place is its x), [x, y], or { x, y }; x may be a date.
  function points(values) {
    return (Array.isArray(values) ? values : [])
      .map((v, i) => (Array.isArray(v) ? [num(v[0]), num(v[1])] : v && typeof v === "object" && !(v instanceof Date) ? [num(v.x), num(v.y)] : [i, num(v)]))
      .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
  }

  /** A small line of values over time: the line, the area under it, a dot on the last value. */
  function sparkline(values, options = {}) {
    addStyles();
    const W = Math.max(8, Number(options.width) || 64);
    const H = Math.max(8, Number(options.height) || 18);
    const el = svg("svg", { class: "tgl-spark", viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    if (options.color) el.style.setProperty("--tgl-c", String(options.color));
    if (options.label) {
      el.setAttribute("role", "img");
      el.setAttribute("aria-label", String(options.label));
      const title = svg("title");
      title.textContent = String(options.label);
      el.append(title);
    } else {
      el.setAttribute("aria-hidden", "true");
    }
    const ps = points(values).sort((a, b) => a[0] - b[0]);
    if (ps.length < 2) {
      if (ps.length) el.append(svg("circle", { class: "tgl-dot", cx: W - 2, cy: H / 2, r: 2 }));
      return el;
    }
    const xs = ps.map(p => p[0]);
    const ys = ps.map(p => p[1]);
    const x0 = xs[0];
    const x1 = xs[xs.length - 1] === x0 ? x0 + 1 : xs[xs.length - 1];
    const lo = Number.isFinite(+options.min) ? Math.min(+options.min, ...ys) : Math.min(...ys);
    const hiAll = Number.isFinite(+options.max) ? Math.max(+options.max, ...ys) : Math.max(...ys);
    const hi = hiAll === lo ? lo + 1 : hiAll;
    const X = x => 2 + ((x - x0) / (x1 - x0)) * (W - 4);
    const Y = y => H - 2.5 - ((y - lo) / (hi - lo)) * (H - 5);
    const d = ps.map(([x, y], i) => `${i ? "L" : "M"}${fixed(X(x))} ${fixed(Y(y))}`).join("");
    el.append(
      svg("path", { class: "tgl-area", d: `${d}L${fixed(X(x1))} ${H}L${fixed(X(x0))} ${H}Z` }),
      svg("path", { class: "tgl-line", d }),
      svg("circle", { class: "tgl-dot", cx: fixed(X(xs[xs.length - 1])), cy: fixed(Y(ys[ys.length - 1])), r: 2 }),
    );
    return el;
  }

  const KINDS = new Set(["ok", "warn", "bad", "done", "new", "none"]);

  /** A state as a coloured dot and a word ("On track"): something to read, never to press. */
  function status(kind, text, options = {}) {
    addStyles();
    const k = KINDS.has(kind) ? kind : "none";
    const el = document.createElement("span");
    el.className = `tgl-status tgl-${k}`;
    const dot = document.createElement("i");
    dot.setAttribute("aria-hidden", "true");
    const word = document.createElement("span");
    word.textContent = String(text ?? "");
    el.append(dot, word);
    if (options.title) el.title = String(options.title);
    return el;
  }

  /** How much of a limit is used: "Open tasks 7 / 20" and a segment for each place, coloured by what holds it. */
  function capacity(options = {}) {
    addStyles();
    const max = Math.max(1, Math.floor(Number(options.max) || 1));
    const items = Array.isArray(options.items) ? options.items : [];
    const used = Number.isFinite(+options.used) ? Math.max(0, Math.floor(+options.used)) : items.length;
    const free = String(options.labels?.free ?? "Free");
    const el = document.createElement("span");
    el.className = "tgl-cap";
    if (used > max) el.classList.add("tgl-over");
    if (options.label) {
      const label = document.createElement("span");
      label.className = "tgl-cap-label";
      label.textContent = String(options.label);
      el.append(label);
    }
    const count = document.createElement("b");
    count.className = "tgl-cap-count";
    count.textContent = `${used} / ${max}`;
    const bar = document.createElement("span");
    bar.className = "tgl-capbar";
    bar.setAttribute("role", "meter");
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", String(max));
    bar.setAttribute("aria-valuenow", String(Math.min(used, max)));
    bar.setAttribute("aria-valuetext", `${used} / ${max}`);
    if (options.label) bar.setAttribute("aria-label", String(options.label));
    if (options.width) bar.style.setProperty("--tgl-cap-w", `${Number(options.width)}px`);
    // A segment a place, up to 40; past that, one filled track.
    if (max <= 40) {
      bar.style.setProperty("--tgl-cap-n", String(max));
      for (let i = 0; i < max; i++) {
        const seg = document.createElement("i");
        const it = items[i];
        if (i < used) {
          seg.className = "tgl-on";
          if (it?.color) seg.style.setProperty("--tgl-c", String(it.color));
          if (it?.title) seg.title = String(it.title);
        } else {
          seg.title = free;
        }
        bar.append(seg);
      }
    } else {
      bar.classList.add("tgl-capbar-track");
      const fill = document.createElement("i");
      fill.className = "tgl-on";
      fill.style.width = `${Math.min(100, (used / max) * 100)}%`;
      bar.append(fill);
    }
    el.append(count, bar);
    if (options.title) el.title = String(options.title);
    return el;
  }

  window.TaurisGlance = { sparkline, status, capacity };
})();
