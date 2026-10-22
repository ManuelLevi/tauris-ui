// One window's page: the strip at the top, the active tab's note below.

const status = document.getElementById("status");
// Asked once already: a tab, or the whole window ("window"), closes on its second try.
const armed = new Set();

const tabs = TaurisTabs.mount(document.getElementById("strip"), {
  panelId: "page",
  // A tab with a note closes on the second try, so a note is not lost by
  // accident; so does a window with notes, however many tabs have them.
  onBeforeClose: (tab, { reason }) => {
    const key = reason === "window" ? "window" : tab.id;
    if (!tab.note || armed.has(key)) return true;
    armed.add(key);
    status.textContent = reason === "window"
      ? "This window has notes. Close it again to throw them away."
      : `"${tab.title}" has a note. Close it again to throw the note away.`;
    setTimeout(() => { armed.delete(key); status.textContent = ""; }, 3000);
    return false;
  },
});

const title = document.getElementById("title");
const note = document.getElementById("note");

// Show the active tab whenever the tabs change. A field being typed in keeps
// what is typed (its own tab's change comes back here too), unless another
// tab became active.
let shown = null;
tabs.on("change", () => {
  const tab = tabs.activeTab();
  const other = tab?.id !== shown;
  shown = tab?.id ?? null;
  if (other || document.activeElement !== title) title.value = tab?.title ?? "";
  if (other || document.activeElement !== note) note.value = tab?.note ?? "";
});

// Typing changes the active tab; update() stores it in Rust (and on disk).
title.addEventListener("input", () => tabs.update(tabs.activeTab(), { title: title.value || "Untitled" }));
note.addEventListener("input", () => tabs.update(tabs.activeTab(), { note: note.value }));
