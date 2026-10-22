// Dialogs in windows of their own (TaurisDialog with `window: true`): a form,
// a review or a sheet opens in a native window attached to the window that
// asked, placed over it and kept above it until it closes. Its page is the
// app's own page (Config::window_url, with "#tauris-dialog"): the dialog there
// reads what to show with `dialog_window_spec`, says its size with
// `dialog_window_ready`, and talks to the window that asked through
// `dialog_window_send` and `dialog_window_reply` (the app's checks and its save
// run there). When it is gone, however it closed, the window that asked hears
// so and takes the keyboard back.

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

struct Open {
    owner: String,
    spec: String,
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
/// the app's page; `ready` sizes, places and shows it.
pub(crate) fn open<R: Runtime>(
    app: &AppHandle<R>,
    owner: &WebviewWindow<R>,
    spec: String,
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
        map.insert(label.clone(), Open { owner: owner.label().to_string(), spec, frame: None });
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

/// What the dialog window at `label` shows.
pub(crate) fn spec(label: &str) -> Option<String> {
    open_dialogs().lock().ok()?.get(label).map(|d| d.spec.clone())
}

/// The dialog has laid out at `width` × `height` CSS pixels in a page now
/// `page_w` × `page_h`: the window takes exactly that size; the first time, it
/// is placed over its owner (a third of the way down) and shown with the
/// keyboard. Later calls (a refusal, a review) resize it, its top edge kept.
/// Answers the height it got: less only on a screen too short (then it scrolls).
pub(crate) async fn ready<R: Runtime>(
    app: &AppHandle<R>,
    me: &WebviewWindow<R>,
    width: f64,
    height: f64,
    page_w: f64,
    page_h: f64,
) -> Result<f64, String> {
    let label = me.label().to_string();
    let owner_label = owner_of(&label).ok_or("This window is not a dialog.")?;
    let owner = app.get_webview_window(&owner_label);
    let first = !me.is_visible().unwrap_or(false);
    let scale = me.scale_factor().unwrap_or(1.0);
    let inner_size = me.inner_size().map_err(|e| e.to_string())?.to_logical::<f64>(scale);
    let outer_size = me.outer_size().map_err(|e| e.to_string())?.to_logical::<f64>(scale);
    let (fw, fh) = {
        let mut map = open_dialogs().lock().map_err(|e| e.to_string())?;
        let d = map.get_mut(&label).ok_or("The dialog is gone.")?;
        *d.frame.get_or_insert(((inner_size.width - page_w).max(0.0), (inner_size.height - page_h).max(0.0)))
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
    let mut at = None;
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
            at = Some(LogicalPosition::new(x.round(), y.round()));
        }
    }
    if let Some(p) = at {
        me.set_position(p).map_err(|e| e.to_string())?;
    }
    // Shown once the system has really sized and moved it (macOS applies both
    // later, on its main thread, while showing is at once): briefly waited for.
    let want = to.to_physical::<u32>(scale);
    let want_at = at.map(|p| p.to_physical::<i32>(scale));
    for _ in 0..60 {
        let sized = me
            .inner_size()
            .map(|s| s.width.abs_diff(want.width) <= 1 && s.height.abs_diff(want.height) <= 1)
            .unwrap_or(true);
        let placed = want_at.is_none_or(|w| {
            me.outer_position().map(|p| (p.x - w.x).abs() <= 1 && (p.y - w.y).abs() <= 1).unwrap_or(true)
        });
        if sized && placed {
            break;
        }
        std::thread::sleep(std::time::Duration::from_millis(5));
    }
    match &owner {
        Some(o) => crate::platform::attach_child(o, me),
        None => me.show().map_err(|e| e.to_string())?,
    }
    me.set_focus().map_err(|e| e.to_string())?;
    Ok(height)
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
    // A click on the window that asked brings its dialog forward.
    if message.get("type").and_then(|t| t.as_str()) == Some("focus") {
        if let Some(d) = app.get_webview_window(label) {
            let _ = d.set_focus();
        }
        return Ok(());
    }
    tell_page(app, label, DIALOG_EVENT, serde_json::json!({ "label": label, "message": message }));
    Ok(())
}

/// A dialog window closes itself (its answer given, or cancelled).
pub(crate) fn close<R: Runtime>(window: &WebviewWindow<R>) -> Result<(), String> {
    if owner_of(window.label()).is_none() {
        return Err("This window is not a dialog.".into());
    }
    window.close().map_err(|e| e.to_string())
}
