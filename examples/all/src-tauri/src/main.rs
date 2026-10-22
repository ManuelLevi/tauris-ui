// Every component of tauris-ui in one app: tabs, a sidebar holding a tree,
// the files table, in-window menus and the terminal look. Run it with
// `cargo run` from this folder. The projects and files are sample data in the
// page: nothing is saved but the tabs.

// A release build on Windows opens no console window beside the app's own.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauris_ui::files::{self, FileInfo};
use tauris_ui::{Config, NewTab, TabsExt};

/// What "Add files…" and a drop hand the page: each path checked, so a folder
/// or a missing file comes back as a sentence the table shows.
#[tauri::command]
fn inspect(paths: Vec<String>) -> Result<Vec<FileInfo>, String> {
    paths.iter().map(|path| files::inspect(path, Some(50 * 1024 * 1024))).collect()
}

fn main() {
    let tabs = Config::new()
        .window_size(1100.0, 720.0)
        .window(|w| w.title("All Components"))
        // A tab is { id, title, ...your fields }: here, what it shows.
        .new_tab(|_| NewTab::new("Project A").with("kind", "project").with("ref", "project-a"));

    tauri::Builder::default()
        .plugin(tauris_ui::init(tabs))
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![inspect])
        .setup(|app| {
            app.set_menu(tauris_ui::default_menu(app.handle(), "All Components")?)?;
            app.tabs().start()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running the example");
}
