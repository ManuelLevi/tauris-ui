// Dragging a tab out of its strip hands the drag to Rust, which follows the
// real mouse until the button is released, so a tab can travel between windows.

use crate::model::{Drag, Frame};
use crate::platform::{mouse, set_alpha};
use crate::windows::{inner, notify, open_window, DROP_HOVER};
use serde::Serialize;
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Emitter, LogicalPosition, Manager, Runtime, WebviewWindow};

#[derive(Clone, Serialize)]
struct Hover {
    label: String,
    index: Option<usize>,
    title: String,
}

// The page calls this once a dragged tab leaves its strip. A tab that is alone
// takes its window along; otherwise it gets a new window under the cursor.
// `grab` is where the cursor should sit inside the moving window's page.
pub(crate) fn start<R: Runtime>(
    app: &AppHandle<R>,
    window: &WebviewWindow<R>,
    tab: u64,
    grab_x: f64,
    grab_y: f64,
) -> Result<(), String> {
    if !crate::platform::CAN_DRAG_OUT {
        return Err("dragging a tab out of its window needs macOS".into());
    }
    let source = window.label().to_string();
    if !crate::windows::owns(app, &source, tab) {
        return Err(format!("tab {tab} is not in window {source}"));
    }
    let scale = window.scale_factor().map_err(|e| e.to_string())?;
    let inner_pos = window.inner_position().map_err(|e| e.to_string())?.to_logical::<f64>(scale);
    let outer = window.outer_position().map_err(|e| e.to_string())?.to_logical::<f64>(scale);
    let grab = (grab_x + inner_pos.x - outer.x, grab_y + inner_pos.y - outer.y);

    let state = inner(app);
    let mut m = state.model();
    if m.drag.is_some() {
        return Ok(());
    }
    let alone = m.win(&source).map(|w| w.tabs.len() <= 1).unwrap_or(true);
    let at = m.win(&source).and_then(|w| w.tabs.iter().position(|t| *t == tab)).unwrap_or(usize::MAX);
    let active = m.win(&source).and_then(|w| w.active);
    let moving = if alone {
        source.clone()
    } else {
        m.detach(&source, tab);
        m.create_win(vec![tab])
    };
    m.drag = Some(Drag { tab, window: moving.clone(), grab, hover: None });
    drop(m);

    if !alone {
        notify(app, &source);
        let (cx, cy) = mouse::location();
        let size = state.config.window_size;
        let frame = Frame { x: cx - grab.0, y: cy - grab.1, width: size.0, height: size.1, maximized: false };
        if let Err(e) = open_window(app, &moving, Some(frame), false) {
            // No new window: put the tab back where it was and end the drag.
            let mut m = state.model();
            m.drag = None;
            m.detach(&moving, tab);
            m.wins.retain(|w| w.label != moving);
            m.put_back(&source, tab, at, active);
            drop(m);
            notify(app, &source);
            return Err(e.to_string());
        }
    }
    let handle = app.clone();
    thread::spawn(move || follow_mouse(handle));
    Ok(())
}

// Strip geometry of every window that could receive the dragged tab, topmost first.
fn drop_targets<R: Runtime>(app: &AppHandle<R>, moving: &str) -> Vec<(String, f64, Vec<f64>)> {
    let m = inner(app).model();
    m.wins
        .iter()
        .rev()
        .filter(|w| w.label != moving)
        .map(|w| (w.label.clone(), w.strip.height, w.strip.mids.clone()))
        .collect()
}

fn hit_test<R: Runtime>(app: &AppHandle<R>, moving: &str, cx: f64, cy: f64) -> Option<(String, usize)> {
    let (above, below) = inner(app).config.drop_slack;
    for (label, height, mids) in drop_targets(app, moving) {
        let Some(w) = app.get_webview_window(&label) else { continue };
        if w.is_minimized().unwrap_or(false) || !w.is_visible().unwrap_or(true) {
            continue;
        }
        let Ok(scale) = w.scale_factor() else { continue };
        let Ok(pos) = w.inner_position() else { continue };
        let Ok(size) = w.inner_size() else { continue };
        let (pos, size) = (pos.to_logical::<f64>(scale), size.to_logical::<f64>(scale));
        let (x, y) = (cx - pos.x, cy - pos.y);
        if x < 0.0 || x > size.width {
            continue;
        }
        if y >= -above && y <= height + below {
            return Some((label, mids.iter().filter(|mid| **mid < x).count()));
        }
        // The cursor is over the body of this window, which hides anything below it.
        if y >= 0.0 && y <= size.height {
            return None;
        }
    }
    None
}

fn tab_title<R: Runtime>(app: &AppHandle<R>, tab: u64) -> String {
    inner(app).model().tabs.get(&tab).map(|t| t.title.clone()).unwrap_or_default()
}

fn send_hover<R: Runtime>(app: &AppHandle<R>, label: &str, index: Option<usize>, title: &str) {
    let _ = app.emit(DROP_HOVER, Hover { label: label.into(), index, title: title.into() });
}

// Moves the dragged window with the mouse until the button is released.
// While the cursor is over another window's strip, the dragged window turns
// invisible and that strip shows where the tab will land.
fn follow_mouse<R: Runtime>(app: AppHandle<R>) {
    let state = inner(&app);
    let rest_alpha = state.config.drag_opacity;
    let mut started = false;
    loop {
        thread::sleep(Duration::from_millis(8));
        let pressed = mouse::left_pressed();
        let (cx, cy) = mouse::location();

        let (tab, moving, grab, previous) = {
            let m = state.model();
            let Some(d) = &m.drag else { return };
            (d.tab, d.window.clone(), d.grab, d.hover.clone())
        };
        let Some(window) = app.get_webview_window(&moving) else {
            state.model().drag = None;
            return;
        };
        let _ = window.set_position(LogicalPosition::new(cx - grab.0, cy - grab.1));
        if !started {
            started = true;
            set_alpha(&window, rest_alpha);
        }

        let hover = hit_test(&app, &moving, cx, cy);
        if hover != previous {
            let title = tab_title(&app, tab);
            if let Some((label, _)) = &previous {
                send_hover(&app, label, None, &title);
            }
            if let Some((label, index)) = &hover {
                send_hover(&app, label, Some(*index), &title);
            }
            set_alpha(&window, if hover.is_some() { 0.0 } else { rest_alpha });
            if let Some(d) = state.model().drag.as_mut() {
                d.hover = hover.clone();
            }
        }

        if !pressed {
            finish(&app, &window, tab, hover);
            return;
        }
    }
}

fn finish<R: Runtime>(app: &AppHandle<R>, window: &WebviewWindow<R>, tab: u64, hover: Option<(String, usize)>) {
    let mut m = inner(app).model();
    m.drag = None;
    // A target window that closed while the tab was over it: no drop.
    let hover = hover.filter(|(target, _)| m.win(target).is_some());
    let Some((target, index)) = hover else {
        drop(m);
        set_alpha(window, 1.0);
        let _ = window.set_focus();
        notify(app, window.label());
        return;
    };
    m.detach(window.label(), tab);
    m.attach(&target, tab, index);
    drop(m);
    send_hover(app, &target, None, "");
    notify(app, &target);
    let _ = window.destroy();
    if let Some(w) = app.get_webview_window(&target) {
        let _ = w.set_focus();
    }
}
