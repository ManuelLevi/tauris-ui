// tauris-ui reorder: drag rows into another order, as in a macOS table. The
// row lifts and follows the pointer, a line shows where it will land, Esc
// puts it back, and the rows slide into their new places. ⌥⌘↑ and ⌥⌘↓
// (Ctrl+Alt elsewhere) move the current row one place. Plain JavaScript: no
// build step, no dependencies. In a Tauri app the plugin injects this file
// with its stylesheet (web/reorder.css), added the first time a page uses it.
//
//   const reorder = TaurisReorder.attach(document.querySelector("#projects"), {
//     rows: "tbody tr",                       // what can be dragged; each row's data-id is its id
//     onStart: ids => hold(ids),              // hold this order still while the row is dragged
//     onMove: ids => { save(ids); draw(); },  // the new order: the app keeps it and draws its rows in it
//     onCancel: () => hold(null),
//   });
//
// Nothing moves unless the app asks for it: the app owns its rows and draws
// them in the order it is given. While a row is dragged, the app holds its
// order still (`onStart` gives it), so a change arriving meanwhile cannot
// move rows under the pointer. `TaurisReorder.arrange(list, order)` puts a
// list in an order. The container is the element that scrolls the rows (a
// table's wrapper): near its top or bottom edge a drag scrolls it.

(() => {
  "use strict";
  if (window.TaurisReorder) return;

  // Filled in by the plugin; left as is when the file is loaded on its own.
  const CSS = "__TAURIS_REORDER_CSS__";
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
  const still = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

  const LABELS = {
    // a key move that cannot go further: (id) => text, or text
    first: "It is first already.",
    last: "It is last already.",
    // the pointer over rows it cannot land among (another group's)
    notHere: "It can only move among its own group.",
    // said to a screen reader after a move: (place, count)
    moved: (place, count) => `Moved to ${place} of ${count}.`,
  };

  const DEFAULTS = {
    // The rows that can be dragged (a selector, read again on every move).
    rows: "[data-id]",
    // A row's id (default its data-id).
    id: row => row.dataset.id ?? null,
    // row => a key: a row moves among the rows of its own group only.
    group: null,
    // row => [{ id, els }]: what the row's item moves among, in the order shown,
    // itself included. For items of several rows (a heading and the rows under it).
    items: null,
    // A selector inside a row: a drag starts only there (default anywhere but
    // its controls, unless a control is marked .tauris-drag).
    handle: null,
    // false: no drags and no keys, until update({ enabled: true }).
    enabled: true,
    // ⌥⌘↑ and ⌥⌘↓ (Ctrl+Alt elsewhere) move the current row.
    keys: true,
    // () => the id the keys move (default: the row with the focus, else the selected one).
    current: null,
    // (id, row) => true, false, or why not (a done task): whether this row may move.
    movable: null,
    // How far in the line starts (px), or row => px (rows under a heading).
    indent: 0,
    labels: {},
    // false: the page brings its own stylesheet.
    styles: true,
    // (id, ids): a drag began; ids is the order to hold still until it ends.
    onStart: null,
    // (ids, { id, from, to, how }): the new order of the moved row's group.
    onMove: null,
    // (id): Esc, a drop back where it was, or the window lost the focus.
    onCancel: null,
    // (text): a move refused (first already, another group's rows, not movable).
    onRefuse: null,
  };

  const say = (label, ...args) => (typeof label === "function" ? label(...args) : String(label ?? ""));

  // Where a drag never starts: the row's own controls, but one marked
  // .tauris-drag (a name that opens on a click: a press and a move drags).
  const CONTROLS = "input, textarea, select, button, a[href], label, [contenteditable]:not([contenteditable='false']), [role='button'], [role='checkbox'], [role='menuitem'], .tauris-no-drag";
  // Elements a <div> cannot be put in: the lifted copy and the line go beside them.
  const NO_DIV = new Set(["TABLE", "THEAD", "TBODY", "TFOOT", "TR", "UL", "OL", "DL", "SELECT"]);

  // One live region for every list: what a move did, for a screen reader.
  let live = null;
  function speak(text) {
    if (!text) return;
    if (!live || !live.isConnected) {
      live = document.createElement("span");
      live.className = "trd-live";
      live.setAttribute("role", "status");
      document.body.append(live);
    }
    live.textContent = "";
    requestAnimationFrame(() => { live.textContent = text; });
  }

  /** `list` in the order of `order` (ids); the ones not in it keep their order, after. */
  function arrange(list, order, key = x => x.id) {
    if (!Array.isArray(list)) return [];
    if (!Array.isArray(order)) return list.slice();
    const at = new Map(order.map((id, i) => [String(id), i]));
    return list
      .map((x, i) => [x, i])
      .sort(([a, i], [b, j]) => (at.get(String(key(a))) ?? order.length + i) - (at.get(String(key(b))) ?? order.length + j))
      .map(([x]) => x);
  }

  function attach(container, options = {}) {
    if (!(container instanceof HTMLElement)) throw new Error("TaurisReorder.attach needs the element that holds (and scrolls) the rows");
    if (container.__taurisReorder) throw new Error("TaurisReorder.attach: this element has one already; call destroy() first");
    container.__taurisReorder = true;
    // An option given as undefined keeps its default.
    const given = changes => Object.fromEntries(Object.entries(changes ?? {}).filter(([, v]) => v !== undefined));
    const opt = { ...DEFAULTS, ...given(options) };
    if (opt.styles) addStyles();
    const L = () => ({ ...LABELS, ...(opt.labels || {}) });
    const life = new AbortController();
    const signal = life.signal;
    const call = (fn, ...args) => {
      if (typeof fn !== "function" || signal.aborted) return undefined;
      try {
        return fn(...args);
      } catch (e) {
        console.error("[tauris-ui reorder] a callback failed:", e);
        return undefined;
      }
    };
    const refuse = text => {
      if (!text) return;
      call(opt.onRefuse, text);
      speak(text);
    };

    // ---------- rows and items ----------

    const idOf = row => {
      const v = call(opt.id, row);
      return v == null ? null : String(v);
    };
    const allRows = () => [...container.querySelectorAll(opt.rows)].filter(r => !r.closest(".trd-ghost"));
    const rowById = id => allRows().find(r => idOf(r) === id) ?? null;
    // What the row's item lands among, in the order shown.
    function itemsOf(row) {
      if (typeof opt.items === "function") {
        const out = call(opt.items, row);
        return (Array.isArray(out) ? out : [])
          .map(it => ({ id: it?.id == null ? null : String(it.id), els: (it?.els ?? []).filter(el => el instanceof Element && !el.closest(".trd-ghost")) }))
          .filter(it => it.id != null && it.els.length);
      }
      const key = typeof opt.group === "function" ? call(opt.group, row) : null;
      return allRows()
        .filter(r => typeof opt.group !== "function" || call(opt.group, r) === key)
        .map(r => ({ id: idOf(r), els: [r] }))
        .filter(it => it.id != null);
    }
    // true, or why not ("" when there is nothing to say).
    function mayMove(id, row) {
      if (typeof opt.movable !== "function") return true;
      const v = call(opt.movable, id, row);
      if (v === true || v === undefined) return true;
      return typeof v === "string" ? v : "";
    }
    const indentOf = row => {
      const v = typeof opt.indent === "function" ? call(opt.indent, row) : opt.indent;
      return Number.isFinite(+v) ? +v : 0;
    };
    // The part of the container the rows show in: under a header row that stays.
    function view() {
      const r = container.getBoundingClientRect();
      const head = container.querySelector("thead");
      const below = head ? Math.min(head.getBoundingClientRect().bottom, r.bottom) : r.top;
      return { top: Math.max(r.top, below), bottom: r.bottom, left: r.left, right: r.right };
    }

    // ---------- the slide into place ----------

    // Notes where every item is, just before its order changes (the dragged one
    // where its lifted copy is, so it slides down from there), then, once the
    // app has drawn the new order, slides each from there.
    function slide(group, order, moved) {
      if (still()) return;
      const was = new Map(group.map(it => [it.id, it.els[0].getBoundingClientRect().top + (moved && it.id === moved.id ? moved.dy : 0)]));
      const want = order.join("\n");
      const until = performance.now() + 600;
      const look = () => {
        if (signal.aborted) return;
        // Drawn again, the rows may be new elements: found by id.
        const anchor = rowById(order[0]);
        const now = anchor ? itemsOf(anchor) : [];
        if (now.map(it => it.id).join("\n") !== want) {
          if (performance.now() < until) requestAnimationFrame(look);
          return;
        }
        for (const it of now) {
          const top = was.get(it.id);
          if (top == null) continue;
          const dy = top - it.els[0].getBoundingClientRect().top;
          if (Math.abs(dy) < 1) continue;
          for (const el of it.els) settle(el, dy);
        }
      };
      requestAnimationFrame(look);
    }
    // A table row's cells move (a row itself does not take a transform everywhere).
    function settle(el, dy) {
      const parts = el.tagName === "TR" ? [...el.children] : [el];
      for (const p of parts) {
        p.style.transition = "none";
        p.style.transform = `translateY(${dy}px)`;
      }
      void el.offsetHeight;
      el.classList.add("trd-settle");
      for (const p of parts) {
        p.style.transition = "";
        p.style.transform = "";
      }
      setTimeout(() => el.classList.remove("trd-settle"), 240);
    }

    // After a move the focus stays on the row (drawn again, it may be a new
    // element): at once, for an app that draws in onMove, so the next key
    // press reaches it, and again a frame later for one that draws then.
    function keepFocus(id) {
      const restore = () => {
        if (signal.aborted) return;
        const row = rowById(id);
        if (!row) return;
        const lost = !document.activeElement || document.activeElement === document.body;
        if (lost) (row.hasAttribute("tabindex") ? row : container).focus({ preventScroll: true });
        row.scrollIntoView({ block: "nearest" });
      };
      restore();
      requestAnimationFrame(restore);
    }

    // ---------- moving by one place ----------

    function move(id, dir, how = "keyboard") {
      if (!opt.enabled || drag) return false;
      id = id == null ? null : String(id);
      const row = id == null ? null : rowById(id);
      if (!row) return false;
      const may = mayMove(id, row);
      if (may !== true) {
        refuse(may);
        return false;
      }
      const group = itemsOf(row);
      const from = group.findIndex(it => it.id === id);
      const to = from + (dir < 0 ? -1 : 1);
      if (from < 0) return false;
      if (to < 0 || to >= group.length) {
        refuse(say(to < 0 ? L().first : L().last, id));
        return false;
      }
      const ids = group.map(it => it.id);
      [ids[from], ids[to]] = [ids[to], ids[from]];
      done(group, ids, { id, from, to, how });
      return true;
    }
    // The new order goes to the app, and the rows slide once it has drawn them.
    function done(group, ids, info, moved) {
      slide(group, ids, moved);
      call(opt.onMove, ids, info);
      speak(say(L().moved, info.to + 1, ids.length));
      keepFocus(info.id);
    }

    function current() {
      if (typeof opt.current === "function") {
        const v = call(opt.current);
        return v == null ? null : String(v);
      }
      const a = document.activeElement;
      if (a && container.contains(a)) {
        const row = a.closest(opt.rows);
        if (row && container.contains(row)) return idOf(row);
        const ref = a.getAttribute("aria-activedescendant");
        const named = ref ? document.getElementById(ref)?.closest(opt.rows) : null;
        if (named && container.contains(named)) return idOf(named);
      }
      const chosen = allRows().find(r => r.getAttribute("aria-selected") === "true");
      return chosen ? idOf(chosen) : null;
    }

    container.addEventListener("keydown", e => {
      if (!opt.enabled || !opt.keys || drag || e.isComposing) return;
      if (!(cmd(e) && e.altKey && !e.shiftKey && (e.key === "ArrowUp" || e.key === "ArrowDown"))) return;
      const id = current();
      if (id == null) return;
      e.preventDefault();
      e.stopPropagation();
      move(id, e.key === "ArrowUp" ? -1 : 1, "keyboard");
    }, { signal });

    // ---------- dragging ----------

    let drag = null;

    container.addEventListener("pointerdown", e => {
      if (!opt.enabled || drag || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      if (e.pointerType === "touch") return;
      const t = e.target instanceof Element ? e.target : null;
      const row = t?.closest(opt.rows);
      if (!row || !container.contains(row) || row.closest(".trd-ghost")) return;
      const control = t.closest(CONTROLS);
      if (opt.handle ? !t.closest(opt.handle) : control && control !== row && row.contains(control) && !control.classList.contains("tauris-drag")) return;
      const id = idOf(row);
      if (id == null) return;
      press(e, row, id);
    }, { signal });

    // Nothing happens until the pointer moves 4px.
    function press(e, row, id) {
      const x0 = e.clientX;
      const y0 = e.clientY;
      const ends = new AbortController();
      const on = (target, type, fn, capture = true) => target.addEventListener(type, fn, { capture, signal: AbortSignal.any ? AbortSignal.any([signal, ends.signal]) : ends.signal });
      const off = () => ends.abort();
      let d = null; // the drag, once it begins

      on(window, "pointermove", ev => {
        if (!d) {
          if ((ev.buttons & 1) === 0) return off();
          if (Math.hypot(ev.clientX - x0, ev.clientY - y0) < 4) return;
          const may = mayMove(id, row);
          if (may !== true) {
            refuse(may);
            return off();
          }
          d = begin(row, id, y0);
          if (!d) return off();
          d.off = off;
        }
        // The button let go outside the window: a drop where it is.
        if ((ev.buttons & 1) === 0) return finish(true);
        d.py = ev.clientY;
        place(d);
      });
      on(window, "pointerup", () => (d ? finish(true, "released") : off()));
      on(window, "pointercancel", () => (d ? finish(false, "gone") : off()));
      on(window, "keydown", ev => {
        if (!d || ev.key !== "Escape") return;
        ev.preventDefault();
        ev.stopImmediatePropagation();
        finish(false, "held");
      });
      on(window, "blur", () => (d ? finish(false, "gone") : off()), false);

      function finish(drop, button) {
        off();
        if (!d) return;
        end(d, drop, button);
        d = null;
      }
    }

    function begin(row, id, y0) {
      const group = itemsOf(row);
      const from = group.findIndex(it => it.id === id);
      if (from < 0 || group.length < 2) return null;
      const first = group[from].els[0];
      const box = first.getBoundingClientRect();
      const host = (() => {
        let h = container;
        while (h && NO_DIV.has(h.tagName)) h = h.parentElement;
        return h ?? document.body;
      })();
      getSelection()?.removeAllRanges();

      // The lifted copy: the row in a table of its own (its cells as wide as they are).
      const ghost = document.createElement("div");
      ghost.className = "trd-ghost";
      ghost.setAttribute("aria-hidden", "true");
      const copy = first.cloneNode(true);
      copy.classList.remove("trd-src", "trd-settle");
      for (const el of [copy, ...copy.querySelectorAll("*")]) {
        // Not a row the app (or this) counts, nor one a screen reader reads.
        for (const a of [...el.attributes]) if (a.name === "id" || a.name.startsWith("aria-") || a.name.startsWith("data-") || a.name === "tabindex") el.removeAttribute(a.name);
      }
      if (first.tagName === "TR") {
        const source = first.closest("table");
        const table = document.createElement("table");
        if (source) table.className = source.className;
        table.style.width = `${box.width}px`;
        table.style.tableLayout = "fixed";
        const cols = document.createElement("colgroup");
        for (const cell of first.children) {
          const col = document.createElement("col");
          col.style.width = `${cell.getBoundingClientRect().width}px`;
          cols.append(col);
        }
        const body = document.createElement("tbody");
        body.append(copy);
        table.append(cols, body);
        ghost.append(table);
      } else {
        copy.style.width = `${box.width}px`;
        copy.style.boxSizing = "border-box";
        ghost.append(copy);
      }
      const line = document.createElement("div");
      line.className = "trd-line";
      line.setAttribute("aria-hidden", "true");
      host.append(line, ghost);
      // Fixed, unless an ancestor (a transform) makes its own box: measured once.
      ghost.style.left = "0px";
      ghost.style.top = "0px";
      const origin = ghost.getBoundingClientRect();
      const d = { id, row, group, from, gap: from, py: y0, grab: y0 - box.top, ghost, line, origin: { x: origin.left, y: origin.top }, refused: false, raf: 0, left: box.left };
      ghost.style.left = `${box.left - d.origin.x}px`;
      for (const el of group[from].els) el.classList.add("trd-src");
      container.classList.add("trd-on");
      document.documentElement.classList.add("trd-active");
      drag = d;
      call(opt.onStart, id, group.map(it => it.id));
      place(d);
      d.raf = requestAnimationFrame(() => scroll(d));
      return d;
    }

    function setRefused(d, why) {
      if (Boolean(why) === d.refused) return;
      d.refused = Boolean(why);
      document.documentElement.classList.toggle("trd-no", d.refused);
      d.ghost.classList.toggle("trd-no", d.refused);
      d.line.classList.toggle("trd-no", d.refused);
      if (why) refuse(why);
    }

    function place(d) {
      // Read again: the app may have drawn its rows anew meanwhile.
      const row = rowById(d.id) ?? d.row;
      d.row = row;
      d.group = itemsOf(row);
      d.from = d.group.findIndex(it => it.id === d.id);
      for (const el of d.group[d.from]?.els ?? []) el.classList.add("trd-src");
      const v = view();
      const h = d.ghost.offsetHeight;
      const top = Math.max(v.top, Math.min(d.py - d.grab, v.bottom - h));
      d.ghost.style.top = `${top - d.origin.y}px`;
      // Over rows it cannot land among: no line, the not-allowed pointer, a drop puts it back.
      const under = document.elementFromPoint(d.left + 4, Math.max(v.top + 1, Math.min(d.py, v.bottom - 1)))?.closest(opt.rows);
      const among = under && container.contains(under) && !under.closest(".trd-ghost")
        ? d.group.some(it => it.els.includes(under)) : true;
      setRefused(d, among ? null : L().notHere);
      if (d.refused || !d.group.length) {
        d.gap = -1;
        return;
      }
      // The gap the pointer is in, by the middle of each item.
      let gap = 0;
      for (const it of d.group) {
        const a = it.els[0].getBoundingClientRect().top;
        const b = it.els[it.els.length - 1].getBoundingClientRect().bottom;
        if (d.py > (a + b) / 2) gap++;
      }
      d.gap = gap;
      const last = d.group[d.group.length - 1].els;
      const at = gap < d.group.length ? d.group[gap].els[0].getBoundingClientRect().top : last[last.length - 1].getBoundingClientRect().bottom;
      const width = d.group[0].els[0].getBoundingClientRect();
      const indent = indentOf(row);
      d.line.style.top = `${Math.max(v.top, Math.min(at, v.bottom)) - d.origin.y}px`;
      d.line.style.left = `${Math.max(v.left, width.left) + indent - d.origin.x}px`;
      d.line.style.width = `${Math.max(0, Math.min(v.right, width.right) - Math.max(v.left, width.left) - indent - 4)}px`;
    }

    // Near the top or bottom edge, the rows scroll, faster the closer the pointer.
    function scroll(d) {
      if (drag !== d || signal.aborted) return;
      const v = view();
      const edge = 28;
      const speed = d.py < v.top + edge ? -Math.ceil((v.top + edge - d.py) / 3) : d.py > v.bottom - edge ? Math.ceil((d.py - v.bottom + edge) / 3) : 0;
      if (speed) {
        const was = container.scrollTop;
        container.scrollTop += Math.max(-24, Math.min(24, speed));
        if (container.scrollTop !== was) place(d);
      }
      d.raf = requestAnimationFrame(() => scroll(d));
    }

    // `button`: "released" (a drop, or a release that puts it back), "held" (Esc:
    // the release comes next), "gone" (the window lost the pointer).
    function end(d, drop, button = "gone") {
      d.off?.();
      cancelAnimationFrame(d.raf);
      drag = null;
      container.classList.remove("trd-on");
      document.documentElement.classList.remove("trd-active", "trd-no");
      d.line.remove();
      for (const it of d.group) for (const el of it.els) el.classList.remove("trd-src");
      d.row.classList.remove("trd-src");
      // The release's click would land on what is under the pointer (a name that opens).
      const eat = ev => {
        ev.stopPropagation();
        ev.preventDefault();
      };
      const eatNext = () => {
        window.addEventListener("click", eat, true);
        setTimeout(() => window.removeEventListener("click", eat, true), 0);
      };
      if (button === "released") eatNext();
      else if (button === "held") window.addEventListener("pointerup", eatNext, { capture: true, once: true });
      const moved = drop && !d.refused && d.from >= 0 && d.gap >= 0 && d.gap !== d.from && d.gap !== d.from + 1;
      if (moved && !signal.aborted) {
        const ids = d.group.map(it => it.id).filter(x => x !== d.id);
        const to = d.gap > d.from ? d.gap - 1 : d.gap;
        ids.splice(to, 0, d.id);
        const src = d.group[d.from].els[0].getBoundingClientRect().top;
        const dy = d.ghost.getBoundingClientRect().top - src;
        d.ghost.remove();
        done(d.group, ids, { id: d.id, from: d.from, to, how: "mouse" }, { id: d.id, dy });
        return;
      }
      // Back where it came from.
      const src = d.group[d.from]?.els[0];
      if (src && !still() && !signal.aborted) {
        d.ghost.classList.add("trd-back");
        d.ghost.style.top = `${src.getBoundingClientRect().top - d.origin.y}px`;
        setTimeout(() => d.ghost.remove(), 170);
      } else {
        d.ghost.remove();
      }
      call(opt.onCancel, d.id);
    }

    return {
      /** Changes options: enabled, keys, rows, id, group, items, handle, current, movable, indent, labels, the on… functions. */
      update(changes = {}) {
        Object.assign(opt, given(changes));
        // Turned off mid-drag: the row goes back.
        if (!opt.enabled && drag) end(drag, false);
      },
      /** Moves the row one place up (-1) or down (1), as ⌥⌘↑ ⌥⌘↓ do (from a menu's Move Up): true if it moved. */
      move(id, dir) {
        return move(id, dir, "menu");
      },
      /** The id of the row being dragged, or null. */
      get dragging() {
        return drag ? drag.id : null;
      },
      /** Removes it: a drag under way ends where it began. */
      destroy() {
        if (drag) end(drag, false);
        life.abort();
        container.classList.remove("trd-on");
        delete container.__taurisReorder;
      },
    };
  }

  window.TaurisReorder = {
    attach,
    arrange,
    /** The keys that move a row, as a menu shows them. */
    keys: MAC ? { up: "⌥⌘↑", down: "⌥⌘↓" } : { up: "Ctrl+Alt+↑", down: "Ctrl+Alt+↓" },
  };
})();
