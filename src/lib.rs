//! UI components for Tauri 2 desktop apps: browser-style tabs, a dense tree
//! view / configuration editor, and an optional terminal look.
//!
//! The plugin injects each component's page script and stylesheet into every
//! page; a component's stylesheet is added only when a page mounts it.
//!
//! - **Tabs** (`TaurisTabs.mount(...)` in the page, `app.tabs()` in Rust): Rust
//!   owns every window's tabs. A tab can be reordered, dragged out into a window
//!   of its own, or dropped onto another window's strip (macOS). The windows and
//!   their tabs are remembered between runs.
//! - **Tree view** (`TaurisTree.mount(...)` in the page): compact rows, dotted
//!   connector lines, +/- boxes, aligned columns and in-place editors. It lives
//!   entirely in the page.
//! - **Terminal** (`TaurisTerminal.mount(...)` in the page): an optional
//!   Bloomberg-style look (amber on black, monospace, dense tables, function
//!   keys, a command line and a message log). It lives entirely in the page.
//!
//! ```ignore
//! use tauris_ui::{Config, NewTab, TabsExt};
//!
//! tauri::Builder::default()
//!     .plugin(tauris_ui::init(Config::new().new_tab(|_| NewTab::new("Home"))))
//!     .setup(|app| {
//!         app.set_menu(tauris_ui::default_menu(app.handle(), "My app")?)?;
//!         app.tabs().start()?;
//!         Ok(())
//!     })
//!     .run(tauri::generate_context!())
//!     .expect("error while running the app");
//! ```
//!
//! Desktop only (macOS, Windows, Linux); dragging a tab out of its window
//! needs macOS. The window capability must include `"tauris-ui:default"` and cover the
//! tab windows (`"windows": ["tabs-*"]`), and `app.withGlobalTauri` must be true.
//! See README.md.

mod commands;
mod config;
mod drag;
mod menu;
mod model;
mod persist;
mod platform;
#[cfg(test)]
mod runtime_tests;
mod windows;

pub use config::Config;
pub use menu::{default_menu, file_menu};

/// Menu item ids the plugin answers, for a menu in your own words:
/// `MenuItem::with_id(app, tauris_ui::menu_ids::NEW_TAB, "Nouvel onglet", true, Some("CmdOrCtrl+T"))`.
pub mod menu_ids {
    pub use crate::menu::{CLOSE_TAB, CLOSE_WINDOW, NEW_TAB, NEW_WINDOW};
}
pub use model::{Fields, NewTab, Tab};
pub use windows::WindowTabs;

use tauri::plugin::{Builder, TauriPlugin};
use tauri::webview::PageLoadEvent;
use tauri::{AppHandle, Manager, RunEvent, Runtime, WindowEvent};

/// The library's version; pages see it as `TaurisTabs.version`.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

const SCRIPT: &str = include_str!("../web/tabs.js");
const STYLE: &str = include_str!("../web/tabs.css");
const TREE_SCRIPT: &str = include_str!("../web/tree.js");
const TREE_STYLE: &str = include_str!("../web/tree.css");
const TERMINAL_SCRIPT: &str = include_str!("../web/terminal.js");
const TERMINAL_STYLE: &str = include_str!("../web/terminal.css");

// The page scripts carry their stylesheets and the version, so one crate
// delivers everything. Each component adds its stylesheet only when a page
// mounts it. The strip's left inset follows where the window buttons are.
fn page_script<R: Runtime>(config: &Config<R>) -> String {
    let inset = match config.traffic_lights {
        Some((x, _)) if cfg!(target_os = "macos") => x + 68.0,
        _ => 8.0,
    };
    let style = format!("{STYLE}\n@layer tauris-ui {{ :root {{ --tt-inset-left: {inset}px; }} }}\n");
    let tabs = SCRIPT
        .replace("\"__TAURIS_TABS_CSS__\"", &serde_json::to_string(&style).unwrap_or_default())
        .replace("__TAURIS_TABS_VERSION__", VERSION)
        .replace("\"__TAURIS_TABS_CAN_DRAG_OUT__\"", if platform::CAN_DRAG_OUT { "true" } else { "false" });
    let tree = TREE_SCRIPT.replace("\"__TAURIS_TREE_CSS__\"", &serde_json::to_string(TREE_STYLE).unwrap_or_default());
    let terminal = TERMINAL_SCRIPT
        .replace("\"__TAURIS_TERMINAL_CSS__\"", &serde_json::to_string(TERMINAL_STYLE).unwrap_or_default());
    format!("{tabs}\n;\n{tree}\n;\n{terminal}")
}

/// The plugin. Register it with `.plugin(tauris_ui::init(config))`.
pub fn init<R: Runtime>(config: Config<R>) -> TauriPlugin<R> {
    let script = page_script(&config);
    Builder::<R>::new("tauris-ui")
        .invoke_handler(tauri::generate_handler![
            commands::window_state,
            commands::new_tab,
            commands::open_tab,
            commands::close_tab,
            commands::activate_tab,
            commands::move_tab,
            commands::update_tab,
            commands::report_strip,
            commands::drag_out,
            commands::set_close_guard,
            commands::close_window,
            commands::move_to_new_window,
            commands::close_asked,
        ])
        .js_init_script(script)
        // A page that (re)loads has not mounted the strip yet: nothing to ask.
        .on_page_load(|webview, payload| {
            if payload.event() == PageLoadEvent::Started {
                windows::page_loading(webview.app_handle(), webview.label());
            }
        })
        .setup(move |app, _| {
            // One per app, alive as long as the app.
            let state: &'static windows::Inner<R> = Box::leak(Box::new(windows::Inner::new(config)));
            app.manage(state);
            Ok(())
        })
        .on_event(|app, event| match event {
            RunEvent::WindowEvent { label, event, .. } => match event {
                WindowEvent::Focused(true) => windows::bring_to_front(app, label),
                // A page with onBeforeClose is asked before its window closes.
                WindowEvent::CloseRequested { api, .. } => {
                    if windows::ask_before_window_closes(app, label) {
                        api.prevent_close();
                    }
                }
                WindowEvent::Moved(_) | WindowEvent::Resized(_) => {
                    if let Some(w) = app.get_webview_window(label) {
                        windows::frame_changed(&w);
                    }
                }
                WindowEvent::Destroyed => windows::forget_window(app, label),
                _ => {}
            },
            RunEvent::MenuEvent(e) => match e.id().as_ref() {
                menu::NEW_TAB => {
                    let _ = app.tabs().new_tab();
                }
                menu::NEW_WINDOW => {
                    let _ = app.tabs().new_window();
                }
                menu::CLOSE_TAB => app.tabs().close_active(),
                menu::CLOSE_WINDOW => windows::close_window(app),
                _ => {}
            },
            // Quitting (⌘Q sends only Exit): save what is open now, not a moment later.
            RunEvent::ExitRequested { .. } | RunEvent::Exit => persist::save(app, true),
            // The dock icon was clicked with no window open: the remembered ones
            // come back (only in an app that uses tabs, i.e. called start()).
            #[cfg(target_os = "macos")]
            RunEvent::Reopen { has_visible_windows: false, .. }
                if windows::inner(app).started.load(std::sync::atomic::Ordering::SeqCst) =>
            {
                let _ = persist::restore(app);
            }
            _ => {}
        })
        .build()
}

/// What an app does with its tabs from Rust. Get it with `app.tabs()`.
pub struct Tabs<R: Runtime>(AppHandle<R>);

/// Adds `.tabs()` to the app, its handle, windows and webviews.
pub trait TabsExt<R: Runtime> {
    /// The tabs of every window.
    fn tabs(&self) -> Tabs<R>;
}

impl<R: Runtime, T: Manager<R>> TabsExt<R> for T {
    fn tabs(&self) -> Tabs<R> {
        Tabs(self.app_handle().clone())
    }
}

impl<R: Runtime> Tabs<R> {
    /// Opens the remembered windows (or one new window) and keeps saving the
    /// layout. Call it once, in `setup`; later calls do nothing.
    pub fn start(&self) -> tauri::Result<()> {
        persist::start(&self.0)
    }

    /// With no window of tabs open: opens the remembered windows, or one new
    /// window. Does nothing while one is open.
    pub fn restore(&self) -> tauri::Result<()> {
        persist::restore(&self.0)
    }

    /// A new window with the app's starting tab. Returns its label.
    pub fn new_window(&self) -> tauri::Result<String> {
        self.new_window_with(windows::default_tab(&self.0))
    }

    /// A new window with this tab. Returns its label.
    pub fn new_window_with(&self, tab: NewTab) -> tauri::Result<String> {
        let (label, _) = windows::create_window(&self.0, vec![tab], None, true)?;
        Ok(label)
    }

    /// The app's starting tab, at the end of the frontmost window (⌘T).
    /// Returns the tab's id.
    pub fn new_tab(&self) -> tauri::Result<u64> {
        windows::open_or_focus(&self.0, windows::default_tab(&self.0), &|_| false)
    }

    /// A new tab at the end of the frontmost window (a window opens if none is).
    pub fn open(&self, tab: NewTab) -> tauri::Result<u64> {
        windows::open_or_focus(&self.0, tab, &|_| false)
    }

    /// Brings forward the tab of the frontmost window that `is_same` picks, or
    /// opens `tab` there when none matches. `is_same` may use `app.tabs()`.
    pub fn open_or_focus(&self, tab: NewTab, is_same: impl Fn(&Tab) -> bool) -> tauri::Result<u64> {
        windows::open_or_focus(&self.0, tab, &is_same)
    }

    /// Several tabs at once in the frontmost window, the last one active. With
    /// `replace_active`, the first one takes over the active tab without
    /// asking the page's `onBeforeClose`.
    pub fn open_many(&self, tabs: Vec<NewTab>, replace_active: bool) -> tauri::Result<Vec<u64>> {
        windows::open_many(&self.0, tabs, replace_active)
    }

    /// Closes the active tab of the focused window (⌘W). A page with an
    /// `onBeforeClose` is asked first. In a window without tabs, closes it.
    pub fn close_active(&self) {
        windows::close_active(&self.0);
    }

    /// Closes a tab the way a user would: if its page has an `onBeforeClose`,
    /// the page is asked first and may keep it open.
    pub fn request_close_tab(&self, tab: u64) {
        windows::request_close(&self.0, tab);
    }

    /// Closes a tab at once, wherever it is, without asking the page. A window
    /// left with no tabs closes.
    pub fn close_tab(&self, tab: u64) {
        if let Some(label) = windows::label_of_tab(&self.0, tab) {
            windows::remove_tab(&self.0, &label, tab);
        }
    }

    /// Makes a tab the active one of its window and shows that window.
    pub fn activate_tab(&self, tab: u64) {
        if let Some(label) = windows::label_of_tab(&self.0, tab) {
            windows::activate(&self.0, &label, tab, true);
            windows::bring_up(&self.0, &label);
        }
    }

    /// Replaces a tab's title and fields; its page redraws.
    pub fn update_tab(&self, tab: u64, title: impl Into<String>, fields: Fields) {
        windows::update(&self.0, tab, title.into(), fields, true);
    }

    /// One tab, by id.
    pub fn tab(&self, id: u64) -> Option<Tab> {
        windows::tab(&self.0, id)
    }

    /// A new tab at the end of window `label`, made active. None when there
    /// is no such window of tabs.
    pub fn open_in(&self, label: &str, tab: NewTab) -> Option<u64> {
        windows::add_tab(&self.0, label, tab, false)
    }

    /// Every window of tabs, frontmost last.
    pub fn windows(&self) -> Vec<WindowTabs> {
        windows::all_windows(&self.0)
    }

    /// The label of the most recently focused window of tabs.
    pub fn frontmost(&self) -> Option<String> {
        windows::frontmost(&self.0)
    }

    /// Shows a window in front, even when minimized or hidden.
    pub fn bring_up(&self, label: &str) {
        windows::bring_up(&self.0, label);
    }

    /// Takes a tab out of its window into a new window of its own (the menu's
    /// "Move to new window"; works on every system). Returns the new window's
    /// label, or None when there is no such tab.
    pub fn move_to_new_window(&self, tab: u64) -> tauri::Result<Option<String>> {
        windows::move_to_new_window(&self.0, tab)
    }

    /// How many windows of tabs are open.
    pub fn window_count(&self) -> usize {
        windows::window_count(&self.0)
    }
}
