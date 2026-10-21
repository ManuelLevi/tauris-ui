// The plugin's event handler must never open a window itself: Tauri holds its
// plugin lock while the handler runs, and opening a window takes that lock, so
// the app freezes (a Dock click with no window open, File › New Window). Only
// the real event loop shows it, so this is checked by hand, on macOS:
//
//   cd test/freeze_check && cargo run
//
// A small window opens, closes, and comes back: for a Dock click, for File ›
// New Window pressed through the real menu, for the app's own on_change hook
// opening a window when the last one closes, and for that hook opening one
// after the page's + button (a page command). It ends with "OK" four times and
// exit code 0, or "FROZEN" and exit code 1. Both actions are
// sent from the main dispatch queue, as macOS delivers them; sent from inside
// one of the event loop's own callbacks, they would freeze tao instead.

#[cfg(not(target_os = "macos"))]
fn main() {
    eprintln!("This check needs macOS (the Dock and the menu bar).");
}

#[cfg(target_os = "macos")]
fn main() {
    mac::main();
}

#[cfg(target_os = "macos")]
mod mac {
    use objc2::runtime::{AnyObject, Bool};
    use objc2::{class, msg_send};
    use std::ffi::CString;
    use std::time::Duration;
    use tauri::{AppHandle, Manager, RunEvent};
    use tauris_ui::{Config, NewTab, TabsExt};

    fn reopen_like_a_dock_click() {
        unsafe {
            let app: *mut AnyObject = msg_send![class!(NSApplication), sharedApplication];
            let delegate: *mut AnyObject = msg_send![app, delegate];
            let _: Bool = msg_send![delegate, applicationShouldHandleReopen: app, hasVisibleWindows: Bool::NO];
        }
    }

    fn press_menu_item(title: &str) {
        let title = CString::new(title).unwrap();
        unsafe {
            let app: *mut AnyObject = msg_send![class!(NSApplication), sharedApplication];
            let main: *mut AnyObject = msg_send![app, mainMenu];
            let text: *mut AnyObject = msg_send![class!(NSString), stringWithUTF8String: title.as_ptr()];
            let count: isize = msg_send![main, numberOfItems];
            for i in 0..count {
                let item: *mut AnyObject = msg_send![main, itemAtIndex: i];
                let sub: *mut AnyObject = msg_send![item, submenu];
                if sub.is_null() {
                    continue;
                }
                let at: isize = msg_send![sub, indexOfItemWithTitle: text];
                if at >= 0 {
                    let _: () = msg_send![sub, performActionForItemAtIndex: at];
                    return;
                }
            }
            eprintln!("no menu item called {title:?}");
        }
    }

    // Every window must be gone first, or a slow close would pass for a reopen.
    fn wait_closed(handle: &AppHandle, what: &str) {
        for _ in 0..30 {
            if handle.webview_windows().is_empty() {
                return;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        eprintln!("STUCK: {what}: the windows did not close");
        std::process::exit(1);
    }

    // A window that was not there before (the old ones closed, a new one opened).
    fn wait_new(handle: &AppHandle, old: &[String], what: &str) {
        for _ in 0..30 {
            std::thread::sleep(Duration::from_millis(100));
            let now: Vec<String> = handle.webview_windows().into_keys().collect();
            if now.iter().all(|l| !old.contains(l)) && !now.is_empty() {
                eprintln!("OK: {what}: {} new window(s)", now.len());
                return;
            }
        }
        eprintln!("STUCK: {what}: no new window 3s later");
        std::process::exit(1);
    }

    fn wait_for(handle: &AppHandle, n: usize, what: &str) {
        for _ in 0..30 {
            std::thread::sleep(Duration::from_millis(100));
            if handle.webview_windows().len() >= n {
                eprintln!("OK: {what}: {} window(s)", handle.webview_windows().len());
                return;
            }
        }
        eprintln!("STUCK: {what}: no window 3s later; tab windows in the model: {}", handle.tabs().window_count());
        let (tx, rx) = std::sync::mpsc::channel();
        let _ = handle.run_on_main_thread(move || {
            let _ = tx.send(());
        });
        match rx.recv_timeout(Duration::from_millis(1500)) {
            Ok(()) => eprintln!("the main thread answers: not frozen"),
            Err(_) => eprintln!("the main thread does not answer: FROZEN"),
        }
        std::process::exit(1);
    }

    // The app's hook opens a window when none is left (third step), or after the
    // page's + button (fourth step).
    static REOPEN_FROM_HOOK: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
    static OPEN_AFTER_PLUS: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

    pub fn main() {
        let tabs =
            Config::new().no_layout().window_size(320.0, 200.0).new_tab(|_| NewTab::new("Freeze check")).on_change(
                |app, _| {
                    if REOPEN_FROM_HOOK.load(std::sync::atomic::Ordering::SeqCst) && app.tabs().window_count() == 0 {
                        let _ = app.tabs().new_window();
                    }
                    if OPEN_AFTER_PLUS.swap(false, std::sync::atomic::Ordering::SeqCst) {
                        let _ = app.tabs().new_window();
                    }
                },
            );
        tauri::Builder::default()
            .plugin(tauris_ui::init(tabs))
            .setup(|app| {
                app.set_menu(tauris_ui::default_menu(app.handle(), "Freeze Check")?)?;
                app.tabs().start()?;
                let handle = app.handle().clone();
                std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_millis(1500));
                    for w in handle.webview_windows().into_values() {
                        let _ = w.destroy();
                    }
                    wait_closed(&handle, "before the Dock click");
                    eprintln!("windows before reopen: {}", handle.webview_windows().len());
                    // From the run loop, as AppKit delivers a Dock click; not from inside one of tao's callbacks.
                    dispatch2::DispatchQueue::main().exec_async(reopen_like_a_dock_click);
                    wait_for(&handle, 1, "Dock click");
                    std::thread::sleep(Duration::from_millis(500));
                    dispatch2::DispatchQueue::main().exec_async(|| press_menu_item("New Window"));
                    wait_for(&handle, 2, "New Window (⌘N)");
                    std::thread::sleep(Duration::from_millis(500));
                    REOPEN_FROM_HOOK.store(true, std::sync::atomic::Ordering::SeqCst);
                    let old: Vec<String> = handle.webview_windows().into_keys().collect();
                    for w in handle.webview_windows().into_values() {
                        let _ = w.destroy();
                    }
                    wait_new(&handle, &old, "the app's hook opens a window when the last one closes");
                    REOPEN_FROM_HOOK.store(false, std::sync::atomic::Ordering::SeqCst);
                    std::thread::sleep(Duration::from_millis(1000));
                    OPEN_AFTER_PLUS.store(true, std::sync::atomic::Ordering::SeqCst);
                    if let Some(w) = handle.webview_windows().into_values().next() {
                        let _ = w.eval("window.__TAURI__.core.invoke('plugin:tauris-ui|new_tab')");
                    }
                    wait_for(&handle, 2, "the app's hook opens a window after the page's + button");
                    std::process::exit(0);
                });
                Ok(())
            })
            .build(tauri::generate_context!())
            .expect("build")
            .run(|_, e| match e {
                RunEvent::ExitRequested { api, code: None, .. } => api.prevent_exit(),
                RunEvent::Reopen { has_visible_windows, .. } => {
                    eprintln!("the app saw Reopen (visible windows: {has_visible_windows})")
                }
                RunEvent::MenuEvent(m) => eprintln!("the app saw the menu item {:?}", m.id()),
                _ => {}
            });
    }
}
