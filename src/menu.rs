// Menu items for the tabs. The plugin answers them itself: put them in your
// menu and ⌘T, ⌘N, ⌘W and ⇧⌘W work with no other code.

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Runtime};

/// The ids the plugin answers. Give your own `MenuItem` one of these ids (with
/// your own words and shortcut) and the plugin does the rest.
pub const NEW_TAB: &str = "tauris-ui:new-tab";
/// See [`NEW_TAB`].
pub const NEW_WINDOW: &str = "tauris-ui:new-window";
/// See [`NEW_TAB`].
pub const CLOSE_TAB: &str = "tauris-ui:close-tab";
/// See [`NEW_TAB`].
pub const CLOSE_WINDOW: &str = "tauris-ui:close-window";

/// A "File" menu: New Tab (⌘T), New Window (⌘N), Close Tab (⌘W; in a window
/// without tabs it closes the window) and Close Window (⇧⌘W).
pub fn file_menu<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<Submenu<R>> {
    Submenu::with_items(
        app,
        "File",
        true,
        &[
            &MenuItem::with_id(app, NEW_TAB, "New Tab", true, Some("CmdOrCtrl+T"))?,
            &MenuItem::with_id(app, NEW_WINDOW, "New Window", true, Some("CmdOrCtrl+N"))?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItem::with_id(app, CLOSE_TAB, "Close Tab", true, Some("CmdOrCtrl+W"))?,
            &MenuItem::with_id(app, CLOSE_WINDOW, "Close Window", true, Some("CmdOrCtrl+Shift+W"))?,
        ],
    )
}

/// A whole menu bar for an app of tabs: the app menu (about, hide, quit),
/// File (see `file_menu`), Edit (undo, cut, copy, paste, select all, so text
/// fields keep working) and Window. Set it with `app.set_menu(...)`.
pub fn default_menu<R: Runtime>(app: &AppHandle<R>, app_name: &str) -> tauri::Result<Menu<R>> {
    let app_menu = Submenu::with_items(
        app,
        app_name,
        true,
        &[
            &PredefinedMenuItem::about(app, None, None)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::hide(app, None)?,
            &PredefinedMenuItem::hide_others(app, None)?,
            &PredefinedMenuItem::show_all(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::quit(app, None)?,
        ],
    )?;
    let edit = Submenu::with_items(
        app,
        "Edit",
        true,
        &[
            &PredefinedMenuItem::undo(app, None)?,
            &PredefinedMenuItem::redo(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::cut(app, None)?,
            &PredefinedMenuItem::copy(app, None)?,
            &PredefinedMenuItem::paste(app, None)?,
            &PredefinedMenuItem::select_all(app, None)?,
        ],
    )?;
    let window = Submenu::with_items(
        app,
        "Window",
        true,
        &[&PredefinedMenuItem::minimize(app, None)?, &PredefinedMenuItem::maximize(app, None)?],
    )?;
    Menu::with_items(app, &[&app_menu, &file_menu(app)?, &edit, &window])
}
