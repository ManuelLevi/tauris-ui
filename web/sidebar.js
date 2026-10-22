// tauris-ui sidebar: a collapsible side bar of sections, as in Mail or Finder.
// Plain JavaScript: no build step, no dependencies. In a Tauri app the plugin
// injects this file with its stylesheet (web/sidebar.css), which is added the
// first time a page uses it. Elsewhere (the demo page) load web/sidebar.css.
//
//   const side = TaurisSidebar.mount(document.getElementById("side"), {
//     image: "logo.svg", title: "Mail",   // a logo, an avatar: beside the title
//     items: [
//       { id: "inbox", label: "Inbox", icon: "📥", count: 3 },
//       { heading: "Projects" },
//       { id: "atlas", label: "Atlas", icon: "<svg …>" },
//     ],
//     content: treeElement,                  // a tree belongs in a TaurisTree, here
//
// Its items are one level: places, as in Mail or Finder. A tree (projects,
// their folders and files) is a TaurisTree in `content`, below the items: the
// desktop outline, with its +/- boxes and dotted lines.
//     selected: "inbox",
//     onSelect: item => show(item.id),
//   });
//
// Put the element beside the page's main area, in a row with a height
// (display: flex): the sidebar sets its own width and the main area takes the
// rest. Collapsed, it is a rail of icons (collapse: "rail", the default) or
// nothing at all (collapse: "hide"; the app then shows it again with toggle()
// or the shortcut). Its button, ⌃⌘S on a Mac (Ctrl+Shift+B elsewhere) and
// toggle() collapse and open it; its edge can be dragged to resize it, and
// dragged narrow it collapses. storageKey keeps the width and whether it is
// collapsed between runs.
//
// Keyboard: Tab reaches the selected item (one Tab stop for the list); Up,
// Down, Home and End move; Enter or Space selects; a letter jumps to the next
// item starting with it. On the edge (Tab reaches it): Left and Right resize, Home and End go
// to the narrowest and widest, Enter collapses or opens.
//
// Nothing here is a <button>, so an app's plain `button { ... }` rule cannot
// restyle it. Labels are set as text; an icon or image starting with "<" is markup.

(() => {
  "use strict";
  if (window.TaurisSidebar) return;

  // Filled in by the plugin; left as is when the file is loaded on its own.
  const CSS = "__TAURIS_SIDEBAR_CSS__";
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
  const SHORTCUT = MAC ? "⌃⌘S" : "Ctrl+Shift+B";
  // ⌃⌘S on a Mac (its Show/Hide Sidebar), Ctrl+Shift+B elsewhere.
  const isShortcut = e => (MAC
    ? e.ctrlKey && e.metaKey && !e.altKey && !e.shiftKey && e.code === "KeyS"
    : e.ctrlKey && e.shiftKey && !e.altKey && !e.metaKey && e.code === "KeyB");

  const LABELS = {
    label: "Sidebar",
    hide: "Hide sidebar",
    show: "Show sidebar",
    resize: "Sidebar width",
  };

  const DEFAULTS = {
    // [{ id, label, icon?, count?, disabled?, title? }, or { heading }]: one level (a tree: TaurisTree in `content`)
    items: [],
    // the id of the selected item, or null
    selected: null,
    // collapsed at first (storageKey, when it has one, says instead)
    collapsed: false,
    // "rail": a column of icons; "hide": nothing (the app shows it again)
    collapse: "rail",
    // the side of the window it is on: the edge to drag is the other one
    side: "left",
    // its width, open; the edge drags it between these
    width: 220,
    minWidth: 160,
    maxWidth: 420,
    // a heading at its top, beside the button (none by default)
    title: "",
    // a picture before the title (a product's or company's logo, a person's avatar):
    // an image's address, or markup starting with "<" (an svg). In the rail it
    // alone shows, above the button. None by default.
    image: null,
    // "square": slightly rounded, the whole picture shown (a logo);
    // "round": a circle the picture fills (an avatar)
    imageShape: "square",
    // an element of the app's to show below the items (a tree view, a search):
    // it fills the rest of the height and scrolls; it shows only while the
    // sidebar is open. Also reached as `body` on what mount returns.
    content: null,
    // ⌃⌘S (Ctrl+Shift+B) collapses and opens it, anywhere in the page
    shortcut: true,
    // how long after a key the next one still adds to the name being typed
    typeAheadMs: 700,
    // the browser storage key keeping its width and whether it is collapsed (none: not kept)
    storageKey: null,
    // false: the page brings its own stylesheet
    styles: true,
    labels: {},
    onSelect: null, // (item, { how: "mouse" | "keyboard" })
    // a right click on an item, or the menu key on it: (item, { x, y, how }); the app opens
    // its own menu there (TaurisMenu.open(items, { x, y })). Given, the browser's menu does not open.
    onContextMenu: null,
    onToggle: null, // ({ collapsed, how: "button" | "shortcut" | "edge" | "api" })
    onResize: null, // ({ width })
  };

  const SIDEBAR_SVG = '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><rect x="1.5" y="2.5" width="13" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M6 2.8v10.4" stroke="currentColor" stroke-width="1.2"/></svg>';

  let uid = 0;

  function el(tag, className, attrs = {}, ...children) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    for (const [key, value] of Object.entries(attrs)) if (value != null) node.setAttribute(key, value);
    node.append(...children.flat().filter(c => c != null));
    return node;
  }

  // An icon given as text or as markup starting with "<".
  function icon(value) {
    const node = el("span", "tsb-icon", { "aria-hidden": "true" });
    if (typeof value === "string" && value.trimStart().startsWith("<")) node.innerHTML = value;
    else if (value != null && value !== "") node.textContent = String(value);
    return node;
  }

  const keyOf = v => String(v);

  function mount(root, options = {}) {
    if (!(root instanceof HTMLElement)) throw new Error("TaurisSidebar.mount needs the element to draw the sidebar in");
    if (root.__taurisSidebar) throw new Error("TaurisSidebar.mount: this element already has a sidebar; call destroy() first");
    root.__taurisSidebar = true;
    // An option given as undefined keeps its default.
    const given = changes => Object.fromEntries(Object.entries(changes ?? {}).filter(([, v]) => v !== undefined));
    const opt = { ...DEFAULTS, ...given(options) };
    if (opt.styles) addStyles();
    const L = () => ({ ...LABELS, ...(opt.labels || {}) });
    const id = `tsb-${++uid}`;
    const life = new AbortController();
    const signal = life.signal;
    const call = (fn, ...args) => {
      if (typeof fn !== "function" || signal.aborted) return;
      try {
        fn(...args);
      } catch (e) {
        console.error("[tauris-ui sidebar] a callback failed:", e);
      }
    };

    // ---------- state ----------

    let items = [];
    let selected = opt.selected == null ? null : keyOf(opt.selected);
    let focusKey = null; // the item Tab reaches
    let width = clampWidth(Number(opt.width) || DEFAULTS.width);
    let collapsed = opt.collapsed === true;
    const stored = read();
    if (stored) {
      if (Number.isFinite(stored.width)) width = clampWidth(stored.width);
      if (typeof stored.collapsed === "boolean") collapsed = stored.collapsed;
    }

    function clampWidth(w) {
      const min = Math.max(48, Number(opt.minWidth) || DEFAULTS.minWidth);
      const max = Math.max(min, Number(opt.maxWidth) || DEFAULTS.maxWidth);
      return Math.round(Math.max(min, Math.min(max, w)));
    }
    function read() {
      if (!opt.storageKey) return null;
      try {
        const data = JSON.parse(localStorage.getItem(String(opt.storageKey)) || "null");
        return data && typeof data === "object" ? data : null;
      } catch {
        return null;
      }
    }
    function keep() {
      if (!opt.storageKey) return;
      try {
        localStorage.setItem(String(opt.storageKey), JSON.stringify({ width, collapsed }));
      } catch {
        // storage blocked (a private window): kept for this page only
      }
    }

    // ---------- the parts ----------

    const addedClass = !root.classList.contains("tsb");
    root.classList.add("tsb");
    const toggleBtn = el("div", "tsb-toggle", { role: "button", tabindex: "0", "aria-controls": `${id}-nav` });
    toggleBtn.innerHTML = SIDEBAR_SVG;
    const title = el("div", "tsb-title", { id: `${id}-title` });
    const image = el("span", "tsb-image", { "aria-hidden": "true" });
    const brand = el("div", "tsb-brand", {}, image, title);
    const head = el("div", "tsb-head", {}, brand, toggleBtn);
    const list = el("div", "tsb-list", { role: "list" });
    const nav = el("nav", "tsb-nav", { id: `${id}-nav` }, list);
    const body = el("div", "tsb-body");
    if (opt.content instanceof Node) body.append(opt.content);
    const grip = el("div", "tsb-grip", { role: "separator", tabindex: "0", "aria-orientation": "vertical", "aria-controls": `${id}-nav` });
    root.replaceChildren(head, nav, body, grip);

    // ---------- drawing ----------

    // The image, drawn again only when it changes (not at every draw, which
    // would load it again). One that fails to load leaves the title's first letter.
    let shownImage = "";
    let imageFailed = false;
    function drawImage(src) {
      shownImage = src;
      imageFailed = false;
      image.replaceChildren();
      if (!src) return;
      if (src.startsWith("<")) {
        image.innerHTML = src;
        return;
      }
      const img = el("img", null, { src, alt: "", draggable: "false" });
      img.addEventListener("error", () => {
        if (shownImage !== src || signal.aborted) return;
        imageFailed = true;
        img.remove();
        drawHead();
      }, { once: true, signal });
      image.append(img);
    }

    function drawHead() {
      const words = L();
      const name = String(opt.title ?? "");
      const src = opt.image == null ? "" : String(opt.image).trim();
      if (src !== shownImage) drawImage(src);
      title.textContent = name;
      title.hidden = !name;
      const letter = imageFailed ? name.trim().charAt(0).toUpperCase() : "";
      image.classList.toggle("tsb-image-letter", imageFailed);
      if (imageFailed) image.textContent = letter;
      image.classList.toggle("tsb-image-round", opt.imageShape === "round");
      image.hidden = !src || (imageFailed && !letter);
      brand.hidden = image.hidden && title.hidden;
      // In the rail the title shows as the image's tooltip.
      brand.title = rail() && !image.hidden ? name : "";
      if (!brand.title) brand.removeAttribute("title");
      root.classList.toggle("tsb-has-image", !image.hidden);
      nav.setAttribute("aria-label", String(name || words.label));
    }

    // The items, and the headings between them. They do not nest: a tree is a
    // TaurisTree in `content` (an item's children are left out, and said so once).
    let flat = [];
    let toldNesting = false;
    function flatten() {
      flat = [];
      for (const item of Array.isArray(items) ? items : []) {
        if (!item || typeof item !== "object") continue;
        if ("heading" in item && item.id == null) {
          flat.push({ heading: String(item.heading ?? "") });
          continue;
        }
        if (item.id == null) continue;
        if (Array.isArray(item.children) && item.children.length && !toldNesting) {
          toldNesting = true;
          console.warn(`[tauris-ui sidebar] items do not nest: the children of “${item.label}” are left out. A tree belongs in a TaurisTree, given as \`content\`.`);
        }
        flat.push({ key: keyOf(item.id), item });
      }
    }
    const rail = () => collapsed && opt.collapse !== "hide";
    const hidden = () => collapsed && opt.collapse === "hide";
    // The items the keys go through.
    const reachable = () => flat.filter(r => r.key && !r.item.disabled);
    const rowOf = key => flat.find(r => r.key === key) ?? null;

    function draw() {
      if (signal.aborted) return;
      const words = L();
      const hadFocus = nav.contains(document.activeElement) ? focusKey : null;
      flatten();
      root.classList.toggle("tsb-right", opt.side === "right");
      root.dataset.tsbState = hidden() ? "hidden" : rail() ? "rail" : "open";
      root.style.setProperty("--tsb-w", `${width}px`);
      drawHead();
      const hint = opt.shortcut ? ` (${SHORTCUT})` : "";
      const toggleName = String(collapsed ? words.show : words.hide);
      toggleBtn.setAttribute("aria-label", toggleName);
      toggleBtn.title = toggleName + hint;
      toggleBtn.setAttribute("aria-expanded", String(!collapsed));
      grip.setAttribute("aria-label", String(words.resize));
      grip.setAttribute("aria-valuemin", String(clampWidth(0)));
      grip.setAttribute("aria-valuemax", String(clampWidth(Infinity)));
      grip.setAttribute("aria-valuenow", String(collapsed ? 0 : width));
      grip.hidden = hidden();
      // Out of view, nothing in it can be reached (by a screen reader either).
      nav.inert = hidden();
      head.inert = hidden();
      // The app's own part shows while it is open; no items, no room for them.
      body.hidden = collapsed || !body.childNodes.length;
      nav.hidden = !flat.length;
      root.classList.toggle("tsb-has-body", !body.hidden);
      root.classList.toggle("tsb-has-items", flat.length > 0);
      // The item Tab reaches: the one with the focus, else the selected one, else the first.
      const can = reachable();
      if (!can.some(r => r.key === focusKey)) {
        const sel = selected != null ? rowOf(selected) : null;
        focusKey = (sel && can.includes(sel) ? sel.key : can[0]?.key) ?? null;
      }
      list.replaceChildren();
      for (const r of flat) {
        if (r.heading !== undefined) {
          list.append(el("div", "tsb-heading", { role: "listitem" }, el("span", "tsb-heading-text", { role: "heading", "aria-level": "2" }, r.heading)));
          continue;
        }
        const item = r.item;
        const label = String(item.label ?? "");
        const count = item.count == null || item.count === "" || item.count === 0 ? null : String(item.count);
        const row = el("div", "tsb-item", {
          role: "button",
          tabindex: r.key === focusKey ? "0" : "-1",
          "data-key": r.key,
          "aria-current": r.key === selected ? "page" : null,
          "aria-disabled": item.disabled ? "true" : null,
          // Named by its label and count; in the rail the label shows as a tooltip.
          "aria-label": count ? `${label}, ${count}` : null,
          title: rail() ? (count ? `${label} (${count})` : label) : (item.title ? String(item.title) : null),
        });
        // No icon: its first letter stands for it in the rail.
        const pic = icon(item.icon);
        if (!pic.childNodes.length) {
          pic.classList.add("tsb-no-icon");
          pic.textContent = label.trim().charAt(0).toUpperCase();
        }
        row.append(pic, el("span", "tsb-label", {}, label));
        if (count) row.append(el("span", "tsb-count", { "aria-hidden": "true" }, count));
        list.append(el("div", "tsb-entry", { role: "listitem" }, row));
      }
      if (hadFocus !== null) itemEl(focusKey)?.focus({ preventScroll: true });
    }

    // Which item is selected and which one Tab reaches, on the rows as drawn: a
    // click's row stays the element clicked (its double-click still reaches it).
    function paint() {
      for (const n of list.querySelectorAll(".tsb-item")) {
        n.tabIndex = n.dataset.key === focusKey ? 0 : -1;
        if (n.dataset.key === selected) n.setAttribute("aria-current", "page");
        else n.removeAttribute("aria-current");
      }
    }

    const itemEl = key => (key == null ? null : list.querySelector(`.tsb-item[data-key="${CSS_escape(key)}"]`));
    const CSS_escape = v => (window.CSS?.escape ? window.CSS.escape(v) : String(v).replace(/["\\]/g, "\\$&"));

    // ---------- acting ----------

    function choose(key, how) {
      const r = rowOf(key);
      if (!r || r.item.disabled) return;
      focusKey = key;
      const changed = selected !== key;
      selected = key;
      paint();
      itemEl(key)?.focus({ preventScroll: true });
      if (changed) call(opt.onSelect, r.item, { how });
    }

    function setCollapsed(on, how) {
      if (collapsed === on) return;
      // The focus inside a part that goes (the list, hidden) goes to the button, or out.
      const inside = root.contains(document.activeElement);
      collapsed = on;
      keep();
      draw();
      if (inside && !root.contains(document.activeElement)) {
        if (!hidden()) toggleBtn.focus({ preventScroll: true });
      }
      call(opt.onToggle, { collapsed, how });
    }

    function setWidth(w, tell) {
      const next = clampWidth(w);
      if (next === width) return;
      width = next;
      root.style.setProperty("--tsb-w", `${width}px`);
      grip.setAttribute("aria-valuenow", String(collapsed ? 0 : width));
      keep();
      if (tell) call(opt.onResize, { width });
    }

    // ---------- the mouse ----------

    list.addEventListener("click", e => {
      const row = e.target instanceof Element ? e.target.closest(".tsb-item") : null;
      if (!row || !list.contains(row)) return;
      choose(row.dataset.key, e.detail === 0 ? "keyboard" : "mouse");
    }, { signal });
    // The item with the focus is the one Tab comes back to (focused by a click, a screen reader, the app).
    list.addEventListener("focusin", e => {
      const row = e.target instanceof Element ? e.target.closest(".tsb-item") : null;
      if (row && row.dataset.key !== focusKey) {
        focusKey = row.dataset.key;
        paint();
      }
    }, { signal });
    // A right click on an item, for the app's own menu.
    list.addEventListener("contextmenu", e => {
      const row = e.target instanceof Element ? e.target.closest(".tsb-item") : null;
      if (!row || typeof opt.onContextMenu !== "function") return;
      const r = rowOf(row.dataset.key);
      if (!r) return;
      e.preventDefault();
      call(opt.onContextMenu, r.item, { x: e.clientX, y: e.clientY, how: "mouse" });
    }, { signal });

    const press = (node, fn) => {
      node.addEventListener("click", fn, { signal });
      node.addEventListener("keydown", e => {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        if (!e.repeat) fn(e);
      }, { signal });
    };
    press(toggleBtn, () => setCollapsed(!collapsed, "button"));

    // ---------- the keys ----------

    let typed = "";
    let typedAt = 0;
    // When the key was pressed, not when it was handled: a page busy drawing the
    // last match does not cut short a name typed quickly (0 in an engine that leaves it out).
    const keyTime = e => e.timeStamp || performance.now();
    list.addEventListener("keydown", e => {
      const row = e.target instanceof Element ? e.target.closest(".tsb-item") : null;
      if (!row || e.altKey || e.ctrlKey || e.metaKey) return;
      const key = row.dataset.key;
      const can = reachable();
      const at = can.findIndex(r => r.key === key);
      const r = rowOf(key);
      const go = i => {
        e.preventDefault();
        const next = can[Math.max(0, Math.min(can.length - 1, i))];
        if (!next) return;
        focusKey = next.key;
        paint();
        itemEl(focusKey)?.focus();
      };
      if (e.key === "ArrowDown") go(at + 1);
      else if (e.key === "ArrowUp") go(at - 1);
      else if (e.key === "Home") go(0);
      else if (e.key === "End") go(can.length - 1);
      else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (!e.repeat) choose(key, "keyboard");
      } else if ((e.key === "ContextMenu" || (e.shiftKey && e.key === "F10")) && r && typeof opt.onContextMenu === "function") {
        // The menu key: the app's menu under the item.
        e.preventDefault();
        const box = row.getBoundingClientRect();
        call(opt.onContextMenu, r.item, { x: box.left + 12, y: box.bottom, how: "keyboard" });
      } else if (e.key.length === 1 && e.key !== " ") {
        // A letter: the next item whose label starts with what was typed.
        const now = keyTime(e);
        typed = now - typedAt < opt.typeAheadMs ? typed + e.key.toLowerCase() : e.key.toLowerCase();
        typedAt = now;
        const starts = x => String(x.item.label ?? "").toLowerCase().startsWith(typed);
        const repeat = typed.length > 1 && [...typed].every(c => c === typed[0]);
        const from = typed.length === 1 || repeat ? at + 1 : at;
        const order = [...can.slice(from), ...can.slice(0, from)];
        const hit = order.find(x => (repeat ? String(x.item.label ?? "").toLowerCase().startsWith(typed[0]) : starts(x)));
        if (hit) go(can.indexOf(hit));
      }
    }, { signal });

    if (opt.shortcut) {
      document.addEventListener("keydown", e => {
        if (!isShortcut(e) || e.repeat) return;
        e.preventDefault();
        setCollapsed(!collapsed, "shortcut");
        // Opened from the keys: the keys go on in it, where they left off.
        if (!collapsed) itemEl(focusKey)?.focus({ preventScroll: true });
      }, { signal });
    }

    // ---------- the edge ----------

    // Dragged: the width follows; narrower than half the narrowest, it collapses
    // (and from the rail, dragged wider, it opens). A double-click puts the
    // width back to the one it started with.
    let dragging = null;
    let lastPress = { at: 0, x: 0 };
    grip.addEventListener("pointerdown", e => {
      if (e.button !== 0) return;
      e.preventDefault();
      // A second press soon after, in the same place, is a double-click (told
      // here: the press's capture can keep the browser from seeing one).
      const now = performance.now();
      const twice = now - lastPress.at < 400 && Math.abs(e.clientX - lastPress.x) < 4;
      lastPress = { at: twice ? 0 : now, x: e.clientX };
      if (twice) {
        if (collapsed) setCollapsed(false, "edge");
        else setWidth(Number(opt.width) || DEFAULTS.width, true);
        return;
      }
      grip.setPointerCapture?.(e.pointerId);
      dragging = { x: e.clientX, from: collapsed ? root.getBoundingClientRect().width : width, was: collapsed, width };
      root.classList.add("tsb-resizing");
    }, { signal });
    grip.addEventListener("pointermove", e => {
      if (!dragging) return;
      const dx = (e.clientX - dragging.x) * (opt.side === "right" ? -1 : 1);
      const raw = dragging.from + dx;
      const small = raw < clampWidth(0) / 2;
      if (small !== collapsed) {
        collapsed = small;
        draw();
      }
      if (!small) setWidth(raw, false);
    }, { signal });
    const endDrag = () => {
      if (!dragging) return;
      const was = dragging;
      dragging = null;
      root.classList.remove("tsb-resizing");
      // Collapsed by the drag: it opens again at the width it had.
      if (collapsed) width = was.width;
      keep();
      draw();
      if (collapsed !== was.was) call(opt.onToggle, { collapsed, how: "edge" });
      if (!collapsed && width !== was.width) call(opt.onResize, { width });
    };
    grip.addEventListener("pointerup", endDrag, { signal });
    grip.addEventListener("pointercancel", endDrag, { signal });
    grip.addEventListener("lostpointercapture", endDrag, { signal });
    grip.addEventListener("keydown", e => {
      const step = e.shiftKey ? 50 : 10;
      const dir = opt.side === "right" ? -1 : 1;
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        if (collapsed) return setCollapsed(false, "edge");
        setWidth(width + (e.key === "ArrowRight" ? step : -step) * dir, true);
      } else if (e.key === "Home" || e.key === "End") {
        e.preventDefault();
        if (collapsed) setCollapsed(false, "edge");
        setWidth(e.key === "Home" ? 0 : Infinity, true);
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (!e.repeat) setCollapsed(!collapsed, "edge");
      }
    }, { signal });

    // ---------- start ----------

    items = Array.isArray(opt.items) ? opt.items : [];
    draw();

    return {
      /** Replaces the items (the focus stays on the item of the same id). */
      setItems(next) {
        items = Array.isArray(next) ? next : [];
        draw();
      },
      /** Selects an item by id (null: none). onSelect is not called. */
      select(itemId) {
        if (itemId == null) {
          selected = null;
          return draw();
        }
        const key = keyOf(itemId);
        if (!rowOf(key)) return;
        selected = key;
        focusKey = key;
        draw();
      },
      /** The selected item, or null. */
      selected() { return selected == null ? null : rowOf(selected)?.item ?? null; },
      /** The element below the items for the app's own part (it holds `content`); call refresh() after filling it. */
      get body() { return body; },
      /** Shows the body after the app put something in it (or took everything out). */
      refresh() { draw(); },
      /** Collapses it (true), opens it (false), or switches (no argument). */
      toggle(on) { setCollapsed(on === undefined ? !collapsed : on === true, "api"); },
      /** Whether it is collapsed. */
      get collapsed() { return collapsed; },
      /** Its width when open, in pixels. */
      get width() { return width; },
      /** Sets its width when open (kept between the narrowest and widest). */
      setWidth(w) { setWidth(Number(w), false); },
      /** Changes options: items, selected, title, image, imageShape, labels, the on… functions, collapse, side, widths. */
      update(changes = {}) {
        changes = given(changes);
        Object.assign(opt, changes);
        if (Array.isArray(changes.items)) items = changes.items;
        if ("selected" in changes) selected = changes.selected == null ? null : keyOf(changes.selected);
        if ("width" in changes || "minWidth" in changes || "maxWidth" in changes) width = clampWidth("width" in changes ? Number(changes.width) : width);
        draw();
      },
      /** Puts the keyboard focus on the item Tab reaches (or the button, collapsed to nothing). */
      focus() {
        if (hidden()) return;
        (itemEl(focusKey) ?? toggleBtn).focus({ preventScroll: true });
      },
      /** Removes the sidebar and its listeners; mount can then be called again. */
      destroy() {
        if (signal.aborted) return;
        life.abort();
        root.replaceChildren();
        if (addedClass) root.classList.remove("tsb", "tsb-right", "tsb-resizing", "tsb-has-body", "tsb-has-items", "tsb-has-image");
        root.style.removeProperty("--tsb-w");
        delete root.dataset.tsbState;
        delete root.__taurisSidebar;
      },
    };
  }

  window.TaurisSidebar = { mount };
})();
