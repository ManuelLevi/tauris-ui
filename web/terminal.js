// tauris-ui terminal look: an amber-on-black, Bloomberg-style screen. Plain
// JavaScript: no build step, no dependencies. In a Tauri app the plugin
// injects this file with its stylesheet (web/terminal.css), which is added the
// first time a page uses it. Elsewhere (the demo page) load web/terminal.css
// with a <link>.
//
// Most of the look is CSS classes (listed at the top of terminal.css). This
// file adds the parts that need a script, on elements the app draws itself
// (in React: a ref):
//
//   const term = TaurisTerminal.mount(root);   // marks .tm, runs the clocks, binds F1-F12
//   const cmd = TaurisTerminal.commandLine(el, { prompt: "ATLAS>", onSubmit: text => { ... } });
//   const log = TaurisTerminal.log(listEl);    // log.add("ORDER FILLED", "ok")
//   const band = TaurisTerminal.pane(paneEl);  // band.ok(), band.error(), band.reset()
//
// Function keys are <span class="tm-key" role="button" tabindex="0">, not
// <button>, so an app's plain `button { ... }` rule cannot restyle them. Inside
// a mounted root, Enter and Space press them, aria-disabled="true" turns them
// off, and aria-keyshortcuts="F8" makes F8 press them from anywhere in the page.
//
// The font is IBM Plex Mono when the app has it, the system's monospace
// otherwise. To bundle it (a strict content policy blocks fonts from the web):
// put the woff2 files of IBM Plex Mono (SIL Open Font License) in the app, for
// example with `npm install @fontsource/ibm-plex-mono` and
//   import "@fontsource/ibm-plex-mono/400.css";
//   import "@fontsource/ibm-plex-mono/500.css";
//   import "@fontsource/ibm-plex-mono/600.css";
// or with your own @font-face { font-family: "IBM Plex Mono"; src: url(...) }
// for weights 400, 500 and 600. Files inside the app count as 'self'.

(() => {
  "use strict";
  if (window.TaurisTerminal) return;

  // Filled in by the plugin; left as is when the file is loaded on its own.
  const CSS = "__TAURIS_TERMINAL_CSS__";
  let stylesAdded = false;
  // Roots mounted with { styles: false } (the page brings its own): while one
  // lives, the parts add no stylesheet unless one asks for it (styles: true).
  let ownStyles = 0;
  function addStyles(asked = false) {
    if (stylesAdded || (ownStyles > 0 && !asked) || CSS.startsWith("__TAURIS")) return;
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

  const KINDS = new Set(["ok", "warn", "error"]);
  const FKEY = /^F([1-9]|1[0-2])$/;
  // Hebrew, Arabic and the other right-to-left scripts.
  const RTL_CHAR = /^(?:[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufeff]|[\ud802\ud803\ud83a][\udc00-\udfff])$/;
  const pad = n => String(n).padStart(2, "0");
  const timeOf = d => `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  const dateOf = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

  function el(tag, className, attrs = {}) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    for (const [k, v] of Object.entries(attrs)) if (v != null) node.setAttribute(k, v);
    return node;
  }

  function need(element, what) {
    if (!(element instanceof HTMLElement)) throw new Error(`TaurisTerminal.${what} needs an element`);
  }

  // ---------- clocks ----------
  // Every [data-tm-clock] (HH:MM:SS) and [data-tm-date] (YYYY-MM-DD) inside a
  // watched element shows the local time. One timer serves the whole page and
  // ticks on the second.

  const clockHosts = new Set();
  let clockTimer = 0;

  function paintClocks() {
    const now = new Date();
    const time = timeOf(now);
    const date = dateOf(now);
    const done = new Set();
    for (const host of clockHosts) {
      for (const node of host.querySelectorAll("[data-tm-clock], [data-tm-date]")) {
        if (done.has(node)) continue;
        done.add(node);
        const text = node.hasAttribute("data-tm-clock") ? time : date;
        if (node.textContent !== text) node.textContent = text;
      }
    }
  }

  function nextTick() {
    clockTimer = setTimeout(() => {
      paintClocks();
      nextTick();
    }, 1000 - (Date.now() % 1000) + 5);
  }

  function watchClocks(host) {
    clockHosts.add(host);
    paintClocks();
    if (!clockTimer) nextTick();
  }

  function unwatchClocks(host) {
    clockHosts.delete(host);
    if (clockHosts.size === 0 && clockTimer) {
      clearTimeout(clockTimer);
      clockTimer = 0;
    }
  }

  // ---------- the root ----------

  function mount(root, options = {}) {
    need(root, "mount");
    if (root.__taurisTerminal) throw new Error("TaurisTerminal.mount: this element is already a terminal; call destroy() first");
    const opt = { styles: true, ...options };
    if (opt.styles) addStyles(options.styles === true);
    else ownStyles++; // nor do the command line, the log or a pane add them later
    const ownedStyles = !opt.styles;
    root.__taurisTerminal = true;
    // An app that writes class="tm" itself keeps it after destroy() (React StrictMode mounts twice).
    const addedClass = !root.classList.contains("tm");
    root.classList.add("tm");
    const life = new AbortController();
    const signal = life.signal;

    const keyAt = target => {
      const key = target instanceof Element ? target.closest(".tm-key") : null;
      return key && root.contains(key) ? key : null;
    };
    const off = key => key.getAttribute("aria-disabled") === "true";

    // A short press, so a key pressed from the keyboard is seen to go down.
    function press(key) {
      key.classList.add("tm-pressed");
      setTimeout(() => key.classList.remove("tm-pressed"), 120);
      key.click();
    }

    // Keys are not <button>s: Enter presses them at once, Space on release, as a button does.
    // Space presses only the key it went down on (a Space that chose a menu item is not a press).
    let spaceOn = null;
    // A Space whose release was never heard (the focus moved, the window went
    // to the back) presses nothing later.
    root.addEventListener("focusout", () => { spaceOn = null; }, { signal });
    window.addEventListener("blur", () => { spaceOn = null; }, { signal });
    root.addEventListener("keydown", e => {
      if (e.key !== " ") spaceOn = null;
      const key = keyAt(e.target);
      if (!key || key !== e.target || key.getAttribute("role") !== "button" || e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === "Enter") {
        e.preventDefault();
        if (!e.repeat && !off(key)) press(key);
      } else if (e.key === " ") {
        e.preventDefault(); // no page scroll
        spaceOn = key;
      }
    }, { signal });

    root.addEventListener("keyup", e => {
      if (e.key !== " ") return;
      const key = keyAt(e.target);
      const down = spaceOn;
      spaceOn = null;
      if (!key || key !== e.target || key !== down || key.getAttribute("role") !== "button") return;
      e.preventDefault();
      if (!off(key)) press(key);
    }, { signal });

    // A disabled key swallows its clicks, so the app's own handlers never see them.
    root.addEventListener("click", e => {
      const key = keyAt(e.target);
      if (key && off(key)) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    }, { signal, capture: true });

    // F1 to F12, from anywhere in the page, press the key that lists them in
    // aria-keyshortcuts (which also tells screen readers). Hidden and disabled keys are skipped.
    document.addEventListener("keydown", e => {
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey || !FKEY.test(e.key)) return;
      const key = [...root.querySelectorAll(".tm-key[aria-keyshortcuts]")].find(k =>
        k.getAttribute("aria-keyshortcuts").split(/\s+/).includes(e.key) && !off(k) && k.getClientRects().length > 0);
      if (!key) return;
      e.preventDefault();
      if (!e.repeat) press(key);
    }, { signal });

    watchClocks(root);

    return {
      /** Stops the clocks and the keys; mount can then be called again. */
      destroy() {
        life.abort();
        unwatchClocks(root);
        if (ownedStyles) ownStyles--; // once none is left, a later mount may add them again
        if (addedClass) root.classList.remove("tm");
        delete root.__taurisTerminal;
      },
    };
  }

  // ---------- command line ----------
  // Draws into an empty element: the prompt, a field for the command with a
  // blinking block cursor at the caret, and the date and time on the right.
  // Enter sends the command to onSubmit and empties the line; Escape empties
  // it; Up and Down step through the commands sent before.

  // The parts take { styles: false } too, for a page that makes them before mount().
  const partStyles = options => {
    if (options.styles !== false) addStyles(options.styles === true);
  };

  function commandLine(element, options = {}) {
    need(element, "commandLine");
    if (element.__taurisCommand) throw new Error("TaurisTerminal.commandLine: this element already has one; call destroy() first");
    partStyles(options);
    element.__taurisCommand = true;
    const prompt = options.prompt ?? ">";
    const onSubmit = typeof options.onSubmit === "function" ? options.onSubmit : () => {};
    const life = new AbortController();
    const signal = life.signal;

    const addedClass = !element.classList.contains("tm-cmd");
    element.classList.add("tm-cmd");
    const promptEl = el("span", "tm-prompt");
    promptEl.textContent = prompt;
    const input = el("input", "tm-cmd-input", {
      type: "text", "aria-label": options.label ?? "Command", spellcheck: "false", autocomplete: "off",
      autocapitalize: "off", autocorrect: "off",
    });
    const cursor = el("span", "tm-cursor", { "aria-hidden": "true" });
    const entry = el("span", "tm-cmd-entry");
    entry.append(input, cursor);
    const date = el("span", null, { "data-tm-date": "" });
    const clock = el("span", null, { "data-tm-clock": "" });
    element.replaceChildren(promptEl, entry, date, clock);

    // The block sits on the caret, found in a hidden copy of the line laid out
    // as the field lays it out: a CJK character or an emoji is wider than a
    // letter, and right-to-left text puts the caret on its left.
    const mirror = el("span", "tm-mirror", { "aria-hidden": "true" });
    entry.append(mirror);
    function caretX(at) {
      const cs = getComputedStyle(input);
      mirror.style.font = cs.font;
      mirror.style.letterSpacing = cs.letterSpacing;
      // As wide as the field and aligned as it is: right-to-left text starts at its right.
      mirror.style.direction = cs.direction;
      mirror.style.textAlign = cs.textAlign;
      mirror.style.width = `${input.clientWidth}px`;
      mirror.textContent = input.value;
      const text = mirror.firstChild;
      if (!text) return 0;
      const range = document.createRange();
      const to = Math.min(at, text.length);
      range.setStart(text, to);
      range.collapse(true);
      const from = mirror.getBoundingClientRect().left;
      if (range.getClientRects().length) return range.getBoundingClientRect().left - from;
      // WebKit has no box for the caret at the end of right-to-left text: the
      // character before it says (the caret is on the left of a right-to-left
      // one, on the right of any other).
      if (to === 0) return 0;
      const back = to > 1 && /[\udc00-\udfff]/.test(text.data[to - 1]) ? 2 : 1; // a pair of surrogates is one character
      range.setStart(text, to - back);
      range.setEnd(text, to);
      const box = range.getBoundingClientRect();
      return (RTL_CHAR.test(text.data.slice(to - back, to)) ? box.left : box.right) - from;
    }
    let frame = 0;
    function place() {
      frame = 0;
      const at = input.selectionDirection === "backward" ? input.selectionStart : input.selectionEnd;
      // Kept inside the field: at the end of a line that scrolls, the block
      // would start at its right edge and hang out.
      // In right-to-left text the next character is on the caret's left: the block sits there.
      const width = cursor.getBoundingClientRect().width;
      const rtl = getComputedStyle(input).direction === "rtl";
      const x = caretX(at ?? input.value.length) - input.scrollLeft - (rtl ? width : 0);
      const room = Math.max(0, input.clientWidth - width);
      entry.style.setProperty("--tm-caret-x", `${Math.min(Math.max(x, 0), room)}px`);
      entry.style.setProperty("--tm-scroll", "0px");
      // Solid while typing; it blinks again once the typing stops.
      if (typeof cursor.getAnimations === "function") for (const a of cursor.getAnimations()) a.currentTime = 0;
    }
    const later = () => {
      if (!frame) frame = requestAnimationFrame(place);
    };
    for (const type of ["input", "keydown", "pointerup", "focus", "select", "scroll"]) input.addEventListener(type, later, { signal });
    // A field that grows or shrinks (the window resized) scrolls its text: the block follows.
    if (typeof ResizeObserver === "function") {
      const resized = new ResizeObserver(later);
      resized.observe(input);
      signal.addEventListener("abort", () => resized.disconnect());
    }
    document.addEventListener("selectionchange", () => {
      if (document.activeElement === input) later();
    }, { signal });

    const history = [];
    let step = 0; // where Up and Down are in the history; history.length is the new command
    let draft = ""; // what was typed before Up, given back by Down
    function set(text) {
      input.value = String(text ?? "");
      input.setSelectionRange(input.value.length, input.value.length);
      place();
    }

    input.addEventListener("keydown", e => {
      // Keys that end an input method's text are the input method's.
      if (e.isComposing || e.keyCode === 229) return;
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === "Enter") {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        if (history[history.length - 1] !== text) history.push(text);
        if (history.length > 50) history.shift();
        step = history.length;
        set("");
        onSubmit(text);
      } else if (e.key === "Escape") {
        if (!input.value) return;
        e.preventDefault();
        step = history.length;
        set("");
      } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        if (!history.length) return;
        e.preventDefault();
        if (step === history.length) draft = input.value;
        step = Math.max(0, Math.min(history.length, step + (e.key === "ArrowUp" ? -1 : 1)));
        set(step === history.length ? draft : history[step]);
      }
    }, { signal });

    watchClocks(element);
    place();

    return {
      /** The command typed so far; setting it puts text on the line. */
      get value() { return input.value; },
      set value(text) { set(text); },
      /** Empties the line. */
      clear() { set(""); },
      /** Moves keyboard focus to the line. */
      focus() { input.focus(); },
      /** Removes the line and its listeners; commandLine can then be called again. */
      destroy() {
        life.abort();
        cancelAnimationFrame(frame);
        unwatchClocks(element);
        element.replaceChildren();
        if (addedClass) element.classList.remove("tm-cmd");
        delete element.__taurisCommand;
      },
    };
  }

  // ---------- message log ----------
  // An <ol> (or any element) that the app leaves empty. Each message gets its
  // time, flashes once, and the log follows the newest one unless the user has
  // scrolled up to read.

  function log(list, options = {}) {
    need(list, "log");
    partStyles(options);
    const max = Number.isInteger(options.max) && options.max > 0 ? options.max : 500;
    list.classList.add("tm-log");
    if (!list.hasAttribute("role")) list.setAttribute("role", "log");
    if (!list.hasAttribute("aria-live")) list.setAttribute("aria-live", "polite");

    return {
      /** Adds a message: kind is "ok", "warn" or "error" (or nothing); at is its time (now). */
      add(text, kind, at = new Date()) {
        const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight <= 4;
        const item = el("li", KINDS.has(kind) ? `tm-new tm-${kind}` : "tm-new");
        const time = el("time", null, { datetime: at.toISOString() });
        time.textContent = timeOf(at);
        const body = el("span");
        body.textContent = String(text);
        item.append(time, body);
        item.addEventListener("animationend", () => item.classList.remove("tm-new"), { once: true });
        list.append(item);
        // The oldest rows go; a person reading further up keeps their place
        // (WebKit, which Tauri uses on macOS, does not keep it by itself).
        const extra = list.children.length - max;
        if (extra > 0) {
          const gone = list.children[extra].offsetTop - list.firstElementChild.offsetTop;
          for (let n = 0; n < extra; n++) list.firstElementChild.remove();
          if (!atBottom) list.scrollTop -= gone;
        }
        if (atBottom) list.scrollTop = list.scrollHeight;
        return item;
      },
      /** Removes every message. */
      clear() { list.replaceChildren(); },
    };
  }

  // ---------- title band state ----------
  // On a pane, every title band of the pane changes; on a band, only that band.

  function pane(element, options = {}) {
    need(element, "pane");
    partStyles(options);
    const set = state => {
      if (state) element.setAttribute("data-tm-state", state);
      else element.removeAttribute("data-tm-state");
    };
    return {
      /** Green band. */
      ok() { set("ok"); },
      /** Red band. */
      error() { set("error"); },
      /** Back to amber. */
      reset() { set(null); },
    };
  }

  window.TaurisTerminal = { mount, commandLine, log, pane };
})();
