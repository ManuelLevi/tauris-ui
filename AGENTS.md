# For agents: using and changing tauris-ui

This folder is the one set of UI components for every Tauri app that uses it:
tabs (`TaurisTabs`) and a tree view / configuration editor (`TaurisTree`). An
app never has its own tab or tree code: it uses this library, and a fix made
here reaches every app at its next build. Below, `<library>` means the folder
this file is in.

## Using it in an app

1. Read `README.md`: for tabs, "Start a new app" and "Tabs carry your data" (one page serves a window, and it shows what the active tab says); for the tree view, "Tree view".
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
6. To change the look, set `--tt-*` (tabs) or `--tv-*` (tree) variables in the app's CSS, outside every `@layer` block. Do not edit the library for one app's colours.
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

1. **Keep it general.** Nothing for one app goes in here: no app names, colours, views or fields. If one app needs something, add an option whose default changes nothing for the others.
2. **Bump the version in `Cargo.toml`** (working for the maintainer; apps on this machine rely on it. A pull request from elsewhere adds to **Unreleased** instead, and the maintainer bumps at release):
   - patch (0.4.x) for fixes and for new options that change nothing by default
   - next series (0.x+1.0) when any app must change something
3. **Add a `CHANGELOG.md` entry** under the new version and date (or under **Unreleased** for a pull request; the maintainer releases). If apps must change, add **Upgrade** lines with the exact steps.
4. **Update the docs** to match: `README.md`, `web/tabs.d.ts` / `web/tree.d.ts`, `examples/basic`.
5. **New behaviour gets a test:**
   - tabs page behaviour in `test/run.py`, tree behaviour in `test/tree_run.py`
   - window behaviour in `src/runtime_tests.rs` (real windows on Tauri's test runtime)
   - pure logic next to it (`#[cfg(test)]`)
6. **A new page command needs four matching edits:**
   - the function in `src/commands.rs`
   - `generate_handler!` in `src/lib.rs`
   - `COMMANDS` in `build.rs`
   - `permissions/default.toml`

   The test `every_command_is_registered_and_allowed` fails if one is missing.
7. **Run every check** and fix any failure before finishing:
   ```
   cargo fmt --check && cargo clippy --all-targets && cargo test   # must print no warnings
   python test/run.py                         # headless; nothing touches the screen
   python test/tree_run.py
   (cd examples/basic/src-tauri && cargo build)
   python scripts/doctor.py examples/basic
   ```
8. **Delete the build output** when finished: `target/` and `examples/basic/src-tauri/target/`.

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
| `src/runtime_tests.rs` | Window tests on Tauri's test runtime |
| `build.rs`, `permissions/` | The commands and the `tauris-ui:default` permission |
| `web/tabs.js` | The page side, `TaurisTabs.mount` |
| `web/tabs.css` | The look; every `--tt-*` variable is at the top |
| `web/tabs.d.ts` | Types for the tabs' page side |
| `web/tree.js`, `web/tree.css`, `web/tree.d.ts` | The tree view: script, look (`--tv-*` variables), types |
| `docs/tree-view.md` | The design brief every tree view is built to |
| `test/` | Headless tests: tabs (`run.py`, with a stand-in for Rust), tree (`tree_run.py`, `tree_demo.html`) |
| `examples/basic/` | The smallest complete app |
| `scripts/doctor.py` | Checks an app's setup and version requirement |

## What tests cannot cover

Dragging a tab out of a window, and between windows, follows the real mouse.
No test can drive that. After changing `src/drag.rs` or the drag code in
`web/tabs.js`, ask the person you work for to try it by hand. Never take
screenshots of their screen to check it.
