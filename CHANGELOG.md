# Changelog

Newest first. Every change gets an entry. **Upgrade** lines say what an app
must change; an entry without them needs only a rebuild (or, with a git
dependency, `cargo update -p tauris-ui`).

## Unreleased

Nothing yet.

## 0.5.5 — 2026-10-23

- Dialogs in their own window now show. The dialog's window waited for an animation frame before telling its size, and WebKit gives none to a window that has never been on screen, so it stayed hidden until the 6-second fallback. It now tells its size as soon as the dialog has laid out.

## 0.5.4 — 2026-10-23

- Dialogs in their own window (`window: true`) now draw in a real app. The dialog's window looked for `window.__TAURI__` before Tauri had set it, so it never drew the dialog, and the window that asked waited for ever. It now looks once the page has loaded.
- Such a dialog can no longer fail silently:
  - if its window has not shown the dialog after 6 seconds, the window closes, the dialog shows in the page, and the console says why;
  - errors in the dialog's window are logged in the window that asked, as "[tauris-ui dialog window]";
  - options that can't be sent to a window (not JSON) are logged, and the dialog shows in the page.

## 0.5.3 — 2026-10-22

- Forms start in their first text field, its text selected, not in a select above it. `autofocus: true` on a field starts there instead.
- A press beside a dialog no longer closes it: the dialog gives a short shake and stays open, so nothing typed is lost (a ring instead of the shake when the system asks for less motion). Esc, ⌘. and ✕ still cancel. `--tdl-nudge-time` sets the shake's length.

## 0.5.2 — 2026-10-22

- Table:
  - a group's row with buttons is as tall as any row, and its name and buttons are centred;
  - in a table whose groups open and close, an empty group keeps the box's space, so every colour square lines up;
  - `emptyInline: true` says an empty group's text on its own row, with no row under it.
- Forms:
  - `validate` or `review` giving `false` keeps the form as it is and says nothing: for a question inside the check that got No. The keys go back to their field;
  - `review` can give `{ rows, note }`, for a note that depends on the values;
  - `maxLength` on a text, password, url or text area field stops typing there and says so under it.

## 0.5.1 — 2026-10-22

- Table:
  - a redraw compares each cell with the old one as it was drawn, before a narrow column shortened it, so a shortened cell that didn't change keeps its element and the press on it;
  - if a redraw takes away the element with the keys (or the one pressed), the keys stay on the table;
  - `selectGroup(id)` selects a group from code, and `onSelect` says which group was selected.

## 0.5.0 — 2026-10-22

A new series: the sidebar's nested groups went in 0.4.35, a change apps must make. That release should have moved the series, so it moves now, and an app on "0.4" stops building until it is upgraded.

**Upgrade:**
- Set `version = "0.5"` on the tauris-ui dependency.
- Sidebar items no longer nest: move a tree from items' `children` into a `TaurisTree` and pass it as `content` (as examples/all does). Drop `openOnSelect`. `scripts/doctor.py` finds both.
- Dialogs in their own window (`window: true`) need `"tauris-dialog-*"` in the capability's `windows`, and the page to check `TaurisDialog.inWindow`. Only for apps that use it; the checker says so.

Also:
- Table: a row's buttons, checkbox and group buttons run the actions as they are now. A kept cell could run the ones from an earlier draw (an old count in a question). The README says to delegate listeners an app's `render` adds, for the same reason.

## 0.4.41 — 2026-10-22

- Sidebar: `railItems`, what the collapsed strip shows (a tree's projects). Each shows its icon or its letter (`letter`, default its label's first). A click opens the sidebar and calls `onRailSelect`, for the app to show it in its tree. The full example shows its projects so.
- Table:
  - the rows keep their elements when the app updates, and only changed cells are new, so a press's click still reaches its button or checkbox;
  - a pending rename (click, pause) ends with any key, a scroll or the window losing focus;
  - a checkbox blocked by `canToggle` looks blocked, with its reason as the tooltip;
  - an edit's `maxLength`;
  - `groupActions` (buttons on a group's row);
  - `selectableGroups`;
  - a collapsible group with no rows has no box;
  - `last(row)` keeps rows after the others either way, and `compare` gets the direction;
  - in a cell the app draws, a part marked `data-short` shortens when narrow.
- Dialogs:
  - `left: { label, danger, run }`, a button on the left ("Delete…"), in a window of its own too;
  - a question's paragraph keeps its single line breaks.

## 0.4.40 — 2026-10-22

- Tree and table: a ⌘-click (without `multiple`) only opens the other way (a new tab). The selection stays where it was, as in Finder's sidebar.

## 0.4.39 — 2026-10-22

- Dialogs: a form's `{ type: "row" }` field showed nothing (it has no `name` of its own, and was left out). It shows now.

## 0.4.38 — 2026-10-22

- Tabs: each tab's Back/Forward. The `history` option (`restore`, `same`, `alive`), with `visit(place)`, `back()`, `forward()`, `canGo()` and a `history` event for the toolbar. The full example uses it.
- Tree:
  - `node.tones` colours a cell (warn, bad, ok, dim);
  - `dropTarget(id)` rings the row a drop would land on, and `nodeAt(x, y)` finds a row from a point;
  - ⌘↩, and ⌘-click without `multiple`, give `activate` with `cmd: true`.
- Table:
  - editing in place (`edit: true` on a column, `onEdit`; F2, or a click on the selected row and a pause);
  - a checkbox column (`check`, `canToggle`, `onToggle`; Space ticks);
  - groups that open and close (`collapsible`, a +/- box, ← →);
  - `rowClass`;
  - row buttons off with a reason (`disabled`);
  - `short` text when a column is narrow;
  - column edges to drag;
  - `storageKey` keeps widths, sort and closed groups;
  - `state` for loading and errors;
  - `multiple`;
  - `copy` (⌘C as text);
  - ⌘-click opens with `cmd`.
- Dialogs:
  - `TaurisDialog.close()`;
  - a form can open refused (`refusal`, `okDisabled`);
  - `{ type: "row", fields }` puts inputs on one line;
  - a refusal can point at a part of an app field (`{ field, part, text }`);
  - a question asked while a form in its own window saves shows in that window.
- Status bar: segments keep their place, so the keys stay on them. New messages fade in (`--tst-msg-in-time`).
- New look variables: easing beside each motion time (`--tt-*-ease`, `--tmn-*-ease`); colours inside a selected row (`--tgl-sel-c`, `--tgl-sel-ring`, `--ttb-sel-dim`, and `--ttb-row-dim` for an app's own dim text).
- `docs/scope.md`: what goes in the library and what stays in an app.

## 0.4.37 — 2026-10-22

- The checker says when sidebar items still have `children`: since 0.4.35 they don't show, and the page only said so in its console.

## 0.4.36 — 2026-10-22

- Tree: a `contextmenu` event for a right click on a row and for the menu key (⇧F10), with where to open the app's menu.
- Tree: the `select` event says `how`: `"mouse"`, `"keyboard"`, or `"api"` when the app selected.
- Tree: `header: false` hides the column headers; `fit: true` makes the tree fit its width (no sideways scroll).
- New style variables, all set to today's values:
  - tabs `--tt-shift-time`, `--tt-settle-time`, `--tt-appear-time`;
  - menus `--tmn-pop-time`, `--tmn-tool-time`;
  - tree `--tv-icon-size`, `--tv-arrow-size`, `--tv-arrow-color`, `--tv-sel-hover-bg`, `--tv-sel-inactive-hover-bg`.
- Every release since 0.4.7 has a git tag (`v0.4.7` …), so an app can pin one.

## 0.4.35 — 2026-10-22

- New: `TaurisTable` (from MLPC's tables): a dense data table. 25px rows under a header that stays, ▲▼ sorting by a click on a header (natural order, within groups), rows in groups (a colour square, a name, a count), the keys of a desktop list (↑ ↓, Home End, ⌘↑ ⌘↓, Page Up and Down, Enter, ⇧F10, typing a name), a row's own buttons (shown on hover and selection; toggles; Copy with a tick), `flash(id)` for a row just added. `Component::Table`.
- New: `TaurisStatus`: the status bar along a window's foot. The last message, with an Undo (or another action) for 10 s, after which the focus goes back where it was; on its right the app's segments: a dot (ok, warn, bad, wait, off), counters, toggles, buttons. `Component::Status`.
- New: `TaurisMenu.toolbar(nav, { back, forward, find })`: a toolbar is one stop for Tab, with ← → Home End between its buttons; Back and Forward (⌘[ ⌘], Alt+← Alt+→ elsewhere) with `setHistory`; a Find anything button at its end.
- Dialogs (MLPC's needs):
  - `window: true` opens a form, a review or a sheet in a native window of its own, attached to the window that asked and sized to the dialog. The app's checks and save run in the window that asked. New plugin commands `dialog_window_*` are in `tauris-ui:default`; the capability must cover `"tauris-dialog-*"` too, and the page checks `TaurisDialog.inWindow` (the checker says both).
  - `TaurisDialog.defineField(type, render)` (and `render` on one field): the app's own widgets inside a form.
  - Passwords take `reveal` and `generate`.
  - A review row can show a picture's change (`beforeImage`, `afterImage`).
  - `confirm({ run })` runs the action inside the question, a refusal kept on its line.
  - About's values can be selected.
  - `validate` and `review` may be async.
- Sidebar: no more nested groups. For a tree, put a `TaurisTree` in the sidebar (`content`).
- The system's alert (`plugin:tauris-ui|ask`) with an empty `cancel` is a notice with one button.
- The full example uses all twelve components: Home is a `TaurisTable`, the window's foot a `TaurisStatus` (Undo after a move), the toolbar has Back, Forward and Find, Edit… opens in a window of its own, and Delete runs inside its question.

**Upgrade** (only if your sidebar items had `children`): move that tree into a `TaurisTree` and pass it as `content`, as examples/all does.

**Upgrade** (only for `window: true`): add `"tauris-dialog-*"` to the `windows` of the capability that has `core:default` and `tauris-ui:default`, and start the page with `if (TaurisDialog.inWindow) { /* defineField(...) only */ } else { /* the app */ }`.

## 0.4.34 — 2026-10-22

- Reorder: a control in a row marked `.tauris-drag` (a project's name that opens on a click) starts a drag too: a click still opens it, a press and a move drags the row, and the click that ends the drag is swallowed. Other controls still never start one.

## 0.4.33 — 2026-10-22

- New: `TaurisReorder.attach(container, { onMove })` (from MLPC's tables): drag rows into another order, as in a macOS table. The row lifts and follows the pointer, a line shows where it lands, Esc puts it back, and the rows slide into place once the app has drawn the new order. ⌥⌘↑ ⌥⌘↓ (Ctrl+Alt elsewhere) move the current row, and `move(id, dir)` is a menu's Move Up. `group` keeps a row among its own; a drop over another group's rows is refused. `movable` says why a row cannot move, `items` moves a heading with its rows, and `onStart` gives the order to hold still while a row is dragged. `TaurisReorder.arrange(list, order)` and `TaurisReorder.keys` help. It is on only where an app attaches it, and `enabled: false` turns it off. `Component::Reorder`.
- New: `TaurisGlance` (from MLPC's views): `sparkline(values)` (dates as x spaced by time), `status(kind, text)` (a coloured dot and a word) and `capacity({ max, items })` (the count and a segment for each place, in its holder's colour). `Component::Glance`. The checker knows both.
- The full example has Home: its projects in an order dragged into place, each with its activity and status, and the files' capacity bar.
- Type-ahead (the tree, the files table, the sidebar, menus) times each key by
  when it was pressed, not when the page got to it: a page busy drawing the
  last match no longer cuts short a name typed quickly.
- Tests: a check that follows a pause asks again for up to 3 s before it fails
  (`engine.settled`), so CI's slow Mac no longer fails a different pair of
  WebKit checks each run. A check that something did not happen still answers
  at once. The type-ahead checks give the slow machine's keys a long window, and
  the delete-then-add check waits for the delete before adding.

## 0.4.32 — 2026-10-22

- Tree: dragging a column's edge tells the app its new width once. WebKit (the
  Mac's webview) ended the drag twice and sent the same width twice.
- Tests: the files table's pointed-at row and its Shift+F10 menu are checked
  once they have settled, not after a fixed 150 ms a slow machine misses.

## 0.4.31 — 2026-10-22

- New: `TaurisDialog` (from MLPC's dialog kit): `confirm` (starts on Cancel; `danger`; `native: true` asks with the system's alert through the plugin's new `ask` command, with the `files` feature and the dialog plugin, else in the page), `form` in the Swing layout (right-aligned "Label:", compact fields, example placeholders, a balloon under a refused field, one kept line for the form's hint or refusal, `validate`, `submit` that may throw, a `review` of the changes before saving), `review` on its own, the Keyboard Shortcuts sheet (groups in balanced columns, keycaps, "either" rows), the About sheet, and titled border panels for a page (`panel`). Esc and ⌘. cancel, Tab stays inside, the rest of the page is out of reach, the focus goes back after. `Component::Dialog`; the checker knows it. The full example asks with it (Edit…, Delete…, Help › Keyboard Shortcuts ⌘/, About).
- Tree: a desktop outline by default. In a table, rows that group others are no longer a bold band (`bandGroups: true` brings it back), and the selection without the focus is its tint alone (`--tv-sel-bar` adds the bar).
- The full example: a click on a tree row only selects it; a double click or Enter opens a project or a file. Its tree takes the sidebar's colours.

## 0.4.30 — 2026-10-22

- Sidebar: `image` puts a picture before its `title`: a product's or company's logo, a person's avatar. An image's address or markup starting with `<` (an svg); `imageShape: "round"` makes it a circle the picture fills (an avatar), `"square"` (default) shows the whole picture with slightly rounded corners. In the rail it alone shows, above the button, the title as its tooltip; one that fails to load leaves the title's first letter. Its size is `--tsb-image` (22px). The full example (`examples/all`) shows its logo and name there.

## 0.4.29 — 2026-10-22

What MLPC's finder had that TaurisFinder missed:
- ⌘↩ or a ⌘-click (Ctrl elsewhere) picks with `onPick(item, { how, cmd: true })`, for the app's other way to open (a new tab); `labels.openAlt` ("New Tab") says so in the key strip. Enter with ⇧, ⌥ or ⌃ does nothing.
- `strict: true` on an item, or on its kind: its letters must sit together (long text such as log entries: no initials, no scattered letters).
- ⌘K (or `open()`) with the panel open selects its field's text, as Spotlight does. Closing fades out over 90ms. A label cut short is whole in its tooltip.

## 0.4.28 — 2026-10-22

- New: `TaurisFinder`, find anything with ⌘K (from MLPC's finder): a panel at the top of the window, as Spotlight or Xcode's Open Quickly, finding in memory as you type. Only an item's `label` and `more` texts are searched (a password left out is never found); words match whole, at the start, at word starts, as initials or scattered letters, accents folded; results in groups by kind, the best first, each cut at its `limit`; recent picks with nothing typed (`storageKey`). ↑ ↓ ⌃N ⌃P, Page Up and Down, Tab between groups, Enter, Esc; `onContextMenu` for a result's menu. `Component::Finder`; the checker knows it. The full example (`examples/all`) finds its teams, projects and files with it.

## 0.4.27 — 2026-10-22

From MLPC's components:
- Menus: a disabled item's `reason` shows after its label and as its tooltip ("Hide Done (no done tasks)"). `TaurisMenu.openFor(element, items)` opens an element's menu (a list's selected row) at it from the keys, the focus back on the list after; `TaurisMenu.isMenuKey(event)` is the menu key or ⇧F10. A menu is at most 420px wide (`--tmn-menu-max-w`): a longer label ends in "…", whole in its tooltip.
- `Config::native_feel()` (off by default): every page behaves like a desktop app's window, with no web right-click menu but in fields, no dragging pictures or links out, no page zoom, ⌘A outside a field selecting no page text, and single-line fields not autocorrected or capitalised (`web/native.js`).

## 0.4.26 — 2026-10-22

- New: `examples/all`, an app that uses every component: tabs, a sidebar holding a tree, the files table, menus and the terminal look (`CLAUDE.md` says what it does). Its page is tested by `test/all_run.py`; CI builds it and runs the checker on it.
- New: `TaurisSidebar`, a collapsible side bar of sections, as in Mail or Finder (`web/sidebar.js`, `web/sidebar.css`, `web/sidebar.d.ts`). Items with icons and counts, headings, groups to any depth; collapsed to a rail of icons (or away) by its button, ⌃⌘S (Ctrl+Shift+B elsewhere), `toggle()` or its edge dragged narrow; resized by its edge, from the mouse or the keys; one Tab stop with the arrows, type-ahead and the menu key (`onContextMenu`); `openOnSelect`; `storageKey` keeps its width and state. `Component::Sidebar` for `Config::components`; the checker knows it.
- Terminal: `commandLine(el, { onKey })` hears each key first; returning true takes it (↑ and ↓ through an app's suggestions). A table row chosen from the keys is `aria-selected="true"` on its `<tr>`.
- CI: the checker's tests read and write files as UTF-8 (on Windows they read the typings in its own code page and failed).

## 0.4.25 — 2026-10-22

- Tabs: in Chromium on a Mac (which says "macOS"), the strip's shortcuts and their labels are the Mac's.
- CI: builds with the newest clippy; a WebKit check waits for what it checks rather than a fixed time.

## 0.4.24 — 2026-10-22

Fixes from the final reviewer:
- Files: only the rows in view are drawn (spacers stand for the others; `aria-rowcount` and `aria-rowindex` say where a row is), so 20,000 files mount, step, search and take a new list at once. A new list is compared file by file. The delete question is not marked modal, as the header stays usable while it is open.
- Tree: past what a browser can scroll (about 1.8 million rows), the rows are spread over the scroll range: End, `select()` and the wheel still reach every row.
- Tabs: Ctrl+Shift+← / → on a tab, or Ctrl+Shift+Page Up / Down anywhere, moves it along the strip; its menu has Move left, Move right and "Move to “…”" for every other open window (`app.tabs().move_to_window(tab, label)` in Rust; the `other_windows` and `move_to_window` commands are in `tauris-ui:default`). A tab from another window that lands in a strip fires `drop` with that tab and its place; a drag that only passes over, or ends elsewhere, fires nothing. What Rust tells a strip (its tabs changed, a tab hovering it, a close asked) goes to that window's page alone, not as an event every listening page gets; the strip no longer listens for Tauri events. Backspace on a tab does not go back a page in WebKit.
- Windows: a remembered window comes back at its own size, even when the app's `window` hook sets one.
- Menus: a fuller toolbar look. The row is 34px (4px above and below its 26px buttons); a button has 10px at its sides and 8px between an icon and its text; a child `<svg>` is a 13px line icon in the text colour (`--tmn-tool-icon`); the line between groups is 24px high; the ▾ sits closer to its text. A pressed or open button is a neutral grey with its own edge (`--tmn-tool-on-bg`, `--tmn-tool-on-border`; a dark grey in dark mode) instead of the selection blue, and has no line along its foot. It no longer follows `--tauris-sel-inactive`: set `--tmn-tool-on-bg` to colour it.
- `Config::components(&[...])`: the page components the plugin puts in pages (default all five; the files table brings the menus).
- The checker: `Tauri.toml` in kebab-case (`with-global-tauri`, `frontend-dist`, `drag-drop-enabled`) is read; `window_prefix` from a `const` or `static` is read, and one it cannot read is said; a capability's `platforms` count (one for other systems grants nothing here); a page using a component `Config::components` leaves out is caught; a capability file that cannot be read is said; an app installing on macOS before 11 is told the components need Safari 16.4.
- Terminal: black text on the red key and error band (6:1; white was 3.4:1). In WebKit, the block cursor finds the caret at the end of right-to-left text.
- The README says what the page needs: Safari 16.4 (macOS 11 with its updates), WebKitGTK 2.40, WebView2. The example app sets `minimumSystemVersion` 11.0.
- CI: the page suites also run in WebKit (Playwright's, on macOS); the window tests run on Windows too (the test program gets the manifest Tauri needs); the real-app check closes a window's last tab by ⌘W and from the page, and checks a remembered size and a tab reaching its page. It is for CI: run by hand it opens windows and takes the focus.

## 0.4.23 — 2026-10-22

- Windows builds with the `files` feature without an unused-variable warning (CI treats warnings as errors). The checks before a release include a Windows clippy run, which works from a Mac.

## 0.4.22 — 2026-10-22

Fixes from the fourth round of the Opus reviewers:
- CI: the page tests no longer hang in Chromium 130 (WebView2's engine for a while), which stops on a colour worked out with a bare channel inside `clamp()` or `max()`; the job has a time limit. Windows builds without an unused-function warning.
- Tabs from Rust: a tab opened midway through a restore goes to the front window. Windows closed together come back in the order they were in front, mixed with open ones too (each window keeps when it was last in front). A layout of any file name left half written is removed. A restore never reads a file a save is writing. Closing the last tab saves before the app's hook hears of it. The event handler's source check covers more calls that open windows.
- `open_path` refuses `.ipa`, `.vncloc`, `.mailloc`, `.atloc`, `.newsloc` and `.pst`; `inspect` says a macOS package (`.rtfd`, `.pages`, `.key`, `.numbers`, a bundle) is a document saved as a folder, to export or zip.
- The checker: permissions written as objects are read (it stopped with an error); an app's own `pick` needs no dialog plugin; `pick` is found in minified code and through a variable, with a note when the options cannot be read; `tauri.conf.json5` with comments, single quotes and trailing commas is read; a tabs app that also uses files is checked for the picker's permission; `dragDropEnabled: false` is flagged. Its tests take the series from `Cargo.toml` and write Windows paths with forward slashes.
- Files: another place shown while several files are deleted never gets the old place's list; `update({ files, sort })` meanwhile applies the sort at once; an add on its way for one place never lands in another reached through an empty list; a file being deleted is out of `selection()` at once. `update()` with an option given as undefined puts its default back (`onDelete: undefined` takes the handler away; `files: undefined` leaves the files). Rows are put right in place rather than all taken out and put back: deleting many files is quicker, and a row's button keeps the focus. The delete question closes once its files are gone; the focus stays in the component after the question, the row menu, or a column header the app took away. The empty place's text is read once. The search field's focus shows as a line, not only a colour; the focused row among several selected has a 2px ring; a row just added flashes softer in dark mode; in Windows high contrast the rename field's ring shows on the selection.
- Tree: Shift+Tab from a checkbox cell leaves it; `setData` moving the row being edited into a closed folder ends the edit, its value kept, without an error; an editor is untouched by what was typed, not by the value it reads as; a right-click or Ctrl-click keeps the keyboard focus; a checkbox cell reached by the keys scrolls into view; a click below the last row keeps the focus in the tree; `setData` keeps the focus on a checkbox cell.
- Menus: new items while a scrolled menu has a sub-menu open keep both; a scroll that moved no row (the browser's, for an arrow key a moment before) leaves a sub-menu open; a menu at a point inside an app's popover shows over it; Space after type-ahead spells only when an item starts with the typed text and a space; shortcuts such as ⌘+, ⌘, and ⌘↑ are said right; a screen reader's click on an item with a sub-menu opens it with the focus inside; a press on a title dragged through its menu and released outside closes it.
- Tabs: `update(tab, patch)` with an older object of the tab takes only what that object changes; a tab updated while it or its × is pressed keeps the click; a right-click in a field the app drew in a tab is the field's; a drop on a tab removed mid-drag lands by its neighbour; the tab with the focus stays in place as the others move (WebKit); `reload()` resolves whether its answer is the one shown (`Promise<boolean>`). The tab menu's focus line follows the menu's colours, not `--tt-accent` (made for the strip).
- The look: lines worked out from the accent, and white or black text on it, only where the engine can (Safari 18, Chromium 119); elsewhere the defaults stand, not nothing. `--tf-accent` alone moves the files' lines too. A primary button hovered moves away from its text (darker under white, lighter under black), so the text still reads. The tree's ticked box and a hovered +/- box are edged in the accent made readable. The README says what each shared colour sets, and that `--tauris-on-accent` goes with `--tauris-accent`.
- Terminal: in a right-to-left command line the block covers the character before the caret; with several terminals on a page that brings its own stylesheet, none is added until the last of them goes, and `styles: true` adds it.
- Docs and tests: the README says a files-only app needs `core:default` too; AGENTS says to run the page tests in CI's browser, and to watch CI after a push. New tests for `contextMenu: false`, Home, the menus' `gap` and `TaurisMenu.close()`, and the files' `formatDate`, `focusSearch()` and `styles: false`.

## 0.4.21 — 2026-10-22

Fixes from the third round of the Opus reviewers:
- Tabs from Rust: a close the page agreed to that the app then refused (a window hidden to the tray) asks the page again next time, also once the window is focused again. A minimized window's place is not remembered (Windows moves it far off screen). Windows that closed together come back in front of each other as they were. A quit right after a Dock click does not save each window twice; nor does a restore while quitting rename the layout away. A drop never lands in a window that is closing or still opening. Closing the last tab, and the next launch, remove a layout a crash left half written. A thread that cannot start ends a drag cleanly. The Dock click's handling has a test (`persist::reopened`), and so does a window whose screen is gone. The docs say where the hook must not wait for the main thread, and that `start()` after a failed one tries again.
- `open_path`: a file marked executable is a program when it has no extension or starts as one (`#!`, ELF, Mach-O), so a document from a USB stick or a network share opens whatever its kind. Also refused: `.rdp`, `.sparseimage`, `.sparsebundle`, `.cdr`, `.toast`, `.mht`, `.mhtml` (web pages open in the browser's sandbox, as a link would). `inspect` says a shortcut (a Finder alias, `.lnk`, `.url`, `.webloc`) is not the file.
- The checker: an app's own `pick` must be on every mount, and `TaurisFiles.pick` or `saveDialog` called directly needs the dialogs; the plugin's commands granted one by one count; `use tauris_ui::*`, `pick` through an inline spread or React's `useMemo`, `Tauri.toml` and `tauri.conf.json5` are read; an app's own `.tabs()` is not the library's; a `Cargo.toml` not in UTF-8 is said so. Its tests run on every system in CI (Windows paths), and as people run it (no `PYTHONUTF8`).
- Files: an app sending its list back after each of many deletes costs one pass a frame (2,000 files in well under a second); another place shown mid-deletes loses none of its files; a rename waiting for the app, or files added while one is open, never touch another place; `onDelete(file, { files, index })` lets an app that asks itself ask once. The focus stays in the component when the part it was in goes (the search field, Clear search, a search matching nothing); a click no pointer made (a screen reader's) selects a row; rows keep their ids as files arrive; the empty place's button is described by what the place says; the search waits for an input method's text, and what it finds is spoken once the typing stops; the row menu's Open says Enter off a Mac. A search re-sorts nothing (the order is kept); in Windows high contrast the rename field reads.
- Tree: setData while someone types keeps their edit (on the new list's node; an untouched field shows the new value). Enter confirming an input method's text keeps the editor; switching to another app keeps it open; a null value left empty stays null; a number keeps its step. The focus put on a row by something else (VoiceOver) is the row the keys act on; a tree emptied and filled again keeps the focus.
- Menus: a menu at a point that does not fit opens beside it, the point at a corner, and a release chooses only after the pointer moved since it opened (a quick press, drag and release from a title chooses at once). A menu at a point closes when what it was opened on scrolls, not anything anywhere; menus inside an app's popover go in the top layer; a sub-menu's side is worked out from its own width; scrolling a menu closes its sub-menu. Pressed and open titles and buttons have a line along their foot; every chosen item is edged; shortcuts are said as `aria-keyshortcuts`; a `<button>` menu button keeps the default cursor.
- Tabs: a field the app draws in a tab keeps the focus and its text while its title is updated as it is typed, and when Rust closes a tab before it; ⌘W for a tab not loaded yet waits for Rust's newest tabs before deciding, and the window's close button asks every tab Rust has now; a new tab pops in once; a strip removed at once sends no stale positions. The close button's hover reads on any strip.
- The look: with `--tauris-accent` alone, lines are that accent kept no lighter (light mode) or no darker (dark) than reads, and text on it is white or black by its luminance, also on a component's own accent (`--tf-accent`, `--tv-check-on`).
- Terminal: the block cursor sits right in a right-to-left command line. The README says the log keeps the newest 500 rows (`max`).
- Docs and tests: the README's dark strip example sets its lines too; the Rust 1.90 check is written as CI runs it. Tests for `typeAheadMs`, `newIcon`/`closeIcon`, `moveThreshold`/`detachDistance`, the tree's `icons` and its console warnings, `open(..., { returnTo })`.

## 0.4.20 — 2026-10-22

Fixes from the second round of the Opus reviewers, and MLPC's review:
- Tabs from Rust: closing the last tab forgets the layout before the app's hook hears of it (a hook that opens a tab no longer brings the old layout back). Pressing a hung page's close button again does not restart its two seconds. A window the app's own close handler kept open takes tabs again. A tab opened while its window is closing, or while a tab is dragged in it, gets a window of its own. A window whose screen is gone opens centred with its size, maximized if it was. Once quitting, no window opens or is recorded, and one still opening is not saved. A `layout_file` that panics saves nothing and stops nothing; the docs say `new_tab` and `layout_file` can run inside Tauri's lock.
- `open_path` refuses Finder aliases (macOS follows them to whatever they point at), and `.ppsm`, `.xlm`, `.xlsb`, `.shs`, `.shb`, `.psdm1`, `.themepack`, `.deskthemepack`, `.onepkg`, `.afploc`, `.ftploc`.
- The checker asks for the event permission (`core:default`) the strip and dropped files need, also for an app with its own `pick`; reads `window.TaurisTabs?.mount`, `let tabs = app.tabs(); tabs.start()`, the files feature through a feature of the app's own, the dialog plugin under another name, and TypeScript types through `/// <reference>`. Every message and note it gives has a test.
- Files: deleting every file says so and keeps the focus in the component (the empty list is the same place); opening several files, or the row menu, never acts on another place shown meanwhile, and a new place has nothing selected. `dropArea: "element"` takes no drop over something drawn on top of it. Deleting thousands of files takes one pass, drawn once a frame; `update({ files })` keeps the rows already drawn. The focus stays in the component when the list empties or fills; a search's count is spoken once the typing stops; a row whose name does not say its kind is named with it. Type-ahead says "Nothing starts with …" on a miss (`labels.noneStarts`), takes `typeAheadMs`, and one letter again and again steps past a doubled one. In dark mode a selected row has a bar at its start; badges and button edges read better; in Windows high contrast a disabled button is GrayText.
- Tree: `setData` with an editor open and untouched keeps the new data (a typed value goes into the new node, and "change" is said for it). `edit()` on a true/false value gives its box the focus. An editor closed with nothing changed changes nothing; the wheel does not change a number being edited. Read-only values show as editable ones do. `-`, `+` and `*` inside a typed name are part of it. An empty box on the selection reads.
- Menus: a sub-menu's pending timer after new items leaves no menu behind. In a `<dialog>` a menu opens in the top layer, where the dialog's transform and overflow do not move or cut it. Chosen after the pointer went on to another menu, or opened from shortcuts back to back, the focus goes back to the field. The release chooses wherever the press began, with any button. A menu taller than the room by its button never covers it. A menu opened at a point closes when what is under it scrolls; a blur into a frame leaves the focus there; a sub-menu past one that flipped left flips left too. In dark mode the chosen item is ringed.
- Tabs: a scrolled row tells Rust where its tabs are; a tab dragged out of a scrolled row is held where it was grabbed; a drop lands on the place it was dropped on; Rust changing other tabs keeps a field the app drew in a tab, its text and the focus; ⌘W for a tab the page had not loaded yet closes it; a menu opened with the mouse gives the focus back where it was. The active tab's bar and every focus line use `--tauris-accent-ink`; with `--tauris-accent` alone they are that accent mixed with the text colour, to read, and text on it is white or black by its lightness. A danger item hovered reads; in Windows high contrast the focus ring shows beside the active frame.
- Terminal: a full log trimming old rows keeps the place of someone reading further up; the block cursor sits right after right-to-left text.
- Docs and tests: the README's tab strip example is complete for a dark strip; its colour check reads both dark blocks; the Rust 1.90 check is the one CI runs. The example app opens no console window on Windows. New tests for a tab's fields reaching Rust, a frame coming back, the screen check, quitting, the Dock click, and the hook's thread; the clocks are read at once; the `open_path` test never launches what it refuses.

## 0.4.19 — 2026-10-22

Fixes from the Opus reviewers, and MLPC's review:
- The layout file is on the disk before it replaces the old one (a power cut leaves the old one, never an empty one), under a name of this process's own (two copies of the app never write one file). A save at quit or at the last window's close that fails is tried again as one, with the windows that closed. ⌘N (`new_window`) with no window open brings the remembered windows back first, behind the new one. A tab opened during a restore of several windows goes in the front one. A window whose close went ahead takes no new tab (`frontmost`, `open_in`). Closing the last tab also forgets the copies kept aside. A system that reports no screens keeps the remembered places.
- `on_change`: a dropped tab tells the hook on its worker, so a slow hook holds up neither the drop nor the target's focus. A window the hook closes by closing its last tab is reported to it once it is done. The docs say other plugins' callbacks (deep-link's `on_open_url`) run inside Tauri's lock too, so they call `app.tabs()` from a thread of their own. The + button's command catches a panicking `new_tab`.
- `open_path` refuses everything Outlook blocks, and more (`.xll`, `.iso`, `.vhdx`, `.appref-ms`, `.settingcontent-ms`, `.one`, `.fileloc`, `.flatpakref`...). The executable mark counts only for a name of no known document type: every file on a USB stick has it.
- The checker: capabilities in folders under `capabilities/`, a `${ }` in `mount`'s first argument, windows the Rust code opens, the workspace's `Cargo.lock`, the files feature turned on by the app's own default features, and a `tauri.conf.json` that cannot be read (said so, not a crash). Every one of its messages has a test now.
- Files: what was started for one place (a delete, several deletes, a rename, the delete question, a drop waiting its turn) never acts on another place shown meanwhile, nor after `destroy()`; a drop goes where it was dropped. Several files being deleted leave the list one by one, drawn once a frame, and a second Delete meanwhile does not delete one twice. The focus goes back to the list only when it fell to the page, not from a field of the app's. While a search hides files the header says "2 of 5 files" and their size (`labels.countShown`). `select()` of a file the search hides shows it. Turning `multiple` off keeps a selected file, not one that only had the focus. New objects for the selected files reach `onSelect`. A row is named by what it shows (not its buttons too); "No files match" and the busy card are spoken through a region that is always there; the row menu for several files is named "3 files". Typing a name through an accent key or AltGr finds it. Selecting thousands of files takes one pass; a search keeps the rows already drawn. An option given as `undefined` keeps its default.
- Tree: a click on another row while editing, with the app redrawing on its "change", keeps the keys on the tree. Tab reaches a checkbox in any column (Space flips it; Enter on a row whose first value is a checkbox goes to it). A node's `editor` goes to the values it fits, `editor: { level: ... }` gives one per column, and a column has its own `editor`. `setData` during an edit shows the value typed, in the new list's node. `sort()` in the order already in place sorts again; `destroy()` keeps a value being typed. An app's `input:focus` rule does not reach the editor. Without the focus, the selection's bar is in the focus colour, which shows in dark mode too (`--tv-sel-bar`). Options given as `undefined` keep their defaults.
- Menus: a bar menu taller than the window stays below the bar and scrolls. The focus leaving a menu (the app focusing a field, a dialog) closes it. A press on plain text puts the focus back where it was. Press on a title, drag to an item, release: it is chosen. The pointer crossing other items on its way to an open sub-menu keeps it open. The keys go past an empty menu of the bar, and pointing at one leaves the open menu open. Escape after the pointer went on to another menu goes to that menu's title. One letter again and again steps through the items starting with it. A template's `button:focus` outline adds no second ring to a toolbar button.
- Tabs: Delete held down closes one tab; a lone tab that carried its window keeps no drag look; "Close tabs to the right" works from where the tab is when chosen; a drop lands by the tab it was dropped by, though Rust changed the tabs meanwhile; `activate` fires for every change of the active tab, Rust's too; the first click on a tab the app draws reaches what it drew. In Windows high contrast the active tab is framed with its bar on top. The light menu's danger colour reads on hover. Terminal: the block cursor stays inside the field, also when the window narrows.
- The look: colours set on a component's element reach the colours worked out from them (`--tv-sel-line`, `--tf-sel-line`, `--tf-sel-hover`, `--tf-focus`, `--tmn-focus` are worked out where they are used; `--tf-focus-mix` and `--tmn-focus-mix` set how strong a halo is). The README's colours come with a full dark set that follows an app's own light or dark switch, and a test reads every pair.
- The example app: a window with several noted tabs closes on the second try; emptying the title and typing a new one gives that title. Its page has tests.
- Tests and CI: what the pages call is checked against Rust's commands and their arguments, and the stand-in for Rust refuses a command it does not have. Tests for ^Tab and ⌘⇧], "Close tabs to the right", `documentTitle`, `middleClickClose`, `shortcuts`, `appear`, the tab events, `lines: false`. CI runs the page tests in the Chromium of its pinned Playwright, and the 1.90 build takes dependencies that build on 1.90, with the files feature too.

## 0.4.18 — 2026-10-22

Fixes from the second round of the stronger reviewers, and MLPC's review:
- Restoring: a tab opened while another thread restores the windows (a deep link at launch) waits for the first of them instead of opening a window of its own; the new window at a first launch is opened by one caller only (a guard was dropped at once before, clearing the flag it set). A window still opening takes no tab (`open_in`), a tab closed meanwhile is not put back, and `windows()` reads every window in one go. A dragged tab's new window follows the mouse at once, however long the app's hook takes.
- `on_change`: async page commands (dragging a tab out, moving it to a new window) call it on its worker too, as plain ones do. Several changes to one window while its call waits make one call, at the place of the newest (so the order of the windows' last changes holds). A hook, or a window hook, whose panic cannot even be dropped stops nothing.
- `open_path` looks at what a link points to, refuses any file marked executable (a program with no extension), more types (`.jnlp`, `.pif`, `.chm`, `.mobileconfig`, macro-enabled Office files...) and names ending in dots or spaces. `safe_name` checks Windows' device names after cutting a long name.
- The checker: template literals inside `${ }`, `<!--` in a script's string, copied `.d.ts` files, an app's own `tabs.js` (only a real copy of the library's is reported), `pick` through a typed, spread or getter option, `>0.4` and `<=0.4`, a capability for `tabs-1` alone, one for windows the app does not have, a Cargo.toml that cannot be read, a renamed dependency, `init::<Wry>`, `use tauris_ui as ui`, raw byte strings; a files-only app with its own `pick` needs no capability. Its tests check every message and the exit code, and clean up after themselves.
- Files: search and type-ahead ignore case, accents and Unicode forms; Enter in the search goes into the list, on the first match; Shift+Enter opens nothing; AltGr and Option letters work in type-ahead; holding Enter in the rename field asks the app once; a list replaced for another place leaves nothing selected; files added during a search get the focus on one that shows; a delete that fails among several leaves that file selected; an empty refusal says nothing; Tab from the delete question's text goes to Cancel; a drop fed with no position goes to one component; a search matching nothing takes the list out of the Tab order; the row's buttons make no column for screen readers. Buttons and the search field have edges readable at 3:1 (`--tf-border-2`). In Windows high contrast a new row does not flash. The dark flash is gentler.
- Tree: a space inside a typed name is part of it; opening or closing another folder keeps an editor open; a column's width stays within its range; an editor off to the side comes fully into view past a scrollbar; a selection without the focus has a bar of the selection's colour; in Windows high contrast the lines on a selected row, colour swatches, the dropdown caret and a column's edge show. The focus ring and the sort arrow use `--tauris-accent-ink`; the scroll thumb is easier to see.
- Menus: holding Enter or Space opens or chooses once; a menu the app opens (from a shortcut) puts the focus back in the field it was in; a right press on a menu button closes its menu; new items keep a scrolled menu's place and the focus in its own level; an `onClose` that throws stops nothing; a menu inside a `<dialog>` closes with it. An open title and a pressed toolbar button take `--tauris-sel-inactive`, not the hover colour.
- Tabs: a drag released where it began, or one Rust refused, leaves no drag look; the drag uses the strip as it is when it begins, and stops if the button was released unseen; a tab the app draws is drawn again when it becomes active (its handlers are the new ones); a press on the tab menu's padding keeps its keys; its focus ring uses `--tauris-accent-ink`. Terminal: `commandLine`, `log` and `pane` take `{ styles: false }` too, and a later `mount` without it adds the stylesheet.
- The look: lines on a selection follow `--tauris-sel-fg`; focus halos follow the accent. The README's example colours keep secondary text readable on hover.
- Tests: the Mac and Linux key rules run on every machine; timing-free waits in the quitting tests.

## 0.4.17 — 2026-10-22

Fixes from the stronger reviewers:
- `on_change`: a window that already has a hook call waiting gets no second one (typing in a field no longer queues a call per key). The docs say where the hook runs: at once for the app's own changes; on a worker for changes inside Tauri's lock and for ⌘N, ⌘T and the Dock click. Quitting also waits for a hook call running on another thread.
- A restore already on its way, at launch or from a Dock click, means no other window opens in its place.
- The checker reads JavaScript, Rust and HTML as such: regular expressions, Rust character literals and nested comments, and the page's own text no longer confuse it. It finds `pick` as `mount<F>(...)`, `TaurisFiles?.mount` or a quoted key; reads capability files that hold a list or `{ "capabilities": [...] }`, and `webviews`; counts only what `app.security.capabilities` lists, inline ones too; reads `version` as Cargo does (`0`, `0.*`, `=0.4.1`, `~`, ranges); and knows `init(...)` after `use tauris_ui::init`. It has its own tests now (`test/doctor_run.py`, in CI).
- `inspect` says "could not be read" for a file it may not read. `open_path` opens no folder and no file that is a program or runs one (`.command`, `.app`, `.exe`, `.bat`, `.lnk`, `.jar` and the like): shared files come from other people.
- Files: holding Enter, F2 or Delete acts once; Delete with ⌥, ⇧ or ⌘ held asks nothing, and ⌘⌫ deletes only on a Mac (elsewhere Ctrl+Backspace is a word); input methods keep Enter and Escape in the rename field; without `multiple`, adding several files selects one; `onSelect` is not called by `mount`; deleting the file being renamed ends the rename; names equal but for case or accents keep one order; a whole name typed is found from the top ("report 1"); Space never scrolls the list; after a rename or a sort the file stays in view; the row's buttons are left to the mouse for screen readers (the keys reach every action); a new selected row flashes from a darker selection. When no file matches the search, a Clear search button empties it (`labels.clearSearch`, "" for none).
- Tree: column edges say their width to screen readers within a range; an editor in a column off to the side comes into view; closing an editor by setData, a sort or a folder closing leaves the focus in the tree; the same letter again steps through the rows; `edit(id)` opens the folders above the row; in Windows high contrast the focused row among several selected has a ring and the column lines show.
- Menus: closing a menu, by the app or by a press elsewhere, puts the focus back where it was; `setMenus` and `setItems` keep an open sub-menu and the item with the focus; `onClose` names the menu that was open even after `setMenus` took it away; a right press on the bar, or a press on a title that is off, closes the open menu; Shift no longer ends type-ahead; a long menu does not hand the wheel to the page; a danger item that is off looks off, and its shortcut is readable; in Windows high contrast a pressed toolbar button shows. The README lists the options of `bar`, `button` and `open`.
- Tabs: a click on a tab gives it the focus; changing which tab is active redraws only what changed, so a double-click reaches what the app drew in a tab; a drag starts holding the pointer only once it moves; nothing redraws the strip while a tab is dragged along it; a tab object the app keeps gets each `update`'s patch; a right click between tabs or on + opens the strip's menu; the item the keys choose in a tab's menu has a ring. Terminal: the block cursor sits after wide characters (CJK, emoji); Enter that confirms an input method's text sends nothing; `mount(root, { styles: false })` keeps the command line, log and panes from adding the stylesheet.
- The look: colours that follow other colours (the tree's selection without the focus, the files' button edge, flash and drop zone, the tabs' focus ring, ghost and + button) follow them where the component is, so setting a colour on the component itself works. The tree's selection without the focus is a little stronger, and its ticks follow `--tauris-on-accent`. The files' drop zone is lighter, so its text is readable. `--tf-faint` is gone (nothing used it). The README's example colours give a hovered or open title a visible step.
- Tests and docs: the Mac-only key checks run on every machine; a date check works on 1 January; the README's check list matches CI (with the oldest Rust); the Save a copy example passes the file's name.

## 0.4.16 — 2026-10-22

- Tree: the `resize` event gives a column's new width (and all of them) when the person drags its edge or uses the keys, `widths()` reads them and `setWidths()` gives them back, so an app can keep them when it draws the tree again or opens next time. The edge between two headers shows a line under the mouse.
- Files: the sort headers are no longer Tab stops, so Tab leaves the list at once. ↑ from the first file reaches them: ← / → go from header to header, Enter or Space sorts, ↓ or Escape goes back.
- A window still opening is never where a new tab goes, so a tab opened meanwhile is not lost if the window fails. A tab handed back from a window that failed, with no window left to take it, is forgotten rather than kept unseen. Windows closed long ago are let go at every save, also with no layout file. The app's `on_change` hook hears of a window a dragged tab opens, and of the dragged window when it is dropped onto another. A drag that ends in a window the app put tabs into shows that window again.

## 0.4.15 — 2026-10-22

Fixes from the first of the stronger reviewers (tabs, saving, dragging):
- While a tab is dragged in a window of its own, `frontmost()` and anything that opens a tab (`open`, `open_or_focus`, ⌘T) leave that window out. A tab opened in it anyway moves with the drop, or back with a drag or a move to a new window that failed. A dragged window that closes mid-drag clears the strip it was over.
- While remembered windows open, nothing saves over the layout. A second caller that finds them opening opens no window of its own in their place. A `start()` whose window could not open can be called again.
- A save after a pause leaves out windows closed a moment ago (only the save as the app quits keeps them), so a window the person closed does not come back after a crash. Closing the last tab forgets the layout only if no window opened meanwhile.
- Tests: a check of a file's date no longer depends on today's date; the ⌘⌫ check uses Ctrl off a Mac.

## 0.4.14 — 2026-10-22

- Files: names sort as in Finder, the name without its extension first and then the extension, so "Q3 plan.md" comes before "Q3 plan 2.md".
- Files: on a Mac, Control never acts as Command. ⌃⌫ and ⌃⌘⌫ no longer delete, ⌃⌘A no longer selects all, and ⌃⌘-click and ⌃⌘↑↓ no longer add to the selection.

Fixes from a second round of the ten reviewers:
- The hook calls that a window job causes (⌘N, the Dock click) go to the hook's worker, so a slow `on_change` never holds up the next window. A hook that panics is the app's bug: the tabs carry on, on every thread. Quitting also waits (half a second at most) for a hook call running on another thread.
- Closing a window's last tab takes the tab and the window out of the layout in one go, so a tab opened meanwhile always gets a new window. A drag whose window closed mid-way drops nothing. `open_many` into a window that closed meanwhile opens a new one. A failed move restores the active tab only if the person did not choose another; a tab whose window has gone goes to the frontmost window. Two restores at once (a Dock click and the app's own open) do not both open every remembered window. One remembered window that fails to open keeps the layout aside as `<name>.unopened`. A failed save keeps the windows closed a moment ago for the next try.
- `safe_name` trims tabs and line breaks at the ends before anything else ("report.pdf\t" is "report.pdf") and drops more invisible characters. `inspect` gives a limit in bytes when a rounded size would hide it ("larger than 1,500 bytes"). `open_path("")` says "The file could not be found."
- The checker reads a page without its HTML comments, keeps a `/*` that is not a comment, finds `pick` only as a key of the options given to `TaurisFiles.mount`, understands `tauris-ui = { workspace = true }` and `version = "*"`, and counts only the capabilities that `app.security.capabilities` enables.
- Files: `destroy()` while a name is being edited renames nothing; a file deleted while another is renamed leaves the screen at once; files added meanwhile show, selected, when the rename ends; a click on the delete question's text keeps it open; type-ahead takes spaces ("Launch p"); Space never scrolls the list; the search field leaves keys to an input method that is composing. Error text and the Delete button have their own colours (`--tf-danger`, `--tf-danger-fill`, `--tf-on-danger`), readable in light and dark. The search placeholder uses `--tf-dim`. The type badges are readable on the README's example colours. In Windows high contrast a selected row's badge and buttons, and the focused row among several selected, are drawn in the system's colours.
- Tree: every column can be resized from the keyboard (Tab to its header: ← / → where it does not sort, Alt+← / Alt+→ where it does), so the header is no longer hidden from screen readers. A folder the person closed stays closed after it left the list for a while (a search). `edit(id)` selects that row. `isExpanded` is false for a leaf. Secondary text on a selection without the focus, and on any selection in Windows high contrast, is as readable as its label.
- Menus: a sub-menu whose `items()` fails is an item that is off (and the console says why); a menu closes when the page, or what holds its opener, scrolls, not when a list elsewhere does; `setMenus` keeps the open menu with its own title even when that title moves; Space right after an arrow chooses; a bar's `destroy()` leaves the element's own children and role. The shortcut on the chosen item is as readable as its label. In Windows high contrast items that are off are greyed and separators show. A `<button class="tmn-tool" aria-disabled="true">` looks off.
- Tabs: `update()` keeps the focus on the tab and one tab reachable with Tab; a tab closed during a drag is not dropped; ⌘W and the window's close button pressed together ask `onBeforeClose` once; a tab the app draws (`renderTab`) is named by what it shows. The tab menu's danger and muted colours are readable in light and dark. Terminal: Down after Up gives back what was being typed.
- Tests: the slow-hook test now fails if the bug comes back; timing checks take the best of three runs; CONTRIBUTING and AGENTS list every check CI runs.

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
