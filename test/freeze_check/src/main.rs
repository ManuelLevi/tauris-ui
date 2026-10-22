// The plugin's event handler must never open a window itself: Tauri holds its
// plugin lock while the handler runs, and opening a window takes that lock, so
// the app freezes (a Dock click with no window open, File › New Window). Only
// the real event loop shows it, so this runs a real app, on macOS (CI runs it
// on every push; here):
//
//   cd test/freeze_check && cargo run
//
// It opens windows and takes the focus: on a machine someone is working on,
// leave it to CI.
//
// A small window opens, closes, and comes back: for a Dock click, for File ›
// New Window pressed through the real menu, for the app's own on_change hook
// opening a window when the last one closes, and for that hook opening one
// after the page's + button (a page command). Then a window's last tab is
// closed by File › Close Tab (⌘W) and by the page (`close_tab`): its window
// goes inside the plugin's lock, and the app must not freeze. First of all, the
// window remembered from a layout comes back at its own size, not the one the
// app's window hook sets, and a tab opened from Rust reaches the page.
//
// It ends with "OK" eight times and exit code 0, or exit code 1 and what went
// wrong: "STUCK: ..." for a window that did not open or close, "FROZEN" for a
// main thread that no longer answers, "WRONG" for a size. The menu actions are
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

    // A window that was not there before, the old ones still open.
    fn wait_added(handle: &AppHandle, old: &[String], what: &str) {
        for _ in 0..30 {
            std::thread::sleep(Duration::from_millis(100));
            let now: Vec<String> = handle.webview_windows().into_keys().collect();
            if now.iter().any(|l| !old.contains(l)) {
                eprintln!("OK: {what}: {} window(s)", now.len());
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

    // The main thread still answers (a window closed inside the plugin's lock froze nothing).
    fn wait_gone_and_alive(handle: &AppHandle, what: &str) {
        for _ in 0..30 {
            std::thread::sleep(Duration::from_millis(100));
            if handle.webview_windows().is_empty() {
                let (tx, rx) = std::sync::mpsc::channel();
                let _ = handle.run_on_main_thread(move || {
                    let _ = tx.send(());
                });
                if rx.recv_timeout(Duration::from_millis(1500)).is_ok() {
                    eprintln!("OK: {what}: the window closed, the app answers");
                    return;
                }
                eprintln!("{what}: the main thread does not answer: FROZEN");
                std::process::exit(1);
            }
        }
        eprintln!("STUCK: {what}: the window did not close 3s later");
        std::process::exit(1);
    }

    // One window with one tab, opened from this thread (outside the plugin's lock).
    fn one_window(handle: &AppHandle) {
        for w in handle.webview_windows().into_values() {
            let _ = w.destroy();
        }
        wait_closed(handle, "before a last tab is closed");
        let _ = handle.tabs().new_window();
        for _ in 0..30 {
            std::thread::sleep(Duration::from_millis(100));
            if handle.webview_windows().len() == 1 {
                std::thread::sleep(Duration::from_millis(800)); // its page loaded
                return;
            }
        }
        eprintln!("STUCK: no window to close a last tab in");
        std::process::exit(1);
    }

    // The app's hook opens a window when none is left (third step), or after the
    // page's + button (fourth step).
    static REOPEN_FROM_HOOK: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
    static OPEN_AFTER_PLUS: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
    // The layout is read only for the first step (the remembered size).
    static LAYOUT_ON: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(true);

    pub fn main() {
        // A window remembered at 480 x 260, which the app's window hook would make 320 x 200.
        let layout = std::env::temp_dir().join(format!("tauris-freeze-check-{}.json", std::process::id()));
        std::fs::write(
            &layout,
            r#"[{"tabs":[{"id":1,"title":"Remembered"}],"active":0,"frame":{"x":120,"y":120,"width":480,"height":260,"maximized":false}}]"#,
        )
        .expect("write the layout");
        let file = layout.clone();
        let tabs = Config::new()
            .layout_file(move |_| LAYOUT_ON.load(std::sync::atomic::Ordering::SeqCst).then(|| file.clone()))
            .window(|w| w.inner_size(320.0, 200.0))
            .window_size(320.0, 200.0)
            .min_window_size(200.0, 150.0)
            .new_tab(|_| NewTab::new("Freeze check"))
            .on_change(|app, _| {
                if REOPEN_FROM_HOOK.load(std::sync::atomic::Ordering::SeqCst) && app.tabs().window_count() == 0 {
                    let _ = app.tabs().new_window();
                }
                if OPEN_AFTER_PLUS.swap(false, std::sync::atomic::Ordering::SeqCst) {
                    let _ = app.tabs().new_window();
                }
            });
        tauri::Builder::default()
            .plugin(tauris_ui::init(tabs))
            .setup(|app| {
                app.set_menu(tauris_ui::default_menu(app.handle(), "Freeze Check")?)?;
                app.tabs().start()?;
                let handle = app.handle().clone();
                std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_millis(1500));
                    let size = handle.webview_windows().into_values().next().and_then(|w| {
                        let scale = w.scale_factor().ok()?;
                        w.inner_size().ok().map(|s| s.to_logical::<f64>(scale))
                    });
                    match size {
                        Some(s) if (s.width - 480.0).abs() < 2.0 && (s.height - 260.0).abs() < 2.0 => {
                            eprintln!("OK: a remembered window comes back at its size, not the window hook's")
                        }
                        other => {
                            eprintln!("WRONG: the remembered window is {other:?}, not 480 x 260");
                            std::process::exit(1);
                        }
                    }
                    LAYOUT_ON.store(false, std::sync::atomic::Ordering::SeqCst);
                    let _ = std::fs::remove_file(&layout);
                    // A tab opened from Rust reaches the page (Rust hands its news to that page alone):
                    // the strip shows it, and the window's title follows the page's.
                    let _ = handle.tabs().open(NewTab::new("Delivered"));
                    let shown = (0..30).any(|_| {
                        std::thread::sleep(Duration::from_millis(100));
                        handle.webview_windows().values().any(|w| w.title().is_ok_and(|t| t == "Delivered"))
                    });
                    if !shown {
                        eprintln!("STUCK: a tab opened from Rust never reached the page");
                        std::process::exit(1);
                    }
                    eprintln!("OK: a tab opened from Rust reaches the page");
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
                    let before: Vec<String> = handle.webview_windows().into_keys().collect();
                    if let Some(w) = handle.webview_windows().into_values().next() {
                        let _ = w.eval("window.__TAURI__.core.invoke('plugin:tauris-ui|new_tab')");
                    }
                    wait_added(&handle, &before, "the app's hook opens a window after the page's + button");
                    std::thread::sleep(Duration::from_millis(500));
                    // ⌘W on a window's last tab: the window goes inside the plugin's lock.
                    one_window(&handle);
                    dispatch2::DispatchQueue::main().exec_async(|| press_menu_item("Close Tab"));
                    wait_gone_and_alive(&handle, "Close Tab (⌘W) on the last tab");
                    // The page closing its window's last tab (a plain page command, inside that lock too).
                    one_window(&handle);
                    let only = handle.tabs().windows().first().and_then(|w| w.tabs.first().map(|t| t.id));
                    if let (Some(w), Some(id)) = (handle.webview_windows().into_values().next(), only) {
                        let _ = w.eval(format!(
                            "window.__TAURI__.core.invoke('plugin:tauris-ui|close_tab', {{ tab: {id} }})"
                        ));
                    }
                    wait_gone_and_alive(&handle, "the page closes its window's last tab");
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
