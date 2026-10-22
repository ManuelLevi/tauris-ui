Read AGENTS.md first: it says how to use this library in an app and the rules for changing it. `<library>` in it is this folder.

# MUST NOT

We MUST NOT COPY the mobile first sheep.

Examples:

* Threeview:
  * if i click on text, obviously I'm interested in the element itself, not in expanding it.
  * if I want to expand obviously I have two options:
    * double click the element
    * or press the "+" before the icon

# Example App

Example app must use all components of tauris-ui, no exception.

It lives in `examples/all` (`test/all_run.py` tests its page). The plugin delivers every component to the page (`Config::new()` has all ten). All data is the sample below, kept in the page: nothing is saved but the tabs.

| Component | Where the app uses it |
| --- | --- |
| Sidebar (`TaurisSidebar`) | The collapsible left column |
| Tree view (`TaurisTree`) | The teams, projects and files, inside the sidebar |
| Tabs (`TaurisTabs`) | "Open in new tab": a tab per opened file |
| Files (`TaurisFiles`) | The table of the selected project's files |
| Menus (`TaurisMenu`) | Menu bar, right-click menus, a toolbar |
| Terminal (`TaurisTerminal`) | The search line |
| Finder (`TaurisFinder`) | ⌘K: find any team, project or file |
| Dialogs (`TaurisDialog`) | Edit (a form, with a review) and Delete (a question) on a file; Help › Keyboard Shortcuts (⌘/) and About |
| Reorder (`TaurisReorder`) | Home: the projects' rows dragged into the person's order, ⌥⌘↑ ⌥⌘↓, and Move Up / Move Down in a row's menu |
| Glance (`TaurisGlance`) | Home: each project's activity (a sparkline) and status (Growing, Slowing), and the files' capacity bar |

## Collapsable Sidebar + Treeview (2 components)

Sidebar contains the treeview:

```
* Team A:
  * Project A:
    * Hello.md     45kb
    * Sup.txt      5kb
* Team B:
  * Megalomania:
    * readme.md.   2kb
* Team C:
  * Vacation Mexico:
    * places to visit.md 1kb
```

User can right click any file and click "Open" "Open in new tab" "Edit" "Delete" etc. (edit and delete do nothing)

* Sidebar: `TaurisSidebar.mount`, its head the product's logo (`image`, `ui/logo.svg`) and name (`title`, "All Components"), with `storageKey` so its width and collapsed state are kept; ⌃⌘S (Ctrl+Shift+B), its button or View › Hide Sidebar collapses it to a rail.
* Tree: `TaurisTree.mount` with two columns, Name and Size (aligned); teams and projects are groups, files are leaves. Its element is the sidebar's `content`.
* The tree leaves the right click to the app: the app listens for `contextmenu` on a file and calls `TaurisMenu.open` with Open, Open in new tab, Edit, Delete (a separator before Delete, which is `danger`).
* A click on a project shows its files in the Files table (in the current tab); Enter or a double click on a file opens it.

## Tabs

* `TaurisTabs.mount` on a strip above the page; one page serves the window and shows what the active tab says.
* Open shows the file in the current tab; "Open in new tab" adds a tab named after the file. A tab can be dragged out into its own window; the layout is remembered between runs.

## Files

* `TaurisFiles.mount` in the main area: the selected project's files (type badge, name, size, date added, who added it), sortable, with search and drag and drop.
* Add files… (the picker, `files` feature plus the dialog plugin) adds to the project in memory. The table's row menu appears for the actions the app gives: `onOpen` opens the file like the tree's Open; `onRename` and `onDelete` do nothing and say so, like the tree's Edit and Delete.

## Menus

* Menu bar (`TaurisMenu.bar`): File (Add files… calls the Files table's `add()`), View (Show/Hide Sidebar calls `toggle()`; Search, ⌘K), Help.
* Right-click menus: on a tree file (`TaurisMenu.open`, above); the Files table's row menu is its own.
* A toolbar (`.tmn-toolbar` with `.tmn-tool` buttons, an icon on each): Home, and one button per team that opens a menu of its projects (`TaurisMenu.button`); the button of the shown project's team is the pressed one.

## Home

* The toolbar's Home shows Home in the current tab: the projects in a table (name, team, files, activity, status), in the order the person puts them in, and above it the files' capacity bar ("Files 5 / 12", a segment each, in its project's colour).
* `TaurisReorder.attach` on the table's scroll box: a row dragged to another place, or ⌥⌘↑ ⌥⌘↓ on the selected one, moves it; the status line says where it went. The order is kept in the page.
* `TaurisGlance.sparkline` draws each project's edits a week (the last six, in `data.js`), `TaurisGlance.status` its trend (the last three weeks against the three before), `TaurisGlance.capacity` the files against the sample's limit (`MAX_FILES`).
* A click selects a project, ↑ ↓ move, Enter or a double click opens it; its right-click menu is the tree's Open and Open in new tab, then Move Up and Move Down.

## Terminal/Search

User can write "mexico" and sees autocomplete ( 1) vacation mexico; 2) places to visit.md )

* `TaurisTerminal.mount` on the screen; `commandLine` with the prompt `SEARCH>`. The app listens to the line's `input` event (the library only gives `onSubmit`) and lists the matching projects and files, numbered, in a `.tm-table` below. A match is by place and name, so "mexico" finds the project and its file; `pane(...).ok()` turns the band green, `.error()` red when nothing matches.
* Enter opens the first match like "Open" does; "mexico 2", or a number alone, then Enter, opens that one. Escape clears the line. ⌘K goes to it.

## Data

Example app is mock data only - read only too.
