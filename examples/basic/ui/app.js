// One window's page: the strip at the top, the active tab's note below.

const status = document.getElementById("status");
let armed = null;

const tabs = TaurisTabs.mount(document.getElementById("strip"), {
  panelId: "page",
  // A tab with a note closes on the second try, so a note is not lost by accident.
  onBeforeClose: tab => {
    if (!tab.note || armed === tab.id) return true;
    armed = tab.id;
    status.textContent = `"${tab.title}" has a note. Close it again to throw the note away.`;
    setTimeout(() => { armed = null; status.textContent = ""; }, 3000);
    return false;
  },
});

const title = document.getElementById("title");
const note = document.getElementById("note");

// Show the active tab whenever the tabs change.
tabs.on("change", () => {
  const tab = tabs.activeTab();
  title.value = tab?.title ?? "";
  note.value = tab?.note ?? "";
});

// Typing changes the active tab; update() stores it in Rust (and on disk).
title.addEventListener("input", () => tabs.update(tabs.activeTab(), { title: title.value || "Untitled" }));
note.addEventListener("input", () => tabs.update(tabs.activeTab(), { note: note.value }));
