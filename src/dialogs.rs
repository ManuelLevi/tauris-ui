// Dialogs in windows of their own (TaurisDialog with `window: true`): a form,
// a review or a sheet opens in a native window attached to the window that
// asked, placed over it and kept above it until it closes. Its page is the
// app's own page (Config::window_url, with "#tauris-dialog"): the dialog there
// reads what to show with `dialog_window_spec`, says its size with
// `dialog_window_ready`, and talks to the window that asked through
// `dialog_window_send` and `dialog_window_reply` (the app's checks and its save
// run there). When it is gone, however it closed, the window that asked hears
// so and takes the keyboard back.
//
// With Config::warm_dialogs, each tab window keeps one such window ready,
// hidden, its page loaded: a dialog is handed to it (no window to make, no page
// to load), and after the dialog it hides and waits for the next.

use crate::windows::{inner, tell_page};
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};
use tauri::{
    AppHandle, LogicalPosition, LogicalSize, Manager, Runtime, WebviewUrl, WebviewWindow, WebviewWindowBuilder,
};

/// What a page hears about its dialog windows (and a dialog window from the window that asked).
pub(crate) const DIALOG_EVENT: &str = "tauris-ui:dialog-window";

static NEXT: AtomicU64 = AtomicU64::new(1);

// How long after a tab window's page has loaded its dialog window is made (not to slow that page).
const WARM_AFTER: std::time::Duration = std::time::Duration::from_millis(1500);

struct Open {
    owner: String,
    // The dialog it shows; None: a window kept ready, waiting for one.
    spec: Option<String>,
    // Its page asked for its dialog and had none: it is told when it has one.
    idle: bool,
    // On screen with a dialog (placed and shown by `ready` when not).
    shown: bool,
    // Has been on screen once (or put there unseen, by `prewarm`).
    prewarmed: bool,
    // What the window adds around its page (a title bar inside the inner size), measured once.
    frame: Option<(f64, f64)>,
}

fn open_dialogs() -> &'static Mutex<HashMap<String, Open>> {
    static OPEN: OnceLock<Mutex<HashMap<String, Open>>> = OnceLock::new();
    OPEN.get_or_init(|| Mutex::new(HashMap::new()))
}

fn owner_of(label: &str) -> Option<String> {
    open_dialogs().lock().ok()?.get(label).map(|d| d.owner.clone())
}

/// Opens `spec` (the page's description of the dialog) in a hidden window of
/// the app's page; `ready` sizes, places and shows it. A window kept ready for
/// `owner` is handed it; otherwise one is made.
pub(crate) fn open<R: Runtime>(
    app: &AppHandle<R>,
    owner: &WebviewWindow<R>,
    spec: String,
    title: String,
    width: f64,
) -> Result<String, String> {
    let handed = open_dialogs().lock().ok().and_then(|mut map| {
        let (label, d) = map.iter_mut().find(|(_, d)| d.owner == owner.label() && d.spec.is_none())?;
        d.spec = Some(spec.clone());
        Some((label.clone(), std::mem::replace(&mut d.idle, false)))
    });
    if let Some((label, idle)) = handed {
        if let Some(w) = app.get_webview_window(&label) {
            let _ = w.set_title(&title);
        }
        // Its page is waiting: told now. Still loading, it asks for it once loaded.
        if idle {
            tell_page(
                app,
                &label,
                DIALOG_EVENT,
                serde_json::json!({ "label": label, "message": { "type": "spec", "spec": spec } }),
            );
        }
        return Ok(label);
    }
    build(app, owner, Some(spec), title, width)
}

/// With `Config::warm_dialogs`: a window kept ready for the tab window `owner`,
/// made a moment after its page has loaded, unless it has one.
pub(crate) fn warm_later<R: Runtime>(app: &AppHandle<R>, owner: &str) {
    let config = &inner(app).config;
    if !config.warm_dialogs || !config.components.contains(&crate::Component::Dialog) || !owner.starts_with(&config.window_prefix) {
        return;
    }
    let (app, owner) = (app.clone(), owner.to_string());
    let _ = std::thread::Builder::new().name("tauris-ui dialog window".into()).spawn(move || {
        std::thread::sleep(WARM_AFTER);
        let has = open_dialogs().lock().map(|m| m.values().any(|d| d.owner == owner)).unwrap_or(true);
        if has {
            return;
        }
        if let Some(o) = app.get_webview_window(&owner) {
            let _ = build(&app, &o, None, String::new(), 440.0);
        }
    });
}

// A hidden window of the app's page for `owner`'s dialogs: showing `spec`, or (None) kept ready.
fn build<R: Runtime>(
    app: &AppHandle<R>,
    owner: &WebviewWindow<R>,
    spec: Option<String>,
    title: String,
    width: f64,
) -> Result<String, String> {
    let label = format!("tauris-dialog-{}", NEXT.fetch_add(1, Ordering::Relaxed));
    let page = inner(app).config.window_url.split('#').next().unwrap_or_default().to_string();
    let url = WebviewUrl::App(format!("{page}#tauris-dialog").into());
    let width = if width.is_finite() && width >= 200.0 { width } else { 440.0 };
    let builder = WebviewWindowBuilder::new(app, &label, url)
        .title(title)
        .inner_size(width, 160.0)
        .resizable(false)
        .minimizable(false)
        .maximizable(false)
        .visible(false);
    // Elsewhere the window belongs to its owner from the start (it stays above it);
    // on macOS it is attached once shown (attached now, it would show at once, blank).
    #[cfg(not(target_os = "macos"))]
    let builder = builder.parent(owner).map_err(|e| e.to_string())?;
    if let Ok(mut map) = open_dialogs().lock() {
        map.insert(label.clone(), Open { owner: owner.label().to_string(), spec, idle: false, shown: false, prewarmed: false, frame: None });
    }
    let dialog = match builder.build() {
        Ok(d) => d,
        Err(e) => {
            if let Ok(mut map) = open_dialogs().lock() {
                map.remove(&label);
            }
            return Err(e.to_string());
        }
    };
    // Gone, however it closed: the window that asked hears it and takes the keyboard back.
    let (app2, me, parent) = (app.clone(), label.clone(), owner.label().to_string());
    dialog.on_window_event(move |e| {
        if let tauri::WindowEvent::Destroyed = e {
            if let Ok(mut map) = open_dialogs().lock() {
                map.remove(&me);
            }
            if let Some(o) = app2.get_webview_window(&parent) {
                let _ = o.set_focus();
            }
            tell_page(
                &app2,
                &parent,
                DIALOG_EVENT,
                serde_json::json!({ "label": me, "message": { "type": "closed" } }),
            );
            // Gone (its close button, or closed from the window that asked): another is kept ready.
            warm_later(&app2, &parent);
        }
    });
    // A dialog never outlives its window.
    let (app3, me2) = (app.clone(), label.clone());
    owner.on_window_event(move |e| {
        if let tauri::WindowEvent::Destroyed = e {
            if let Some(d) = app3.get_webview_window(&me2) {
                let _ = d.close();
            }
        }
    });
    Ok(label)
}

/// What the dialog window at `label` shows; None for a window kept ready
/// (its page is told when it has a dialog).
pub(crate) fn spec(label: &str) -> Option<String> {
    let mut map = open_dialogs().lock().ok()?;
    let d = map.get_mut(label)?;
    if d.spec.is_none() {
        d.idle = true;
    }
    d.spec.clone()
}

/// The dialog has laid out at `width` × `height` CSS pixels in a page now
/// `page_w` × `page_h`: the window takes exactly that size; the first time, it
/// is placed over its owner (a third of the way down) and shown with the
/// keyboard. Later calls (a refusal, a review) resize it, its top edge kept.
/// Answers the height it got: less only on a screen too short (then it scrolls).
/// All of it happens in one turn of the main thread, so the size and the place
/// are the window's before it shows, with nothing to wait for.
pub(crate) async fn ready<R: Runtime>(
    app: &AppHandle<R>,
    me: &WebviewWindow<R>,
    width: f64,
    height: f64,
    page_w: f64,
    page_h: f64,
) -> Result<f64, String> {
    let owner_label = owner_of(me.label()).ok_or("This window is not a dialog.")?;
    let (tx, rx) = std::sync::mpsc::channel();
    let (app2, me2) = (app.clone(), me.clone());
    me.run_on_main_thread(move || {
        let _ = tx.send(place(&app2, &me2, &owner_label, width, height, page_w, page_h));
    })
    .map_err(|e| e.to_string())?;
    tauri::async_runtime::spawn_blocking(move || rx.recv())
        .await
        .map_err(|e| e.to_string())?
        .map_err(|_| "The dialog's window is gone.".to_string())?
}

// `ready`, on the main thread (where the window's calls happen at once).
fn place<R: Runtime>(
    app: &AppHandle<R>,
    me: &WebviewWindow<R>,
    owner_label: &str,
    width: f64,
    height: f64,
    page_w: f64,
    page_h: f64,
) -> Result<f64, String> {
    let label = me.label().to_string();
    let owner = app.get_webview_window(owner_label);
    let scale = me.scale_factor().unwrap_or(1.0);
    let inner_size = me.inner_size().map_err(|e| e.to_string())?.to_logical::<f64>(scale);
    let outer_size = me.outer_size().map_err(|e| e.to_string())?.to_logical::<f64>(scale);
    let (fw, fh, first) = {
        let mut map = open_dialogs().lock().map_err(|e| e.to_string())?;
        let d = map.get_mut(&label).ok_or("The dialog is gone.")?;
        let first = !d.shown;
        d.shown = true;
        d.prewarmed = true;
        let (fw, fh) = *d.frame.get_or_insert(((inner_size.width - page_w).max(0.0), (inner_size.height - page_h).max(0.0)));
        (fw, fh, first)
    };
    let chrome = outer_size.height - inner_size.height + fh;
    let screen = owner.as_ref().unwrap_or(me).current_monitor().ok().flatten().map(|m| {
        let (a, s) = (m.work_area(), m.scale_factor());
        (a.position.x as f64 / s, a.position.y as f64 / s, a.size.width as f64 / s, a.size.height as f64 / s)
    });
    let height = match screen {
        Some((_, _, _, sh)) => height.min(sh - chrome - 16.0).max(60.0),
        None => height,
    };
    // Exactly the dialog's size, which it cannot be dragged away from. The limit
    // in the way moves first, so the window grows or shrinks downward.
    let to = LogicalSize::new(width + fw, height + fh);
    if inner_size.height <= to.height && inner_size.width <= to.width {
        me.set_max_size(Some(to)).map_err(|e| e.to_string())?;
        me.set_min_size(Some(to)).map_err(|e| e.to_string())?;
    } else {
        me.set_min_size(Some(to)).map_err(|e| e.to_string())?;
        me.set_max_size(Some(to)).map_err(|e| e.to_string())?;
    }
    me.set_size(to).map_err(|e| e.to_string())?;
    if !first {
        return Ok(height);
    }
    if let Some(o) = &owner {
        let os = o.scale_factor().unwrap_or(1.0);
        if let (Ok(pos), Ok(size)) = (o.outer_position(), o.outer_size()) {
            let (px, py) = (pos.x as f64 / os, pos.y as f64 / os);
            let (pw, ph) = (size.width as f64 / os, size.height as f64 / os);
            let (ww, wh) = (to.width, outer_size.height - inner_size.height + to.height);
            let mut x = px + (pw - ww) / 2.0;
            let mut y = py + ((ph - wh) / 3.0).max(48.0);
            if let Some((sx, sy, sw, sh)) = screen {
                x = x.min(sx + sw - ww).max(sx);
                y = y.min(sy + sh - wh).max(sy);
            }
            me.set_position(LogicalPosition::new(x.round(), y.round())).map_err(|e| e.to_string())?;
        }
    }
    match &owner {
        Some(o) => crate::platform::attach_child(o, me),
        None => me.show().map_err(|e| e.to_string())?,
    }
    me.set_focus().map_err(|e| e.to_string())?;
    Ok(height)
}

/// A window kept ready, its page loaded and waiting: put on screen once,
/// unseen, so the system and WebKit make what drawing it needs. Its first real
/// show is then as quick as the later ones.
pub(crate) fn prewarm<R: Runtime>(window: &WebviewWindow<R>) {
    let label = window.label().to_string();
    let first = open_dialogs()
        .lock()
        .ok()
        .and_then(|mut map| {
            let d = map.get_mut(&label)?;
            (!d.prewarmed && d.spec.is_none()).then(|| d.prewarmed = true)
        })
        .is_some();
    if !first {
        return;
    }
    crate::platform::order_in_unseen(window);
    let w = window.clone();
    let _ = std::thread::Builder::new().name("tauris-ui dialog window".into()).spawn(move || {
        std::thread::sleep(std::time::Duration::from_millis(300));
        // Off again, unless a dialog was handed to it meanwhile and it shows that.
        crate::platform::order_out_unseen(&w, move || {
            open_dialogs().lock().ok().and_then(|m| m.get(&label).map(|d| !d.shown)).unwrap_or(false)
        });
    });
}

/// From a dialog window to the window that asked.
pub(crate) fn send<R: Runtime>(app: &AppHandle<R>, from: &str, message: serde_json::Value) -> Result<(), String> {
    let owner = owner_of(from).ok_or("This window is not a dialog.")?;
    tell_page(app, &owner, DIALOG_EVENT, serde_json::json!({ "label": from, "message": message }));
    Ok(())
}

/// From the window that asked to its dialog window: only to its own.
pub(crate) fn reply<R: Runtime>(
    app: &AppHandle<R>,
    from: &str,
    label: &str,
    message: serde_json::Value,
) -> Result<(), String> {
    if owner_of(label).as_deref() != Some(from) {
        return Err(format!("{label} is not a dialog of this window"));
    }
    match message.get("type").and_then(|t| t.as_str()) {
        // A click on the window that asked brings its dialog forward.
        Some("focus") => {
            if let Some(d) = app.get_webview_window(label) {
                let _ = d.set_focus();
            }
            return Ok(());
        }
        // Closed from the window that asked (TaurisDialog.close(), or a dialog that never showed):
        // closed here, so it closes even when its page never loaded.
        Some("close") => {
            if let Some(d) = app.get_webview_window(label) {
                let _ = d.close();
            }
            return Ok(());
        }
        _ => {}
    }
    tell_page(app, label, DIALOG_EVENT, serde_json::json!({ "label": label, "message": message }));
    Ok(())
}

/// A dialog window closes itself (its answer given, or cancelled). With
/// `Config::warm_dialogs` it hides instead, kept for the next dialog (its
/// answer was given first, so the window that asked has nothing to hear).
pub(crate) fn close<R: Runtime>(window: &WebviewWindow<R>) -> Result<(), String> {
    let label = window.label().to_string();
    let owner = owner_of(&label).ok_or("This window is not a dialog.")?;
    let app = window.app_handle();
    // Its dialog is over: its page, asking again, has none.
    if let Ok(mut map) = open_dialogs().lock() {
        if let Some(d) = map.get_mut(&label) {
            d.spec = None;
            d.idle = false;
            d.shown = false;
        }
    }
    if !inner(app).config.warm_dialogs {
        return window.close().map_err(|e| e.to_string());
    }
    let o = app.get_webview_window(&owner);
    if let Some(o) = &o {
        crate::platform::detach_child(o, window);
    }
    window.hide().map_err(|e| e.to_string())?;
    if let Some(o) = &o {
        let _ = o.set_focus();
    }
    Ok(())
}
