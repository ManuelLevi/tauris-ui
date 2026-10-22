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
  let lastReturn = null; // where the last menu sent the focus back to

  function closeCurrent(refocus) {
    current?.close(refocus);
  }

  // The open <dialog> or popover an element is in (the top layer): a menu opened
  // from there goes in it, or it would be drawn behind it or made inert.
  function openLayer(node) {
    try {
      return node?.closest?.("dialog[open], [popover]:popover-open") ?? null;
    } catch {
      return node?.closest?.("dialog[open]") ?? null; // an engine without :popover-open
    }
  }

  // A place for the focus to go back to: on the page, still there, not in a menu.
  const fine = t => t instanceof HTMLElement && t.isConnected && t !== document.body && !t.closest(".tmn-menu");
  // `target`, unless it is inside a menu (one about to close) or gone: then
  // where the open menu would have put the focus.
  function settle(target) {
    if (fine(target)) return target;
    if (fine(current?.returnTarget)) return current.returnTarget;
    if (fine(lastReturn)) return lastReturn;
    return target;
  }

  // Where focus goes back to: the element that had it before the menu opened.
  function restore(target) {
    if (target instanceof HTMLElement && target.isConnected && target !== document.body) {
      // Kept for the opener of this same press (a click from one menu's button
      // to another's), not for later.
      lastReturn = target;
      setTimeout(() => {
        if (lastReturn === target) lastReturn = null;
      }, 0);
      target.focus({ preventScroll: true });
    }
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
        // A sub-menu whose items() fails is an item that is off; the menu still opens.
        try {
          row.__tmnSub = listOf(item.items);
        } catch (e) {
          console.error(`TaurisMenu: the items of "${item.label}" could not be made:`, e);
          row.__tmnSub = [];
        }
        if (row.__tmnSub.length) {
          row.setAttribute("aria-haspopup", "menu");
          row.setAttribute("aria-expanded", "false");
          row.append(el("span", "tmn-sub", { "aria-hidden": "true" }));
        } else {
          row.setAttribute("aria-disabled", "true");
        }
      } else if (item.shortcut != null && item.shortcut !== "") {
        // Shown, not read as part of the name: said as the item's shortcut instead.
        row.append(el("span", "tmn-shortcut", { "aria-hidden": "true" }, String(item.shortcut)));
        const keys = keyShortcuts(String(item.shortcut));
        if (keys) row.setAttribute("aria-keyshortcuts", keys);
      }
      row.__tmnItem = item;
      menu.append(row);
    }
    return menu;
  }

  // Below the point (or the anchor), kept inside the window; above the anchor
  // when it does not fit below. A sub-menu opens to the right of its item, or
  // to the left (at.flipX) when it does not fit. A menu taller than the window scrolls.
  // A menu of the bar (at.below) stays below its title, never over the bar: it scrolls instead.
  function place(menu, at) {
    const pad = 4;
    const vw = document.documentElement.clientWidth || window.innerWidth;
    const vh = document.documentElement.clientHeight || window.innerHeight;
    menu.style.maxHeight = `${Math.max(80, (at.below ? vh - at.y - pad : vh - 2 * pad))}px`;
    const { width, height } = menu.getBoundingClientRect();
    let x = at.x;
    let y = at.y;
    if (y + height > vh - pad && !at.below) {
      if (at.point && at.y - height >= pad) {
        y = at.y - height; // above the point, which stays at a corner
      } else if (at.above == null) {
        y = Math.max(pad, vh - pad - height);
      } else if (at.above - height >= pad) {
        y = at.above - height;
      } else {
        // Room on neither side of its button: on the roomier side, scrolling, never over the button.
        const below = vh - pad - at.y;
        const above = at.above - pad;
        const room = Math.max(80, below, above);
        menu.style.maxHeight = `${room}px`;
        y = below >= above ? at.y : at.above - Math.min(height, room);
      }
    }
    let leftward = false;
    if (at.left && at.flipX != null && at.flipX - width >= pad) {
      x = at.flipX - width;
      leftward = true;
    } else if (x + width > vw - pad) {
      leftward = at.flipX != null && at.flipX - width >= pad;
      x = leftward ? at.flipX - width : at.point && at.x - width >= pad ? at.x - width : Math.max(pad, vw - pad - width);
    }
    menu.style.left = `${Math.round(x)}px`;
    menu.style.top = `${Math.round(y)}px`;
    return leftward;
  }

  const hasSub = item => Boolean(item) && (Array.isArray(item.items) || typeof item.items === "function");

  // A shortcut as shown ("⇧⌘N", "Ctrl+Shift+N", "↩", "Del") in aria-keyshortcuts' words
  // ("Shift+Meta+N"); null when it is not one of those.
  function keyShortcuts(text) {
    const glyphs = { "⌘": "Meta", "⇧": "Shift", "⌥": "Alt", "⌃": "Control" };
    const names = { "↩": "Enter", "⏎": "Enter", "⌫": "Backspace", "⌦": "Delete", "⎋": "Escape", "⇥": "Tab", "Del": "Delete",
      "Ctrl": "Control", "Cmd": "Meta", "Esc": "Escape", "Space": "Space", "␣": "Space" };
    const parts = [];
    let rest = text.trim();
    while (rest && glyphs[rest[0]]) {
      parts.push(glyphs[rest[0]]);
      rest = rest.slice(1);
    }
    for (const piece of rest.split("+").map(p => p.trim()).filter(Boolean)) {
      const key = names[piece] ?? (glyphs[piece] || (/^(F\d{1,2}|[A-Za-z0-9]|Enter|Delete|Backspace|Escape|Tab|Shift|Alt|Meta|Control)$/.test(piece) ? piece : null));
      if (!key) return null;
      parts.push(key.length === 1 ? key.toUpperCase() : key);
    }
    return parts.length ? parts.join("+") : null;
  }

  // Opens a menu. `at` is { x, y, above? } in window pixels; `how` is "mouse"
  // (nothing chosen yet), "keyboard" (first item) or "last" (last item).
  // An item with `items` opens a sub-menu: to the right, on Right, Enter or
  // Space, or when the mouse rests on it; Left or Escape goes back.
  // `list` is made by the caller (listOf) before anything changes, so items()
  // that throws leaves everything as it was.
  function show(list, at, how, o = {}) {
    // Where the focus goes back to; in a menu about to close, or on the page
    // itself (a menu that had it was just closed by this press), where that
    // menu would have put it.
    const before = settle(o.returnTo ?? document.activeElement);
    closeCurrent(false);
    addStyles();
    const returnTo = o.returnTo || !fine(document.activeElement) ? before : document.activeElement;
    // Inside a modal <dialog> everything else is inert: the menu goes in the dialog.
    const host = openLayer(o.owner ?? returnTo) ?? document.body;
    // What is under a menu opened at a point: its scrolling closes the menu.
    const under = at.point ? document.elementFromPoint(at.x, at.y) : null;
    const life = new AbortController();
    const signal = life.signal;
    const levels = []; // the open menus, the first one first
    // The pointer moved since the menu came up: a release now is a choice (one
    // right where the menu opened is not, which a right click's release is).
    let movedSinceOpen = false;
    let firstPoint = null;
    document.addEventListener("pointermove", e => {
      if (!firstPoint) firstPoint = { x: e.clientX, y: e.clientY };
      else if (Math.hypot(e.clientX - firstPoint.x, e.clientY - firstPoint.y) > 3) movedSinceOpen = true;
    }, { capture: true, signal });
    let pressedInside = false; // the press now began on a menu (its click chooses), not on the opener

    const handle = {
      el: null,
      owner: o.owner ?? null,
      returnTarget: returnTo,
      closed: false,
      // why it closed: an item was picked, or the bar went on to another menu
      chosen: false,
      hop: false,
      close(refocus = true) {
        if (handle.closed) return;
        handle.closed = true;
        life.abort();
        // The focus was in the menu (opened from the keys, or the mouse): it
        // goes back where it was, also when the app or a press elsewhere closes it.
        const inside = levels.some(lv => lv.menu.contains(document.activeElement));
        for (const lv of levels) {
          clearTimeout(lv.timer);
          clearTimeout(lv.rest);
          lv.menu.remove();
        }
        if (current === handle) current = null;
        if (refocus || (inside && !handle.hop)) restore(o.refocusTo?.() ?? returnTo);
        // The app's hook last, and a failing one (a sound that cannot play) stops nothing.
        try {
          o.onClose?.({ chosen: handle.chosen, hop: handle.hop });
        } catch (e) {
          console.error("TaurisMenu: onClose failed:", e);
        }
      },
      // New items while it is open: drawn again in place, the focus kept on
      // the item with the same label. Returns the new menu's id.
      replace(next, label = o.label) {
        o.label = label;
        if (handle.closed) return null;
        const active = document.activeElement;
        const inside = levels.some(lv => lv.menu.contains(active));
        const labelOf = node => node?.querySelector(".tmn-label")?.textContent ?? null;
        const was = labelOf(active?.closest?.(".tmn-item"));
        // Which menu of the chain had the focus, and how far each was scrolled.
        const focusLevel = Math.max(0, levels.findIndex(lv => lv.menu.contains(active)));
        const scrolls = levels.map(lv => lv.menu.scrollTop);
        // The sub-menus open now, by the labels of the items that opened them.
        const path = levels.slice(1).map(lv => labelOf(lv.row));
        for (const lv of levels) {
          clearTimeout(lv.timer);
          clearTimeout(lv.rest);
          lv.menu.remove();
        }
        levels.length = 0;
        handle.el = null;
        let lv = level(next, o.label, at, "mouse");
        const top = lv;
        const chain = [lv];
        for (const name of path) {
          const row = enabledIn(lv.menu).find(n => labelOf(n) === name && n.__tmnSub?.length);
          if (!row) break;
          openSub(lv, row, "mouse");
          lv = lv.child;
          chain.push(lv);
        }
        chain.forEach((l, n) => { l.menu.scrollTop = scrolls[n] ?? 0; });
        if (inside) {
          const home = chain[Math.min(focusLevel, chain.length - 1)];
          // The same item; if it is gone, the first one (the keys keep a place).
          const item = enabledIn(home.menu).find(n => labelOf(n) === was) ?? (was !== null ? enabledIn(home.menu)[0] : null);
          if (item) item.focus({ preventScroll: true });
          else home.menu.focus({ preventScroll: true });
        }
        return top.menu.id;
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
      clearTimeout(child.rest);
      child.menu.remove();
      const at = levels.indexOf(child);
      if (at >= 0) levels.splice(at, 1);
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
      const child = level(row.__tmnSub, item.label, { x: r.right - 3, y: r.top - 5, flipX: r.left + 3, left: lv.leftward }, how, lv, row);
      row.setAttribute("aria-expanded", "true");
      row.setAttribute("aria-controls", child.menu.id);
      lv.child = child;
    }

    const enabledIn = menu => [...menu.querySelectorAll(":scope > .tmn-item:not([aria-disabled='true'])")];

    // Whether the pointer, going from `from` to `to`, heads for lv's open
    // sub-menu: inside the triangle from where it was to that menu's near edge.
    function towards(lv, from, to) {
      if (!lv.child || !from) return false;
      const box = lv.child.menu.getBoundingClientRect();
      const x = box.left >= lv.menu.getBoundingClientRect().left ? box.left : box.right;
      const [a, b, c] = [from, { x, y: box.top - 8 }, { x, y: box.bottom + 8 }];
      const side = (p, q, r) => (p.x - r.x) * (q.y - r.y) - (q.x - r.x) * (p.y - r.y);
      const d = [side(to, a, b), side(to, b, c), side(to, c, a)];
      return !(d.some(v => v < 0) && d.some(v => v > 0)) && (to.x !== from.x || to.y !== from.y);
    }
    const go = (lv, node) => (node ? node.focus({ preventScroll: false }) : lv.menu.focus({ preventScroll: true }));

    // One menu of the chain: its keys and its mouse.
    function level(list, label, where, how, parent = null, row = null) {
      const menu = build(list, label);
      host.append(menu);
      // In a <dialog>, in the top layer: neither the dialog's transform nor its overflow moves or cuts it.
      if (host !== document.body && typeof menu.showPopover === "function") {
        menu.popover = "manual";
        menu.showPopover();
      }
      const leftward = place(menu, where);
      const lv = { menu, parent, row, child: null, timer: 0, rest: 0, hover: null, opening: null, last: null, leftward };
      levels.push(lv);
      if (!handle.el) handle.el = menu;

      let typed = "";
      let typedAt = 0;
      menu.addEventListener("keydown", e => {
        if (e.isComposing) return;
        // Any other key ends what was being typed (Shift and the like do not).
        if (e.key.length !== 1 && !["Shift", "Control", "Alt", "Meta", "CapsLock", "Dead", "AltGraph", "Compose", "Process", "Unidentified"].includes(e.key)) typed = "";
        const list = enabledIn(menu);
        const i = list.indexOf(document.activeElement);
        const focused = i >= 0 ? list[i] : null;
        // A space in the middle of typing a label is part of it, not a choice.
        const spelling = e.key === " " && typed !== "" && Date.now() - typedAt < 700;
        // Moving with the keys leaves a sub-menu opened by the mouse behind: it closes.
        const to = n => {
          e.preventDefault();
          clearTimeout(lv.timer);
          clearTimeout(lv.rest);
          lv.opening = null;
          if (lv.child) closeSub(lv);
          if (list.length) go(lv, list[(n + list.length) % list.length]);
        };
        if (e.key === "ArrowDown") to(i + 1);
        else if (e.key === "ArrowUp") to(i < 0 ? list.length - 1 : i - 1);
        else if (e.key === "Home") to(0);
        else if (e.key === "End") to(list.length - 1);
        else if ((e.key === "Enter" || (e.key === " " && !spelling)) && e.repeat) e.preventDefault(); // held: chosen once
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
          // Typing jumps to the next item that starts with what was typed; one
          // letter again and again steps through the items that start with it.
          e.preventDefault();
          const now = Date.now();
          typed = now - typedAt < 700 ? typed + e.key.toLowerCase() : e.key.toLowerCase();
          typedAt = now;
          const text = node => node.querySelector(".tmn-label").textContent.trim().toLowerCase();
          const same = [...typed].every(c => c === typed[0]);
          const from = typed.length > 1 && !same ? Math.max(i, 0) : i + 1;
          const order = list.slice(from).concat(list.slice(0, from));
          // "aaa" is "a" three times, also past an "Aardvark".
          const hit = same ? order.find(node => text(node).startsWith(typed[0])) : order.find(node => text(node).startsWith(typed));
          if (hit) {
            clearTimeout(lv.timer);
            clearTimeout(lv.rest);
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
        // Heading for the open sub-menu, across other items: nothing opens or
        // closes, unless the pointer rests there.
        const point = { x: e.clientX, y: e.clientY };
        const heading = item !== lv.child?.row && towards(lv, lv.last, point);
        lv.last = point;
        clearTimeout(lv.rest);
        if (heading) {
          clearTimeout(lv.timer);
          lv.opening = null;
          lv.rest = setTimeout(() => hoverOn(item), 300);
          return;
        }
        hoverOn(item);
      }, { signal });
      // The item under the pointer is the one Enter chooses; resting on one with a sub-menu opens it.
      function hoverOn(item) {
        if (handle.closed || !levels.includes(lv)) return;
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
            lv.timer = setTimeout(() => { if (levels.includes(lv)) openSub(lv, item, "mouse"); }, 150);
          }
        } else if (lv.child) {
          lv.timer = setTimeout(() => { if (levels.includes(lv)) closeSub(lv); }, 250);
        }
      }
      menu.addEventListener("pointerenter", () => {
        if (parent) {
          clearTimeout(parent.timer);
          clearTimeout(parent.rest);
        }
      }, { signal });
      // Leaving the menu drops a sub-menu about to open, unless the mouse leaves
      // beside its item, on the side where it opens. A sub-menu about to close
      // still closes.
      menu.addEventListener("pointerleave", e => {
        lv.hover = null;
        clearTimeout(lv.rest);
        if (lv.opening) {
          const item = lv.opening.getBoundingClientRect();
          const box = menu.getBoundingClientRect();
          // Beside its item, through the side it will open on: worked out as
          // place() will, from the sub-menu's own width (measured off screen).
          const beside = e.clientY >= item.top - 4 && e.clientY <= item.bottom + 4;
          const probe = build(lv.opening.__tmnSub ?? [], "");
          probe.style.visibility = "hidden";
          host.append(probe);
          const width = probe.getBoundingClientRect().width;
          probe.remove();
          const vw = document.documentElement.clientWidth || window.innerWidth;
          const roomLeft = item.left + 3 - width >= 4;
          const opensLeft = (lv.leftward && roomLeft) || (item.right - 3 + width > vw - 4 && roomLeft);
          const towards = opensLeft ? e.clientX <= box.left + 2 : e.clientX >= box.right - 2;
          if (!(beside && towards)) {
            clearTimeout(lv.timer);
            lv.opening = null;
          }
        }
        if (!lv.child) menu.focus({ preventScroll: true });
      }, { signal });
      menu.addEventListener("click", e => {
        if (e.detail > 0) return; // a pointer's click: its release chose already
        const hit = e.target instanceof Element ? e.target.closest(".tmn-item") : null;
        if (!hit || hit.parentElement !== menu) return;
        if (hasSub(hit.__tmnItem)) openSub(lv, hit, "mouse");
        else choose(lv, hit);
      }, { signal });
      menu.addEventListener("contextmenu", e => e.preventDefault(), { signal });
      menu.addEventListener("scroll", () => { if (lv.child) closeSub(lv); }, { passive: true, signal });
      // The release chooses, as in desktop menus: after a press on an item (or
      // another item, sliding over), or on the title or button that opened it
      // (press, drag, release; not a release right after the menu came up under
      // the pointer), with any button.
      menu.addEventListener("pointerdown", () => { pressedInside = true; }, { signal });
      menu.addEventListener("pointerup", e => {
        if (!pressedInside && !movedSinceOpen) return;
        const hit = e.target instanceof Element ? e.target.closest(".tmn-item") : null;
        if (!hit || hit.parentElement !== menu || off(hit)) return;
        if (hasSub(hit.__tmnItem)) openSub(lv, hit, "mouse");
        else choose(lv, hit);
      }, { signal });
      // The focus going elsewhere without a press (the app focusing a field, a
      // dialog opening) closes it, and leaves the focus there.
      menu.addEventListener("focusout", () => setTimeout(() => {
        const now = document.activeElement;
        if (handle.closed || !now || now === document.body) return;
        if (levels.some(l => l.menu.contains(now)) || handle.owner?.contains(now)) return;
        handle.close(false);
      }), { signal });

      if (how === "keyboard") go(lv, enabledIn(menu)[0]);
      else if (how === "last") go(lv, enabledIn(menu).at(-1));
      else if (!parent) menu.focus({ preventScroll: true });
      return lv;
    }

    level(list, o.label, at, how);

    // A press outside closes it; a press on its own opener is left to the opener.
    document.addEventListener("pointerdown", e => {
      const t = e.target;
      if (!(t instanceof Node) || levels.some(lv => lv.menu.contains(t)) || (handle.owner && handle.owner.contains(t))) return;
      const inside = levels.some(lv => lv.menu.contains(document.activeElement));
      handle.close(false);
      // Pressed on plain text: the browser then drops the focus on the page;
      // it goes back where it was once the press is done.
      if (inside) {
        const back = o.refocusTo?.() ?? returnTo;
        setTimeout(() => {
          if (!document.activeElement || document.activeElement === document.body) restore(back);
        });
      }
    }, { capture: true, signal });
    document.addEventListener("pointerup", () => { pressedInside = false; }, { signal });
    // Focus goes back where it was, so the app answers keys when the person returns.
    // (Not when the focus went into a frame of this page: it stays there.)
    window.addEventListener("blur", () => handle.close(document.activeElement?.tagName !== "IFRAME"), { signal });
    // Inside a <dialog>: the dialog closing takes the menu with it.
    if (host !== document.body) {
      host.addEventListener("close", () => handle.close(false), { signal });
      host.addEventListener("toggle", e => { if (e.newState === "closed") handle.close(false); }, { signal });
    }
    window.addEventListener("resize", () => handle.close(true), { signal });
    // The page scrolling under it, or whatever holds its opener, would leave it
    // hanging away from its title. A list scrolling elsewhere changes nothing.
    document.addEventListener("scroll", e => {
      const t = e.target;
      if (levels.some(lv => lv.menu.contains(t))) return;
      const page = t === document || t === document.documentElement || t === document.body;
      // A menu opened at a point (a right click) closes when what it was opened on scrolls.
      const opener = o.owner ?? (under instanceof Node ? under : returnTo);
      if (page || (t instanceof Node && opener instanceof Node && t.contains(opener))) handle.close(true);
    }, { capture: true, signal });
    return handle;
  }

  // ---------- pop-up menu at a point ----------

  function open(items, at = {}, options = {}) {
    const x = Number.isFinite(at.x) ? at.x : 0;
    const y = Number.isFinite(at.y) ? at.y : 0;
    const list = listOf(items);
    if (!list.length) return { close() {} }; // nothing to show
    const handle = show(list, { x, y, point: true }, options.keyboard ? "keyboard" : "mouse", {
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
    let destroyed = false;
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
      if (disabled() || destroyed) return;
      const list = listOf(items);
      if (!list.length) return;
      const r = element.getBoundingClientRect();
      const gap = Number(options.gap ?? 3);
      const name = label ?? element.textContent.trim();
      handle = show(list, { x: r.left, y: r.bottom + gap, above: r.top - gap }, how, {
        label: name,
        owner: element,
        returnTo,
        refocusTo: () => (how === "mouse" || returnTo !== element ? returnTo : element),
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
      // A right or middle press closes its open menu (as one elsewhere does).
      if (e.button !== 0) {
        handle?.close(true);
        return;
      }
      if (disabled()) return;
      // Keep focus where it was (a field, a list), as a desktop menu does.
      e.preventDefault();
      toggle("mouse", document.activeElement);
    }, { signal });
    element.addEventListener("keydown", e => {
      if (e.altKey || e.ctrlKey || e.metaKey || disabled()) return;
      if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (e.repeat) return; // held: opened once
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
      /** Replaces the items (or the function that makes them); an open menu shows the new ones. */
      setItems(next) {
        if (destroyed) return;
        items = next ?? [];
        if (!handle) return;
        const list = listOf(items);
        if (!list.length) return handle.close(true);
        element.setAttribute("aria-controls", handle.replace(list));
      },
      /** Opens the menu with its first item chosen. */
      open() {
        // From an app's shortcut the focus is elsewhere (a field): it goes back there.
        const from = settle(document.activeElement);
        if (!handle) openIt("keyboard", fine(from) ? from : element);
      },
      /** Closes the menu if it is open. */
      close() { handle?.close(false); },
      /** Removes the menu and its listeners; button can then be called again. */
      destroy() {
        if (destroyed) return;
        destroyed = true;
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
    const hadRole = nav.getAttribute("role");
    nav.setAttribute("role", "menubar");
    const addedLabel = !nav.hasAttribute("aria-label");
    if (addedLabel) nav.setAttribute("aria-label", options.label ?? "Menu");
    let destroyed = false;
    const life = new AbortController();
    const signal = life.signal;
    let menus = Array.isArray(options.menus) ? options.menus : [];
    let titles = [];
    let openAt = -1;
    let openHow = "keyboard";
    let openName = ""; // the open menu's title, for onClose even after setMenus
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

    // Only the titles are the bar's: anything else the page put in the element stays.
    function render() {
      for (const t of titles.splice(menus.length)) t.remove();
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
      if (!usable(i) || destroyed) return;
      const list = listOf(menus[i].items);
      // A menu with nothing in it does not open; its title keeps the focus.
      // Pointing at it from another menu of the bar leaves that one open.
      if (!list.length) {
        if (handle && how === "mouse") return;
        handle?.close(false);
        if (how !== "mouse") focusTitle(i);
        return;
      }
      const keepReturn = handle?.returnTo;
      // From one menu of the bar to the next: the bar stays open, so no onClose or onOpen.
      const hopping = handle != null;
      if (handle) {
        handle.hop = true;
        handle.close(false);
      }
      const t = titles[i];
      const r = t.getBoundingClientRect();
      const back = settle(returnTo ?? keepReturn ?? document.activeElement);
      openAt = i;
      openHow = how;
      openName = String(menus[i].label ?? "");
      handle = show(list, { x: r.left, y: r.bottom, below: true }, how, {
        label: menus[i].label,
        owner: nav,
        returnTo: back,
        // Escape goes back to the title; a chosen item, to where focus was before the bar.
        // (Opened by the app with the focus outside the bar, say from a shortcut: back there.)
        // When the focus was on a title, it is this menu's title (the mouse may have gone on from the first one).
        refocusTo: () => (!nav.contains(back) ? back : t),
        // A chosen item: the focus goes back to where it was before the bar
        // (the field Copy acts on), also after the pointer went on to this menu.
        afterChoose: () => {
          const to = !nav.contains(back) ? back : outside?.isConnected ? outside : how === "mouse" ? null : t;
          if (to) restore(to);
        },
        onSide: dir => {
          // On to the next menu with something in it (an empty one would end the bar's open mode).
          let next = i;
          for (let n = 0; n < menus.length; n++) {
            next = step(next, dir);
            if (next === i || listOf(menus[next].items).length) break;
          }
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
          if (!info.hop) options.onClose?.({ label: openName, chosen: info.chosen });
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
      // A right press, a press beside the titles or on a title that is off: the open menu closes.
      if (e.button !== 0 || !t || !usable(t.__tmnIndex)) {
        handle?.close(true);
        return;
      }
      e.preventDefault(); // focus stays where it was
      const i = t.__tmnIndex;
      if (openAt === i) handle?.close(true);
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
      if (e.repeat && (e.key === "Enter" || e.key === " " || e.key === "ArrowDown" || e.key === "ArrowUp")) {
        e.preventDefault(); // held: opened once
        return;
      }
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
      /** Replaces the menus. An open menu stays open, with its new items, if its title is still there. */
      setMenus(next) {
        if (destroyed) return;
        const was = openAt >= 0 ? menus[openAt] : null;
        menus = Array.isArray(next) ? next : [];
        render();
        if (!was || !handle) return;
        // The open menu is found again by itself, or by its title.
        let at = menus.indexOf(was);
        if (at < 0) at = menus.findIndex(m => String(m?.label ?? "") === String(was.label ?? ""));
        const list = usable(at) ? listOf(menus[at].items) : [];
        if (!list.length) handle.close(true);
        else if (at === openAt) {
          openName = String(menus[at].label ?? "");
          titles[at].setAttribute("aria-controls", handle.replace(list, menus[at].label));
        } else {
          // Its title moved: it opens again under it (the bar stays open: no
          // onClose, no onOpen), the focus on the same item.
          const was = document.activeElement?.closest?.(".tmn-item")?.querySelector(".tmn-label")?.textContent;
          openMenu(at, openHow === "mouse" ? "mouse" : "keyboard");
          const same = [...(handle?.el?.querySelectorAll(".tmn-item:not([aria-disabled='true'])") ?? [])]
            .find(n => n.querySelector(".tmn-label").textContent === was);
          same?.focus({ preventScroll: true });
        }
      },
      /** Opens menu number `index` with its first item chosen, and moves focus into it. */
      open(index = 0) { openMenu(index, "keyboard", settle(document.activeElement)); },
      /** Closes the open menu, if any. */
      close() { handle?.close(false); },
      /** Moves keyboard focus to the first title. */
      focus() {
        if (!destroyed) focusTitle(usable(roving) ? roving : step(-1, 1));
      },
      /** Removes the titles and listeners; bar can then be called again. */
      destroy() {
        if (destroyed) return;
        destroyed = true;
        handle?.close(false);
        life.abort();
        for (const t of titles) t.remove();
        titles = [];
        if (addedClass) nav.classList.remove("tmn-bar");
        if (hadRole == null) nav.removeAttribute("role");
        else nav.setAttribute("role", hadRole);
        if (addedLabel) nav.removeAttribute("aria-label");
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
