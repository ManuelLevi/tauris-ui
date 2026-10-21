// The smallest app of tabs: each tab holds a note. Run it with `cargo run`
// from this folder.

use tauris_ui::{Config, NewTab, TabsExt};

fn main() {
    let tabs = Config::new()
        .window_size(960.0, 640.0)
        .window(|w| w.title("Tabs Example"))
        // A tab is { id, title, ...your fields }: here, a note.
        .new_tab(|_| NewTab::new("New note").with("note", ""));

    tauri::Builder::default()
        .plugin(tauris_ui::init(tabs))
        .setup(|app| {
            // File menu with ⌘T, ⌘N and ⌘W, answered by the plugin.
            app.set_menu(tauris_ui::default_menu(app.handle(), "Tabs Example")?)?;
            // Opens the windows from last time, or one new window.
            app.tabs().start()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running the example");
}
