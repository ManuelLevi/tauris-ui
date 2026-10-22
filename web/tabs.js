// tauris-ui, the page side. The Rust plugin injects this file into every page,
// with the stylesheet in `CSS` and the version in `VERSION`. It draws one
// window's tab strip and reports back to Rust, which owns the tabs of every
// window.
//
//   const tabs = TaurisTabs.mount(document.getElementById("strip"), { ...options });
//   tabs.on("change", ({ tabs, active }) => { ... });
//
// See README.md for every option, method and event; types are in tabs.d.ts.

(() => {
  "use strict";
  if (window.TaurisTabs) return;

  const CSS = "__TAURIS_TABS_CSS__";
  const VERSION = "__TAURIS_TABS_VERSION__";
  // Whether Rust can follow a tab dragged out of its window (macOS only).
  const CAN_DRAG_OUT = "__TAURIS_TABS_CAN_DRAG_OUT__" !== false;
  const PLUGIN = "plugin:tauris-ui|";
  const STATE_CHANGED = "tauris-ui:state-changed";
  const DROP_HOVER = "tauris-ui:drop-hover";
  const CLOSE_REQUEST = "tauris-ui:close-request";
  const CLOSE_WINDOW_REQUEST = "tauris-ui:close-window-request";

  const CLOSE_SVG = '<svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true"><path d="M1.2 1.2l7.6 7.6M8.8 1.2L1.2 8.8" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';
  const PLUS_SVG = '<svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M6 1.2v9.6M1.2 6h9.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';

  const MAC = /Mac|iPhone|iPad/.test(navigator.userAgentData?.platform || navigator.platform || navigator.userAgent);
  const KEY = MAC ? "⌘" : "Ctrl+";
  const LABELS = {
    tabs: "Tabs",
    newTab: "New tab",
    newTabHint: `New tab (${KEY}T)`,
    closeTab: "Close tab",
    closeOthers: "Close other tabs",
    closeRight: "Close tabs to the right",
    moveToWindow: "Move to new window",
    newTabShortcut: `${KEY}T`,
    closeTabShortcut: `${KEY}W`,
  };

  const DEFAULTS = {
    // every word the strip shows, for another language or other shortcuts
    labels: LABELS,
    // icons: text, or markup starting with "<" (an svg)
    newIcon: PLUS_SVG,
    closeIcon: CLOSE_SVG,
    // what a tab shows: (tab, { active }) => Node | string | Node[] | null.
    // Null (the default) shows the title and a close button. An element with
    // data-tt-close closes the tab when clicked; buttons, links and anything
    // with data-tt-action get their clicks and never start a drag.
    renderTab: null,
    // the menu on a right click of a tab (or of the empty strip):
    //   true   the default items (default)
    //   false  no menu
    //   (tab, items) => items   change the default items; `tab` is null on the strip.
    // An item is { label, action(tab), shortcut?, disabled?, danger? } or "-" for a line.
    contextMenu: true,
    // asked before a tab closes, however it is closed (button, menu, middle
    // click, Delete, ⌘W, or the window's close button, once per tab):
    // (tab, { reason: "tab" | "window" }) => boolean | Promise<boolean>
    onBeforeClose: null,
    // the id of the element that shows the active tab (sets aria-controls)
    panelId: null,
    // extra class names for a tab: (tab) => string
    tabClass: null,
    // the window title follows the active tab: (tab) => string | undefined
    documentTitle: tab => tab?.title,
    // what floats under the mouse while a tab is dragged inside its strip:
    // "tab" (the tab itself, default), "ghost", "title", "none", or (tab, tabEl) => HTMLElement
    dragPreview: "tab",
    dragOut: true,          // a tab can be dragged out of the strip into a window of its own (macOS)
    appear: true,           // new tabs pop in
    middleClickClose: true,
    shortcuts: true,        // ^Tab, ^⇧Tab, ⌘⇧], ⌘⇧[ step through the tabs
    styles: true,           // add the stylesheet (false: bring your own)
    moveThreshold: 4,       // px before a press becomes a drag
    detachDistance: 28,     // px above or below the strip before a tab leaves it
  };

  // Elements inside a tab that keep their own clicks.
  const OWN_CLICKS = "[data-tt-close], [data-tt-action], button, a, input, select, textarea";

  // Grows with every mount and destroy in this page, so Rust can tell the
  // newest close-guard message from a late older one.
  let guardSeq = 0;

  let stylesAdded = false;
  function addStyles() {
    if (stylesAdded) return;
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

  function el(tag, className, attrs = {}, ...children) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    for (const [key, value] of Object.entries(attrs)) if (value != null) node.setAttribute(key, value);
    node.append(...children.flat().filter(c => c != null));
    return node;
  }

  // An icon given as text or as svg markup.
  function icon(node, value) {
    if (typeof value === "string" && value.trimStart().startsWith("<")) node.innerHTML = value;
    else node.textContent = value;
    return node;
  }

  function mount(strip, options = {}) {
    if (!(strip instanceof HTMLElement)) throw new Error("TaurisTabs.mount needs the element to draw the strip in");
    if (strip.__taurisTabs) throw new Error("TaurisTabs.mount: this strip already has tabs; call destroy() first");
    if (!window.__TAURI__?.core) {
      throw new Error('TaurisTabs needs window.__TAURI__: set "app": { "withGlobalTauri": true } in tauri.conf.json');
    }
    const opt = { ...DEFAULTS, ...options, labels: { ...LABELS, ...(options.labels || {}) } };
    opt.dragOut = opt.dragOut && CAN_DRAG_OUT;
    const L = opt.labels;
    if (opt.styles) addStyles();

    const { invoke } = window.__TAURI__.core;
    const { listen } = window.__TAURI__.event;
    const ME = window.__TAURI__.webviewWindow.getCurrentWebviewWindow().label;
    const life = new AbortController();
    const signal = life.signal;

    let warned = false;
    // Every call to Rust; a refusal says how to fix it once, in the console.
    const call = (command, args) => invoke(PLUGIN + command, args).catch(err => {
      const text = String(err?.message ?? err);
      if (!warned && /not allowed|denied|permission|capabilit/i.test(text)) {
        warned = true;
        console.error(`[tauris-ui] Rust refused "${command}" for window "${ME}": ${text}\n` +
          'Fix: in src-tauri/capabilities/*.json add "tauris-ui:default" to "permissions" and make ' +
          '"windows" cover the tab windows, e.g. ["tabs-*"] (or "*").');
      } else {
        console.error(`[tauris-ui] ${command} failed: ${text}`);
      }
      throw err;
    });
    const quiet = promise => promise.catch(() => {});

    strip.__taurisTabs = true;
    strip.classList.add("tt-strip");
    strip.setAttribute("data-tauri-drag-region", "");
    const tabsEl = el("div", "tt-tabs", { role: "tablist", "aria-label": L.tabs, "aria-orientation": "horizontal" });
    // The +, the close crosses and the menu items are not <button>s, so an
    // app's own `button { ... }` rules (starter templates have them) leave
    // them alone; they act as buttons for the keyboard and screen readers.
    const newBtn = icon(el("div", "tt-new", { role: "button", tabindex: "0", title: L.newTabHint, "aria-label": L.newTab }), opt.newIcon);
    const fill = el("div", "tt-fill", { "data-tauri-drag-region": "" });
    strip.prepend(tabsEl, newBtn, fill);

    let tabs = [];
    let active = null;
    let hover = null; // { index, title } while another window's tab hovers this strip
    let drag = null;  // a tab drag in progress inside this strip
    const known = new Set();
    const listeners = new Map();
    const unlisten = [];

    const on = (event, fn) => {
      if (!listeners.has(event)) listeners.set(event, new Set());
      listeners.get(event).add(fn);
      return () => listeners.get(event)?.delete(fn);
    };
    const emit = (event, payload) => listeners.get(event)?.forEach(fn => {
      try { fn(payload); } catch (err) { console.error(`[tauris-ui] a "${event}" listener failed`, err); }
    });

    const activeTab = () => tabs.find(t => t.id === active) ?? null;
    const tabEl = id => tabsEl.querySelector(`.tt-tab[data-id="${id}"]`);

    // ---------- state ----------

    // An answer from Rust is drawn only if nothing changed since it was asked
    // for: a newer answer, or a change made here (a click, an update).
    let loads = 0;
    let pending = 0;
    async function load() {
      const mine = ++loads;
      pending++;
      let state;
      try {
        state = await call("window_state");
      } finally {
        pending--;
      }
      if (signal.aborted || mine !== loads) return;
      // Rust finished that drag: the tab it left behind loses its drag look.
      if (drag?.handedOff) {
        resetDragStyles();
        drag = null;
      }
      const was = active;
      tabs = state.tabs;
      active = state.active;
      render();
      emit("change", { tabs, active });
      // Another tab is active (the +, a tab closed, ⌘T, a drop, Rust): said too.
      if (active !== was) emit("activate", activeTab());
    }

    // A change made here: answers already on their way are now out of date,
    // so they are dropped and Rust is asked again once it has the change.
    function local(promise) {
      const stale = pending > 0;
      loads++;
      promise.then(() => { if (stale) quiet(load()); }, () => quiet(load()));
    }

    function save(tab) {
      const { id, title, ...fields } = tab;
      return call("update_tab", { tab: id, title, fields });
    }

    function activate(id) {
      if (id === active || !tabs.some(t => t.id === id)) return;
      active = id;
      local(call("activate_tab", { tab: id }));
      render();
      emit("change", { tabs, active });
      emit("activate", activeTab());
    }

    // Closes a tab after asking onBeforeClose; true when it closed. A second
    // request for the same tab while the first is being answered is ignored.
    const closing = new Set();
    // The app's answer: false keeps the tab. One that fails keeps it too, and
    // says why. A tab is asked once at a time: ⌘W and the window's close button
    // pressed together share one question (one "Save changes?", not two).
    const asking = new Map();
    function mayClose(tab, reason) {
      if (!opt.onBeforeClose) return Promise.resolve(true);
      let answer = asking.get(tab.id);
      if (!answer) {
        answer = Promise.resolve()
          .then(() => opt.onBeforeClose(tab, { reason }))
          .then(yes => yes !== false, e => {
            console.error("TaurisTabs: onBeforeClose failed, so the tab stays open:", e);
            return false;
          });
        asking.set(tab.id, answer);
        answer.then(() => { if (asking.get(tab.id) === answer) asking.delete(tab.id); });
      }
      return answer;
    }
    async function close(id, reason = "tab") {
      const tab = tabs.find(t => t.id === id);
      if (!tab || closing.has(id)) return false;
      closing.add(id);
      try {
        if (!(await mayClose(tab, reason))) return false;
        emit("close", tab);
        await call("close_tab", { tab: id });
        return true;
      } finally {
        closing.delete(id);
      }
    }

    async function closeAll(list) {
      for (const t of list) if (!(await close(t.id))) return;
    }

    // ---------- right-click menu ----------

    let menu = null;
    let menuReturn = null;
    let menuReturnTab = null;
    function closeMenu() {
      if (!menu) return;
      menu.remove();
      menu = null;
      // The strip may have been drawn again meanwhile: the tab's new element.
      const back = menuReturn?.isConnected ? menuReturn : menuReturnTab != null ? tabEl(menuReturnTab) ?? tabEl(active) : null;
      back?.focus?.({ preventScroll: true });
      menuReturn = null;
      menuReturnTab = null;
    }

    function defaultItems(tab) {
      const at = tab ? tabs.findIndex(t => t.id === tab.id) : -1;
      const items = [{ label: L.newTab, shortcut: L.newTabShortcut, action: () => quiet(call("new_tab")) }];
      if (tab) {
        items.push("-",
          { label: L.closeTab, shortcut: L.closeTabShortcut, action: () => quiet(close(tab.id)) },
          { label: L.closeOthers, disabled: tabs.length < 2, action: () => quiet(closeAll(tabs.filter(t => t.id !== tab.id))) },
          // Where the tab is when chosen: tabs may have come or gone since the menu opened.
          { label: L.closeRight, disabled: at >= tabs.length - 1, action: () => {
            const now = tabs.findIndex(t => t.id === tab.id);
            if (now >= 0) quiet(closeAll(tabs.slice(now + 1)));
          } },
          "-",
          { label: L.moveToWindow, disabled: tabs.length < 2, action: () => quiet(call("move_to_new_window", { tab: tab.id })) });
      }
      return items;
    }

    function openMenu(x, y, tab, returnFocus) {
      if (!opt.contextMenu) return;
      closeMenu();
      let items = defaultItems(tab);
      if (typeof opt.contextMenu === "function") items = opt.contextMenu(tab, items) || items;
      if (!items.length) return;
      menu = el("div", "tt-menu", { role: "menu", tabindex: "-1", "aria-label": tab ? tab.title : L.tabs }, items.map(item => {
        if (item === "-") return el("div", "tt-menu-sep", { role: "separator" });
        const row = el("div", `tt-menu-item${item.danger ? " tt-danger" : ""}`,
          { role: "menuitem", tabindex: "-1", "aria-disabled": item.disabled ? "true" : null },
          el("span", "tt-menu-label", {}, item.label), item.shortcut ? el("span", "tt-menu-shortcut", {}, item.shortcut) : null);
        row.addEventListener("click", () => {
          if (item.disabled) return;
          closeMenu();
          item.action?.(tab);
        });
        return row;
      }));
      document.body.append(menu);
      // Keep it inside the window.
      const { width, height } = menu.getBoundingClientRect();
      menu.style.left = `${Math.max(0, Math.min(x, window.innerWidth - width - 4))}px`;
      menu.style.top = `${Math.max(0, Math.min(y, window.innerHeight - height - 4))}px`;
      menuReturn = returnFocus ?? null;
      menuReturnTab = returnFocus && tab ? tab.id : null;
      menuItems()[0]?.focus({ preventScroll: true });
      menu.addEventListener("keydown", onMenuKey);
      // A press on its padding or a line keeps the focus (and the keys) in the menu.
      menu.addEventListener("pointerdown", e => {
        if (!e.target.closest(".tt-menu-item")) e.preventDefault();
      });
    }

    const menuItems = () => menu ? [...menu.querySelectorAll('.tt-menu-item:not([aria-disabled="true"])')] : [];

    function onMenuKey(e) {
      const items = menuItems();
      const at = items.indexOf(document.activeElement);
      const go = i => { e.preventDefault(); items[(i + items.length) % items.length]?.focus(); };
      if (e.key === "ArrowDown") go(at + 1);
      else if (e.key === "ArrowUp") go(at - 1);
      else if (e.key === "Home") go(0);
      else if (e.key === "End") go(items.length - 1);
      else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); document.activeElement?.click(); }
      else if (e.key === "Escape" || e.key === "Tab") { e.preventDefault(); closeMenu(); }
    }

    document.addEventListener("pointerdown", e => { if (menu && !menu.contains(e.target)) closeMenu(); }, { capture: true, signal });
    window.addEventListener("blur", closeMenu, { signal });
    strip.addEventListener("contextmenu", e => {
      // The strip's empty parts: around and between the tabs, and the + button.
      if (![strip, fill, tabsEl].includes(e.target) && !newBtn.contains(e.target)) return;
      e.preventDefault();
      openMenu(e.clientX, e.clientY, null);
    }, { signal });

    // ---------- rendering ----------

    let shownActive = null;
    function render() {
      // Held while a tab is dragged along the strip: the drop draws it all.
      if (drag?.moved && !drag.handedOff) return;
      const hadFocus = tabsEl.contains(document.activeElement);
      const shown = [...tabsEl.children];
      if (!hover && shown.length === tabs.length && shown.every((n, i) => n.__ttSig === JSON.stringify(tabs[i]))) {
        // The same tabs: only which one is active changed. Each tab stays the
        // element it was (a click, then a second one for a double-click, still
        // reach what was pressed), unless it now draws differently.
        shown.forEach((node, i) => {
          if (!node.__ttStale && node.classList.contains("tt-active") === (tabs[i].id === active)) return;
          const next = tabElement(tabs[i]);
          // What renderTab returns is the app's (its handlers, its references): it
          // is used. But the tab being pressed stays the element pressed until its
          // click is done (the click is the app's), and is drawn again after.
          const held = opt.renderTab && tabs[i].id === pressed;
          if (!held && (opt.renderTab || next.innerHTML !== node.innerHTML)) return node.replaceWith(next);
          node.className = next.className;
          node.setAttribute("aria-selected", next.getAttribute("aria-selected"));
          if (held) node.__ttStale = true;
        });
        const now = [...tabsEl.children];
        now.forEach(n => n.setAttribute("tabindex", Number(n.dataset.id) === active ? "0" : "-1"));
        if (!now.some(n => n.tabIndex === 0)) now[0]?.setAttribute("tabindex", "0");
        finishRender(hadFocus);
        return;
      }
      const items = tabs.map(tabElement);
      // Tabs that just arrived pop in; the first render of a window does not.
      const first = known.size === 0;
      for (const node of items) {
        const id = Number(node.dataset.id);
        if (opt.appear && !known.has(id) && !first) node.classList.add("tt-appear");
        known.add(id);
      }
      if (hover) {
        const ghost = el("div", "tt-tab tt-ghost", { "aria-hidden": "true" }, el("span", "tt-title", {}, hover.title || "Tab"));
        items.splice(Math.min(hover.index, items.length), 0, ghost);
      }
      // One tab is always reachable with Tab, even with none active.
      if (!items.some(n => n.tabIndex === 0)) items.find(n => !n.classList.contains("tt-ghost"))?.setAttribute("tabindex", "0");
      tabsEl.replaceChildren(...items);
      finishRender(hadFocus);
    }

    function finishRender(hadFocus) {
      const current = tabEl(active);
      if (hadFocus) current?.focus({ preventScroll: true });
      // Bring the active tab into view only when it changed, so a row the user
      // scrolled stays put while they type.
      fitStrip(active !== shownActive ? current : null);
      shownActive = active;
      if (!hover && !drag) reportStrip();
      const title = opt.documentTitle(activeTab());
      if (title != null) document.title = title;
    }

    // Too many tabs to fit: the row scrolls; `current` is brought into view.
    function fitStrip(current) {
      const over = tabsEl.scrollWidth > tabsEl.clientWidth + 1;
      tabsEl.classList.toggle("tt-scrolling", over);
      if (over && current) current.scrollIntoView({ block: "nearest", inline: "nearest" });
    }

    function tabElement(tab) {
      const isActive = tab.id === active;
      const body = opt.renderTab ? opt.renderTab(tab, { active: isActive }) : defaultBody(tab);
      const node = el("div", `tt-tab${isActive ? " tt-active" : ""}${opt.tabClass ? " " + (opt.tabClass(tab) || "") : ""}`,
        { role: "tab", "aria-selected": String(isActive), tabindex: isActive ? "0" : "-1", title: tab.title,
          // The default tab is named by its title alone (not "Close tab" too); a tab
          // the app draws is named by what it shows.
          "aria-label": opt.renderTab ? null : tab.title, "aria-controls": opt.panelId }, body);
      node.dataset.id = tab.id;
      node.__ttSig = JSON.stringify(tab); // what it was drawn from: a tab that changed is drawn again
      node.querySelectorAll("button, a, input, select, textarea").forEach(c => c.setAttribute("tabindex", "-1"));
      node.addEventListener("pointerdown", e => startDrag(e, tab.id));
      node.addEventListener("contextmenu", e => { e.preventDefault(); openMenu(e.clientX, e.clientY, tab, node); });
      node.addEventListener("click", e => {
        if (!e.target.closest("[data-tt-close]")) return;
        e.stopPropagation();
        quiet(close(tab.id));
      });
      if (opt.middleClickClose) node.addEventListener("auxclick", e => { if (e.button === 1) quiet(close(tab.id)); });
      return node;
    }

    function defaultBody(tab) {
      return [
        el("span", "tt-title", {}, tab.title),
        icon(el("span", "tt-close", { role: "button", "aria-label": `${L.closeTab}: ${tab.title}`, "data-tt-close": "" }), opt.closeIcon),
      ];
    }

    // Tells Rust where the tabs sit, for drops from other windows; only when it changed.
    let reported = "";
    function reportStrip() {
      const mids = [...tabsEl.querySelectorAll(".tt-tab:not(.tt-ghost)")].map(node => {
        const r = node.getBoundingClientRect();
        return Math.round(r.left + r.width / 2);
      });
      const height = strip.getBoundingClientRect().height;
      const key = `${height}:${mids}`;
      if (key === reported) return;
      reported = key;
      quiet(call("report_strip", { height, mids }));
    }

    // ---------- keyboard on the strip ----------
    // One tab is focusable at a time; arrows move between tabs and show them.

    tabsEl.addEventListener("keydown", e => {
      // Typing in a field inside a tab (a rename box) is the field's business.
      if (e.target.closest?.("input, textarea, select, [contenteditable]:not([contenteditable=false])")) return;
      const node = e.target.closest?.(".tt-tab");
      if (!node || node.classList.contains("tt-ghost")) return;
      // Enter, Space and Delete on a button inside a tab are that button's.
      if (e.target !== node && (e.key === "Enter" || e.key === " " || e.key === "Delete")) return;
      const at = tabs.findIndex(t => t.id === Number(node.dataset.id));
      const go = i => {
        e.preventDefault();
        const next = tabs[Math.max(0, Math.min(i, tabs.length - 1))];
        if (!next) return;
        activate(next.id);
        tabEl(next.id)?.focus();
      };
      if (e.key === "ArrowRight") go(at + 1);
      else if (e.key === "ArrowLeft") go(at - 1);
      else if (e.key === "Home") go(0);
      else if (e.key === "End") go(tabs.length - 1);
      else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(tabs[at].id); }
      // Held down, Delete closes one tab, not one per repeat.
      else if (e.key === "Delete") { e.preventDefault(); if (!e.repeat) quiet(close(tabs[at].id)); }
      else if (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10")) {
        e.preventDefault();
        const r = node.getBoundingClientRect();
        openMenu(r.left + 8, r.bottom, tabs[at], node);
      }
    }, { signal });

    // A wheel over the strip scrolls the tabs sideways when they overflow.
    tabsEl.addEventListener("wheel", e => {
      if (!tabsEl.classList.contains("tt-scrolling") || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
      e.preventDefault();
      tabsEl.scrollLeft += e.deltaY;
    }, { passive: false, signal });

    // ---------- dragging ----------
    // While a tab is dragged along its strip the DOM order stays put: the
    // dragged tab follows the cursor and its neighbours slide aside. The order
    // is committed on release.

    let pressed = null; // the tab under a press, until its click is done
    function startDrag(e, id) {
      // A control-click is a right click on a Mac: it opens the menu, not a drag.
      if (e.button !== 0 || e.ctrlKey || e.target.closest(OWN_CLICKS)) return;
      closeMenu();
      pressed = id;
      activate(id);
      const els = [...tabsEl.querySelectorAll(".tt-tab")];
      const from = els.findIndex(node => Number(node.dataset.id) === id);
      if (from < 0) return;
      const rects = els.map(node => node.getBoundingClientRect());
      // Positions inside the row's content, so they hold while the row scrolls.
      const origin = tabsEl.getBoundingClientRect().left - tabsEl.scrollLeft;
      drag = {
        id, from, to: from, els,
        lefts: rects.map(r => r.left - origin),
        firstLeft: rects[0].left,
        width: rects[from].width,
        x0: e.clientX, y0: e.clientY, x: e.clientX,
        grabInTab: e.clientX - rects[from].left,
        grabY: e.clientY - rects[from].top,
        moved: false, handedOff: false, preview: null, frame: 0, pointer: e.pointerId,
      };
    }

    function makePreview(tab, node) {
      const mode = opt.dragPreview;
      if (mode === "tab" || mode === "none") return null;
      let preview;
      if (typeof mode === "function") {
        preview = mode(tab, node);
        if (!preview) return null;
      } else if (mode === "title") {
        preview = el("div", "tt-preview-title", {}, tab.title);
      } else {
        preview = node.cloneNode(true);
        preview.classList.add("tt-preview-ghost");
        preview.style.width = `${node.getBoundingClientRect().width}px`;
      }
      preview.classList.add("tt-preview");
      preview.setAttribute("aria-hidden", "true");
      document.body.append(preview);
      return preview;
    }

    // Heard on the whole window: before the drag begins the strip does not hold
    // the pointer, and a quick move can leave the strip in one step.
    window.addEventListener("pointermove", e => {
      if (!drag || drag.handedOff) return;
      // The release was lost (a dialog, the window going to the back): no drag without the button.
      if (e.buttons === 0) return endDrag();
      if (!drag.moved) {
        if (Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) < opt.moveThreshold) return;
        drag.moved = true;
        // The strip may have been drawn again since the press: its elements, and
        // where they sit, as they are now.
        drag.els = [...tabsEl.querySelectorAll(".tt-tab:not(.tt-ghost)")];
        drag.from = Math.max(0, drag.els.findIndex(n => Number(n.dataset.id) === drag.id));
        drag.to = drag.from;
        const rects = drag.els.map(n => n.getBoundingClientRect());
        const origin = tabsEl.getBoundingClientRect().left - tabsEl.scrollLeft;
        drag.lefts = rects.map(r => r.left - origin);
        drag.firstLeft = rects[0].left;
        drag.width = rects[drag.from].width;
        // The pointer is held by the strip only once the drag begins, so a plain
        // click or double-click still reaches what was pressed (a renderTab's span).
        try { strip.setPointerCapture(drag.pointer); } catch { /* the pointer is gone */ }
        const node = drag.els[drag.from];
        node.classList.add("tt-dragging");
        drag.els.forEach((n, i) => { if (i !== drag.from) n.classList.add("tt-shifting"); });
        drag.preview = makePreview(tabs.find(t => t.id === drag.id), node);
        if (drag.preview || opt.dragPreview === "none") node.classList.add("tt-slot");
        drag.frame = requestAnimationFrame(edgeScroll);
      }
      drag.x = e.clientX;
      // A lone tab carries its window, exactly like dragging the title bar; it
      // stays drawn as it was (Rust's answer changes nothing in the strip).
      if (opt.dragOut && tabs.length === 1) {
        resetDragStyles();
        return handOff(drag.x0, drag.y0);
      }

      const r = strip.getBoundingClientRect();
      const outside = e.clientY > r.bottom + opt.detachDistance || e.clientY < r.top - opt.detachDistance ||
                      e.clientX < 0 || e.clientX > window.innerWidth;
      if (opt.dragOut && outside) {
        resetDragStyles();
        return handOff(drag.firstLeft + Math.min(drag.grabInTab, drag.width - 12), drag.y0);
      }
      if (drag.preview) {
        drag.preview.style.transform = `translate(${e.clientX - Math.min(drag.grabInTab, 24)}px, ${e.clientY - drag.grabY}px)`;
      }
      slide(e.clientX);
    }, { signal });

    // With more tabs than fit, holding a dragged tab near an end of the row scrolls it.
    function edgeScroll() {
      if (!drag || !drag.moved || drag.handedOff) return;
      if (tabsEl.classList.contains("tt-scrolling")) {
        const box = tabsEl.getBoundingClientRect();
        const step = drag.x < box.left + 32 ? -16 : drag.x > box.right - 32 ? 16 : 0;
        if (step) {
          tabsEl.scrollLeft += step;
          slide(drag.x);
        }
      }
      drag.frame = requestAnimationFrame(edgeScroll);
    }

    // Keeps the dragged tab inside the strip and slides the tabs it passes.
    function slide(clientX) {
      const { from, lefts, width, els } = drag;
      const x = clientX - tabsEl.getBoundingClientRect().left + tabsEl.scrollLeft;
      const first = lefts[0];
      const last = lefts[lefts.length - 1];
      const left = Math.min(Math.max(x - drag.grabInTab, first), last);
      drag.to = Math.min(Math.max(Math.round((left - first) / width), 0), els.length - 1);

      els[from].style.setProperty("--dx", `${left - lefts[from]}px`);
      els.forEach((node, i) => {
        if (i === from) return;
        let shift = 0;
        if (from < i && i <= drag.to) shift = -width;
        if (drag.to <= i && i < from) shift = width;
        node.style.setProperty("--dx", `${shift}px`);
      });
    }

    function resetDragStyles() {
      cancelAnimationFrame(drag.frame);
      drag.preview?.remove();
      drag.preview = null;
      drag.els.forEach(node => {
        node.classList.remove("tt-dragging", "tt-shifting", "tt-slot");
        node.style.removeProperty("--dx");
      });
    }

    function handOff(grabX, grabY) {
      drag.handedOff = true;
      cancelAnimationFrame(drag.frame);
      drag.preview?.remove();
      const id = drag.id;
      // Rust could not take the tab (not macOS, or no new window): it stays.
      call("drag_out", { tab: id, grabX, grabY }).catch(() => {
        if (drag) resetDragStyles();
        drag = null;
        quiet(load());
      });
    }

    function endDrag() {
      // The click that follows the release reaches the pressed tab first; then
      // a tab the app draws is drawn as it now is.
      if (pressed != null) {
        pressed = null;
        setTimeout(() => { if (!signal.aborted) render(); });
      }
      if (!drag) return;
      const finished = drag;
      if (finished.moved && !finished.handedOff) resetDragStyles(); // the tabs drawn in place keep no drag look
      drag = null;
      cancelAnimationFrame(finished.frame);
      finished.preview?.remove();
      // A click: the tab was drawn again as it became active; the focus goes to it
      // (a click gives a tab the focus), not to the page.
      if (!finished.moved && !finished.handedOff) tabEl(finished.id)?.focus({ preventScroll: true });
      if (finished.handedOff || !finished.moved) return;

      // The strip may have been drawn again meanwhile (a tab closed elsewhere):
      // the tab is found by its id, and one that has gone is not dropped.
      const at = tabs.findIndex(t => t.id === finished.id);
      if (at < 0) {
        render();
        return;
      }
      // Let the dropped tab glide from where it was released into its slot.
      const was = finished.els[finished.from];
      const releasedAt = was.isConnected ? was.getBoundingClientRect().left : null;
      // The slot is the place of a tab as the strip was drawn; Rust may have
      // changed the tabs since (one closed elsewhere): it is found by its id.
      const beside = finished.to !== finished.from ? Number(finished.els[finished.to]?.dataset.id) : null;
      const [tab] = tabs.splice(at, 1);
      const near = tabs.findIndex(t => t.id === beside);
      let to = finished.to === finished.from ? at : near >= 0 ? near + (finished.to > finished.from ? 1 : 0) : finished.to;
      to = Math.min(to, tabs.length);
      tabs.splice(to, 0, tab);
      render();
      const dropped = tabEl(finished.id);
      if (dropped && releasedAt !== null) {
        dropped.style.setProperty("--dx", `${releasedAt - dropped.getBoundingClientRect().left}px`);
        dropped.getBoundingClientRect();
        dropped.classList.add("tt-settling");
        dropped.style.setProperty("--dx", "0px");
        // Settled: the tab keeps no trace of the glide (it may stay this element).
        const settled = () => {
          dropped.classList.remove("tt-settling");
          dropped.style.removeProperty("--dx");
        };
        dropped.addEventListener("transitionend", settled, { once: true });
        setTimeout(settled, 300); // no transition (reduced motion, no move): still cleared
      }
      emit("drop", { tab, index: to });

      if (to !== at) local(call("move_tab", { tab: finished.id, index: to }));
    }

    strip.addEventListener("pointerup", endDrag, { signal });
    window.addEventListener("pointerup", endDrag, { signal });
    strip.addEventListener("pointercancel", endDrag, { signal });
    strip.addEventListener("lostpointercapture", endDrag, { signal });

    newBtn.addEventListener("click", () => quiet(call("new_tab")), { signal });
    newBtn.addEventListener("keydown", e => {
      if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      newBtn.click();
    }, { signal });

    // ---------- from Rust and the keyboard ----------

    const keep = promise => promise.then(off => { if (signal.aborted) off(); else unlisten.push(off); });
    keep(listen(STATE_CHANGED, e => { if (e.payload === ME) quiet(load()); }));
    keep(listen(DROP_HOVER, e => {
      const { label, index, title } = e.payload;
      if (label !== ME) return;
      // A tab from another window landed here.
      if (hover && index === null && !title) emit("drop", { tab: null, index: null });
      hover = index === null ? null : { index, title };
      render();
    }));
    keep(listen(CLOSE_REQUEST, e => {
      if (e.payload?.label === ME) quiet(close(e.payload.tab));
    }));
    // The window's close button: every tab is asked, and the window closes
    // only if all of them agree.
    let askingWindow = false;
    keep(listen(CLOSE_WINDOW_REQUEST, async e => {
      if (e.payload !== ME) return;
      quiet(call("close_asked")); // alive: Rust waits for the tabs' answers
      if (askingWindow) return;
      askingWindow = true;
      try {
        for (const tab of [...tabs]) {
          if (!(await mayClose(tab, "window"))) return;
        }
        quiet(call("close_window"));
      } finally {
        askingWindow = false;
      }
    }));
    // With an onBeforeClose, Rust asks this page before ⌘W or the close button act.
    if (opt.onBeforeClose) quiet(call("set_close_guard", { on: true, seq: ++guardSeq }));

    window.addEventListener("resize", () => { if (!hover && !drag) { fitStrip(tabEl(active)); reportStrip(); } }, { signal });

    if (opt.shortcuts) {
      document.addEventListener("keydown", e => {
        // ^Tab and ^⇧Tab (or ⌘⇧] and ⌘⇧[, as in Safari) step through this window's tabs.
        const step = e.ctrlKey && e.key === "Tab" ? (e.shiftKey ? -1 : 1)
          : e.metaKey && e.shiftKey && e.code === "BracketRight" ? 1
            : e.metaKey && e.shiftKey && e.code === "BracketLeft" ? -1 : 0;
        if (!step || tabs.length < 2) return;
        e.preventDefault();
        const at = tabs.findIndex(t => t.id === active);
        activate(tabs[(at + step + tabs.length) % tabs.length].id);
      }, { signal });
    }

    quiet(load());

    return {
      get tabs() { return tabs; },
      get active() { return active; },
      activeTab,
      activate,
      /** Closes a tab after asking onBeforeClose; resolves to true when it closed. */
      close,
      /** Opens a tab after the active one: { title, ...yourFields }. Resolves to its id. */
      open({ title = L.newTab, ...fields } = {}) {
        return call("open_tab", { title, fields });
      },
      /** Sends a tab's title and fields to Rust (after you changed them) and redraws the strip. */
      update(tab, patch = {}) {
        const at = tabs.findIndex(t => t.id === (typeof tab === "number" ? tab : tab?.id));
        if (at < 0) return;
        const { id: _id, ...rest } = patch; // a tab's id is Rust's, never the page's
        // Changes made to the tab object itself are kept too; the result is a
        // new object, so frameworks that compare objects (React) see the change.
        const next = { ...tabs[at], ...(typeof tab === "object" ? tab : {}), ...rest, id: tabs[at].id };
        // The object the app holds gets the patch too, so changing it later and
        // calling update(tab) again does not undo this.
        if (tab && typeof tab === "object" && !Object.isFrozen(tab)) Object.assign(tab, rest);
        tabs = tabs.slice();
        tabs[at] = next;
        local(save(next));
        const old = tabEl(next.id);
        if (drag?.moved && !drag.handedOff) {
          // Drawn when the drag ends.
        } else if (old && !hover) {
          // Only this tab is drawn again; it keeps the focus, and stays the one Tab reaches.
          const hadFocus = old.contains(document.activeElement);
          const fresh = tabElement(next);
          fresh.tabIndex = old.tabIndex;
          old.replaceWith(fresh);
          if (hadFocus) fresh.focus({ preventScroll: true });
        } else {
          render();
        }
        if (next.id === active) {
          const title = opt.documentTitle(next);
          if (title != null) document.title = title;
        }
        emit("update", next);
        emit("change", { tabs, active });
      },
      reload: load,
      reportStrip,
      on,
      destroy() {
        if (opt.onBeforeClose) quiet(call("set_close_guard", { on: false, seq: ++guardSeq }));
        life.abort();
        unlisten.splice(0).forEach(off => off());
        closeMenu();
        drag?.preview?.remove();
        drag = null;
        tabsEl.remove();
        newBtn.remove();
        fill.remove();
        strip.classList.remove("tt-strip");
        strip.removeAttribute("data-tauri-drag-region");
        delete strip.__taurisTabs;
        listeners.clear();
      },
    };
  }

  window.TaurisTabs = { mount, version: VERSION };
})();
