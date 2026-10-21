# Changelog

Newest first. Every change gets an entry. **Upgrade** lines say what an app
must change; an entry without them needs only a rebuild (or, with a git
dependency, `cargo update -p tauris-ui`).

## Unreleased

- Files: names sort as in Finder, the name without its extension first and then the extension, so "Q3 plan.md" comes before "Q3 plan 2.md".
- Files: on a Mac, Control never acts as Command. ⌃⌫ and ⌃⌘⌫ no longer delete, ⌃⌘A no longer selects all, and ⌃⌘-click and ⌃⌘↑↓ no longer add to the selection.

## 0.4.13 — 2026-10-21

Fixes from ten reviewers, one per area:
- Window jobs (⌘N, ⌘T, the Dock click) and `on_change` calls have a worker each, so a slow hook never holds up a new window. Quitting waits for the hook at most half a second and opens no new window. Debug builds stop at once when a window opens inside Tauri's plugin lock.
- Closing the last tab takes its window out of the layout at once: a tab opened meanwhile gets a new window, and nothing is lost. `open_many` replacing the active tab where there is none loses no tab. A failed move puts the tab back where it was, still active; if its window has gone, it is not kept.
- A layout that could not be saved (a full disk) is saved at the next try. Remembered windows that all fail to open are kept aside as `<name>.unopened`, not overwritten.
- `safe_name` drops invisible characters (a right-to-left mark can make "fdp.exe" read as "exe.pdf"), trims dots and spaces at both ends together, and keeps names under 255 bytes. `size_text` never says "1,024 KB" (nor the page). `inspect` says "100 bytes" for limits under 1 KB, and "is not a file that can be added" for devices. `mime_for(".pdf")` is a hidden file, not a PDF.
- The checker ignores commented-out code, looks for `tauri-plugin-dialog` in Cargo.toml, and finds a `pick` option only in what is given to `TaurisFiles.mount`.
- Files: one picker at a time; each file deleted is the app's newest object; Escape while the app renames waits for it; files added while renaming stay; a hidden search hides nothing; `onSelect` hears a new name; Shift+F10 with no file chosen opens the first one's menu; the same letter again steps through the files starting with it; the files under the delete question cannot be reached; with two components, a drop goes to the one under the pointer; nothing runs after `destroy()`.
- Tree: `expanded: true` opens a node only the first time it comes, so `setData` keeps a closed folder closed; an edit in progress is saved before `setData` (unless its node is gone); a column with its own `compare` puts empty values last; editors are named by row and column; Alt+← and Alt+→ on a header resize its column; secondary text on the selection is readable.
- Menus: `items()` that throws leaves the bar working; a menu with no items does not open; the same letter again steps through the items; the page scrolling closes an open menu; `setMenus` and `setItems` show new items in an open menu at once; nothing opens after `destroy()`, which also removes the name it added.
- Tabs: Enter, Space and Delete on a button inside a tab are that button's; a tab's name for screen readers is its title; with no active tab the first is reachable with Tab; `onBeforeClose` that throws keeps the tab and says why in the console; Escape in the tab menu finds the tab after a redraw. Terminal: a Space whose release was lost presses nothing later.
- The look: focus rings are a solid line (`--tauris-accent-ink`) with a soft halo, readable on any background, and drawn in Windows high contrast too; secondary text and pressed toolbar buttons have more contrast. New shared colour `--tauris-on-accent` (text on the accent). The primary button and a new row's flash follow the accent.
- CI runs clippy on the example app and the freeze check. The test counts are gone from the README.

## 0.4.12 — 2026-10-21

Fixes from a fourth review:
- `on_change` calls never overlap and keep their order: a call made while earlier ones wait on the worker, or while the hook runs on another thread, waits on the worker too.
- A tab whose move to a new window failed goes back to its place, not to the end.
- Files: an action started from the delete question or the row menu gets the app's newest objects, and skips files that have gone. Enter, F2 and Delete act on the selected files, never on a file that only has the focus; Shift+F10 on such a file selects it first.
- Files and tree: with `multiple`, plain Space adds or takes out the item with the focus (macOS keeps ⌘Space and Ctrl+Space for itself), so any selection can be made from the keyboard. In the tree, a row with a checkbox value still flips its checkbox. `selected()` (and `onSelect`'s first argument) is the selected item with the focus, or the first selected one; never an item that only has the focus.
- Files: when the only selected file leaves the app's list, the file now in its place takes the selection, as in the tree. The delete question starts on Cancel, the safe answer (Tab reaches Delete), and is marked modal. In Windows high contrast the focus ring is drawn with borders.
- Tree: `select([ids])` keeps the focus in the tree, and changes nothing when none of the ids exist.
- Menus: a sub-menu's items are made once per opening; an empty sub-menu is an item that is off.
- New shared colours: `--tauris-sel-inactive` (the tree's selection while it does not have the focus) and `--tauris-faint` (faint and disabled text).
- `safe_name` also covers COM0–9 and LPT0–9 with ¹²³, CONIN$ and CONOUT$, and never ends a cut name with a space or a dot.
- `escalating_evaluators.md` is not part of the library.

## 0.4.11 — 2026-10-21

Fixes from a third review:
- `on_change` runs at once again when the app's own code makes the change, as up to 0.4.9. Only a change made inside Tauri's plugin lock (the plugin's own events, the page's commands) reaches it a moment later on the worker, where a hook that opened a window would freeze the app.
- A window whose opening panicked (the app's window hook) leaves no record on every path: a new window, a tab moved to a new window, a tab dragged out, restored windows.
- Files: when the app hands new objects that look the same, Enter, the selection and `onSelect` get the new ones.
- Files and tree: with `multiple`, ⌘ (Ctrl) with the arrows moves the focus alone and ⌘ (Ctrl) Space adds or takes out that item. The item with the focus has a thin ring when several are selected or when it is not selected. ⌘A never selects the page's text.
- Tree: when `setData` drops the only selected row, the row now in its place takes the selection and the focus. `select([ids])` without `multiple` opens only the first row's parents.
- More colours follow the shared `--tauris-*` colours (the tree's lines, boxes, group rows and checkboxes, the menus' disabled items), and each component tells the browser its light or dark mode, so its scrollbars and checkboxes match. An app that is always light or always dark sets `data-tauris-theme`.
- The delete question is named by its text for screen readers. A closed sub-menu leaves no `aria-controls` behind; an empty sub-menu does not open.
- `safe_name` puts "_" in front of Windows' device names (CON, NUL, COM1…).
- `test/freeze_check` waits for windows to close before each reopen and checks the window is new.

## 0.4.10 — 2026-10-21

Fixes from a second review:
- Fixed: an `on_change` hook that opened a window froze the app when the change came from a page (the + button, closing a tab): Tauri holds its plugin lock during plain page commands too. The hook now always runs a moment after the change, on the worker, in order; a quitting app waits for it (half a second at most) so it hears the last changes.
- A window whose opening panicked (the app's window hook) no longer stays in the layout, where later tabs would go unseen.
- Tree: after `setData` drops the focused row, the focus and the selection move to the same row, and `select` is fired once.
- Files: `onSelect` hears every change of what can be acted on, including "nothing" when a search hides every selected file. Several files at once are asked about with `labels.confirmDeleteMany` (translate it there); the `confirmDelete` function is only for one file. ⌘A in the list never selects the page's text.
- Sub-menus: a key pressed while one is about to open stops it; leaving the menu drops only a sub-menu about to open (towards its side, it still opens), and one about to close still closes.
- README: the dark colours for an app that follows the system, and which keys need `multiple: true`.

**Upgrade** (TypeScript apps only): copy `web/files.d.ts` over the app's copy. An app whose `on_change` hook relied on running at once now gets it a moment later.

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
