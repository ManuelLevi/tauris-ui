# Changelog

Newest first. Every change gets an entry. **Upgrade** lines say what an app
must change; an entry without them needs only a rebuild (or, with a git
dependency, `cargo update -p tauris-ui`).

## Unreleased

Nothing yet.

## 0.4.9 — 2026-10-21

Fixes from a review of 0.4.7 and 0.4.8:
- **Files: selecting several is off by default again** (`multiple: true` turns it on). In 0.4.8 it was on, which changed apps that had not asked for it.
- Files: an app's own `confirmDelete` question written for one file is never shown for several; the component asks "Delete 3 files?" itself. A function that takes `(file, files)` gets them all.
- Files and tree: Control-click on a Mac is a right click and keeps the selection; taking the focused item out with ⌘-click moves the focus to the nearest selected one; after a search, ⌘A puts the focus on a file that is shown. `multiple: false` is kept by `select([ids])`, `selectAll()` and `update()`.
- Tree: `setData` that drops selected rows fires `select`.
- Fixed: an app's `on_change` hook that opened a window while a window closed froze the app. Inside the plugin's events the hook now runs a moment later on the worker; `test/freeze_check` checks this case too.
- A job on the worker that panics no longer stops ⌘N, ⌘T and the Dock click for the rest of the session.
- Sub-menus: moving with the keys closes a sub-menu the mouse opened; a sub-menu about to open is dropped when the mouse leaves the menu, unless it leaves beside its item.
- `data-tauris-theme="light"` or `"dark"` on `<html>` sets the mode of every component when an app has its own light/dark switch. The README says which component follows which `--tauris-*` colour.

**Upgrade** (TypeScript apps only): copy `web/files.d.ts` over the app's copy. An app that wants several files selected at once adds `multiple: true`.

## 0.4.8 — 2026-10-21

- **One look for every component:** `--tauris-font`, `--tauris-bg`, `--tauris-chrome`, `--tauris-fg`, `--tauris-dim`, `--tauris-line`, `--tauris-hover`, `--tauris-accent`, `--tauris-accent-ink`, `--tauris-sel-bg`, `--tauris-sel-fg`, `--tauris-focus` and `--tauris-mono`, set once on `:root`, are followed by the tabs, the tree, the files table and the menus. Unset, every component looks as before; each component's own variables still win.
- **Selecting several:** the files table selects several files with ⌘-click (Ctrl-click), Shift-click, Shift+arrows and ⌘A. Enter opens them all; Delete deletes them all after one question (`onDelete` once per file); the row menu acts on all of them. `onSelect(file, files)`, `selection()`, `selectAll()`, `select([ids])`; `multiple: false` keeps one at a time. Files just added are all selected.
- The tree selects several rows the same way with `multiple: true` (off by default): the `select` event carries `nodes`, plus `selection()`, `selectAll()`, `select([ids])`.
- **Sub-menus:** a menu item with `items` opens a sub-menu to its right (Right, Enter, or the mouse resting on it; Left or Escape goes back). It opens to the left near the window's edge.
- CI runs `test/freeze_check` on macOS at every push: a real Dock click and File › New Window must open their windows.

**Upgrade** (TypeScript apps only): copy `web/files.d.ts`, `web/tree.d.ts` and `web/menus.d.ts` over the app's copies; `doctor.py` points to them.

## 0.4.7 — 2026-10-21

- Fixed: the app froze (macOS "not responding") on a Dock click with no window open, on File › New Window (⌘N), and on File › New Tab (⌘T) with no window open. Tauri holds its plugin lock while the plugin's event handler runs, and opening a window takes that lock. These now open their window just after the handler returns, one after the other, in order.
- `test/freeze_check`: a small app that clicks the Dock and presses ⌘N for real (macOS), because no headless test can show this freeze. Run it with `cd test/freeze_check && cargo run` after changing the plugin's event handler.

## 0.4.6 — 2026-10-21

- Tree view: **sortable columns.** With `sortable: true` (or a first `sort: { key, up }`), a click on a column's header sorts by it and a second click turns it round (▲ / ▼); Enter and Space do the same on a focused header.
  - Rows sort among their siblings, so groups stay groups.
  - Numbers sort as numbers; text sorts as people read it ("Brian 49" before "Brian 169"); empty values go last both ways.
  - Per column: `sortable: false`, `sortValue: node => ...` (sort by something other than the text shown), `compare: (a, b) => ...`.
  - A `sort` event (`{ key, up }`, or null), `sort(key, up)` and `sorting()`. `setData` keeps the order; selection and focus stay on their node. 3,200 rows sort in a few milliseconds.

  A tree without these options is unchanged: its header has no buttons.

  **Upgrade** (TypeScript apps only): copy `web/tree.d.ts` over the app's copy; `doctor.py` points to it.
- Files: the header keeps its height (26px) with or without the search field, so the list no longer moves when the first file arrives or the last one goes.

## 0.4.5 — 2026-10-21

- Files: the columns keep their widths with every row, one row or none (a search that matches nothing no longer squeezes them); the name takes the rest. `--tf-size-w`, `--tf-added-w`, `--tf-by-w` and `--tf-acts-w` set them; the buttons' column fits how many buttons there are.
- Files: `onMenuOpen({ label, how })` and `onMenuClose({ label, chosen })` for the row's menu (right click, Shift+F10), as the menus' `onOpen` and `onClose`.

## 0.4.4 — 2026-10-21

- Files: with `onMessage` (the app shows the messages) or `header: false`, the list takes the room of the part that is not shown, with no empty gap above or below it.

## 0.4.3 — 2026-10-21

- Menus: `onOpen({ label, how })` and `onClose({ label, chosen })` on `TaurisMenu.bar` and `TaurisMenu.button`, for a sound or anything else. `chosen` is true when an item was picked. Going from one menu of the bar to the next (Left, Right, pointing at another title) fires neither. `TaurisMenu.open`'s `onClose` gets the same `{ label, chosen }`.
- Files: the drop zone is a solid 2px ring round the whole list, as a desktop app marks a drop target, instead of a dashed box.
- Files: `--tf-accent-ink`, the accent as text and lines (the drop zone, the sort arrow). In dark mode it is lighter, so "Drop to add to …" is readable (about 5:1 instead of 2.5:1).

## 0.4.2 — 2026-10-21

- New, optional component: **files** (`TaurisFiles`), a place's shared files as a dense table:
  - a type badge, the name, size, date added and who added it; sort by any column (▲ / ▼)
  - Open, Save a copy…, Rename and Delete on the row, on a right click and from the keyboard (Enter, F2, ⌘⌫)
  - search, a header with the count and total size, an empty state and a "no match" line
  - **Add files…** with the system's picker, and files dropped on the window, with a dashed drop zone
  - a segmented bar while files are added, renaming in place, a question before deleting
  - every word can be changed (`labels`); light and dark; `--tf-*` variables

  The app keeps the files: the component hands it every action (`onAdd`, `onOpen`, `onSaveAs`, `onRename`, `onDelete`). Types are in `web/files.d.ts`, tests in `test/files_run.py`.
- `tauris_ui::files` in Rust: `inspect` (refuses folders, missing and oversized files in a sentence), `mime_for`, `safe_name`, `size_text`. With the new `files` feature: `pick_files`, `save_dialog` and `open_path`, and the page's `TaurisFiles.pick` and `TaurisFiles.saveDialog` (new page commands `pick_files` and `save_dialog`, in `tauris-ui:default`). The feature uses the dialog plugin, which the app registers.
- New, optional component: **menus** (`TaurisMenu`): an in-window menu bar, toolbar buttons with a ▾ menu, and menus at a point, with a desktop app's keyboard (arrows, Home, End, letters, Left and Right across the bar, Escape back to where focus was). Items have shortcut hints, colour chips, ✓, red and disabled states. Types are in `web/menus.d.ts`, tests in `test/menus_run.py`.
- `doctor.py` knows both: the `files` feature, the dialog plugin, and the capability a window needs for the picker.
- Terminal: a Space that went down on something else (a menu item) no longer presses the key that has the focus when it comes up.

## 0.4.1 — 2026-10-21

- New, optional component: the **terminal** look (`TaurisTerminal`):
  - amber on black, IBM Plex Mono, square corners, 1px gaps between panes
  - a command line with a block cursor and clock
  - title bands that turn green or red
  - form lines with `[X]` checkboxes
  - function keys bound to F1 to F12
  - dense tables with segmented bars
  - a message log with timestamps and a flash on new rows
  - a key legend

  It changes nothing outside the element marked `.tm`, and its stylesheet is added only when a page uses it. Types are in `web/terminal.d.ts`, tests in `test/terminal_run.py`.
- `doctor.py` knows the terminal, and accepts an app's own menu that calls `app.tabs()` for ⌘T and ⌘W.

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
