// Windows of tabs: opening, closing, remembering where they are.

use crate::config::Config;
use crate::model::{Fields, Frame, Model, NewTab, Tab};
use serde::Serialize;
use std::cell::Cell;
use std::sync::atomic::AtomicBool;
use std::sync::mpsc::Sender;
use std::sync::{Mutex, MutexGuard, PoisonError};
use tauri::{AppHandle, Emitter, Manager, Runtime, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

pub(crate) const STATE_CHANGED: &str = "tauris-ui:state-changed";
pub(crate) const DROP_HOVER: &str = "tauris-ui:drop-hover";
pub(crate) const CLOSE_REQUEST: &str = "tauris-ui:close-request";
pub(crate) const CLOSE_WINDOW_REQUEST: &str = "tauris-ui:close-window-request";
// A page that has not answered a close request within this time is taken to be
// hung; the next press of the close button closes the window.
pub(crate) const UNANSWERED: std::time::Duration = std::time::Duration::from_secs(2);

/// Work for the app's handle, run after an event handler has returned.
pub(crate) type Job<R> = Box<dyn FnOnce(&AppHandle<R>) + Send>;

pub(crate) struct Inner<R: Runtime> {
    model: Mutex<Model>,
    save: Mutex<()>,
    after: Mutex<Option<Sender<Job<R>>>>,
    // Jobs sent to the worker and not finished yet.
    pending: std::sync::atomic::AtomicUsize,
    pub config: Config<R>,
    pub started: AtomicBool,
}

impl<R: Runtime> Inner<R> {
    pub fn new(config: Config<R>) -> Self {
        Inner {
            model: Mutex::new(Model::new(&config.window_prefix)),
            save: Mutex::new(()),
            after: Mutex::new(None),
            pending: std::sync::atomic::AtomicUsize::new(0),
            config,
            started: AtomicBool::new(false),
        }
    }

    // Held while the layout file is decided and written, so two saves (or a
    // save and a forget) never overlap.
    pub fn save_lock(&self) -> MutexGuard<'_, ()> {
        self.save.lock().unwrap_or_else(PoisonError::into_inner)
    }

    // The worker that runs, one after the other, what the plugin's event
    // handler must not do itself (see after_event in lib.rs).
    pub fn after_events(&self) -> MutexGuard<'_, Option<Sender<Job<R>>>> {
        self.after.lock().unwrap_or_else(PoisonError::into_inner)
    }

    // A panic elsewhere must not lock every later caller out of the tabs.
    pub fn model(&self) -> MutexGuard<'_, Model> {
        self.model.lock().unwrap_or_else(PoisonError::into_inner)
    }
}

// The plugin's state lives as long as the app, so it is handed out as 'static.
pub(crate) fn inner<R: Runtime>(app: &AppHandle<R>) -> &'static Inner<R> {
    match app.try_state::<&'static Inner<R>>() {
        #[allow(clippy::explicit_auto_deref)] // keeps the 'static lifetime
        Some(state) => *state.inner(),
        None => panic!(
            "tauris-ui: the plugin is not registered. Add .plugin(tauris_ui::init(tauris_ui::Config::new())) to tauri::Builder"
        ),
    }
}

/// One window of tabs, as `Tabs::windows` and pages see it.
#[derive(Clone, Debug, Serialize)]
pub struct WindowTabs {
    /// The window's label (`tabs-1`, ...).
    pub label: String,
    /// Its tabs, in strip order.
    pub tabs: Vec<Tab>,
    /// The id of its active tab.
    pub active: Option<u64>,
}

pub(crate) fn window_tabs<R: Runtime>(app: &AppHandle<R>, label: &str) -> WindowTabs {
    let mut m = inner(app).model();
    let Some(win) = m.win(label) else {
        return WindowTabs { label: label.to_string(), tabs: vec![], active: None };
    };
    let (ids, active) = (win.tabs.clone(), win.active);
    let tabs = ids.iter().filter_map(|id| m.tabs.get(id).cloned()).collect();
    WindowTabs { label: label.to_string(), tabs, active }
}

pub(crate) fn all_windows<R: Runtime>(app: &AppHandle<R>) -> Vec<WindowTabs> {
    let labels: Vec<String> = inner(app).model().wins.iter().map(|w| w.label.clone()).collect();
    labels.iter().map(|l| window_tabs(app, l)).collect()
}

thread_local! {
    // Set while the app's change hook runs, so changes it makes do not call it again.
    static IN_HOOK: Cell<bool> = const { Cell::new(false) };

}

// Tauri calls a plugin's on_event, and its plain (not async) commands, while
// it holds its plugin lock, and opening a window takes that same lock, so a
// window opened there waits forever (the Dock click and ⌘N froze the app).
// run_on_main_thread is no way out: on the main thread it runs at once. The
// work goes to one worker thread instead, which runs it as soon as the
// handler has returned, one job after the other (a second ⌘T adds a tab to
// the window the first one opened). A job that panics is caught, so the
// worker keeps going; a worker that is gone is replaced.
pub(crate) fn after_event<R: Runtime>(app: &AppHandle<R>, job: impl FnOnce(&AppHandle<R>) + Send + 'static) {
    use std::sync::atomic::Ordering;
    let state = inner(app);
    let mut worker = state.after_events();
    let mut job: Job<R> = Box::new(job);
    state.pending.fetch_add(1, Ordering::SeqCst);
    for _ in 0..2 {
        if worker.is_none() {
            let (tx, rx) = std::sync::mpsc::channel::<Job<R>>();
            let app = app.clone();
            std::thread::spawn(move || {
                for job in rx {
                    let _ = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| job(&app)));
                    inner(&app).pending.fetch_sub(1, Ordering::SeqCst);
                }
            });
            *worker = Some(tx);
        }
        match worker.as_ref().map(|tx| tx.send(job)) {
            Some(Ok(())) => return,
            None => break,
            Some(Err(std::sync::mpsc::SendError(back))) => {
                job = back;
                *worker = None;
            }
        }
    }
    state.pending.fetch_sub(1, Ordering::SeqCst);
}

// Waits, at most `limit`, for the worker to finish what it was given: the app
// is quitting, and its hook should still hear the last changes.
pub(crate) fn drain<R: Runtime>(app: &AppHandle<R>, limit: std::time::Duration) {
    let until = std::time::Instant::now() + limit;
    while inner(app).pending.load(std::sync::atomic::Ordering::SeqCst) > 0 && std::time::Instant::now() < until {
        std::thread::sleep(std::time::Duration::from_millis(5));
    }
}

// Tells the app (its on_change hook) that window `label` changed. The hook
// runs a moment later, on the worker, in order: a change can come from inside
// the plugin's on_event or a page's command, where a hook that opened a window
// would freeze the app (see after_event). Changes the hook itself makes do not
// call it again.
pub(crate) fn changed<R: Runtime>(app: &AppHandle<R>, label: &str) {
    if inner(app).config.on_change.is_none() || IN_HOOK.with(|h| h.get()) {
        return;
    }
    let label = label.to_string();
    after_event(app, move |app| run_hook(app, &label));
}

fn run_hook<R: Runtime>(app: &AppHandle<R>, label: &str) {
    let Some(hook) = &inner(app).config.on_change else { return };
    if IN_HOOK.with(|h| h.replace(true)) {
        return;
    }
    // Cleared on the way out, even if the hook panics.
    struct Leave;
    impl Drop for Leave {
        fn drop(&mut self) {
            IN_HOOK.with(|h| h.set(false));
        }
    }
    let _leave = Leave;
    hook(app, label);
}

// Tells the page of window `label` that its tabs changed, then the app. Never
// call it with the lock held: the app's hook may use the tabs.
pub(crate) fn notify<R: Runtime>(app: &AppHandle<R>, label: &str) {
    inner(app).model().changed();
    let _ = app.emit(STATE_CHANGED, label.to_string());
    if std::env::var_os("TAURIS_UI_LOG").is_some() {
        log_layout(app);
    }
    changed(app, label);
}

// With TAURIS_UI_LOG set, every change prints each window's tabs.
fn log_layout<R: Runtime>(app: &AppHandle<R>) {
    let m = inner(app).model();
    let windows: Vec<String> = m
        .wins
        .iter()
        .map(|w| {
            let titles: Vec<&str> = w.tabs.iter().filter_map(|t| m.tabs.get(t)).map(|t| t.title.as_str()).collect();
            format!("{}[{}]", w.label, titles.join(", "))
        })
        .collect();
    eprintln!("tauris-ui layout: {}", windows.join("  "));
}

// `frame`: where to put it; the default size, centred, when None.
pub(crate) fn open_window<R: Runtime>(
    app: &AppHandle<R>,
    label: &str,
    frame: Option<Frame>,
    focused: bool,
) -> tauri::Result<WebviewWindow<R>> {
    let config = &inner(app).config;
    let (width, height) = frame.map_or(config.window_size, |f| (f.width, f.height));
    let mut builder = WebviewWindowBuilder::new(app, label, WebviewUrl::App(config.window_url.clone().into()))
        .inner_size(width, height)
        .min_inner_size(config.min_window_size.0, config.min_window_size.1)
        .focused(focused)
        // The window's own title (Window menu, taskbar) follows the page's,
        // which follows the active tab.
        .on_document_title_changed(|window, title| {
            let _ = window.set_title(&title);
        });
    #[cfg(target_os = "macos")]
    if let Some((x, y)) = config.traffic_lights {
        builder = builder
            .title_bar_style(tauri::TitleBarStyle::Overlay)
            .hidden_title(true)
            .traffic_light_position(tauri::LogicalPosition::new(x, y));
    }
    if let Some(hook) = &config.window_hook {
        builder = hook(builder);
    }
    builder = match frame {
        Some(f) => builder.position(f.x, f.y).maximized(f.maximized),
        None => builder.center(),
    };
    builder.build()
}

// Records a window with these tabs and opens it. If the window cannot open,
// nothing is recorded.
pub(crate) fn create_window<R: Runtime>(
    app: &AppHandle<R>,
    tabs: Vec<NewTab>,
    frame: Option<Frame>,
    focused: bool,
) -> tauri::Result<(String, Vec<u64>)> {
    let state = inner(app);
    let (label, ids) = {
        let mut m = state.model();
        let ids: Vec<u64> = tabs.into_iter().map(|t| m.create_tab(t)).collect();
        (m.create_win(ids.clone()), ids)
    };
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| open_window(app, &label, frame, focused))) {
        Ok(Ok(_)) => {}
        Ok(Err(e)) => {
            state.model().remove_win(&label);
            return Err(e);
        }
        // The app's window hook panicked: no window, so no record of one.
        Err(panic) => {
            state.model().remove_win(&label);
            std::panic::resume_unwind(panic);
        }
    }
    changed(app, &label);
    Ok((label, ids))
}

pub(crate) fn default_tab<R: Runtime>(app: &AppHandle<R>) -> NewTab {
    (inner(app).config.new_tab)(app)
}

fn focused_window<R: Runtime>(app: &AppHandle<R>) -> Option<WebviewWindow<R>> {
    app.webview_windows().into_values().find(|w| w.is_focused().unwrap_or(false))
}

pub(crate) fn is_tab_window<R: Runtime>(app: &AppHandle<R>, label: &str) -> bool {
    inner(app).model().wins.iter().any(|w| w.label == label)
}

pub(crate) fn label_of_tab<R: Runtime>(app: &AppHandle<R>, tab: u64) -> Option<String> {
    inner(app).model().wins.iter().find(|w| w.tabs.contains(&tab)).map(|w| w.label.clone())
}

// True when `tab` is one of window `label`'s tabs; pages may only touch their own.
pub(crate) fn owns<R: Runtime>(app: &AppHandle<R>, label: &str, tab: u64) -> bool {
    inner(app).model().win(label).is_some_and(|w| w.tabs.contains(&tab))
}

pub(crate) fn add_tab<R: Runtime>(app: &AppHandle<R>, label: &str, tab: NewTab, after_active: bool) -> Option<u64> {
    let id = {
        let mut m = inner(app).model();
        m.win(label)?;
        let id = m.create_tab(tab);
        let win = m.win(label)?;
        let at = if after_active {
            win.active.and_then(|a| win.tabs.iter().position(|t| *t == a)).map(|p| p + 1).unwrap_or(win.tabs.len())
        } else {
            win.tabs.len()
        };
        win.tabs.insert(at, id);
        win.active = Some(id);
        id
    };
    notify(app, label);
    Some(id)
}

pub(crate) fn remove_tab<R: Runtime>(app: &AppHandle<R>, label: &str, tab: u64) {
    let empty = {
        let mut m = inner(app).model();
        if !m.win(label).is_some_and(|w| w.tabs.contains(&tab)) {
            return;
        }
        m.detach(label, tab);
        m.tabs.remove(&tab);
        let empty = m.win(label).map(|w| w.tabs.is_empty()).unwrap_or(false);
        // The user closed the last tab there was: the next launch starts fresh.
        if empty && m.wins.len() == 1 {
            m.emptied = true;
        }
        empty
    };
    if empty {
        changed(app, label);
        if let Some(w) = app.get_webview_window(label) {
            let _ = w.destroy();
        }
    } else {
        notify(app, label);
    }
}

pub(crate) fn move_tab<R: Runtime>(app: &AppHandle<R>, label: &str, tab: u64, index: usize) {
    {
        let mut m = inner(app).model();
        if !m.win(label).is_some_and(|w| w.tabs.contains(&tab)) {
            return;
        }
        m.detach(label, tab);
        m.attach(label, tab, index);
    }
    notify(app, label);
}

// `tell_page`: false when the page made the change itself and shows it already.
pub(crate) fn activate<R: Runtime>(app: &AppHandle<R>, label: &str, tab: u64, tell_page: bool) {
    {
        let mut m = inner(app).model();
        let Some(win) = m.win(label) else { return };
        if !win.tabs.contains(&tab) || win.active == Some(tab) {
            return;
        }
        win.active = Some(tab);
        m.changed();
    }
    if tell_page {
        notify(app, label);
    } else {
        changed(app, label);
    }
}

// `tell_page`: false when the page made the change itself and shows it already.
pub(crate) fn update<R: Runtime>(app: &AppHandle<R>, tab: u64, title: String, fields: Fields, tell_page: bool) {
    {
        let mut m = inner(app).model();
        let Some(t) = m.tabs.get_mut(&tab) else { return };
        t.title = title;
        t.fields = crate::model::clean(fields);
        m.changed();
    }
    let Some(label) = label_of_tab(app, tab) else { return };
    if tell_page {
        notify(app, &label);
    } else {
        changed(app, &label);
    }
}

// Shows a window in front, even when minimized or hidden.
pub(crate) fn bring_up<R: Runtime>(app: &AppHandle<R>, label: &str) {
    if let Some(w) = app.get_webview_window(label) {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}

// The most recently focused window of tabs.
pub(crate) fn frontmost<R: Runtime>(app: &AppHandle<R>) -> Option<String> {
    inner(app).model().wins.last().map(|w| w.label.clone())
}

#[derive(Clone, Serialize)]
struct CloseRequest {
    label: String,
    tab: u64,
}

// ⌘W: the active tab of the focused window of tabs; a window without tabs
// (settings, a pop-up) simply closes.
pub(crate) fn close_active<R: Runtime>(app: &AppHandle<R>) {
    let Some(window) = focused_window(app) else { return };
    let label = window.label().to_string();
    if !is_tab_window(app, &label) {
        let _ = window.close();
        return;
    }
    let active = inner(app).model().win(&label).and_then(|w| w.active);
    if let Some(tab) = active {
        request_close(app, tab);
    }
}

// Closes a tab the way a user would: a page with onBeforeClose is asked first.
pub(crate) fn request_close<R: Runtime>(app: &AppHandle<R>, tab: u64) {
    let Some(label) = label_of_tab(app, tab) else { return };
    let guarded = inner(app).model().win(&label).is_some_and(|w| w.guarded);
    if guarded {
        let _ = app.emit(CLOSE_REQUEST, CloseRequest { label, tab });
    } else {
        remove_tab(app, &label, tab);
    }
}

pub(crate) fn tab<R: Runtime>(app: &AppHandle<R>, id: u64) -> Option<Tab> {
    inner(app).model().tabs.get(&id).cloned()
}

// The page has (or no longer has) an onBeforeClose to ask before tabs close.
// `seq` grows with each mount in the page, so a late message from an older
// mount (React's StrictMode mounts twice) never wins over a newer one.
pub(crate) fn set_guard<R: Runtime>(app: &AppHandle<R>, label: &str, on: bool, seq: u64) {
    if let Some(win) = inner(app).model().win(label) {
        if seq >= win.guard_seq {
            win.guard_seq = seq;
            win.guarded = on;
        }
    }
}

// The window's page is (re)loading: until it mounts again, nobody is there to
// ask, so the window closes normally.
pub(crate) fn page_loading<R: Runtime>(app: &AppHandle<R>, label: &str) {
    if let Some(win) = inner(app).model().win(label) {
        win.guarded = false;
        win.guard_seq = 0;
        win.may_close = false;
        win.close_asked_at = None;
        win.close_seen = false;
    }
}

// The window's close button (or ⇧⌘W) was used. True when its page must be
// asked first; the page then calls `close_window_agreed`.
pub(crate) fn ask_before_window_closes<R: Runtime>(app: &AppHandle<R>, label: &str) -> bool {
    let ask = {
        let mut m = inner(app).model();
        let Some(win) = m.win(label) else { return false };
        // Asked before and the page never even answered: it is hung or gone.
        let unanswered = win.close_asked_at.is_some_and(|at| at.elapsed() >= UNANSWERED) && !win.close_seen;
        let ask = win.guarded && !win.may_close && !unanswered;
        if ask {
            win.close_asked_at = Some(std::time::Instant::now());
            win.close_seen = false;
        }
        ask
    };
    if ask {
        let _ = app.emit(CLOSE_WINDOW_REQUEST, label.to_string());
    }
    ask
}

// The page answered a close request: it is alive and asking its tabs.
pub(crate) fn close_asked<R: Runtime>(app: &AppHandle<R>, label: &str) {
    if let Some(win) = inner(app).model().win(label) {
        win.close_seen = true;
    }
}

// The page agreed: the window closes without asking again.
pub(crate) fn close_window_agreed<R: Runtime>(app: &AppHandle<R>, label: &str) {
    if let Some(win) = inner(app).model().win(label) {
        win.may_close = true;
    }
    if let Some(w) = app.get_webview_window(label) {
        let _ = w.close();
    }
}

// Takes a tab out of its window into a new window of its own. The old window
// closes if it is left empty. Returns the new window's label.
pub(crate) fn move_to_new_window<R: Runtime>(app: &AppHandle<R>, tab: u64) -> tauri::Result<Option<String>> {
    let state = inner(app);
    let (source, label, emptied) = {
        let mut m = state.model();
        let Some(source) = m.wins.iter().find(|w| w.tabs.contains(&tab)).map(|w| w.label.clone()) else {
            return Ok(None);
        };
        if m.win(&source).is_some_and(|w| w.tabs.len() == 1) {
            return Ok(Some(source)); // already alone in its window
        }
        m.detach(&source, tab);
        let label = m.create_win(vec![tab]);
        (source.clone(), label, m.win(&source).is_some_and(|w| w.tabs.is_empty()))
    };
    if let Err(e) = open_window(app, &label, None, true) {
        let mut m = state.model();
        m.wins.retain(|w| w.label != label);
        m.attach(&source, tab, usize::MAX);
        drop(m);
        notify(app, &source);
        return Err(e);
    }
    if emptied {
        if let Some(w) = app.get_webview_window(&source) {
            let _ = w.destroy();
        }
    } else {
        notify(app, &source);
    }
    changed(app, &label);
    Ok(Some(label))
}

// ⇧⌘W: closes the focused window, whatever it is.
pub(crate) fn close_window<R: Runtime>(app: &AppHandle<R>) {
    if let Some(window) = focused_window(app) {
        let _ = window.close();
    }
}

// A window is gone. If it was the last one, the app is closing or quitting:
// save now, with every window that closed a moment ago, so all of them come
// back. A window closed on its own drops out of the layout at the next save.
pub(crate) fn forget_window<R: Runtime>(app: &AppHandle<R>, label: &str) {
    let last = {
        let mut m = inner(app).model();
        if !m.wins.iter().any(|w| w.label == label) {
            return;
        }
        m.close_win(label);
        m.wins.is_empty()
    };
    changed(app, label);
    if last {
        let emptied = std::mem::take(&mut inner(app).model().emptied);
        if emptied {
            crate::persist::forget(app);
        } else {
            crate::persist::save(app, true);
        }
    }
}

pub(crate) fn bring_to_front<R: Runtime>(app: &AppHandle<R>, label: &str) {
    let mut m = inner(app).model();
    if let Some(pos) = m.wins.iter().position(|w| w.label == label) {
        let win = m.wins.remove(pos);
        m.wins.push(win);
        m.changed();
    }
}

// A window moved or was resized: remember where it is.
pub(crate) fn frame_changed<R: Runtime>(window: &WebviewWindow<R>) {
    let Ok(scale) = window.scale_factor() else { return };
    let (Ok(pos), Ok(size)) = (window.outer_position(), window.inner_size()) else { return };
    let (pos, size) = (pos.to_logical::<f64>(scale), size.to_logical::<f64>(scale));
    let maximized = window.is_maximized().unwrap_or(false);
    let mut m = inner(window.app_handle()).model();
    if let Some(win) = m.win(window.label()) {
        // A maximized window keeps the size it had before, to go back to.
        let before = win.frame.filter(|_| maximized);
        win.frame = Some(match before {
            Some(f) => Frame { maximized: true, ..f },
            None => Frame { x: pos.x, y: pos.y, width: size.width, height: size.height, maximized },
        });
        m.changed();
    }
}

pub(crate) fn window_count<R: Runtime>(app: &AppHandle<R>) -> usize {
    inner(app).model().wins.len()
}

// The frontmost window; with none open, the remembered ones come back first.
fn front_or_restored<R: Runtime>(app: &AppHandle<R>) -> Option<String> {
    if frontmost(app).is_none() {
        crate::persist::restore_saved(app);
    }
    frontmost(app)
}

// Opens a tab in the frontmost window, or brings forward the one `is_same`
// picks. `is_same` runs with no lock held.
pub(crate) fn open_or_focus<R: Runtime>(
    app: &AppHandle<R>,
    tab: NewTab,
    is_same: &dyn Fn(&Tab) -> bool,
) -> tauri::Result<u64> {
    let Some(label) = front_or_restored(app) else {
        let (label, ids) = create_window(app, vec![tab], None, true)?;
        bring_up(app, &label);
        return Ok(ids[0]);
    };
    let existing = window_tabs(app, &label).tabs.iter().find(|t| is_same(t)).map(|t| t.id);
    let id = {
        let mut m = inner(app).model();
        let id = match existing {
            Some(id) if m.win(&label).is_some_and(|w| w.tabs.contains(&id)) => id,
            _ => {
                let id = m.create_tab(tab);
                if let Some(win) = m.win(&label) {
                    win.tabs.push(id);
                }
                id
            }
        };
        if let Some(win) = m.win(&label) {
            win.active = Some(id);
        }
        id
    };
    notify(app, &label);
    bring_up(app, &label);
    Ok(id)
}

// Opens several tabs at once in the frontmost window. With `replace_active`,
// the first one takes over the active tab instead of opening a new one.
pub(crate) fn open_many<R: Runtime>(
    app: &AppHandle<R>,
    tabs: Vec<NewTab>,
    replace_active: bool,
) -> tauri::Result<Vec<u64>> {
    if tabs.is_empty() {
        return Ok(vec![]);
    }
    let Some(label) = front_or_restored(app) else {
        let (label, ids) = create_window(app, tabs, None, true)?;
        bring_up(app, &label);
        return Ok(ids);
    };
    let ids = {
        let mut m = inner(app).model();
        let mut rest = tabs.into_iter();
        let mut ids = vec![];
        if replace_active {
            let active = m.win(&label).and_then(|w| w.active);
            if let (Some(id), Some(new)) = (active, rest.next()) {
                if let Some(tab) = m.tabs.get_mut(&id) {
                    tab.title = new.title;
                    tab.fields = crate::model::clean(new.fields);
                    ids.push(id);
                }
            }
        }
        for new in rest {
            let id = m.create_tab(new);
            if let Some(win) = m.win(&label) {
                win.tabs.push(id);
            }
            ids.push(id);
        }
        if let (Some(id), Some(win)) = (ids.last().copied(), m.win(&label)) {
            win.active = Some(id);
        }
        ids
    };
    notify(app, &label);
    bring_up(app, &label);
    Ok(ids)
}
