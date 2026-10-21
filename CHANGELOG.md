# Changelog

Newest first. Every change gets an entry. **Upgrade** lines say what an app
must change; an entry without them needs only a rebuild (or, with a git
dependency, `cargo update -p tauris-ui`).

## Unreleased

Nothing yet.

## 0.4.0 — 2026-10-21

First public release. UI components for Tauri 2 desktop apps:

**Tabs** (`TaurisTabs.mount` in the page, `app.tabs()` in Rust):
- Drag to reorder; drag out into a window of its own and drop onto another window (macOS).
- On macOS the strip sits in the title bar.
- Right-click menu: New tab, Close tab, Close other tabs, Close tabs to the right, Move to new window. Keyboard and screen-reader support.
- ⌘T ⌘N ⌘W ⇧⌘W through a ready-made menu (`default_menu`, `file_menu`, `menu_ids`).
- Tabs carry the app's own fields.
- Windows, tabs and fields are remembered between runs:
  - saved a second after changes stop, at least every five seconds
  - saved at once on quit
  - cleared when the last tab is closed by hand
- `onBeforeClose` is asked before any tab or window closes. A page that hangs cannot keep its window open.
- A page can change only its own window's tabs.
- The look is a set of `--tt-*` variables, light and dark.

**Tree view and configuration editor** (`TaurisTree.mount`, page only):
- Built to `docs/tree-view.md`:
  - 18px rows and 16px indents
  - +/- boxes and dotted guide lines that join without a seam
  - aligned, resizable columns
- In-place editors: text, number, checkbox, choice, colour. Tab moves between a row's values.
- Keyboard and ARIA as in Windows and Qt trees.
- Only the visible rows are drawn.
- The look is a set of `--tv-*` variables, light and dark, and Windows high contrast.

**For every component:**
- Each stylesheet is added only when a page mounts the component.
- Nothing needs `data:` images or inline styles, so the components work under a strict content policy.
- A starter template's plain `button` / `input` rules don't restyle them.
- `scripts/doctor.py` checks an app's setup, its version requirement, and its copies of the TypeScript types.
- `examples/basic` is the smallest complete app.
