# What goes in tauris-ui, and what stays in an app

Agreed on 2026-10-22 between tauris-ui and the apps that use it (MLPC, MHive).

## The rules

1. tauris-ui holds what any desktop app needs and knows nothing of an app's data or trade.
2. Everything new is an option whose default changes nothing.
3. The look is set through variables (`--tt-*`, `--tv-*`, …). No app restyles a library class.
4. Words are options too: labels, with English defaults.
5. The library calls hooks at the key moments (pick, move, refuse, cancel, open). It never plays a sound, a reward or a brand animation itself. Its own motion is set through variables.
6. It behaves like a desktop app: a click selects, a double click or the +/- box opens, and the keys work everywhere.

## In tauris-ui

- **Tabs**, and each tab's Back/Forward history (`history` option, `visit`, `back`, `forward`).
- **Menus**, and the toolbar (`TaurisMenu.toolbar`): Back, Forward and Find. The pressed button is the app's `aria-pressed`.
- **Sidebar**: one level of places. A tree goes in a `TaurisTree` passed as `content`. Collapsed, the strip can show the tree's projects (`railItems`), each its icon or its letter.
- **Tree**:
  - a right-click hook, and `how` on select;
  - `fit` and `header: false`;
  - cell tones, a drop ring and `nodeAt`;
  - ⌘-click and ⌘↩ to open the other way.
- **Table**:
  - sorting, groups (that can open and close), and type-to-select;
  - row buttons (off with a reason), editing in place, and a checkbox column;
  - row classes, short text when a column is narrow, and widths kept;
  - loading and error states, several rows selected, and ⌘C as text.
- **Dialogs**:
  - questions, forms, reviews and sheets, in the page or in their own window;
  - app fields (`defineField`), and inputs on one line;
  - forms that open refused;
  - `close()`.
- **Finder**: the panel, matching, groups and recents.
- **Status bar**, **Glance** (sparkline, status, capacity), **Reorder**, **Files**, **Terminal**.
- `native_feel`, opt-in.
- **Releases**: every release is tagged. A change that needs app edits moves the series (0.5.0), and the release note says what to change. The checker (`scripts/doctor.py`) catches what it can.

## Later

- A `key:value` filter syntax in the finder and the table, when an app moves its search to them.

## Not in tauris-ui

- **No.** A group name that opens on a click: a click selects, a double click opens.
- **No.** A cell spanning two columns.
- **No.** An app's own Settings window as a library dialog.

## Stays in each app

- Data, API calls, Rust commands, the store and caching.
- Its own views and words, and what each row opens.
- Data safety: undo, journals, re-reading before saving.
- Filter keys and what the search indexes.
- Brand: colours, fonts, logo, sounds, rewards, set through the variables and hooks.
- Notifications and Dock badges.
