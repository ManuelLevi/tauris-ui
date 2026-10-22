// tauris-ui status: the status bar along a window's foot, as in a desktop
// app. On its left the last message, with an Undo (or another action) for a
// moment; on its right the app's segments: a connection's dot, counters, a
// toggle, a button. Plain JavaScript: no build step, no dependencies. In a
// Tauri app the plugin injects this file with its stylesheet (web/status.css),
// added the first time a page uses it.
//
//   const status = TaurisStatus.mount(document.querySelector("footer"), {
//     segments: [
//       { id: "online", dot: "ok", text: "Online", title: "Connected to the server" },
//       { id: "tasks", text: "7 / 20 tasks" },
//       { id: "sound", text: "Sound: On", pressed: true, onClick: () => toggleSound() },
//     ],
//   });
//   status.say("Deleted “Atlas”.", { undo: () => restore(atlas) });
//   status.set("online", { dot: "bad", text: "Offline" });
//
// A message stays until the next one (or `timeout`); its action goes after
// `actionFor` (10 s), so an old Undo is never pressed by mistake. After the
// action the focus goes back where it was.

(() => {
  "use strict";
  if (window.TaurisStatus) return;

  // Filled in by the plugin; left as is when the file is loaded on its own.
  const CSS = "__TAURIS_STATUS_CSS__";
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

  const LABELS = {
    undo: "Undo",
  };

  const DEFAULTS = {
    // [{ id, text, dot?, title?, strong?, pressed?, onClick? }]: on the right, in this order
    segments: [],
    // How long a message stays (ms); 0: until the next one.
    timeout: 0,
    // How long a message's action (Undo) stays (ms).
    actionFor: 10000,
    labels: {},
    // false: the page brings its own stylesheet
    styles: true,
    // ({ x, y }): a right click on the bar
    onContextMenu: null,
  };

  const DOTS = new Set(["ok", "warn", "bad", "wait", "off"]);
  let uid = 0;

  function mount(root, options = {}) {
    if (!(root instanceof HTMLElement)) throw new Error("TaurisStatus.mount needs the element to draw the status bar in");
    if (root.__taurisStatus) throw new Error("TaurisStatus.mount: this element already has a status bar; call destroy() first");
    root.__taurisStatus = true;
    // An option given as undefined keeps its default.
    const given = changes => Object.fromEntries(Object.entries(changes ?? {}).filter(([, v]) => v !== undefined));
    const opt = { ...DEFAULTS, ...given(options) };
    if (opt.styles) addStyles();
    const L = () => ({ ...LABELS, ...(opt.labels || {}) });
    const id = `tst-${++uid}`;
    const life = new AbortController();
    const signal = life.signal;
    const call = async (fn, ...args) => {
      if (typeof fn !== "function" || signal.aborted) return;
      try {
        await fn(...args);
      } catch (e) {
        console.error("[tauris-ui status] a callback failed:", e);
      }
    };

    const addedClass = !root.classList.contains("tst");
    root.classList.add("tst");
    const left = document.createElement("div");
    left.className = "tst-msg-part";
    const msg = document.createElement("span");
    msg.className = "tst-msg";
    msg.id = `${id}-msg`;
    msg.setAttribute("aria-live", "polite");
    const act = document.createElement("button");
    act.type = "button";
    act.className = "tst-act";
    act.hidden = true;
    left.append(msg, act);
    const right = document.createElement("div");
    right.className = "tst-segments";
    root.replaceChildren(left, right);

    let segments = [];
    let action = null;
    let clearTimer = 0;
    let actionTimer = 0;
    let from = null; // where the focus was before the action was pressed

    // ---------- the message ----------

    function say(text, options = {}) {
      clearTimeout(clearTimer);
      clearTimeout(actionTimer);
      const t = String(text ?? "");
      msg.textContent = t;
      msg.title = t;
      msg.className = `tst-msg${options.kind ? ` tst-${options.kind}` : ""}`;
      const run = typeof options.undo === "function" ? options.undo : typeof options.action?.run === "function" ? options.action.run : null;
      action = run ? { run, label: String(typeof options.undo === "function" ? options.undoLabel ?? L().undo : options.action.label ?? "") } : null;
      act.hidden = !action;
      act.textContent = action ? action.label : "";
      if (action) actionTimer = setTimeout(() => { action = null; act.hidden = true; }, Number(options.actionFor ?? opt.actionFor) || 10000);
      const timeout = Number(options.timeout ?? opt.timeout) || 0;
      if (timeout > 0) clearTimer = setTimeout(clear, timeout);
    }
    function clear() {
      clearTimeout(clearTimer);
      clearTimeout(actionTimer);
      msg.textContent = "";
      msg.title = "";
      msg.className = "tst-msg";
      action = null;
      act.hidden = true;
    }
    act.addEventListener("pointerdown", () => { from = document.activeElement; }, { signal });
    // Reached by Tab: where the focus came from.
    act.addEventListener("focus", e => { if (!from) from = e.relatedTarget; }, { signal });
    act.addEventListener("click", async () => {
      const a = action;
      if (!a) return;
      const was = from;
      from = null;
      clear();
      await call(a.run);
      // Back where the person was (the list they undid in), unless they went on elsewhere.
      const now = document.activeElement;
      if (now && now !== document.body && now !== act) return;
      if (was instanceof HTMLElement && was.isConnected && was !== act && was !== document.body) was.focus({ preventScroll: true });
    }, { signal });

    // ---------- the segments ----------

    function segmentFor(s) {
      const clickable = typeof s.onClick === "function";
      const node = document.createElement(clickable ? "button" : "span");
      node.className = "tst-seg";
      if (clickable) {
        node.type = "button";
        node.classList.add("tst-button");
        node.addEventListener("click", () => call(s.onClick, { how: "mouse" }), { signal });
      }
      node.dataset.id = String(s.id);
      if (s.pressed != null) node.setAttribute("aria-pressed", String(Boolean(s.pressed)));
      if (s.strong) node.classList.add("tst-strong");
      if (s.title) node.title = String(s.title);
      if (s.dot && DOTS.has(s.dot)) {
        const dot = document.createElement("i");
        dot.className = `tst-dot tst-dot-${s.dot}`;
        dot.setAttribute("aria-hidden", "true");
        node.append(dot);
      }
      const text = document.createElement("span");
      text.textContent = String(s.text ?? "");
      node.append(text);
      return node;
    }
    function drawSegments() {
      right.replaceChildren(...segments.map(segmentFor));
    }

    root.addEventListener("contextmenu", e => {
      if (typeof opt.onContextMenu !== "function") return;
      e.preventDefault();
      call(opt.onContextMenu, { x: e.clientX, y: e.clientY });
    }, { signal });

    segments = Array.isArray(opt.segments) ? opt.segments.map(s => ({ ...s })) : [];
    drawSegments();

    return {
      /** Shows a message on the left: { kind: "ok" | "error" | "info", undo, undoLabel, action: { label, run }, timeout }. */
      say,
      /** Takes the message away. */
      clear,
      /** The message shown now. */
      get message() {
        return msg.textContent;
      },
      /** Changes one segment: { text, dot, title, strong, pressed, onClick }. */
      set(segId, changes = {}) {
        const s = segments.find(x => String(x.id) === String(segId));
        if (!s) return;
        Object.assign(s, changes);
        drawSegments();
      },
      /** Changes options: segments, timeout, actionFor, labels, onContextMenu. */
      update(changes = {}) {
        changes = given(changes);
        Object.assign(opt, changes);
        if ("segments" in changes) segments = Array.isArray(changes.segments) ? changes.segments.map(s => ({ ...s })) : [];
        drawSegments();
      },
      destroy() {
        clear();
        life.abort();
        root.replaceChildren();
        if (addedClass) root.classList.remove("tst");
        delete root.__taurisStatus;
      },
    };
  }

  window.TaurisStatus = { mount };
})();
