// tauris-ui native feel: the page behaves like a desktop app's window, not a
// web page. The plugin puts this in every page when the app asks for it
// (Config::native_feel()); nothing else of the library needs it.
//
// - No web right-click menu (Reload, Inspect…), except in fields and text
//   marked .tauris-selectable; menus the app or a component opens still open.
// - Pictures, links and drawings cannot be dragged out of the page (one with
//   draggable="true" still can).
// - No page zoom: ⌘+ ⌘- ⌘0 (Ctrl elsewhere), and the pinch or Ctrl-wheel.
// - ⌘A (Ctrl+A) outside a field selects no page text; a list that selects
//   all its rows on ⌘A still does.
// - Single-line fields (names, file names, numbers) are not autocorrected,
//   autocapitalised or spell-checked; text areas keep their spell check. A
//   field with its own autocorrect attribute keeps it.

(() => {
  "use strict";
  if (window.__taurisNativeFeel) return;
  Object.defineProperty(window, "__taurisNativeFeel", { value: true });

  const MAC = /mac|iphone|ipad/i.test(navigator.userAgentData?.platform || navigator.platform || navigator.userAgent || "");
  const cmd = e => (MAC ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey);
  const editable = t => t instanceof Element
    && !!t.closest("input, textarea, select, [contenteditable]:not([contenteditable='false']), .tauris-selectable");

  // On the window, after everything in the page: a menu the page opened has
  // already done its work (and prevented the browser's).
  window.addEventListener("contextmenu", e => {
    if (!editable(e.target)) e.preventDefault();
  });

  window.addEventListener("dragstart", e => {
    const t = e.target instanceof Element ? e.target : null;
    if (!t || t.closest("[draggable='true']")) return;
    if (t.closest("img, a, svg, picture")) e.preventDefault();
  });

  window.addEventListener("keydown", e => {
    if (cmd(e) && !e.altKey && ["+", "=", "-", "_", "0"].includes(e.key)) e.preventDefault();
    if (cmd(e) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "a" && !editable(e.target) && !editable(document.activeElement)) {
      e.preventDefault();
      window.getSelection()?.removeAllRanges();
    }
  });
  // The pinch comes as a Ctrl-wheel (and as gesture events in WebKit).
  window.addEventListener("wheel", e => { if (e.ctrlKey) e.preventDefault(); }, { passive: false });
  window.addEventListener("gesturestart", e => e.preventDefault());

  const SINGLE_LINE = new Set(["text", "search", "email", "url", "tel", "number", ""]);
  document.addEventListener("focusin", e => {
    const field = e.target;
    if (!(field instanceof HTMLInputElement) || !SINGLE_LINE.has(field.getAttribute("type") ?? "")) return;
    if (field.hasAttribute("autocorrect")) return; // the app chose
    field.spellcheck = false;
    field.setAttribute("autocorrect", "off");
    field.setAttribute("autocapitalize", "off");
  }, true);
})();
