// tauris-ui in-window menus: a menu bar, menu buttons (a toolbar button with
// a ▾ caret) and pop-up menus at a point (a right click). Plain JavaScript:
// no build step, no dependencies. In a Tauri app the plugin injects this file
// with its stylesheet (web/menus.css), which is added the first time a page
// uses it. Elsewhere (the demo page) load web/menus.css with a <link>.
//
//   const bar = TaurisMenu.bar(navElement, { menus: [
//     { label: "File", items: [{ label: "New project…", shortcut: "⌘N", action: () => { ... } }, "-", ...] },
//   ] });
//   TaurisMenu.button(toolbarButton, { items: () => [...] });   // ▾ opens a menu under it
//   TaurisMenu.open(items, { x: e.clientX, y: e.clientY });     // a right-click menu
//
// An item is { label, shortcut?, disabled?, checked?, color?, danger?, action? }, or "-" for a
// line between groups; null and false are skipped, for items that only sometimes exist.
// An item with `items` (a list, or a function) opens a sub-menu.
// `items` can be a function: it is called each time the menu opens, so the
// menu always shows the app's state as it is now.
//
// Keyboard, as in desktop menus: Enter, Space or Down opens a menu (Up opens
// it at its last item); Up, Down, Home and End move; a letter jumps to the
// next item starting with it; Enter or Space chooses; Escape closes and puts
// focus back where it was; Left and Right go to the next menu of the bar.
// Shortcuts are shown, not bound: the app binds its own keys.
//
// onOpen({ label, how }) and onClose({ label, chosen }) on a bar or a button
// tell the app when a menu opens and closes (for a sound, say). chosen is true
// when an item was picked. Going from one menu of the bar to the next (Left,
// Right, or pointing at another title) is neither: the bar stays open.
//
// Nothing here is a <button>, so an app's plain `button { ... }` rule cannot
// restyle the menus. Labels are set as text, never as markup.

(() => {
  "use strict";
  if (window.TaurisMenu) return;

  // Filled in by the plugin; left as is when the file is loaded on its own.
  const CSS = "__TAURIS_MENUS_CSS__";
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

  let uid = 0;
  const nextId = () => `tmn-${++uid}`;

  function el(tag, className, attrs = {}, ...children) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    for (const [k, v] of Object.entries(attrs)) if (v != null) node.setAttribute(k, v);
    node.append(...children.flat().filter(c => c != null));
    return node;
  }

  function need(element, what) {
    if (!(element instanceof HTMLElement)) throw new Error(`TaurisMenu.${what} needs an element`);
  }

  const off = node => node.getAttribute("aria-disabled") === "true";
  const isSeparator = item => item === "-" || (item && typeof item === "object" && item.separator === true);
  const listOf = items => {
    const list = typeof items === "function" ? items() : items;
    return Array.isArray(list) ? list.filter(item => item != null && item !== false) : [];
  };

  // ---------- the one open menu ----------
  // Only one menu is open at a time, in the whole page. It hangs from <body>
  // (position: fixed), so no container of the app can clip it.

  let current = null;

  function closeCurrent(refocus) {
    current?.close(refocus);
  }

  // Where focus goes back to: the element that had it before the menu opened.
  function restore(target) {
    if (target instanceof HTMLElement && target.isConnected && target !== document.body) target.focus({ preventScroll: true });
  }

  function build(list, label) {
    const checks = list.some(item => !isSeparator(item) && typeof item.checked === "boolean");
    const menu = el("div", "tmn-menu" + (checks ? " tmn-checks" : ""), { id: nextId(), role: "menu", tabindex: "-1", "aria-label": label || null });
    for (const item of list) {
      if (isSeparator(item)) {
        menu.append(el("div", "tmn-sep", { role: "separator" }));
        continue;
      }
      const checkable = typeof item.checked === "boolean";
      const row = el("div", "tmn-item" + (item.danger ? " tmn-danger" : ""), {
        role: checkable ? "menuitemcheckbox" : "menuitem",
        tabindex: "-1",
        "aria-checked": checkable ? String(item.checked) : null,
        "aria-disabled": item.disabled ? "true" : null,
      });
      if (checks) row.append(el("span", "tmn-check", { "aria-hidden": "true" }, checkable && item.checked ? "✓" : ""));
      if (item.color) {
        const chip = el("span", "tmn-chip", { "aria-hidden": "true" });
        chip.style.setProperty("--tmn-chip", String(item.color));
        row.append(chip);
      }
      row.append(el("span", "tmn-label", {}, String(item.label ?? "")));
      if (Array.isArray(item.items) || typeof item.items === "function") {
        // Made once here; an empty sub-menu is an item that is off.
        row.__tmnSub = listOf(item.items);
        if (row.__tmnSub.length) {
          row.setAttribute("aria-haspopup", "menu");
          row.setAttribute("aria-expanded", "false");
          row.append(el("span", "tmn-sub", { "aria-hidden": "true" }));
        } else {
          row.setAttribute("aria-disabled", "true");
        }
      } else if (item.shortcut != null && item.shortcut !== "") {
        row.append(el("span", "tmn-shortcut", {}, String(item.shortcut)));
      }
      row.__tmnItem = item;
      menu.append(row);
    }
    return menu;
  }

  // Below the point (or the anchor), kept inside the window; above the anchor
  // when it does not fit below. A sub-menu opens to the right of its item, or
  // to the left (at.flipX) when it does not fit. A menu taller than the window scrolls.
  function place(menu, at) {
    const pad = 4;
    const vw = document.documentElement.clientWidth || window.innerWidth;
    const vh = document.documentElement.clientHeight || window.innerHeight;
    menu.style.maxHeight = `${Math.max(80, vh - 2 * pad)}px`;
    const { width, height } = menu.getBoundingClientRect();
    let x = at.x;
    let y = at.y;
    if (y + height > vh - pad) y = at.above != null && at.above - height >= pad ? at.above - height : Math.max(pad, vh - pad - height);
    if (x + width > vw - pad) x = at.flipX != null && at.flipX - width >= pad ? at.flipX - width : Math.max(pad, vw - pad - width);
    menu.style.left = `${Math.round(x)}px`;
    menu.style.top = `${Math.round(y)}px`;
  }

  const hasSub = item => Boolean(item) && (Array.isArray(item.items) || typeof item.items === "function");

  // Opens a menu. `at` is { x, y, above? } in window pixels; `how` is "mouse"
  // (nothing chosen yet), "keyboard" (first item) or "last" (last item).
  // An item with `items` opens a sub-menu: to the right, on Right, Enter or
  // Space, or when the mouse rests on it; Left or Escape goes back.
  function show(items, at, how, o = {}) {
    closeCurrent(false);
    addStyles();
    const returnTo = o.returnTo ?? document.activeElement;
    // Inside a modal <dialog> everything else is inert: the menu goes in the dialog.
    const host = (o.owner ?? returnTo)?.closest?.("dialog[open]") ?? document.body;
    const life = new AbortController();
    const signal = life.signal;
    const levels = []; // the open menus, the first one first

    const handle = {
      el: null,
      owner: o.owner ?? null,
      closed: false,
      // why it closed: an item was picked, or the bar went on to another menu
      chosen: false,
      hop: false,
      close(refocus = true) {
        if (handle.closed) return;
        handle.closed = true;
        life.abort();
        for (const lv of levels) {
          clearTimeout(lv.timer);
          lv.menu.remove();
        }
        if (current === handle) current = null;
        o.onClose?.({ chosen: handle.chosen, hop: handle.hop });
        if (refocus) restore(o.refocusTo?.() ?? returnTo);
      },
    };
    current = handle;

    function choose(lv, row) {
      if (!row || off(row)) return;
      const item = row.__tmnItem;
      if (hasSub(item)) {
        openSub(lv, row, "keyboard");
        return;
      }
      handle.chosen = true;
      handle.close(true);
      o.afterChoose?.();
      if (typeof item.action === "function") item.action(item);
    }

    function closeSub(lv) {
      const child = lv.child;
      if (!child) return;
      closeSub(child);
      clearTimeout(child.timer);
      child.menu.remove();
      levels.splice(levels.indexOf(child), 1);
      child.row.setAttribute("aria-expanded", "false");
      child.row.removeAttribute("aria-controls");
      lv.child = null;
    }

    function openSub(lv, row, how) {
      clearTimeout(lv.timer);
      if (lv.child?.row === row) {
        if (how !== "mouse") go(lv.child, enabledIn(lv.child.menu)[0]);
        return;
      }
      closeSub(lv);
      if (off(row)) return;
      const item = row.__tmnItem;
      if (!row.__tmnSub?.length) return;
      const r = row.getBoundingClientRect();
      const child = level(row.__tmnSub, item.label, { x: r.right - 3, y: r.top - 5, flipX: r.left + 3 }, how, lv, row);
      row.setAttribute("aria-expanded", "true");
      row.setAttribute("aria-controls", child.menu.id);
      lv.child = child;
    }

    const enabledIn = menu => [...menu.querySelectorAll(":scope > .tmn-item:not([aria-disabled='true'])")];
    const go = (lv, node) => (node ? node.focus({ preventScroll: false }) : lv.menu.focus({ preventScroll: true }));

    // One menu of the chain: its keys and its mouse.
    function level(list, label, where, how, parent = null, row = null) {
      const menu = build(list, label);
      host.append(menu);
      place(menu, where);
      const lv = { menu, parent, row, child: null, timer: 0, hover: null, opening: null };
      levels.push(lv);
      if (!handle.el) handle.el = menu;

      let typed = "";
      let typedAt = 0;
      menu.addEventListener("keydown", e => {
        if (e.isComposing) return;
        const list = enabledIn(menu);
        const i = list.indexOf(document.activeElement);
        const focused = i >= 0 ? list[i] : null;
        // A space in the middle of typing a label is part of it, not a choice.
        const spelling = e.key === " " && typed !== "" && Date.now() - typedAt < 700;
        // Moving with the keys leaves a sub-menu opened by the mouse behind: it closes.
        const to = n => {
          e.preventDefault();
          clearTimeout(lv.timer);
          lv.opening = null;
          if (lv.child) closeSub(lv);
          if (list.length) go(lv, list[(n + list.length) % list.length]);
        };
        if (e.key === "ArrowDown") to(i + 1);
        else if (e.key === "ArrowUp") to(i < 0 ? list.length - 1 : i - 1);
        else if (e.key === "Home") to(0);
        else if (e.key === "End") to(list.length - 1);
        else if (e.key === "Enter" || (e.key === " " && !spelling)) {
          e.preventDefault();
          if (focused) choose(lv, focused);
        } else if (e.key === "ArrowRight" && focused && hasSub(focused.__tmnItem)) {
          e.preventDefault();
          openSub(lv, focused, "keyboard");
        } else if (e.key === "ArrowLeft" && parent) {
          // Back to the item that opened this sub-menu.
          e.preventDefault();
          closeSub(parent);
          row.focus({ preventScroll: true });
        } else if (e.key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          if (parent) {
            closeSub(parent);
            row.focus({ preventScroll: true });
          } else {
            handle.close(true);
          }
        } else if (e.key === "Tab") {
          e.preventDefault();
          handle.close(true);
        } else if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && o.onSide) {
          e.preventDefault();
          o.onSide(e.key === "ArrowLeft" ? -1 : 1);
        } else if (e.key.length === 1 && !e.altKey && !e.ctrlKey && !e.metaKey) {
          // Typing jumps to the next item that starts with what was typed.
          e.preventDefault();
          const now = Date.now();
          typed = now - typedAt < 700 ? typed + e.key.toLowerCase() : e.key.toLowerCase();
          typedAt = now;
          const text = node => node.querySelector(".tmn-label").textContent.trim().toLowerCase();
          const from = typed.length > 1 ? Math.max(i, 0) : i + 1;
          const order = list.slice(from).concat(list.slice(0, from));
          const hit = order.find(node => text(node).startsWith(typed));
          if (hit) {
            clearTimeout(lv.timer);
            lv.opening = null;
            if (lv.child && lv.child.row !== hit) closeSub(lv);
            go(lv, hit);
          }
        }
      }, { signal });

      // The item under the mouse is the one Enter would choose, as in a
      // desktop menu; leaving the menu leaves nothing chosen. Resting on an
      // item with a sub-menu opens it; moving on to another item closes it a
      // moment later, so the mouse can cross other items on its way there.
      menu.addEventListener("pointermove", e => {
        const hit = e.target instanceof Element ? e.target.closest(".tmn-item") : null;
        const item = hit && hit.parentElement === menu ? hit : null;
        if (item && !off(item)) {
          if (document.activeElement !== item) item.focus({ preventScroll: true });
        } else if (document.activeElement !== menu) {
          menu.focus({ preventScroll: true });
        }
        if (item === lv.hover) return;
        lv.hover = item;
        clearTimeout(lv.timer);
        lv.opening = null;
        if (item && hasSub(item.__tmnItem) && !off(item)) {
          if (lv.child?.row !== item) {
            lv.opening = item;
            lv.timer = setTimeout(() => openSub(lv, item, "mouse"), 150);
          }
        } else if (lv.child) {
          lv.timer = setTimeout(() => closeSub(lv), 250);
        }
      }, { signal });
      menu.addEventListener("pointerenter", () => {
        if (parent) clearTimeout(parent.timer);
      }, { signal });
      // Leaving the menu drops a sub-menu about to open, unless the mouse leaves
      // beside its item, on the side where it opens. A sub-menu about to close
      // still closes.
      menu.addEventListener("pointerleave", e => {
        lv.hover = null;
        if (lv.opening) {
          const item = lv.opening.getBoundingClientRect();
          const box = menu.getBoundingClientRect();
          const vw = document.documentElement.clientWidth || window.innerWidth;
          const opensLeft = box.right + box.width > vw - 4;
          const beside = e.clientY >= item.top - 4 && e.clientY <= item.bottom + 4;
          const towards = opensLeft ? e.clientX <= box.left + 2 : e.clientX >= box.right - 2;
          if (!(beside && towards)) {
            clearTimeout(lv.timer);
            lv.opening = null;
          }
        }
        if (!lv.child) menu.focus({ preventScroll: true });
      }, { signal });
      menu.addEventListener("click", e => {
        const hit = e.target instanceof Element ? e.target.closest(".tmn-item") : null;
        if (!hit || hit.parentElement !== menu) return;
        if (hasSub(hit.__tmnItem)) openSub(lv, hit, "mouse");
        else choose(lv, hit);
      }, { signal });
      menu.addEventListener("contextmenu", e => e.preventDefault(), { signal });

      if (how === "keyboard") go(lv, enabledIn(menu)[0]);
      else if (how === "last") go(lv, enabledIn(menu).at(-1));
      else if (!parent) menu.focus({ preventScroll: true });
      return lv;
    }

    level(listOf(items), o.label, at, how);

    // A press outside closes it; a press on its own opener is left to the opener.
    document.addEventListener("pointerdown", e => {
      const t = e.target;
      if (!(t instanceof Node) || levels.some(lv => lv.menu.contains(t)) || (handle.owner && handle.owner.contains(t))) return;
      handle.close(false);
    }, { capture: true, signal });
    // Focus goes back where it was, so the app answers keys when the person returns.
    window.addEventListener("blur", () => handle.close(true), { signal });
    window.addEventListener("resize", () => handle.close(true), { signal });
    return handle;
  }

  // ---------- pop-up menu at a point ----------

  function open(items, at = {}, options = {}) {
    const x = Number.isFinite(at.x) ? at.x : 0;
    const y = Number.isFinite(at.y) ? at.y : 0;
    const handle = show(items, { x, y }, options.keyboard ? "keyboard" : "mouse", {
      label: options.label,
      returnTo: options.returnTo,
      onClose: info => options.onClose?.({ label: String(options.label ?? ""), chosen: info.chosen }),
    });
    return { close: () => handle.close(true) };
  }

  // ---------- menu button (a toolbar button with ▾) ----------

  function button(element, options = {}) {
    need(element, "button");
    if (element.__taurisMenu) throw new Error("TaurisMenu.button: this element already opens a menu; call destroy() first");
    addStyles();
    element.__taurisMenu = true;
    let items = options.items ?? [];
    let label = options.label;
    const life = new AbortController();
    const signal = life.signal;
    let handle = null;
    const caret = options.caret !== false;
    const added = [];
    const mark = (cls) => {
      if (!element.classList.contains(cls)) {
        element.classList.add(cls);
        added.push(cls);
      }
    };
    mark("tmn-opener");
    if (caret) mark("tmn-caret");
    const hadPopup = element.getAttribute("aria-haspopup");
    element.setAttribute("aria-haspopup", "menu");
    element.setAttribute("aria-expanded", "false");
    // Not a <button>? It still has to be reachable and pressable.
    const addedRole = !(element instanceof HTMLButtonElement) && !element.hasAttribute("role");
    if (addedRole) element.setAttribute("role", "button");
    const addedTab = !(element instanceof HTMLButtonElement) && !element.hasAttribute("tabindex");
    if (addedTab) element.setAttribute("tabindex", "0");
    const disabled = () => element.getAttribute("aria-disabled") === "true" || element.disabled === true;

    function openIt(how, returnTo, again = false) {
      if (disabled()) return;
      const r = element.getBoundingClientRect();
      const gap = Number(options.gap ?? 3);
      const name = label ?? element.textContent.trim();
      handle = show(items, { x: r.left, y: r.bottom + gap, above: r.top - gap }, how, {
        label: name,
        owner: element,
        returnTo,
        refocusTo: () => (how === "mouse" ? returnTo : element),
        onClose: info => {
          element.setAttribute("aria-expanded", "false");
          element.removeAttribute("aria-controls");
          handle = null;
          if (!info.hop) options.onClose?.({ label: name, chosen: info.chosen });
        },
      });
      element.setAttribute("aria-expanded", "true");
      element.setAttribute("aria-controls", handle.el.id);
      if (!again) options.onOpen?.({ label: name, how: how === "mouse" ? "mouse" : "keyboard" });
    }
    const toggle = (how, returnTo) => (handle ? handle.close(true) : openIt(how, returnTo));

    element.addEventListener("pointerdown", e => {
      if (e.button !== 0 || disabled()) return;
      // Keep focus where it was (a field, a list), as a desktop menu does.
      e.preventDefault();
      toggle("mouse", document.activeElement);
    }, { signal });
    element.addEventListener("keydown", e => {
      if (e.altKey || e.ctrlKey || e.metaKey || disabled()) return;
      if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const again = handle != null;
        if (handle) {
          handle.hop = true;
          handle.close(false);
        }
        openIt(e.key === "ArrowUp" ? "last" : "keyboard", element, again);
      }
    }, { signal });
    // A click that no pointer made (a screen reader's): open from the keyboard.
    element.addEventListener("click", e => {
      if (e.detail === 0 && !handle && !disabled()) openIt("keyboard", element);
    }, { signal });

    return {
      /** Replaces the items (or the function that makes them). */
      setItems(next) { items = next ?? []; },
      /** Opens the menu with its first item chosen. */
      open() { if (!handle) openIt("keyboard", element); },
      /** Closes the menu if it is open. */
      close() { handle?.close(false); },
      /** Removes the menu and its listeners; button can then be called again. */
      destroy() {
        handle?.close(false);
        life.abort();
        for (const cls of added) element.classList.remove(cls);
        if (hadPopup == null) element.removeAttribute("aria-haspopup");
        else element.setAttribute("aria-haspopup", hadPopup);
        element.removeAttribute("aria-expanded");
        if (addedRole) element.removeAttribute("role");
        if (addedTab) element.removeAttribute("tabindex");
        delete element.__taurisMenu;
      },
    };
  }

  // ---------- menu bar ----------

  function bar(nav, options = {}) {
    need(nav, "bar");
    if (nav.__taurisMenuBar) throw new Error("TaurisMenu.bar: this element already has a menu bar; call destroy() first");
    addStyles();
    nav.__taurisMenuBar = true;
    const addedClass = !nav.classList.contains("tmn-bar");
    nav.classList.add("tmn-bar");
    nav.setAttribute("role", "menubar");
    if (!nav.hasAttribute("aria-label")) nav.setAttribute("aria-label", options.label ?? "Menu");
    const life = new AbortController();
    const signal = life.signal;
    let menus = Array.isArray(options.menus) ? options.menus : [];
    let titles = [];
    let openAt = -1;
    let handle = null;
    let roving = 0;
    // Where focus was before it came into the bar: a chosen item puts it back there.
    let outside = null;

    const usable = i => i >= 0 && i < menus.length && !menus[i].disabled;
    const step = (from, dir) => {
      for (let n = 1; n <= menus.length; n++) {
        const i = (from + dir * n + menus.length * n) % menus.length;
        if (usable(i)) return i;
      }
      return from;
    };

    function render() {
      titles.length = Math.min(titles.length, menus.length);
      while (nav.children.length > menus.length) nav.lastElementChild.remove();
      menus.forEach((m, i) => {
        let t = titles[i];
        if (!t) {
          t = el("span", "tmn-title", { role: "menuitem", "aria-haspopup": "menu", "aria-expanded": "false", tabindex: "-1" });
          t.__tmnIndex = i;
          titles[i] = t;
          nav.append(t);
        }
        const text = String(m.label ?? "");
        if (t.textContent !== text) t.textContent = text;
        if (m.disabled) t.setAttribute("aria-disabled", "true");
        else t.removeAttribute("aria-disabled");
      });
      if (!usable(roving)) roving = Math.max(0, menus.findIndex((_, i) => usable(i)));
      titles.forEach((t, i) => t.setAttribute("tabindex", i === roving ? "0" : "-1"));
    }

    function focusTitle(i) {
      if (!titles[i]) return;
      roving = i;
      titles.forEach((t, n) => t.setAttribute("tabindex", n === i ? "0" : "-1"));
      titles[i].focus({ preventScroll: true });
    }

    function openMenu(i, how, returnTo) {
      if (!usable(i)) return;
      const keepReturn = handle?.returnTo;
      // From one menu of the bar to the next: the bar stays open, so no onClose or onOpen.
      const hopping = handle != null;
      if (handle) {
        handle.hop = true;
        handle.close(false);
      }
      const t = titles[i];
      const r = t.getBoundingClientRect();
      const back = returnTo ?? keepReturn ?? document.activeElement;
      openAt = i;
      handle = show(menus[i].items, { x: r.left, y: r.bottom }, how, {
        label: menus[i].label,
        owner: nav,
        returnTo: back,
        // Escape goes back to the title; a chosen item, to where focus was before the bar.
        refocusTo: () => (how === "mouse" ? back : t),
        afterChoose: () => {
          if (how !== "mouse") restore(outside?.isConnected ? outside : t);
        },
        onSide: dir => {
          const next = step(i, dir);
          roving = next;
          openMenu(next, "keyboard", back);
          titles.forEach((title, n) => title.setAttribute("tabindex", n === next ? "0" : "-1"));
        },
        onClose: info => {
          t.setAttribute("aria-expanded", "false");
          t.removeAttribute("aria-controls");
          if (openAt === i) {
            openAt = -1;
            handle = null;
          }
          if (!info.hop) options.onClose?.({ label: String(menus[i]?.label ?? t.textContent), chosen: info.chosen });
        },
      });
      if (!hopping) options.onOpen?.({ label: String(menus[i].label ?? ""), how: how === "mouse" ? "mouse" : "keyboard" });
      handle.returnTo = back;
      roving = i;
      titles.forEach((title, n) => title.setAttribute("tabindex", n === i ? "0" : "-1"));
      t.setAttribute("aria-expanded", "true");
      t.setAttribute("aria-controls", handle.el.id);
    }

    const titleAt = target => {
      const t = target instanceof Element ? target.closest(".tmn-title") : null;
      return t && nav.contains(t) ? t : null;
    };

    const ours = node => node instanceof Element && (nav.contains(node) || node.closest(".tmn-menu") != null);
    nav.addEventListener("focusin", e => {
      if (e.relatedTarget instanceof HTMLElement && !ours(e.relatedTarget)) outside = e.relatedTarget;
    }, { signal });
    nav.addEventListener("focusout", e => {
      if (e.relatedTarget instanceof HTMLElement && !ours(e.relatedTarget)) outside = null;
    }, { signal });

    nav.addEventListener("pointerdown", e => {
      const t = titleAt(e.target);
      if (e.button !== 0) return;
      if (!t) {
        handle?.close(true);
        return;
      }
      e.preventDefault(); // focus stays where it was
      const i = t.__tmnIndex;
      if (openAt === i) handle.close(true);
      else openMenu(i, "mouse", handle?.returnTo ?? document.activeElement);
    }, { signal });

    // With a menu of the bar open, pointing at another title opens that one.
    nav.addEventListener("pointerover", e => {
      const t = titleAt(e.target);
      if (!t || openAt < 0 || t.__tmnIndex === openAt) return;
      openMenu(t.__tmnIndex, "mouse");
    }, { signal });

    nav.addEventListener("keydown", e => {
      const t = titleAt(e.target);
      if (!t || e.altKey || e.ctrlKey || e.metaKey) return;
      const i = t.__tmnIndex;
      if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
        e.preventDefault();
        openMenu(i, "keyboard", t);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        openMenu(i, "last", t);
      } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        focusTitle(step(i, e.key === "ArrowLeft" ? -1 : 1));
      } else if (e.key === "Home" || e.key === "End") {
        e.preventDefault();
        focusTitle(e.key === "Home" ? step(-1, 1) : step(menus.length, -1));
      } else if (e.key === "Escape" && outside?.isConnected) {
        e.preventDefault();
        restore(outside);
      }
    }, { signal });

    // A click that no pointer made (a screen reader's) opens the menu.
    nav.addEventListener("click", e => {
      const t = titleAt(e.target);
      if (t && e.detail === 0 && openAt !== t.__tmnIndex) openMenu(t.__tmnIndex, "keyboard", t);
    }, { signal });

    render();

    return {
      /** Replaces the menus. An open menu stays open if its title is still there. */
      setMenus(next) {
        menus = Array.isArray(next) ? next : [];
        const was = openAt;
        render();
        if (was >= 0 && !usable(was)) handle?.close(false);
      },
      /** Opens menu number `index` with its first item chosen, and moves focus into it. */
      open(index = 0) { openMenu(index, "keyboard", document.activeElement); },
      /** Closes the open menu, if any. */
      close() { handle?.close(false); },
      /** Moves keyboard focus to the first title. */
      focus() { focusTitle(usable(roving) ? roving : step(-1, 1)); },
      /** Removes the titles and listeners; bar can then be called again. */
      destroy() {
        handle?.close(false);
        life.abort();
        nav.replaceChildren();
        if (addedClass) nav.classList.remove("tmn-bar");
        nav.removeAttribute("role");
        delete nav.__taurisMenuBar;
      },
    };
  }

  window.TaurisMenu = {
    bar,
    button,
    open,
    /** Closes whichever menu is open. */
    close: () => closeCurrent(false),
  };
})();
