# tauris-ui

UI components for Tauri 2 desktop apps. One library for every app.

| Component | In the page | What it is |
|---|---|---|
| [Tabs](#tabs) | `TaurisTabs.mount(strip)` | Browser-style tabs that can leave their window and come back, remembered between runs |
| [Tree view](#tree-view) | `TaurisTree.mount(element, { data })` | A dense tree and configuration editor: compact rows, dotted guide lines, aligned columns, in-place editing |

The plugin delivers every component's script and stylesheet to every page. A component's stylesheet is added only when a page mounts it, so a component you don't use changes nothing.

## Tabs

- Drag a tab to reorder it.
- Drag it out of the strip: it becomes its own window, under the mouse (macOS).
- Drop it on another window's strip to move it there (macOS).
- Right click: New tab, Close tab, Close other tabs, Close tabs to the right, Move to new window.
- ⌘T, ⌘N, ⌘W and ⇧⌘W, through a ready-made menu.
- Keyboard: arrows, Home, End, Delete, Shift+F10 for the menu, ^Tab to step. Keys typed into a field inside a tab stay in the field.
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
| `labels` | English, ⌘ or Ctrl+ by system | `{ tabs, newTab, newTabHint, closeTab, closeOthers, closeRight, moveToWindow, newTabShortcut, closeTabShortcut }` |
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
- **Read:** `tab(id)`, `windows()` (every window with its tabs), `frontmost()`, `bring_up(label)`, `window_count()`.

Windows remember their place, size and whether they were maximized.

Menu in your own words: give your own `MenuItem` an id from `tauris_ui::menu_ids` (`NEW_TAB`, `NEW_WINDOW`, `CLOSE_TAB`, `CLOSE_WINDOW`). The plugin answers it like its own.

Calls that open windows return `tauri::Result`. A page can only change the tabs of its own window.

`Config::new()` then any of:

| Method | Default |
|---|---|
| `window(\|builder\| ...)` | Dress each window: title, background, anything Tauri's window builder offers. |
| `new_tab(\|app\| NewTab)` | `"New tab"`. Used by +, ⌘T and new windows. |
| `window_size(w, h)`, `min_window_size(w, h)` | 1180 × 760, 560 × 360 |
| `window_buttons_at(x, y)` | 16, 23: where the macOS window buttons sit in the strip. |
| `native_title_bar()` | Off. Puts the normal title bar back, with the strip below it. |
| `window_prefix("tabs-")` | Window names. The capability must cover them. |
| `window_url("index.html")` | The page each window loads. |
| `layout_file(\|app\| Some(path))` / `no_layout()` | `tabs.json` in the app's data folder. |
| `on_change(\|app, label\| ...)` | Called after anything about a window's tabs changes, from Rust or the page. It may use `app.tabs()`; its own changes don't call it again. |
| `drop_slack(above, below)`, `drag_opacity(0.2..1)` | 10, 16 px; 1.0 |

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
  --tt-tab-h: 34px;
  --tt-tab-w: 140px;
}
```

Every variable is listed at the top of `web/tabs.css`. They cover:
- the strip
- tabs and the separators between them
- the active tab's curves
- the close and + buttons
- dragging
- the right-click menu

Any `.tt-*` class can be overridden too.

The library's rules sit in a cascade layer named `tauris-ui`, so plain CSS always wins over them. If your CSS uses layers (Tailwind 4, shadcn), set the `--tt-*` variables and any `.tt-*` overrides **outside every `@layer` block**, as above. Inside any layer, the library's defaults win. Don't declare or reorder the `tauris-ui` layer yourself: Tailwind's reset would then strip the tabs' spacing.

## Tree view

The classic Qt / Windows tree, for the information density and precision it had, without the old look:
- rows 18 px high, indented 16 px per level, small system type
- tiny +/- boxes and dotted guide lines that join without a seam and stop at the last child
- aligned columns you can resize
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

**A node** is `{ id, label, children?, icon?, values?, editor?, readOnly?, expanded? }`. Every node needs its own `id`; the console warns about repeats.
- `icon` is one of the built-in names (`folder`, `file`, `code`, `doc`, `data`, `image`, `package`, `lock`) or a name you add with the `icons` option. A folder icon opens when its row does.
- `editor` is `"text"`, `{ type: "number", min, max, step }`, `"checkbox"`, `{ type: "select", options }` or `"color"`. Without one, the value's own type decides: booleans get a checkbox, numbers a number field, everything else text.

**Options:**

| Option | Default | What it does |
|---|---|---|
| `data` | `[]` | The nodes |
| `columns` | none | A plain tree, or `[{ label, width, key?, editable?, minWidth?, align?, className? }]` (`align`: `"left"`, `"right"` or `"center"`) |
| `label` | `"Tree"` | The tree's accessible name |
| `lines` | `true` | The dotted guide lines |
| `icons` | none | More icons by name, as SVG markup |
| `overscan` | `8` | Rows drawn above and below the visible ones |
| `styles` | `true` | Add the stylesheet |

**Keyboard** (as in Windows and Qt):
- Up and Down move.
- Right opens a row, or goes to its first child.
- Left closes a row, or goes to its parent.
- Home, End, PageUp and PageDown jump.
- `*` opens everything below.
- `+` and `-` open and close.
- Enter edits the row's first editable value; on a row without one, it activates the row.
- F2 always edits.
- While editing: Tab and Shift+Tab save and go to the row's next or previous editable value. Enter saves, and Escape cancels.
- Typing a letter jumps to the next row starting with it.

**Events:** `select`, `toggle`, `change` (`{ node, column, value }`, already written into `node.values`) and `activate`.

**Methods:**
- `setData(nodes)`
- `expand(id)`, `collapse(id)`, `toggle(id)`, `expandAll()`, `collapseAll()`
- `select(id)`, `selected()`, `get(id)`, `isExpanded(id)`
- `edit(id, column?)`, `focus()`
- `destroy()`

Types are in `web/tree.d.ts`: copy it into a TypeScript app. `mount<{ ...your values }>` types your values.

**The look:** every size and colour is a `--tv-*` variable at the top of `web/tree.css`, with the same layer rules as the tabs (set them outside every `@layer` block). The default row height of 18 px keeps the dotted lines exact. With an odd row height, a dot can stop a pixel short of a box.

## Tests

```
cargo fmt --check && cargo clippy --all-targets && cargo test   # the model, the windows on Tauri's test runtime, saving, the command lists
python test/run.py [shots-dir]             # the tabs page side: 101 checks in headless Chrome, nothing on screen
python test/tree_run.py [shots-dir]        # the tree view: 97 checks, including the pixels of its lines and boxes
cd examples/basic/src-tauri && cargo build
```

## Limits

- Dragging a tab out of its window, and between windows, follows the real mouse. That needs macOS, and it is checked by hand, not by tests. On every system, "Move to new window" in a tab's menu does the same without dragging.
- The close button sits inside its tab, as in browsers. Screen readers reach it through the tab's menu (Shift+F10) and Delete.
- The page tests run in Chrome. Tauri on macOS uses WebKit; the tabs suite has also been run in WebKit.
- The tree's choice and colour editors open the system's own pop-ups, which headless tests cannot show; they are checked through their elements.

## Contributing

See `CONTRIBUTING.md`. AI agents: see `AGENTS.md`.

## License

MIT
