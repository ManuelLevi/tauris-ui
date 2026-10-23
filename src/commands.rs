// What a page can ask of its tab strip (through `TaurisTabs`, see web/tabs.js).
// A page may only touch the tabs of its own window. Commands that only change
// the tabs are not async: Tauri then runs them one after another, in the order
// the page sent them. Those that open a window are async (opening one inside
// Tauri's lock would freeze the app); closing one (`close_tab` on a window's
// last tab) is safe there.

use crate::model::{Fields, NewTab, Strip};
use crate::windows::{self, inner, WindowTabs};
use tauri::{AppHandle, Manager, Runtime, WebviewWindow};

fn not_here(tab: u64, label: &str) -> String {
    format!("tab {tab} is not in window {label}")
}

#[tauri::command]
pub fn window_state<R: Runtime>(window: WebviewWindow<R>) -> Result<WindowTabs, String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    Ok(windows::window_tabs(window.app_handle(), window.label()))
}

// The + button: the app's starting tab, at the end of this window's strip.
#[tauri::command]
pub fn new_tab<R: Runtime>(window: WebviewWindow<R>, app: AppHandle<R>) -> Result<u64, String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
                                              // The app's new_tab panicking must not unwind through Tauri's lock.
    let tab = match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| windows::default_tab(&app))) {
        Ok(tab) => tab,
        Err(payload) => {
            // Not dropped: a payload whose drop panics would panic here.
            std::mem::forget(payload);
            return Err("the app's new_tab panicked".into());
        }
    };
    windows::add_tab(&app, window.label(), tab, false)
        .ok_or_else(|| format!("window {} is not a window of tabs", window.label()))
}

// A tab with a title and fields of the page's choosing, right after the active one.
#[tauri::command]
pub fn open_tab<R: Runtime>(
    window: WebviewWindow<R>,
    app: AppHandle<R>,
    title: String,
    fields: Fields,
) -> Result<u64, String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    windows::add_tab(&app, window.label(), NewTab { title, fields }, true)
        .ok_or_else(|| format!("window {} is not a window of tabs", window.label()))
}

#[tauri::command]
pub fn close_tab<R: Runtime>(window: WebviewWindow<R>, app: AppHandle<R>, tab: u64) -> Result<(), String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    if !windows::owns(&app, window.label(), tab) {
        return Err(not_here(tab, window.label()));
    }
    windows::remove_tab(&app, window.label(), tab);
    Ok(())
}

// The page shows the tab already; only the app is told.
#[tauri::command]
pub fn activate_tab<R: Runtime>(window: WebviewWindow<R>, app: AppHandle<R>, tab: u64) -> Result<(), String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    if !windows::owns(&app, window.label(), tab) {
        return Err(not_here(tab, window.label()));
    }
    windows::activate(&app, window.label(), tab, false);
    Ok(())
}

#[tauri::command]
pub fn move_tab<R: Runtime>(window: WebviewWindow<R>, app: AppHandle<R>, tab: u64, index: usize) -> Result<(), String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    if !windows::owns(&app, window.label(), tab) {
        return Err(not_here(tab, window.label()));
    }
    windows::move_tab(&app, window.label(), tab, index);
    Ok(())
}

// Replaces a tab's title and fields (what the page keeps on it).
#[tauri::command]
pub fn update_tab<R: Runtime>(
    window: WebviewWindow<R>,
    app: AppHandle<R>,
    tab: u64,
    title: String,
    fields: Fields,
) -> Result<(), String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    if !windows::owns(&app, window.label(), tab) {
        return Err(not_here(tab, window.label()));
    }
    windows::update(&app, tab, title, fields, false);
    Ok(())
}

// The page tells where its tabs sit, so another window can drop a tab among them.
#[tauri::command]
pub fn report_strip<R: Runtime>(window: WebviewWindow<R>, height: f64, mids: Vec<f64>) -> Result<(), String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    let mut m = inner(window.app_handle()).model();
    if let Some(win) = m.win(window.label()) {
        win.strip = Strip { height, mids };
    }
    Ok(())
}

// The page has an onBeforeClose: ⌘W and the close button ask it first.
#[tauri::command]
pub fn set_close_guard<R: Runtime>(
    window: WebviewWindow<R>,
    app: AppHandle<R>,
    on: bool,
    seq: u64,
) -> Result<(), String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    windows::set_guard(&app, window.label(), on, seq);
    Ok(())
}

// The page has seen a request to close its window and is asking its tabs.
#[tauri::command]
pub fn close_asked<R: Runtime>(window: WebviewWindow<R>, app: AppHandle<R>) -> Result<(), String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    windows::close_asked(&app, window.label());
    Ok(())
}

// The page agreed to close its whole window.
#[tauri::command]
pub async fn close_window<R: Runtime>(window: WebviewWindow<R>, app: AppHandle<R>) -> Result<(), String> {
    windows::close_window_agreed(&app, window.label());
    Ok(())
}

// The tab menu's "Move to": the other windows a tab can go to.
#[tauri::command]
pub fn other_windows<R: Runtime>(window: WebviewWindow<R>, app: AppHandle<R>) -> Vec<windows::OtherWindow> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    windows::other_windows(&app, window.label())
}

// "Move to" one of them: the tab goes to the end of that window's strip.
#[tauri::command]
pub fn move_to_window<R: Runtime>(
    window: WebviewWindow<R>,
    app: AppHandle<R>,
    tab: u64,
    target: String,
) -> Result<(), String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    if !windows::owns(&app, window.label(), tab) {
        return Err(not_here(tab, window.label()));
    }
    if !windows::is_tab_window(&app, &target) {
        return Err(format!("{target} is not a window of tabs"));
    }
    windows::move_to_window(&app, tab, &target);
    Ok(())
}

// "Move to new window" in the tab's menu: works on every system.
#[tauri::command]
pub async fn move_to_new_window<R: Runtime>(
    window: WebviewWindow<R>,
    app: AppHandle<R>,
    tab: u64,
) -> Result<(), String> {
    let _later = windows::DeferHook::enter(); // the app's hook runs on its worker, not here
    if !windows::owns(&app, window.label(), tab) {
        return Err(not_here(tab, window.label()));
    }
    windows::move_to_new_window(&app, tab).map(|_| ()).map_err(|e| e.to_string())
}

// The system's file picker for the files component: only the paths the
// person chose come back ([] if they cancel).
#[tauri::command]
pub async fn pick_files<R: Runtime>(
    window: WebviewWindow<R>,
    title: Option<String>,
    multiple: Option<bool>,
) -> Result<Vec<String>, String> {
    crate::files::pick_for_page(window, title, multiple.unwrap_or(true)).await
}

// A yes/no question as the system's alert (TaurisDialog.confirm with native: true).
#[tauri::command]
pub async fn ask<R: Runtime>(
    window: WebviewWindow<R>,
    title: String,
    message: String,
    ok: String,
    cancel: String,
    warning: Option<bool>,
) -> Result<bool, String> {
    crate::files::ask_for_page(window, title, message, ok, cancel, warning.unwrap_or(false)).await
}

// ---------- dialogs in windows of their own (TaurisDialog with window: true) ----------

// Opens the page's dialog in a hidden window of its own; the window's label.
// Async: a window opens outside Tauri's lock.
#[tauri::command]
pub async fn dialog_window_open<R: Runtime>(
    window: WebviewWindow<R>,
    app: AppHandle<R>,
    spec: String,
    title: String,
    width: f64,
) -> Result<String, String> {
    crate::dialogs::open(&app, &window, spec, title, width)
}

// What this dialog window shows (null: it is not one).
#[tauri::command]
pub fn dialog_window_spec<R: Runtime>(window: WebviewWindow<R>) -> Option<String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    let spec = crate::dialogs::spec(window.label());
    // A window kept ready, waiting: put on screen once, unseen.
    if spec.is_none() {
        crate::dialogs::prewarm(&window);
    }
    spec
}

// This dialog window's page has laid out: its size, then (the first time) shown.
#[tauri::command]
pub async fn dialog_window_ready<R: Runtime>(
    window: WebviewWindow<R>,
    app: AppHandle<R>,
    width: f64,
    height: f64,
    page_w: f64,
    page_h: f64,
) -> Result<f64, String> {
    crate::dialogs::ready(&app, &window, width, height, page_w, page_h).await
}

// From a dialog window to the window that asked.
#[tauri::command]
pub fn dialog_window_send<R: Runtime>(
    window: WebviewWindow<R>,
    app: AppHandle<R>,
    message: serde_json::Value,
) -> Result<(), String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    crate::dialogs::send(&app, window.label(), message)
}

// From the window that asked to one of its dialog windows.
#[tauri::command]
pub fn dialog_window_reply<R: Runtime>(
    window: WebviewWindow<R>,
    app: AppHandle<R>,
    label: String,
    message: serde_json::Value,
) -> Result<(), String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    crate::dialogs::reply(&app, window.label(), &label, message)
}

// A dialog window closes itself.
#[tauri::command]
pub fn dialog_window_close<R: Runtime>(window: WebviewWindow<R>) -> Result<(), String> {
    let _locked = windows::InPlugin::enter(); // Tauri holds its plugin lock here
    crate::dialogs::close(&window)
}

// The system's save dialog with a name filled in: the chosen path, or null.
#[tauri::command]
pub async fn save_dialog<R: Runtime>(
    window: WebviewWindow<R>,
    title: Option<String>,
    name: Option<String>,
) -> Result<Option<String>, String> {
    crate::files::save_for_page(window, title, name).await
}

#[tauri::command]
pub async fn drag_out<R: Runtime>(
    window: WebviewWindow<R>,
    app: AppHandle<R>,
    tab: u64,
    grab_x: f64,
    grab_y: f64,
) -> Result<(), String> {
    let _later = windows::DeferHook::enter(); // the app's hook runs on its worker, not here
    crate::drag::start(&app, &window, tab, grab_x, grab_y)
}
