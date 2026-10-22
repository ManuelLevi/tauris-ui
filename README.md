# tauris-ui

UI components for Tauri 2 desktop apps. One library for every app.

| Component | In the page | What it is |
|---|---|---|
| [Tabs](#tabs) | `TaurisTabs.mount(strip)` | Browser-style tabs that can leave their window and come back, remembered between runs |
| [Tree view](#tree-view) | `TaurisTree.mount(element, { data })` | A dense tree and configuration editor: compact rows, dotted guide lines, aligned columns, in-place editing |
| [Files](#files) | `TaurisFiles.mount(element, { files, onAdd })` | A place's shared files: a dense, sortable table with drag and drop, search, in-place renaming and the system's pickers |
| [Menus](#menus) | `TaurisMenu.bar(nav, { menus })` | An in-window menu bar, toolbar buttons with a ▾ menu, and right-click menus, with a desktop app's keyboard |
| [Sidebar](#sidebar) | `TaurisSidebar.mount(element, { items })` | A collapsible side bar of sections, as in Mail or Finder: icons, counts, groups, a rail of icons when collapsed, an edge to resize |
| [Terminal](#terminal) | `TaurisTerminal.mount(element)` | An optional Bloomberg-style look: amber on black, monospace, dense tables, function keys, a command line and a message log |

The plugin delivers every component's script and stylesheet to every page (or the ones `Config::components` names). A component's stylesheet is added only when a page mounts it, so a component you don't use changes nothing.

**What the page needs.** The components use what Safari 16.4 has (stylesheets made in script, `color-mix()`, `:has()`, `inert`, cascade layers). That is macOS 11 or later with its Safari updates, WebKitGTK 2.40 or later on Linux, and WebView2 on Windows (Windows keeps it current). Set `"bundle": { "macOS": { "minimumSystemVersion": "11.0" } }`, as the example does; the checker says so when it is lower. Colours worked out from your accent need Safari 18 or Chromium 119; an older engine shows each component's own colours instead.

## One look for every component

Set a few `--tauris-*` colours once, and the tabs, the tree, the files table and the menus all follow them. Each component keeps its own look until you do; its own variables (`--tt-*`, `--tv-*`, `--tf-*`, `--tmn-*`) still win when you set them. The terminal keeps its amber look.

```css
:root {                                   /* outside every @layer block */
  --tauris-font: "Source Sans 3", system-ui, sans-serif;
  --tauris-mono: "Source Code Pro", ui-monospace, monospace;
  --tauris-bg: #ffffff;                   /* lists, fields, menus, the active tab */
  --tauris-chrome: #e9e9eb;               /* bars and column headers */
  --tauris-fg: #1e1f22;
  --tauris-dim: #555a66;                  /* secondary text: readable on --tauris-chrome and --tauris-hover */
  --tauris-line: #c4c6cc;                 /* borders and separators */
  --tauris-hover: #dcdfe5;                /* a step from --tauris-chrome, so a hovered title shows */
  --tauris-accent: #2675bf;
  --tauris-accent-ink: #1f64a6;           /* the accent as text and focus lines: 4.5:1 on --tauris-bg and --tauris-chrome */
  --tauris-on-accent: #ffffff;            /* text on the accent (the files' Add button, the tree's ticks) */
  --tauris-sel-bg: #2675bf;               /* the selected row, the chosen menu item */
  --tauris-sel-fg: #ffffff;
  --tauris-sel-inactive: #c9d6ea;         /* a selection without the focus; an open menu's title */
  --tauris-faint: #a3a6ad;                /* faint and disabled text */
  --tauris-focus: rgb(31 100 166 / 0.32); /* the soft halo around a focus line */
}
/* Dark: on a dark system unless the app picks light, and whenever it picks dark. */
@media (prefers-color-scheme: dark) {
  :root:not([data-tauris-theme="light"]) {
    --tauris-bg: #2f3234; --tauris-chrome: #3c3f41; --tauris-fg: #dfe1e5; --tauris-dim: #bfc2c8;
    --tauris-line: #5e6165; --tauris-hover: #46494c; --tauris-accent: #3570b0; --tauris-accent-ink: #7ab0e6;
    --tauris-on-accent: #ffffff; --tauris-sel-bg: #3570b0; --tauris-sel-fg: #ffffff; --tauris-sel-inactive: #3d5a8f;
    --tauris-faint: #7d8188; --tauris-focus: rgb(122 176 230 / 0.45);
  }
}
:root[data-tauris-theme="dark"] {
  --tauris-bg: #2f3234; --tauris-chrome: #3c3f41; --tauris-fg: #dfe1e5; --tauris-dim: #bfc2c8;
  --tauris-line: #5e6165; --tauris-hover: #46494c; --tauris-accent: #3570b0; --tauris-accent-ink: #7ab0e6;
  --tauris-on-accent: #ffffff; --tauris-sel-bg: #3570b0; --tauris-sel-fg: #ffffff; --tauris-sel-inactive: #3d5a8f;
  --tauris-faint: #7d8188; --tauris-focus: rgb(122 176 230 / 0.45);
}
```

Set every colour for dark, not a few: the library's own dark colours of the others are made for its own dark background, not yours.

An app that is always light (or always dark) also sets `data-tauris-theme` on `<html>` (below). Without it, a dark system still gives the components dark scrollbars and the dark colours of everything you did not set.

Set them on `:root` (on another element they do not reach the components). Which component follows which:

| Variable | Tabs | Tree | Files | Menus | Sidebar |
|---|---|---|---|---|---|
| `--tauris-font` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `--tauris-bg`, `--tauris-fg`, `--tauris-line`, `--tauris-hover` | ✓ | ✓ | ✓ | ✓ | ✓ (not bg) |
| `--tauris-chrome`, `--tauris-dim` | ✓ | ✓ | ✓ | ✓ (chrome) | ✓ (chrome: its background) |
| `--tauris-accent` | ✓ (without `--tauris-accent-ink`: the active tab's bar and focus lines, made readable) | ✓ (the ticked boxes; without `--tauris-accent-ink`, made readable: focus lines and box edges) | ✓ (the buttons; without `--tauris-accent-ink`, made readable: the lines) | ✓ (without `--tauris-accent-ink`: focus lines, made readable) | ✓ (a count's dot in the rail; without `--tauris-accent-ink`, made readable: focus lines, the edge) |
| `--tauris-sel-bg`, `--tauris-sel-fg` | | ✓ | ✓ | ✓ | ✓ |
| `--tauris-sel-inactive` | | ✓ | | ✓ (an open title) | ✓ (the selected item, the focus elsewhere) |
| `--tauris-faint` | | | | ✓ | |
| `--tauris-focus` | | | ✓ | ✓ | |
| `--tauris-accent-ink` | ✓ (the active tab's bar, focus lines) | ✓ (focus lines, box edges, the sort arrow) | ✓ (lines, the sort arrow, the drop zone) | ✓ (focus lines) | ✓ (focus lines, the edge) |
| `--tauris-mono` | | | ✓ | | |
| `--tauris-on-accent` | | ✓ (the checkbox tick) | ✓ (text on the buttons) | | |

"Made readable": the accent no lighter than oklch 0.5 in light mode, no darker than 0.75 in dark, where the engine works colours out (Safari 18, Chromium 119; elsewhere the component's own default). Unset, `--tauris-on-accent` is white or black, whichever reads on the accent. Set, it is the text on every component's accent: a component given an accent of its own (`--tf-accent`, `--tv-check-on`) needs its own text colour with it (`--tf-on-accent`, `--tv-check-mark`).

**Light and dark.** Every component follows the system's light or dark mode. An app with its own switch, or one that is always light or always dark, sets `data-tauris-theme="light"` or `"dark"` on `<html>`, and every component (all its colours, its scrollbars and checkboxes, not only the ones above) follows the app instead:

```js
document.documentElement.dataset.taurisTheme = theme; // "light" or "dark"; remove it to follow the system again
```

The example above sets its colours for both: the dark ones on a dark system unless the app picks light, and whenever it picks dark.

## Tabs

- Drag a tab to reorder it.
- Drag it out of the strip: it becomes its own window, under the mouse (macOS).
- Drop it on another window's strip to move it there (macOS).
- Right click: New tab, Close tab, Close other tabs, Close tabs to the right, Move to new window.
- ⌘T, ⌘N, ⌘W and ⇧⌘W, through a ready-made menu.
- Keyboard: arrows, Home, End, Delete, Shift+F10 for the menu, ^Tab to step. Ctrl+Shift+← / → on a tab (or Ctrl+Shift+Page Up / Down anywhere, as in browsers) moves it along the strip; the tab's menu also moves it left or right, to a new window, or into any other open window ("Move to “…”"). Keys typed into a field inside a tab stay in the field; Enter, Space and Delete on a button inside a tab are that button's.
- Too many tabs to fit: the row scrolls, also while you drag a tab.
- On macOS the tabs sit in the title bar, level with the window buttons; elsewhere, just below the system's title bar.
- Windows, tabs and the data on them are remembered between runs, quits included.
- Unsaved work is safe: with `onBeforeClose`, every way of closing a tab or a window asks first.
- The look is a set of CSS variables. It follows light and dark mode.

Rust owns the tabs of every window. Each window's page draws its own strip. The plugin puts the page part (`web/tabs.js`) and its stylesheet (`web/tabs.css`) into every page itself, so there is nothing to copy into your app. Change the library, rebuild the app, and it has the new version.

**How it fits your app:** there is one page per window, not one page per tab. Your page shows whatever the active tab says it should show. Keep that on the tab as fields (`view`, `query`, a record id, a draft), and switch what the page shows when the active tab changes.

Desktop only: macOS, Windows, Linux. Dragging a tab out of its window needs macOS; elsewhere tabs still reorder, open and close.

## Start a new app

The fastest way is to copy `examples/basic`, the smallest complete app, which is kept working:

`examples/all` is the same app with every component in it (tabs, a sidebar holding a tree, the files table, menus, the terminal look): read it to see how they fit together.

1. Copy the folder. Leave out the build output: `src-tauri/target/`, `src-tauri/gen/` and `src-tauri/Cargo.lock`.
2. In `src-tauri/Cargo.toml`:
   - set the package `name`
   - set the `tauris-ui` path to where the library is
3. In `src-tauri/tauri.conf.json`, set `productName` and `identifier`. Two apps with the same identifier share their saved tabs.
4. In `src-tauri/src/main.rs`, change "Tabs Example" in the window title and the menu name.
5. Run the checker (see step 6 below).
6. Run it with `cargo run` from `src-tauri`. For installers:
   - set `"bundle": { "active": true }`
   - install Tauri's CLI with `cargo install tauri-cli --version "^2"`
   - run `cargo tauri build` from `src-tauri`

Or add it to an existing Tauri 2 app:

**1. `src-tauri/Cargo.toml`.** Add the dependency:

```toml
[dependencies]
tauris-ui = { git = "https://github.com/ManuelLevi/tauris-ui", version = "0.4" }
# tauris-ui = { path = "../tauris-ui", version = "0.4" }    # a copy on this computer
# tauris-ui = "0.4"                                         # once it is on crates.io
```

Keep the `version`. With a `path` dependency every build uses the library as it is now; with `git`, run `cargo update -p tauris-ui` to take the latest. When the library changes in a way that needs changes in your app, its version moves to 0.5, and the build (or the update) stops with:

```
failed to select a version for the requirement `tauris-ui = "^0.4"`
```

Read `CHANGELOG.md`, do its **Upgrade** steps, then set `version = "0.5"`.

The library is for desktop apps. If the app also builds for iOS or Android, keep it off those builds:
- Put the dependency under `[target.'cfg(not(any(target_os = "android", target_os = "ios")))'.dependencies]`.
- Put `#[cfg(desktop)]` on the lines that use it.
- Add `"platforms": ["macOS", "windows", "linux"]` to the capability from step 3.

**2. `src-tauri/tauri.conf.json`.** Turn on the global API, and remove the app's own windows. The plugin opens them.

```json
"app": {
  "withGlobalTauri": true,
  "windows": []
}
```

**3. `src-tauri/capabilities/default.json`.** Change `"windows"` and add two permissions; keep everything else that is there:

```json
"windows": ["tabs-*"],
"permissions": ["core:default", "core:window:allow-start-dragging", "tauris-ui:default", ...]
```

Tab windows are named `tabs-1`, `tabs-2` and so on. The capability `create-tauri-app` makes only covers `"main"`. Left like that, every call is refused, the strip stays empty, and the console says what to change.

**4. Rust.** Register the plugin, set the menu, and start. In a `create-tauri-app` project this goes in `src-tauri/src/lib.rs`, in `run()`, next to the plugins already there:

```rust
use tauris_ui::{Config, NewTab, TabsExt};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauris_ui::init(
            Config::new()
                .window(|w| w.title("My app"))
                .new_tab(|_| NewTab::new("Home").with("view", "home")),
        ))
        .setup(|app| {
            // App menu, File (⌘T ⌘N ⌘W ⇧⌘W), Edit (copy and paste keep working), Window.
            app.set_menu(tauris_ui::default_menu(app.handle(), "My app")?)?;
            // Opens the windows from last time, or one new window.
            app.tabs().start()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running the app");
}
```

You can build your own menu instead. Put `tauris_ui::file_menu(app)` in it, and the shortcuts still work.

**5. The page (`index.html`)**

```html
<header id="strip"></header>
<main id="page"></main>
<script>
  const tabs = TaurisTabs.mount(document.getElementById("strip"), { panelId: "page" });
  tabs.on("change", () => {
    const tab = tabs.activeTab();
    // show what `tab` is about
  });
</script>
```

```css
/* The strip is fixed at the top of the window: keep your page below it. */
body { padding-top: var(--tt-strip-h); }
```

In React, mount it once and destroy it on cleanup (StrictMode mounts twice):

```tsx
import { useEffect, useRef, useState } from "react";
import "./App.css"; // where the padding rule for the strip goes

type Fields = { view: string };

export default function App() {
  const strip = useRef<HTMLElement>(null);
  const [active, setActive] = useState<TaurisTab<Fields> | null>(null);

  useEffect(() => {
    const tabs = TaurisTabs.mount<Fields>(strip.current!, { panelId: "page" });
    const off = tabs.on("change", () => setActive(tabs.activeTab()));
    return () => { off(); tabs.destroy(); };
  }, []);

  return (
    <>
      <header ref={strip} />
      <main id="page">{active?.view}</main>
    </>
  );
}
```

Put the padding rule above in the app's main stylesheet (`src/App.css` or `src/index.css` in a Vite app).

In TypeScript, copy `web/tabs.d.ts` into the app, for example as `src/tabs.d.ts`. `TaurisTabs` then type-checks with no import, and `mount<{ ...your fields }>` types your fields. The checker says when the copy is out of date.

**6. Check it.** With Python 3.11 or newer, from the library's folder. If the app takes the library from git, clone it once for this: `git clone https://github.com/ManuelLevi/tauris-ui`.

```
python scripts/doctor.py path/to/your/app
```

It checks every step above and says exactly what to change. It also flags:
- a dependency path that doesn't lead to the library
- an app that asks for an older version
- CSS layers that would hide your colours

## Tabs carry your data

A tab is `{ id, title, ...your fields }`. `id` and `title` are the library's own. A field with either name is dropped.

- **In the page:** change the tab object, then call `tabs.update(tab)` or `tabs.update(tab, { query: "abc" })`. Rust stores it, and it is remembered between runs.
Tab ids are given fresh at every launch. To find a tab again after a restart, keep your own key in a field.

- **In Rust:**
  - `NewTab::new("Users").with("view", "users")` makes one.
  - `tab.str("view")` reads a text field, and `tab.get("n")` reads any field. A missing field gives `None`, never a crash.
  - `app.tabs().update_tab(id, title, fields)` changes one.

## Closing and quitting

- **With `onBeforeClose`**, every way of closing a tab asks first, and the tab stays open if the answer is `false`. That covers:
  - the ×
  - the menu
  - middle click and Delete
  - ⌘W
  - the window's close button and ⇧⌘W, which ask once per tab and close the window only if every tab agrees
- **A page that hangs** cannot keep its window open: if it does not answer a close request within two seconds, the next press of the close button closes the window.
- **Quitting** (⌘Q) does not ask. It saves every window and every tab with all its fields, including the last keystroke, so the next launch shows exactly what was open. While the app runs, changes are saved a second after they stop, and at least every five seconds.
- **From Rust**, `request_close_tab(id)` asks like a user would. `close_tab(id)` and `open_many(…, true)` act at once without asking.
- `onBeforeClose` receives `{ reason: "tab" | "window" }`. While it is answering, more requests to close the same tab or window are ignored.
- **Closing the last tab by hand** clears the saved layout. The next launch starts fresh, and old tab titles don't come back.

## The page: `TaurisTabs.mount(strip, options)`

| Option | Default | What it does |
|---|---|---|
| `renderTab` | title and × | `(tab, { active }) => Node \| string \| Node[]`: what a tab shows. Add `data-tt-close` to an element to make it close the tab. Buttons, links and `data-tt-action` elements get their own clicks. |
| `contextMenu` | default items | `false`, or `(tab, items) => items` to change the menu. `tab` is `null` on the empty strip. An item is `{ label, action(tab), shortcut?, disabled?, danger? }` or `"-"`. |
| `onBeforeClose` | none | `(tab) => boolean \| Promise<boolean>`. Return `false` to keep the tab open (unsaved work). See "Closing and quitting". |
| `dragPreview` | `"tab"` | What follows the mouse in the strip: `"tab"`, `"ghost"`, `"title"`, `"none"`, or `(tab, tabEl) => HTMLElement`. |
| `panelId` | none | The id of the element that shows the active tab, for screen readers. |
| `labels` | English, ⌘ or Ctrl+ by system | `{ tabs, newTab, newTabHint, closeTab, closeOthers, closeRight, moveToWindow, moveLeft, moveRight, moveToOther, newTabShortcut, closeTabShortcut, moveLeftShortcut, moveRightShortcut }` (`moveToOther`: text, or `title => text` for another window) |
| `newIcon`, `closeIcon` | SVG | Text, or SVG markup. |
| `tabClass` | none | `(tab) => "class names"` |
| `documentTitle` | the tab's title | `(tab) => string \| undefined` |
| `dragOut` | `true` on macOS | Tabs can leave the strip into a window of their own. |
| `appear`, `middleClickClose`, `shortcuts`, `styles` | `true` | Pop-in animation, middle click closes, ^Tab steps, add the stylesheet. |
| `moveThreshold`, `detachDistance` | `4`, `28` | Pixels before a press becomes a drag, and before a tab leaves the strip. |

The returned object:

- **Read:** `tabs.tabs`, `tabs.active`, `activeTab()`.
- **Change:** `activate(id)`, `close(id)` (asks `onBeforeClose`), `open({ title, ...fields })` (resolves to the new id), `update(tab, patch)`, `reload()`.
- **Events:** `on(event, fn)` returns a function that stops listening. The events are:
  - `change`: tabs or the active tab changed.
  - `activate`: another tab became active.
  - `update`: a tab's data changed.
  - `close`: a tab is closing.
  - `drop`: a tab landed in this strip.
- **Remount:** `destroy()` removes the strip and every listener, so `mount` can be called again. A second `mount` on the same element without `destroy()` is refused.

`TaurisTabs.version` is the library version.

## Rust: `app.tabs()` and `Config`

`app.tabs()` works on the app, its handle, and any window:

- **Start:** `start()` (call once, in `setup`; a second call does nothing) and `restore()`.
- **Windows:** `new_window()` and `new_window_with(tab)`.
- **Open tabs:**
  - `new_tab()`
  - `open(tab)`
  - `open_or_focus(tab, |t| t.str("view") == Some("users"))`
  - `open_many(tabs, replace_active)`
- **Open in a window:** `open_in(label, tab)`.
- **Change tabs:**
  - `close_active()` (⌘W; in a window without tabs it closes the window)
  - `request_close_tab(id)` (asks the page)
  - `close_tab(id)` (at once)
  - `activate_tab(id)`
  - `update_tab(id, title, fields)`
  - `move_to_new_window(id)`
  - `move_to_window(id, label)` (into another open window, at the end of its strip; a window left with no tab closes)
- **Read:** `tab(id)`, `windows()` (every window with its tabs), `frontmost()`, `bring_up(label)`, `window_count()`.

Windows remember their place, size and whether they were maximized.

Menu in your own words: give your own `MenuItem` an id from `tauris_ui::menu_ids` (`NEW_TAB`, `NEW_WINDOW`, `CLOSE_TAB`, `CLOSE_WINDOW`). The plugin answers it like its own.

Calls that open windows return `tauri::Result`. A page can only change the tabs of its own window.

`Config::new()` then any of:

| Method | Default |
|---|---|
| `window(\|builder\| ...)` | Dress each window: title, background, anything Tauri's window builder offers. A size or place set here is where a new window opens; a remembered one comes back where it was. |
| `new_tab(\|app\| NewTab)` | `"New tab"`. Used by +, ⌘T and new windows. |
| `window_size(w, h)`, `min_window_size(w, h)` | 1180 × 760, 560 × 360 |
| `window_buttons_at(x, y)` | 16, 23: where the macOS window buttons sit in the strip. |
| `native_title_bar()` | Off. Puts the normal title bar back, with the strip below it. |
| `window_prefix("tabs-")` | Window names. The capability must cover them. |
| `window_url("index.html")` | The page each window loads. |
| `layout_file(\|app\| Some(path))` / `no_layout()` | `tabs.json` in the app's data folder. |
| `on_change(\|app, label\| ...)` | Called after anything about a window's tabs changes, from Rust or the page. It may use `app.tabs()`; its own changes don't call it again. Several changes to one window while its call waits on the worker make one call. |
| `drop_slack(above, below)`, `drag_opacity(0.2..1)` | 10, 16 px; 1.0 |
| `components(&[Component::Tabs, ...])` | All five. The page components the plugin puts in every page; leave out the ones the app does not use, so its pages load less (`Component::Files` brings the menus). The checker says when a page uses one left out. |

Set `TAURIS_UI_LOG=1` to print every window's tabs after each change.

The window's own title (Window menu, taskbar) follows the active tab.

Tauri ends the app when its last window closes. On macOS, to keep it running and bring the remembered windows back when the dock icon is clicked, keep it alive:

```rust
.build(tauri::generate_context!())
.expect("error while building the app")
.run(|_app, event| {
    if let tauri::RunEvent::ExitRequested { code: None, api, .. } = event {
        api.prevent_exit(); // the last window closed; ⌘Q still quits
    }
});
```

## The look

Set variables in your own CSS:

```css
:root {
  --tt-accent: #FFB800;     /* the bar on top of the active tab */
  --tt-active-bg: #171a23;  /* use your page's background */
  --tt-strip-bg: #0a0c11;
  --tt-fg: #9aa0ad;         /* a dark strip on a light system: its text colours too */
  --tt-fg-hover: #d4d8e0;
  --tt-fg-active: #f2f4f8;
  --tt-hover-bg: #1c2030;
  --tt-line: #2a2f3d;       /* the line under the strip */
  --tt-separator: #2a2f3d;  /* between idle tabs */
  --tt-tab-h: 34px;
  --tt-tab-w: 140px;
}
```

A strip darker (or lighter) than the system's mode gets its text colours from that mode unless you set them, as above; an app that is dark all through sets `data-tauris-theme="dark"` instead (see [One look](#one-look-for-every-component)).

Every variable is listed at the top of `web/tabs.css`. They cover:
- the strip
- tabs and the separators between them
- the active tab's curves
- the close and + buttons
- dragging
- the right-click menu

Any `.tt-*` class can be overridden too.

The library's rules sit in a cascade layer named `tauris-ui`, so plain CSS always wins over them. That includes a bare `div { ... }` or `span { ... }` rule, which reaches the parts of every component: keep such rules on your own classes. (Fields and buttons are protected from bare `input` and `button` rules.) If your CSS uses layers (Tailwind 4, shadcn), set the `--tt-*` variables and any `.tt-*` overrides **outside every `@layer` block**, as above. Inside a layer, which rule wins depends on the order the layers were first named, so do not count on it. Don't declare or reorder the `tauris-ui` layer yourself: Tailwind's reset would then strip the tabs' spacing.

## Tree view

The classic Qt / Windows tree, for the information density and precision it had, without the old look:
- rows 18 px high, indented 16 px per level, small system type
- tiny +/- boxes and dotted guide lines that join without a seam and stop at the last child
- aligned columns you can resize: drag the line between two headers (it shows under the mouse), or from the keyboard (Tab to a column's header: ← / → on one that does not sort, Alt+← / Alt+→ on one that does). The `resize` event gives the new widths, to keep them (`columns[i].width` at mount, or `setWidths`); `widths()` reads them.
- values you can edit in place: text, numbers, checkboxes, choices and colours
- light and dark mode

Only the rows in view are drawn, so thousands of rows stay fast. Open `test/tree_demo.html` in a browser to try it.

The tree view lives entirely in the page. An app that uses only the tree needs the dependency and `.plugin(tauris_ui::init(Config::new()))`, which delivers it. It needs no capability and no `start()`.

**Give the tree's element a height** (`height: 400px`, or `flex: 1` inside a parent that has one). Only the rows in view are drawn, and without a height there is no "in view": the element grows to hold every row. The console warns when that happens.

```js
const tree = TaurisTree.mount(document.getElementById("settings"), {
  label: "Settings",
  columns: [
    { label: "Setting", width: 220 },                        // the first column holds the tree
    { label: "Value", key: "value", width: 180, editable: true },
    { label: "Type", key: "type" },                          // the last column stretches
  ],
  data: [
    { id: "general", label: "General", expanded: true, children: [
      { id: "name", label: "Application name", values: { value: "Atlas", type: "String" } },
      { id: "login", label: "Open at login", values: { value: true, type: "Boolean" } },
      { id: "theme", label: "Theme", values: { value: "System", type: "Enum" },
        editor: { type: "select", options: ["System", "Light", "Dark"] } },
    ] },
  ],
});
tree.on("change", ({ node, column, value }) => console.log(node.id, column, value)); // save it in your app
```

**Sorting.** With `sortable: true` (or a first `sort`), a click on a column's header sorts by it, and a second click turns it round (▲ / ▼). Enter and Space do the same on a focused header.
- Rows sort among their siblings: groups stay groups, and children sort inside each group.
- Numbers sort as numbers. Text sorts as people read it ("Brian 49" before "Brian 169"). Empty values go last both ways.
- A column with `sortable: false` never sorts. `sortValue: node => ...` sorts by something other than the text shown (an ISO date behind "21 Oct 2026"), and `compare: (a, b) => ...` replaces the comparison.
- Selection and focus stay on their node. `setData` keeps the order. An edit does not move its row until the next sort or `setData`.
- `setData` keeps what the person did: a folder they closed stays closed, even after it left the list for a while, as in a search (`expanded: true` opens a node only the first time it comes), and an edit in progress goes on, on the new list's node (it is saved when the person finishes it; a field they have not touched shows the new value), unless its node is gone.

```js
const tree = TaurisTree.mount(el, {
  data, sort: saved ?? { key: "score", up: false },          // the first order; "label" is the first column
  columns: [
    { label: "Candidate", width: 220 },
    { label: "Score", key: "score", align: "right" },
    { label: "Added", key: "added", sortValue: n => n.values.addedIso },
    { label: "Notes", key: "notes", sortable: false },
  ],
});
tree.on("sort", order => remember(order));                   // { key, up }, or null for the data's own order
```

**A node** is `{ id, label, children?, icon?, values?, editor?, readOnly?, expanded? }`. Every node needs its own `id`; the console warns about repeats.
- `icon` is one of the built-in names (`folder`, `file`, `code`, `doc`, `data`, `image`, `package`, `lock`) or a name you add with the `icons` option. A folder icon opens when its row does.
- `editor` is `"text"`, `{ type: "number", min, max, step }`, `"checkbox"`, `{ type: "select", options }` or `"color"`, for every value of the node it fits (a checkbox only for true or false, and they only for a checkbox). `{ level: { type: "select", options } }` gives one per column, by key, and a column's own `editor` is the default for its values. Without one, the value's own type decides: booleans get a checkbox, numbers a number field, everything else text.

**Options:**

| Option | Default | What it does |
|---|---|---|
| `data` | `[]` | The nodes |
| `columns` | none | A plain tree, or `[{ label, width, key?, editable?, minWidth?, align?, className?, sortable?, sortValue?, compare? }]` (`align`: `"left"`, `"right"` or `"center"`) |
| `label` | `"Tree"` | The tree's accessible name |
| `lines` | `true` | The dotted guide lines |
| `icons` | none | More icons by name, as SVG markup |
| `overscan` | `8` | Rows drawn above and below the visible ones |
| `sortable` | on when `sort` is given | A click on a column header sorts by it |
| `sort` | none | The first order: `{ key, up }` |
| `multiple` | `false` | ⌘-click (Ctrl-click) and Shift-click select several rows; ⌘A selects every row shown |
| `styles` | `true` | Add the stylesheet |

**Keyboard** (as in Windows and Qt):
- Up and Down move. With `multiple`, Shift extends the selection, ⌘A selects every row shown, ⌘ (Ctrl) with the arrows moves the focus alone, and Space adds or takes out the row with the focus (a row with a checkbox value flips its checkbox instead).
- Right opens a row, or goes to its first child.
- Left closes a row, or goes to its parent.
- Home, End, PageUp and PageDown jump.
- `*` opens everything below.
- `+` and `-` open and close.
- Enter edits the row's first editable value (a checkbox takes the focus, for Space to flip it); on a row without one, it activates the row.
- F2 always edits.
- While editing: Tab and Shift+Tab save and go to the row's next or previous editable value (a checkbox takes the focus, and Space flips it); past the last one, back to the row. Enter saves, and Escape cancels.
- Typing a letter jumps to the next row starting with it.

**Events:** `select` (`{ node, nodes }`: the row with the focus, and every selected row), `toggle`, `change` (`{ node, column, value }`, already written into `node.values`), `activate`, `sort` (`{ key, up }`, or `null`), and `resize` (`{ column, index, width, widths }`: a column the person made wider or narrower).

**Methods:**
- `setData(nodes)`
- `expand(id)`, `collapse(id)`, `toggle(id)`, `expandAll()`, `collapseAll()`
- `select(id)` (an array selects several, with `multiple`), `selected()`, `selection()`, `selectAll()`, `get(id)`, `isExpanded(id)`, `widths()`, `setWidths(widths)`
- `edit(id, column?)`, `focus()`
- `sort(key, up?)` (`null`: the data's own order; in the order already in place it sorts again, moving rows edited since), `sorting()`
- `destroy()` (a value being typed is kept first: a `change`, as with `setData`)

Types are in `web/tree.d.ts`: copy it into a TypeScript app. `mount<{ ...your values }>` types your values.

**The look:** every size and colour is a `--tv-*` variable at the top of `web/tree.css`, with the same layer rules as the tabs (set them outside every `@layer` block). The default row height of 18 px keeps the dotted lines exact. With an odd row height, a dot can stop a pixel short of a box.

## Files

A place's shared files (a project's, a client's, a folder's) as a dense table:
- a type badge (PDF, IMG, DOC, XLS, PPT, ZIP, TXT…), the name (cut short with …), the size, the date added and who added it
- click a header to sort (▲ / ▼); the selected row in the accent colour
- Open, Save a copy…, Rename and Delete on the row under the mouse or selected, and on a right click
- a search field, and a header with the count and the total size
- **Add files…** opens the system's picker; files dropped on the window are added too, with a "Drop to add to …" ring round the list while they hover
- a card with a segmented bar while files are being added, an empty state, and a "no match" line
- renaming in place (the name without its extension selected), and a question before deleting
- several files at once, with `multiple: true`: ⌘-click, Shift-click, Shift+arrows and ⌘A select them; Enter opens them all, Delete deletes them all after one question
- light and dark mode

Open `test/files_demo.html` in a browser to try it with the menus below.

**The app keeps the files** (on its server, in a folder): the component shows them and hands every action to the app. Only the actions the app gives appear.

**Setup.** The page side comes with the plugin. Dropping files and the picker reach Tauri through `window.__TAURI__`, so `app.withGlobalTauri` must be true, and the window needs `core:default` (dropped files arrive as events) and `tauris-ui:default` (the picker) in a capability (the tab windows have both already). For the system's picker and save dialog, turn on the `files` feature and register the dialog plugin:

```toml
tauris-ui = { path = "../tauris-ui", version = "0.4", features = ["files"] }
tauri-plugin-dialog = "2"
```

```rust
tauri::Builder::default()
    .plugin(tauris_ui::init(tauris_ui::Config::new()))
    .plugin(tauri_plugin_dialog::init())
```

**In the page** (React; plain JavaScript is the same calls):

```tsx
import { invoke } from "@tauri-apps/api/core";
import { useEffect, useRef } from "react";

type Doc = TaurisFile & { project: string };

export default function Docs({ project, docs, say }: { project: { id: string; name: string; color: string }; docs: Doc[]; say: (text: string) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const view = useRef<TaurisFilesView<Doc> | null>(null);

  useEffect(() => {
    view.current = TaurisFiles.mount<Doc>(el.current!, {
      subtitle: "Documents",
      labels: { dropHint: "Up to 50 MB per file" },
      onOpen: doc => invoke("doc_open", { id: doc.id }),
      onSaveAs: doc => invoke<boolean>("doc_save_as", { id: doc.id, name: doc.name }),
      onRename: (doc, name) => invoke("doc_rename", { id: doc.id, name }),
      onDelete: doc => invoke("doc_delete", { id: doc.id }),
      onMessage: text => say(text),
    });
    return () => view.current?.destroy();
  }, []);

  // The app's list is the truth: hand it over whenever it changes, with what depends on it.
  useEffect(() => {
    view.current?.update({
      title: project.name,
      color: project.color,
      files: docs,
      onAdd: paths => invoke<Doc[]>("doc_add", { project: project.id, paths }),
    });
  }, [project, docs]);

  return <div ref={el} className="docs" />; // give it a height: the list scrolls inside
}
```

**In Rust**, the app's commands store and open the files. `tauris_ui::files` has the parts every app needs:

```rust
use tauris_ui::files;

#[tauri::command]
async fn doc_add(project: String, paths: Vec<String>) -> Result<Vec<Doc>, String> {
    let mut added = Vec::new();
    for path in paths {
        // A folder, a missing file or one over 50 MB comes back as a sentence the page shows:
        // "Contracts is a folder. Add files, not folders."
        let file = files::inspect(&path, Some(50 * 1024 * 1024))?;
        added.push(upload(&project, &file.path, &file.name, file.mime).await?);
    }
    Ok(added)
}

#[tauri::command]
async fn doc_open(app: tauri::AppHandle, id: String) -> Result<(), String> {
    let path = download_to_cache(&app, &id).await?; // a local copy, named with files::safe_name
    files::open_path(path)                           // the system's default app ("files" feature)
}

#[tauri::command]
async fn doc_save_as(app: tauri::AppHandle, id: String, name: String) -> Result<bool, String> {
    let Some(target) = files::save_dialog(&app, &format!("Save a copy of {name}"), &name).await? else {
        return Ok(false); // cancelled: the page says nothing
    };
    std::fs::write(target, download(&id).await?).map_err(|e| e.to_string())?;
    Ok(true)
}
```

- `inspect(path, max_bytes)` → `FileInfo { path, name, size, mime }`, or the sentence that says why not
- `mime_for(name)`, `safe_name(name)` (a name every system can create), `size_text(bytes)` ("2.4 MB", as the page shows it)
- with the `files` feature: `pick_files(&app, title)`, `save_dialog(&app, title, name)`, `open_path(path)` (which opens no folder and no file that is a program or runs one, such as `.command`, `.exe` or a shortcut: shared files come from other people)

The page can open the system's picker and save dialog (`TaurisFiles.pick`, `TaurisFiles.saveDialog`): they return only what the person chose. It cannot open a path with its default app: a page that could open any path could start any program, so the app opens the files it knows from its own command.

**Options:**

| Option | Default | What it does |
|---|---|---|
| `files` | `[]` | `[{ id, name, size?, added?, by?, type?, kind? }]`; your own fields stay on them |
| `title` | `"Files"` | The heading |
| `place` | the title | The place in "Drop to add to …" and "No files in … yet" |
| `subtitle` | none | A word before the count: "Documents · 3 files · 2.1 MB" (while a search hides some files, "Documents · 2 of 3 files" and their size; `labels.countShown` words it otherwise) |
| `color` | none | A colour chip before the heading |
| `columns` | all | Any of `kind`, `name`, `size`, `added`, `by`, in order |
| `sort` | `{ key: "name", up: true }` | The first order. A new column starts A to Z for names, biggest and newest first for sizes and dates. Names sort as in Finder: the name before its extension ("Q3 plan.md" before "Q3 plan 2.md"), numbers as numbers ("Item 2" before "Item 10") |
| `header`, `search` | `true` | The header row, and its search field (shown once there are files) |
| `multiple` | `false` | ⌘-click (Ctrl-click) and Shift-click select several files. Turn it on when the app's own actions (a File › Delete) use `selection()` |
| `dropArea` | `"window"` | Where a drop adds files: `"window"` (anywhere; with two components shown, a drop over one is that one's, and elsewhere the first mounted takes it), `"element"` (over the component only, where nothing is drawn over it) or `"none"` |
| `typeAheadMs` | `700` | How long after a key the next one still adds to the name being typed in the list (a miss says `labels.noneStarts`, as an `"error"` message) |
| `confirmDelete` | `true` | The component asks; `false`: the app asks in `onDelete` (and rejects with `""` when the person says no; its second argument `{ files, index }` lets it ask once for several, at index 0); a function `(file) => question`: its own question for one file (`null`, `false` or `""`: that file goes without a question). Several files at once are asked about with `labels.confirmDeleteMany` (`files => "Delete 3 files?"`) |
| `formatDate` | short | `(date, file) => text` for the Added column |
| `pick` | the system's | `(title) => Promise<paths>` behind Add files… |
| `labels` | English | Any word or sentence it shows (`web/files.d.ts` lists them), e.g. `{ add: "Ajouter…", dropHint: "Up to 50 MB per file" }` |
| `styles` | `true` | Add the stylesheet |

**The app's side**, each optional, each may return a Promise. A rejection's text is shown to the person; a rejection with an empty text is a quiet "cancelled" and shows nothing:
- `onAdd(paths)`: resolve with the new files; they are selected, flash once, and "Added 2 files to Health." is said
- `onOpen(file)`, `onSaveAs(file)` (resolve `false` when the person cancels), `onRename(file, name)`, `onDelete(file, { files, index })`
- `onSelect(file | null, files)`: the file with the focus, and every selected file. When several are deleted, `onDelete` is called for each, one after the other; the first refusal stops the rest
- `onMenuOpen({ label, how })`, `onMenuClose({ label, chosen })`: the row's menu opened and closed, as the menus' `onOpen` and `onClose` (for a sound)
- `onMessage(text, "info" | "ok" | "error")`: for the app's own status bar. Without it the component shows its messages under the list.

**Methods:** `setFiles(files)`, `files()` (the files as the component has them now), `update(options)`, `select(id)` (an array selects several), `selected()`, `selection()`, `selectAll()`, `add()` (as Add files…, for a File menu), `addPaths(paths)`, `open(id)`, `rename(id)`, `remove(id)`, `search(text)`, `dragDrop(event)` (to feed drag-and-drop events yourself), `busy(text)`, `message(text, kind)`, `focus()`, `focusSearch()`, `destroy()`. Helpers: `TaurisFiles.kindOf(file)`, `TaurisFiles.formatSize(bytes)`.

**Keyboard:** Up, Down, Home, End, PageUp and PageDown move (with `multiple: true`, Shift selects along the way, ⌘A selects every file, ⌘ (Ctrl) with the arrows moves the focus alone, and Space adds or takes out the file with the focus); a letter jumps to the next name starting with it. Enter opens the selected files, F2 renames the selected file (Enter saves, Escape cancels), Delete or ⌘⌫ deletes the selected files after the question (it starts on Cancel; Tab reaches Delete); they never act on a file that only has the focus. Shift+F10 opens the row's menu. Up from the first file reaches the column headers (they are not Tab stops, so Tab leaves the list at once): Left and Right go from header to header, Enter or Space sorts, Down or Escape goes back. In the search field, Down goes to the list and Escape empties it.

Types are in `web/files.d.ts`: copy it into a TypeScript app.

**The look:** every size and colour is a `--tf-*` variable at the top of `web/files.css` (set them outside every `@layer` block). An app with its own colour tokens maps them: `--tf-accent: var(--accent); --tf-bg: var(--field);`. `--tf-accent-ink` is the accent as text and lines (the drop zone, the sort arrow): unset, it is `--tf-accent` made readable on the list; set it to keep your own. The columns have fixed widths, so they stay put while searching: `--tf-size-w`, `--tf-added-w`, `--tf-by-w` and `--tf-acts-w` change them, and the name takes the rest. The defaults follow the system's light or dark mode; an app with its own light/dark switch sets the variables for each.

## Menus

An in-window menu bar, toolbar buttons with a ▾ that open a menu, and menus at a point (a right click), with the keyboard of a desktop app:
- Enter, Space or Down opens a menu; Up opens it at its last item
- Up, Down, Home and End move; a letter (or a few, quickly) jumps to an item
- Left and Right go from one menu of the bar to the next
- Enter or Space chooses; Escape closes and puts the focus back where it was
- shortcut hints, items that are off, ✓ items, colour chips and red items
- sub-menus: an item with `items` opens one to its right (Right, Enter, or the mouse resting on it); Left or Escape goes back

```js
const bar = TaurisMenu.bar(document.getElementById("menubar"), { menus: [
  { label: "File", items: () => [                       // a function: made each time the menu opens
    { label: "New project…", shortcut: "⌘N", action: newProject },
    { label: "Add files…", disabled: !current, action: () => files.add() },
    "-",
    { label: "Sign out", action: signOut },
  ] },
  { label: "View", items: () => [{ label: "Status bar", checked: showStatus, action: toggleStatus }] },
] });

// A toolbar button (any element; .tmn-tool is the toolbar look) that opens a menu under it.
TaurisMenu.button(document.getElementById("tb-docs"), {
  items: () => projects.map(p => ({ label: p.name, color: p.color, shortcut: String(p.docs), action: () => openDocs(p) })),
});

// A right-click menu.
row.addEventListener("contextmenu", e => {
  e.preventDefault();
  TaurisMenu.open([{ label: "Open", action: open }, "-", { label: "Delete", danger: true, action: remove }], { x: e.clientX, y: e.clientY });
});
```

In React, make the bar once (`useEffect(() => { const b = TaurisMenu.bar(nav.current!, { menus }); return () => b.destroy(); }, [])`) and give items as functions that read the app's current state, or call `bar.setMenus(menus)` when it changes (an open menu shows the new items at once). A menu with no items does not open. A menu closes when the page scrolls under it.

**An item** is `{ label, shortcut?, disabled?, checked?, color?, danger?, action?, items? }`, or `"-"` for a line (`items` makes a sub-menu: `{ label: "Open Recent", items: () => recent.map(...) }`); `null` and `false` are skipped. The action runs after the menu has closed and the focus is back where it was, so Edit › Copy acts on the field the person was in. Shortcuts are shown, not bound: the app binds its own keys.

**For a sound** (or anything else), `bar` and `button` take `onOpen({ label, how })` (`how` is `"mouse"` or `"keyboard"`) and `onClose({ label, chosen })`. `chosen` is true when an item was picked, false for Escape, a click outside, or the title or button again. Going from one menu of the bar to the next fires neither: the bar stays open.

```js
TaurisMenu.bar(nav, { menus, onOpen: () => sound.open(), onClose: ({ chosen }) => { if (!chosen) sound.close(); } });
```

**Options:** `bar(nav, { menus, label?, onOpen?, onClose? })` (`label`: the bar's name for screen readers, "Menu" by default); `button(element, { items, label?, caret?, gap?, onOpen?, onClose? })` (`caret: false` for no ▾, `gap`: pixels between the button and its menu); `TaurisMenu.open(items, { x, y }, { label?, keyboard?, returnTo?, onClose? })` (`keyboard: true` starts on the first item; `returnTo`: where the focus goes after).

**Methods:** `bar(...)` returns `setMenus`, `open(index)`, `close`, `focus`, `destroy`; `button(...)` returns `setItems`, `open`, `close`, `destroy`; `TaurisMenu.open(items, { x, y })` returns `close`; `TaurisMenu.close()` closes whichever is open. Closing a menu, by any of these or by a press elsewhere, puts the focus back where it was when the menu had it.

Types are in `web/menus.d.ts`. **The look:** `--tmn-*` variables at the top of `web/menus.css`. `.tmn-toolbar`, `.tmn-tool` (`aria-pressed="true"` for the current view: a neutral grey fill with its own edge, `--tmn-tool-on-bg` and `--tmn-tool-on-border`) and `.tmn-tool-sep` give a toolbar the same look; they are optional. The row is 34px with 26px buttons; put an `<svg>` (any `viewBox`, drawn as a 13px line icon in the text colour) before the label for an icon; `--tmn-toolbar-pad`, `--tmn-tool-pad`, `--tmn-tool-gap` and `--tmn-tool-icon` set the spacing and the icon's size.

## Sidebar

A side bar of sections beside the page, as in Mail or Finder. It collapses to a rail of icons (or away), and its edge resizes it.

```html
<body>
  <aside id="side"></aside>
  <main>…</main>
</body>
```

```css
body { display: flex; height: 100vh; margin: 0; }
main { flex: 1; min-width: 0; }
```

```js
const side = TaurisSidebar.mount(document.getElementById("side"), {
  title: "Mail",
  items: [
    { id: "inbox", label: "Inbox", icon: "📥", count: 12 },
    { id: "sent", label: "Sent", icon: "<svg viewBox='0 0 16 16'>…</svg>" },
    { heading: "Projects" },
    { id: "atlas", label: "Atlas", expanded: true, children: [{ id: "atlas-docs", label: "Documents" }] },
  ],
  selected: "inbox",
  storageKey: "my-app-sidebar",       // keeps its width and whether it is collapsed
  onSelect: item => show(item.id),
  onContextMenu: (item, { x, y }) => TaurisMenu.open(itemsFor(item), { x, y }),
});
```

Put it in a row with a height (`display: flex`): it sets its own width, and the main area takes the rest. An item is `{ id, label, icon?, count?, children?, expanded?, disabled?, title? }`, or `{ heading }` between sections. An icon is text (an emoji) or markup starting with `<` (an svg, drawn in the text colour); without one, its first letter stands for it in the rail. Groups nest to any depth.

- **Collapsing:** its button, ⌃⌘S on a Mac (its Show/Hide Sidebar; Ctrl+Shift+B elsewhere; `shortcut: false` for none), `toggle()`, or its edge dragged narrow. `collapse: "rail"` (default) leaves a 44px column of icons, each named by a tooltip, with a count as a dot (with no items, only `content`, a 32px strip with its button); choosing a group there opens the sidebar. `collapse: "hide"` leaves nothing: the app shows it again with `toggle()` or the shortcut.
- **Resizing:** drag its edge (between `minWidth` and `maxWidth`, 160 and 420 by default); dragged from the rail it opens; a double-click on the edge puts `width` back. From the keys, Tab reaches the edge: ← / → by 10px (⇧ by 50), Home and End, Enter collapses or opens.
- **Keyboard:** the list is one Tab stop (the selected item). ↑ ↓ Home End move; → opens a group, then goes into it; ← closes it, or goes to its parent; Enter or Space chooses; a letter jumps to the next item starting with it; the menu key or ⇧F10 calls `onContextMenu`.
- **Choosing:** a click chooses an item; a group's arrow, a double-click, or → opens it (`openOnSelect: true`: choosing it opens it too).

| Option | Default | |
|---|---|---|
| `items`, `selected` | `[]`, `null` | |
| `title` | none | A heading at its top; also the list's name for screen readers |
| `collapsed`, `collapse` | `false`, `"rail"` | `storageKey`, when it has a value kept, says instead of `collapsed` |
| `side` | `"left"` | `"right"`: the edge to drag is on its left |
| `width`, `minWidth`, `maxWidth` | 220, 160, 420 | |
| `storageKey` | none | Keeps the width and whether it is collapsed in the browser's storage |
| `openOnSelect`, `shortcut`, `typeAheadMs` | `false`, `true`, 700 | |
| `labels` | English | `{ label, hide, show, resize }` |
| `onSelect(item, { how })` | | The person chose an item (`select()` does not call it) |
| `onContextMenu(item, { x, y, how })` | | A right click or the menu key on an item; given, the browser's own menu does not open |
| `onToggle({ collapsed, how })`, `onResize({ width })` | | |

**Methods:** `setItems(items)` (the focus stays on the same item, open groups stay open), `select(id)` (opens the groups around it), `selected()`, `toggle(collapsed?)`, `collapsed`, `width`, `setWidth(px)`, `update(changes)`, `focus()`, `destroy()`.

Types are in `web/sidebar.d.ts`. **The look:** `--tsb-*` variables at the top of `web/sidebar.css` (its background is `--tauris-chrome`; the selected item is `--tauris-sel-bg` while the sidebar has the focus, `--tauris-sel-inactive` otherwise). `[data-tsb-state]` on the element says `"open"`, `"rail"` or `"hidden"`.

## Terminal

An optional look for an app or a part of one: amber on black, IBM Plex Mono at 12/18 px, square corners, 1 px gaps between panes. It changes nothing outside the element you mark as a terminal (`.tm`), and its stylesheet is added only when a page uses it. A page that brings its own passes `{ styles: false }` to `mount` (and to `commandLine`, `log` or `pane` made before it). Like the tree, it lives in the page: the plugin delivers it, and it needs no capability.

Most of it is CSS classes on your own markup. Every class is listed at the top of `web/terminal.css`; every colour and size is a `--tm-*` variable. Open `test/terminal_demo.html` in a browser to see every part.

| Part | Markup | Behaviour from `TaurisTerminal` |
|---|---|---|
| The screen | `.tm-screen`, panes in `.tm-panes` > `.tm-pane` | `mount(el)` marks the root and keeps every `[data-tm-clock]` and `[data-tm-date]` inside it current |
| Command line | an empty element | `commandLine(el, { prompt, onSubmit, onKey })`: prompt, block cursor, clock. Enter sends, Escape clears, Up and Down step through history. `onKey(event)` hears each key first: return true to take it (Up and Down through suggestions the app shows; mark the chosen `<tr>` with `aria-selected="true"`) |
| Title band | `.tm-band` on a pane | `pane(el)` returns `ok()`, `error()` and `reset()`, turning the band green, red or amber |
| Form | `.tm-form` > `.tm-form-line` with `.tm-label` and `input.tm-field`; `input.tm-check` draws `[X]` / `[ ]` | |
| Function keys | `.tm-key` (`.tm-go`, `.tm-cancel`, `.tm-yellow`), as `role="button"` | Enter and Space press a focused key. `aria-keyshortcuts="F8"` makes F8 press it from anywhere, and `aria-disabled="true"` turns it off |
| Table | `table.tm-table`, `.tm-num` for numbers, `meter.tm-bar` for a segmented bar | |
| Message log | an empty list | `log(el)` returns `add(text, "ok" \| "warn" \| "error")` and `clear()`, with timestamps, a flash on new rows and auto-scroll. It keeps the newest 500 rows (`log(el, { max })`), and someone reading further up keeps their place. It is `role="log"`, and text is added as text only |
| Legend | `.tm-legend` along the bottom | |
| Text colours | `.tm-ok`, `.tm-warn`, `.tm-error`, `.tm-off`, `.tm-value`, `.tm-dim` | |

```tsx
import { useEffect, useRef } from "react";

export default function Desk() {
  const root = useRef<HTMLDivElement>(null);
  const line = useRef<HTMLDivElement>(null);
  const messages = useRef<HTMLOListElement>(null);
  const pane = useRef<HTMLElement>(null);
  const log = useRef<TaurisTerminalLog | null>(null);

  useEffect(() => {
    const term = TaurisTerminal.mount(root.current!);
    log.current = TaurisTerminal.log(messages.current!);
    const band = TaurisTerminal.pane(pane.current!);
    const cmd = TaurisTerminal.commandLine(line.current!, {
      prompt: "ATLAS>",
      onSubmit: command => { log.current!.add(`RUN ${command}`, "ok"); band.ok(); },
    });
    return () => { cmd.destroy(); term.destroy(); };
  }, []);

  return (
    <div ref={root} className="tm tm-screen">
      <div ref={line} />
      <div className="tm-panes">
        <section ref={pane} className="tm-pane">
          <h2 className="tm-band"><span>MESSAGES</span><span data-tm-clock /></h2>
          <ol ref={messages} />
        </section>
      </div>
      <footer className="tm-legend">
        <span className="tm-key tm-yellow" role="button" tabIndex={0} aria-keyshortcuts="F9"
              onClick={() => log.current?.clear()}>CLR LOG</span>
        <span>= F9</span>
      </footer>
    </div>
  );
}
```

Types are in `web/terminal.d.ts`: copy it into a TypeScript app.

**The font:** under a strict content policy an app cannot load IBM Plex Mono from the web, and the look falls back to the system's monospace. To bundle the font, see the header of `web/terminal.js` (for example `@fontsource/ibm-plex-mono`).

## Tests

The page suites need Python 3.11+, Playwright, Pillow and Google Chrome.

```
cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test   # the model, the windows on Tauri's test runtime, saving, the command lists
cargo clippy --all-targets --features files -- -D warnings && cargo test --features files   # the Rust side of the files component
python test/run.py [shots-dir]             # the tabs page side, in headless Chrome, nothing on screen
python test/tree_run.py [shots-dir]        # the tree view, including the pixels of its lines and boxes
python test/terminal_run.py [shots-dir]    # the terminal, including its gaps and bars by pixel
python test/files_run.py [shots-dir]       # the files component, with drops and the picker stood in for
python test/menus_run.py [shots-dir]       # the menus, mouse and keyboard
python test/sidebar_run.py [shots-dir]     # the sidebar: collapsing, the edge, the keys
python test/all_run.py [shots-dir]         # examples/all: every component in one app
python test/doctor_run.py                  # the checker, on small apps set up right and wrong
(cd examples/basic/src-tauri && cargo clippy -- -D warnings && cargo build) && python scripts/doctor.py examples/basic
(cd examples/all/src-tauri && cargo clippy -- -D warnings && cargo build) && python scripts/doctor.py examples/all
(cd test/freeze_check && cargo run)        # macOS: a real app (it opens windows and takes the focus; CI runs it at every push)
rm -f Cargo.lock && export CARGO_RESOLVER_INCOMPATIBLE_RUST_VERSIONS=fallback && cargo +1.90 build && cargo +1.90 build --features files   # the oldest Rust, as CI
rustup target add x86_64-pc-windows-msvc && cargo clippy --all-targets --features files --target x86_64-pc-windows-msvc -- -D warnings   # Windows's code, from a Mac
TAURIS_TEST_WEBKIT=1 python test/run.py    # any page suite in WebKit (python -m playwright install webkit first)
```

## Limits

- Dragging a tab out of its window, and between windows, follows the real mouse. That needs macOS, and it is checked by hand, not by tests. On every system, "Move to new window" in a tab's menu does the same without dragging.
- The close button sits inside its tab, as in browsers. Screen readers reach it through the tab's menu (Shift+F10) and Delete.
- The page tests run in Chrome here. CI runs them in the Chromium and the WebKit that come with its pinned Playwright, the same browsers every day (`TAURIS_TEST_CHROMIUM=1` or `TAURIS_TEST_WEBKIT=1` does that here too): Tauri uses WebKit on macOS and Linux, and WebView2 (Chromium) on Windows. Windows's high-contrast colours and an input method's composing are tested in Chromium only, which is where they can be driven.
- The tree's choice and colour editors open the system's own pop-ups, which headless tests cannot show; they are checked through their elements.
- The system's file picker and save dialog cannot be shown by a test either. The page tests stand in for them; Rust checks that a page is told what is missing (the feature, the dialog plugin).
- A window opened inside Tauri's plugin lock (the plugin's event handler: the Dock click, ⌘N; its page commands; an `on_change` hook called from either) freezes only the real event loop. `test/freeze_check` does each of them in a real app on macOS, and closes a window's last tab by ⌘W and from the page; CI runs it on every push (run by hand, it opens windows and takes the focus). A change the app makes from its own code reaches `on_change` at once (unless earlier calls are still waiting, or the hook is running on another thread: then it waits its turn, on the worker); one made inside that lock, by an async page command, or by ⌘N, ⌘T or the Dock click, reaches it a moment later on a worker thread, so the hook may open windows. A quitting app waits for it (half a second at most; it cannot open windows then, and a hook that waits for the main thread then does not finish). Other plugins' callbacks (deep-link's `on_open_url`, for one) can run inside that same lock: there, call `app.tabs()` from a thread of your own (`std::thread::spawn`), or a window that opens freezes the app.
- A dropped folder cannot be told from a file in the page. The app refuses it where it reads the paths (`tauris_ui::files::inspect` says why), and the component shows that sentence.

## Contributing

See `CONTRIBUTING.md`. AI agents: see `AGENTS.md`.

## License

MIT
