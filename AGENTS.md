# For agents: using and changing tauris-ui

This folder is the one set of UI components for every Tauri app that uses it:
tabs (`TaurisTabs`), a tree view / configuration editor (`TaurisTree`), a
shared-files table (`TaurisFiles`), in-window menus (`TaurisMenu`), a
collapsible sidebar (`TaurisSidebar`), a find-anything panel (`TaurisFinder`), dialogs (`TaurisDialog`), drag to reorder (`TaurisReorder`),
small figures (`TaurisGlance`: a sparkline, a status, a capacity bar), a dense data table (`TaurisTable`),
a status bar (`TaurisStatus`) and an optional terminal look
(`TaurisTerminal`). An
app never has its own tab or tree code: it uses this library, and a fix made
here reaches every app at its next build. Below, `<library>` means the folder
this file is in.

## Using it in an app

1. Read `README.md`: for tabs, "Start a new app" and "Tabs carry your data" (one page serves a window, and it shows what the active tab says); for the tree view, "Tree view"; for files and menus, "Files" and "Menus".
2. The quickest start is to copy `examples/basic` as the README says: new package name, `productName` and `identifier`, the dependency path, and no build output. Otherwise follow the six steps in the README.
3. Run the checker. It must end with "Ready":
   ```
   python <library>/scripts/doctor.py <app folder>
   ```
4. Add this line to the app's `CLAUDE.md` (or `AGENTS.md`), so the next agent in that app knows where its tabs come from:
   ```
   UI components (tabs, tree view) come from <library>. Read its AGENTS.md before touching them, and run its scripts/doctor.py on this app.
   ```
5. Never copy `web/*.js` or `web/*.css` into the app. The plugin injects them. (A TypeScript app keeps a copy of `web/*.d.ts`; doctor says when it is out of date.)
6. To change the look, set `--tt-*` (tabs), `--tv-*` (tree), `--tf-*` (files), `--tmn-*` (menus), `--tsb-*` (sidebar), `--tfd-*` (finder), `--tdl-*` (dialogs), `--trd-*` (reorder), `--tgl-*` (glance), `--ttb-*` (table), `--tst-*` (status bar) or `--tm-*` (terminal) variables in the app's CSS, outside every `@layer` block. Do not edit the library for one app's colours.
7. Read fields in Rust with `tab.str("view")` or `tab.get("n")`, never `tab.fields["view"]`, which panics when the field is missing.
8. If the app has unsaved work, give `mount` an `onBeforeClose`. ⌘W, the close button and every other way of closing then ask it first.

## Is the app on the latest version?

- Apps depend on the library by `path` (or `git`) plus a `version` requirement (`version = "0.4"`). With `path`, each build compiles the library as it is on disk now; with `git`, `cargo update -p tauris-ui` takes the latest.
- A fix or a new option keeps the version in the same series (0.4.x). The app gets it at its next build, and nothing is needed.
- A change that needs app changes moves the version to a new series (0.5.0). The app's build then fails with ``failed to select a version for the requirement `tauris-ui = "^0.4"` ``. That failure is the signal. To fix it:
  1. Read `CHANGELOG.md` from the app's version to the new one.
  2. Do every **Upgrade** step.
  3. Set `version = "0.5"`.
  4. Rebuild.
- `scripts/doctor.py` reports the same mismatch before a build. It also flags a dependency path that leads nowhere.
- A page can read `TaurisTabs.version`, and Rust can read `tauris_ui::VERSION`.

## Changing the library

Do all of these, every time:

1. **Keep it general.** Nothing for one app goes in here: no app names, colours, views or fields. If one app needs something, add an option whose default changes nothing for the others. `docs/scope.md` says what belongs here and what stays in an app, as agreed with the apps.
2. **Bump the version in `Cargo.toml`** (working for the maintainer; apps on this machine rely on it. A pull request from elsewhere adds to **Unreleased** instead, and the maintainer bumps at release):
   - patch (0.4.x) for fixes and for new options that change nothing by default
   - next series (0.x+1.0) when any app must change something
3. **Add a `CHANGELOG.md` entry** under the new version and date (or under **Unreleased** for a pull request; the maintainer releases). If apps must change, add **Upgrade** lines with the exact steps.
4. **Update the docs** to match: `README.md`, the component's `web/*.d.ts`, `examples/basic`.
5. **New behaviour gets a test:**
   - tabs page behaviour in `test/run.py`, tree behaviour in `test/tree_run.py`, files in `test/files_run.py`, menus in `test/menus_run.py`, the sidebar in `test/sidebar_run.py`, the finder in `test/finder_run.py`, the dialogs in `test/dialog_run.py`, reorder in `test/reorder_run.py`, glance in `test/glance_run.py`, the table in `test/table_run.py`, the status bar in `test/status_run.py` (the toolbar's keys in `test/menus_run.py`), the example that uses every component in `test/all_run.py`
   - window behaviour in `src/runtime_tests.rs` (real windows on Tauri's test runtime)
   - pure logic next to it (`#[cfg(test)]`)
6. **Never open a window inside the plugin's `on_event`** (`src/lib.rs`), nor run app code there: Tauri holds its plugin lock and opening a window takes it, so the app freezes. Send the work through `after_event(app, |app| ...)`. The same holds for plain (not async) page commands, which must start with `let _locked = windows::InPlugin::enter();` (a test checks): inside that lock, and on the worker that opens windows, the app's `on_change` hook runs on its own worker. The test `the_event_handler_opens_no_window_itself` reads the source for it, and debug builds stop at once when a window opens while the lock is marked; only `test/freeze_check` proves it in a real app (see below), on macOS.
7. **A new page command needs four matching edits:**
   - the function in `src/commands.rs`
   - `generate_handler!` in `src/lib.rs`
   - `COMMANDS` in `build.rs`
   - `permissions/default.toml`

   The test `every_command_is_registered_and_allowed` fails if one is missing.
8. **Run every check** and fix any failure before finishing:
   ```
   cargo fmt --check && cargo clippy --all-targets && cargo test   # must print no warnings
   cargo clippy --all-targets --features files && cargo test --features files
   python test/run.py                         # headless; nothing touches the screen
   python test/tree_run.py
   python test/terminal_run.py
   python test/files_run.py
   python test/menus_run.py
   python test/sidebar_run.py
   python test/finder_run.py
   python test/dialog_run.py
   python test/reorder_run.py
   python test/glance_run.py
   python test/table_run.py
   python test/status_run.py
   python test/all_run.py                    # the example that uses every component
   (cd examples/basic/src-tauri && cargo clippy -- -D warnings && cargo build)
   (cd examples/all/src-tauri && cargo clippy -- -D warnings && cargo build)
   python scripts/doctor.py examples/basic
   python scripts/doctor.py examples/all
   python test/doctor_run.py                 # the checker itself, on small apps set up right and wrong
   (cd test/freeze_check && cargo clippy -- -D warnings)   # only builds it: never `cargo run` it here (see "What tests cannot cover")
   rm -f Cargo.lock && export CARGO_RESOLVER_INCOMPATIBLE_RUST_VERSIONS=fallback && cargo +1.90 build && cargo +1.90 build --features files   # the oldest Rust it builds with, as CI
   rustup target add x86_64-pc-windows-msvc && cargo clippy --all-targets --features files --target x86_64-pc-windows-msvc -- -D warnings   # Windows's code paths, from any system
   ```
   The page suites also run in CI's two browsers, from Playwright 1.48: its Chromium (older than Chrome: it hangs on some CSS current Chrome takes) and its WebKit, the engine Tauri uses on macOS and Linux. In a virtualenv with `pip install playwright==1.48.0 pillow && python -m playwright install chromium webkit`, run each suite with `TAURIS_TEST_CHROMIUM=1`, then with `TAURIS_TEST_WEBKIT=1`.
9. **Delete the build output** when finished: `target/`, `examples/basic/src-tauri/target/`, `examples/all/src-tauri/target/` and `test/freeze_check/target/`.
10. **Commit and push the release** once every check passes, as `tauris-ui X.Y.Z: what changed`, and tag it `vX.Y.Z` (`git tag vX.Y.Z && git push origin vX.Y.Z`), so an app can pin it. Do not ask the maintainer first. Then watch CI (`gh run watch`): the release is done when every job is green (Windows and Linux build what a Mac does not); a red or stuck job is fixed and pushed at once.

## Where things are

| Path | What |
|---|---|
| `src/lib.rs` | The plugin, `app.tabs()` (Rust API), menu and window events |
| `src/config.rs` | `Config`: every option and its default |
| `src/model.rs` | Tabs and windows in memory (+ tests) |
| `src/windows.rs` | Opening, closing, activating, notifying pages and the app |
| `src/drag.rs` | Dragging a tab out and across windows (follows the real mouse) |
| `src/persist.rs` | Saving and restoring the layout (+ tests) |
| `src/menu.rs` | `default_menu`, `file_menu` |
| `src/platform.rs` | macOS calls; stubs elsewhere |
| `src/commands.rs` | What a page can call (`plugin:tauris-ui|…`); a page only touches its own window's tabs |
| `src/dialogs.rs` | Dialogs in windows of their own (TaurisDialog with `window: true`): opening, sizing, attaching, the messages between a dialog and the window that asked |
| `src/files.rs` | `tauris_ui::files`: names, types, `inspect`; with the `files` feature the system's pickers and `open_path` (+ tests) |
| `src/runtime_tests.rs` | Window tests on Tauri's test runtime |
| `build.rs`, `permissions/` | The commands and the `tauris-ui:default` permission |
| `web/tabs.js` | The page side, `TaurisTabs.mount` |
| `web/tabs.css` | The look; every `--tt-*` variable is at the top |
| `web/tabs.d.ts` | Types for the tabs' page side |
| `web/tree.js`, `web/tree.css`, `web/tree.d.ts` | The tree view: script, look (`--tv-*` variables), types |
| `docs/tree-view.md` | The design brief every tree view is built to |
| `web/terminal.js`, `web/terminal.css`, `web/terminal.d.ts` | The terminal look: helpers, classes (`--tm-*` variables), types |
| `web/files.js`, `web/files.css`, `web/files.d.ts` | The files component: script, look (`--tf-*` variables), types |
| `web/menus.js`, `web/menus.css`, `web/menus.d.ts` | The in-window menus (not the native menu, which is `src/menu.rs`): script, look (`--tmn-*`), types |
| `web/sidebar.js`, `web/sidebar.css`, `web/sidebar.d.ts` | The collapsible sidebar: script, look (`--tsb-*`), types |
| `web/finder.js`, `web/finder.css`, `web/finder.d.ts` | The find-anything panel (⌘K): script, look (`--tfd-*`), types |
| `web/dialog.js`, `web/dialog.css`, `web/dialog.d.ts` | Questions, forms, reviews, sheets and titled panels: script, look (`--tdl-*`), types |
| `web/reorder.js`, `web/reorder.css`, `web/reorder.d.ts` | Drag rows into another order (and ⌥⌘↑ ⌥⌘↓): script, look (`--trd-*`), types |
| `web/glance.js`, `web/glance.css`, `web/glance.d.ts` | The sparkline, the status and the capacity bar: script, look (`--tgl-*`), types |
| `web/table.js`, `web/table.css`, `web/table.d.ts` | The dense data table: script, look (`--ttb-*`), types |
| `web/status.js`, `web/status.css`, `web/status.d.ts` | The status bar: script, look (`--tst-*`), types |
| `web/native.js` | `Config::native_feel()`: the page behaves like a desktop app's window (no web right-click menu, no page zoom, …) |
| `test/` | Headless tests: tabs (`run.py`, with a stand-in for Rust), tree (`tree_run.py`, `tree_demo.html`), terminal (`terminal_run.py`, `terminal_demo.html`), files and menus (`files_run.py`, `menus_run.py`, both on `files_demo.html`), the sidebar (`sidebar_run.py`, `sidebar_demo.html`), the finder (`finder_run.py`, `finder_demo.html`), the dialogs (`dialog_run.py`, `dialog_demo.html`), reorder (`reorder_run.py`, `reorder_demo.html`), glance (`glance_run.py`, `glance_demo.html`), the table (`table_run.py`, `table_demo.html`), the status bar and the toolbar (`status_run.py`, `frame_demo.html`), the browser each runs in (`engine.py`); the checker (`doctor_run.py`, on small apps it writes); `mock_tauri.js`, Rust stood in for the tabs page; `freeze_check/`, a real macOS app (see below) |
| `examples/basic/` | The smallest complete app |
| `examples/all/` | An app that uses every component: tabs, a sidebar holding a tree, the files table, menus, the finder, the dialogs (Edit in a window of its own), Home's projects (a table, reorder and glance), the status bar and the terminal look (`CLAUDE.md` says what it does; `test/all_run.py` tests its page) |
| `scripts/doctor.py` | Checks an app's setup and version requirement |

## What tests cannot cover

A window opened from the plugin's event handler freezes only the real event
loop. `test/freeze_check` checks it in a real app, and CI runs it on macOS at
every push. Never run it on the maintainer's machine: it opens windows, presses
menu items and takes the focus from whatever they are doing. Watch CI's
`freeze-check` job instead (it must end with "OK" eight times).

Dragging a tab out of a window, and between windows, follows the real mouse.
No test can drive that. After changing `src/drag.rs` or the drag code in
`web/tabs.js`, ask the person you work for to try it by hand. Never take
screenshots of their screen to check it.
