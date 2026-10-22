// Windows of tabs: opening, closing, remembering where they are.

use crate::config::Config;
use crate::model::{Fields, Frame, Model, NewTab, Tab};
use serde::Serialize;
use std::cell::Cell;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
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

// A worker thread and its queue: jobs run one after the other, in order.
pub(crate) struct Queue<R: Runtime> {
    tx: Mutex<Option<Sender<Job<R>>>>,
    // Jobs sent and not finished yet.
    pending: AtomicUsize,
}

impl<R: Runtime> Queue<R> {
    fn new() -> Self {
        Queue { tx: Mutex::new(None), pending: AtomicUsize::new(0) }
    }
}

// Which worker: window jobs (⌘N, ⌘T, the Dock click) and the app's on_change
// hook have one each, so a slow hook never holds up a new window.
#[derive(Clone, Copy)]
pub(crate) enum Kind {
    Windows,
    Hook,
}

pub(crate) struct Inner<R: Runtime> {
    model: Mutex<Model>,
    save: Mutex<()>,
    windows_q: Queue<R>,
    hook_q: Queue<R>,
    // Held while the app's on_change hook runs: one call at a time.
    pub(crate) hook: Mutex<()>,
    // Held while a change decides whether its hook call runs now or queues,
    // so calls reach the hook in the order they were made.
    hook_gate: Mutex<()>,
    // Windows with a hook call waiting on the worker, and the newest call's
    // number: an older call for the same window skips itself (the hook reads
    // the tabs as they are), and the newest keeps its place in the order.
    hook_waiting: Mutex<std::collections::HashMap<String, u64>>,
    hook_seq: AtomicUsize,
    // The app is quitting: no new windows.
    exiting: AtomicBool,
    // Remembered windows are being opened (see persist::restore_saved).
    pub restoring: AtomicBool,
    // A save at once (the last window closing, a quit) could not be written:
    // the next save is one at once too, with the windows that closed.
    pub retry_now: AtomicBool,
    pub config: Config<R>,
    pub started: AtomicBool,
}

impl<R: Runtime> Inner<R> {
    pub fn new(config: Config<R>) -> Self {
        Inner {
            model: Mutex::new(Model::new(&config.window_prefix)),
            save: Mutex::new(()),
            windows_q: Queue::new(),
            hook_q: Queue::new(),
            hook: Mutex::new(()),
            hook_gate: Mutex::new(()),
            hook_waiting: Mutex::new(std::collections::HashMap::new()),
            hook_seq: AtomicUsize::new(0),
            exiting: AtomicBool::new(false),
            restoring: AtomicBool::new(false),
            retry_now: AtomicBool::new(false),
            config,
            started: AtomicBool::new(false),
        }
    }

    // Held while the layout file is decided and written, so two saves (or a
    // save and a forget) never overlap.
    pub fn save_lock(&self) -> MutexGuard<'_, ()> {
        self.save.lock().unwrap_or_else(PoisonError::into_inner)
    }

    fn queue(&self, kind: Kind) -> &Queue<R> {
        match kind {
            Kind::Windows => &self.windows_q,
            Kind::Hook => &self.hook_q,
        }
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

// Read in one go: a window closing meanwhile is not reported as an empty one.
pub(crate) fn all_windows<R: Runtime>(app: &AppHandle<R>) -> Vec<WindowTabs> {
    let m = inner(app).model();
    m.wins
        .iter()
        .map(|w| WindowTabs {
            label: w.label.clone(),
            tabs: w.tabs.iter().filter_map(|id| m.tabs.get(id).cloned()).collect(),
            active: w.active,
        })
        .collect()
}

thread_local! {
    // Set while the app's change hook runs, so changes it makes do not call it again.
    static IN_HOOK: Cell<bool> = const { Cell::new(false) };
    // Set while Tauri holds its plugin lock on this thread: the plugin's
    // on_event, and its plain (not async) page commands.
    static IN_PLUGIN: Cell<bool> = const { Cell::new(false) };
    // Set on the worker that opens windows: a hook run there would hold up the
    // next ⌘N, so its calls go to the hook's worker.
    static ON_WINDOWS_WORKER: Cell<bool> = const { Cell::new(false) };
    // Set while an async page command runs (on the async runtime's thread):
    // its hook calls go to the worker too, as a plain command's do.
    static DEFER_HOOK: Cell<bool> = const { Cell::new(false) };
}

// Tauri calls a plugin's on_event, and its plain (not async) commands, while
// it holds its plugin lock, and opening a window takes that same lock, so a
// window opened there waits forever (the Dock click and ⌘N froze the app).
// run_on_main_thread is no way out: on the main thread it runs at once. The
// work goes to the windows worker instead, which runs it as soon as the
// handler has returned, one job after the other (a second ⌘T adds a tab to
// the window the first one opened). The app's on_change hook has a worker of
// its own (see changed), so the two never wait for each other. A job that
// panics is caught, so the worker keeps going; a worker that is gone is replaced.
pub(crate) fn after_event<R: Runtime>(app: &AppHandle<R>, job: impl FnOnce(&AppHandle<R>) + Send + 'static) {
    // Quitting: a window opened now would only hold up the quit.
    if inner(app).exiting.load(Ordering::SeqCst) {
        return;
    }
    send(app, Kind::Windows, Box::new(job));
}

// Gives a job to a worker, starting it (or a new one) when needed; false
// when no worker could take it.
pub(crate) fn send<R: Runtime>(app: &AppHandle<R>, kind: Kind, mut job: Job<R>) -> bool {
    let queue = inner(app).queue(kind);
    let mut tx = queue.tx.lock().unwrap_or_else(PoisonError::into_inner);
    queue.pending.fetch_add(1, Ordering::SeqCst);
    for _ in 0..2 {
        if tx.is_none() {
            let (sender, rx) = std::sync::mpsc::channel::<Job<R>>();
            let worker_app = app.clone();
            let started = std::thread::Builder::new().name("tauris-ui".into()).spawn(move || {
                ON_WINDOWS_WORKER.with(|w| w.set(matches!(kind, Kind::Windows)));
                for job in rx {
                    // Counted as done even if the job panics.
                    struct Done<'a>(&'a AtomicUsize);
                    impl Drop for Done<'_> {
                        fn drop(&mut self) {
                            self.0.fetch_sub(1, Ordering::SeqCst);
                        }
                    }
                    let _done = Done(&inner(&worker_app).queue(kind).pending);
                    if let Err(payload) = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| job(&worker_app))) {
                        // Not dropped: a payload whose drop panics would end the worker.
                        std::mem::forget(payload);
                    }
                }
            });
            if started.is_err() {
                break;
            }
            *tx = Some(sender);
        }
        match tx.as_ref().map(|t| t.send(job)) {
            Some(Ok(())) => return true,
            None => break,
            Some(Err(std::sync::mpsc::SendError(back))) => {
                job = back;
                *tx = None;
            }
        }
    }
    // No worker could take it: it is dropped, and not counted as waiting.
    queue.pending.fetch_sub(1, Ordering::SeqCst);
    false
}

// Marks this thread as running an async page command, until dropped: the
// app's hook is called on its worker, not on the async runtime's thread.
pub(crate) struct DeferHook(bool);

impl DeferHook {
    pub(crate) fn enter() -> Self {
        DeferHook(DEFER_HOOK.with(|d| d.replace(true)))
    }
}

impl Drop for DeferHook {
    fn drop(&mut self) {
        let was = self.0;
        DEFER_HOOK.with(|d| d.set(was));
    }
}

// Marks this thread as running inside Tauri's plugin lock, until dropped.
pub(crate) struct InPlugin(bool);

impl InPlugin {
    pub(crate) fn enter() -> Self {
        InPlugin(IN_PLUGIN.with(|p| p.replace(true)))
    }
}

impl Drop for InPlugin {
    fn drop(&mut self) {
        let was = self.0;
        IN_PLUGIN.with(|p| p.set(was));
    }
}

// Waits, at most `limit`, for the hook's calls to end: the app is quitting,
// and its hook should still hear the last changes. Those waiting on its worker
// and one running on another thread. A window job is not waited for: it could
// not finish while the app quits (it needs the lock the quitting thread holds).
pub(crate) fn drain<R: Runtime>(app: &AppHandle<R>, limit: std::time::Duration) {
    let until = std::time::Instant::now() + limit;
    let state = inner(app);
    let running = || matches!(state.hook.try_lock(), Err(std::sync::TryLockError::WouldBlock));
    while (state.hook_q.pending.load(Ordering::SeqCst) > 0 || running()) && std::time::Instant::now() < until {
        std::thread::sleep(std::time::Duration::from_millis(5));
    }
}

// Tests: waits until both workers have nothing left to do.
#[cfg(test)]
pub(crate) fn settle<R: Runtime>(app: &AppHandle<R>, limit: std::time::Duration) {
    let until = std::time::Instant::now() + limit;
    let state = inner(app);
    let busy = || state.windows_q.pending.load(Ordering::SeqCst) > 0 || state.hook_q.pending.load(Ordering::SeqCst) > 0;
    while busy() && std::time::Instant::now() < until {
        std::thread::sleep(std::time::Duration::from_millis(5));
    }
}

// The app is quitting: window jobs are dropped from now on.
pub(crate) fn begin_exit<R: Runtime>(app: &AppHandle<R>) {
    inner(app).exiting.store(true, Ordering::SeqCst);
}

// Tells the app (its on_change hook) that window `label` changed. A change
// the app makes itself reaches the hook at once, as it always did. One made
// inside Tauri's plugin lock (the plugin's on_event, a page's plain command)
// reaches it a moment later, on the hook's worker: there a hook that opened a
// window would freeze the app (see after_event). So does one made by a window
// job (⌘N, the Dock click), so a slow hook never holds up the next one. Calls
// never overlap and keep their order: while earlier ones wait on the worker,
// or the hook is running on another thread, this one waits on the worker too.
// Several changes to one window while its call waits make one call, at the
// place of the newest. Changes the hook itself makes do not call it again.
pub(crate) fn changed<R: Runtime>(app: &AppHandle<R>, label: &str) {
    let state = inner(app);
    if state.config.on_change.is_none() || IN_HOOK.with(|h| h.get()) {
        return;
    }
    // The gate is held only to decide, never while the hook runs.
    let gate = state.hook_gate.lock().unwrap_or_else(PoisonError::into_inner);
    let defer = IN_PLUGIN.with(|p| p.get()) || ON_WINDOWS_WORKER.with(|w| w.get()) || DEFER_HOOK.with(|d| d.get());
    if !defer && state.hook_q.pending.load(Ordering::SeqCst) == 0 {
        // try_lock: a thread here never waits for the hook (the main thread
        // waiting could stop a hook that is opening a window).
        let free = match state.hook.try_lock() {
            Ok(one) => Some(one),
            // A hook that panicked once does not shut out the next call.
            Err(std::sync::TryLockError::Poisoned(one)) => Some(one.into_inner()),
            Err(std::sync::TryLockError::WouldBlock) => None,
        };
        if let Some(_one) = free {
            drop(gate);
            run_hook(app, label);
            return;
        }
    }
    // A call for this window already waiting skips itself: this newer one,
    // later in the queue, tells the hook (the tabs as they are by then).
    let waiting = |s: &'static Inner<R>| s.hook_waiting.lock().unwrap_or_else(PoisonError::into_inner);
    let seq = state.hook_seq.fetch_add(1, Ordering::SeqCst) as u64;
    waiting(state).insert(label.to_string(), seq);
    let queued = label.to_string();
    let sent = send(
        app,
        Kind::Hook,
        Box::new(move |app| {
            {
                let mut w = waiting(inner(app));
                if w.get(&queued) != Some(&seq) {
                    return;
                }
                w.remove(&queued);
            }
            let _one = inner(app).hook.lock().unwrap_or_else(PoisonError::into_inner);
            run_hook(app, &queued);
        }),
    );
    if !sent {
        let mut w = waiting(state);
        if w.get(label) == Some(&seq) {
            w.remove(label);
        }
    }
    drop(gate);
}

// A window left the layout. When the hook itself closed it (its last tab),
// it still hears of it, once it is done.
fn window_gone<R: Runtime>(app: &AppHandle<R>, label: &str) {
    if !IN_HOOK.with(|h| h.get()) {
        changed(app, label);
        return;
    }
    IN_HOOK.with(|h| h.set(false));
    {
        let _later = DeferHook::enter();
        changed(app, label);
    }
    IN_HOOK.with(|h| h.set(true));
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
    // A hook that panics is the app's bug; the tabs carry on (on every thread
    // alike: the window being closed still closes, the layout is still saved).
    if let Err(payload) = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| hook(app, label))) {
        // Not dropped: a payload whose drop panics would panic here.
        std::mem::forget(payload);
        eprintln!("tauris-ui: the app's on_change hook panicked (window {label})");
    }
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

// `frame`: where to put it; the default size, centred, when None. A panic in
// the app's window hook comes back as an error, so every caller takes back
// the window it recorded (no tabs go into a window nobody sees).
pub(crate) fn open_window<R: Runtime>(
    app: &AppHandle<R>,
    label: &str,
    frame: Option<Frame>,
    focused: bool,
) -> tauri::Result<WebviewWindow<R>> {
    debug_assert!(
        !IN_PLUGIN.with(|p| p.get()),
        "tauris-ui: window {label} opened inside Tauri's plugin lock; it would freeze the app (use after_event)"
    );
    let opened = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| build_window(app, label, frame, focused)))
        .unwrap_or_else(|payload| {
            std::mem::forget(payload); // its drop could panic too
            Err(tauri::Error::Io(std::io::Error::other(format!(
                "window {label} did not open: the app's window hook panicked"
            ))))
        });
    if opened.is_ok() {
        inner(app).model().opened(label);
    }
    opened
}

fn build_window<R: Runtime>(
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
    if let Err(e) = open_window(app, &label, frame, focused) {
        state.model().remove_win(&label);
        return Err(e);
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
        // A window still opening takes nothing: if it fails, what it held goes
        // with it. Nor does one about to close.
        let win = m.win(label)?;
        if win.opening || win.leaving {
            return None;
        }
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
    // The tab goes, and a window left empty leaves the layout, in one go: a
    // tab opened meanwhile (⌘T, a Dock click) never lands in a window about to
    // close, but in a new one.
    let closed = {
        let mut m = inner(app).model();
        if !m.win(label).is_some_and(|w| w.tabs.contains(&tab)) {
            return;
        }
        m.detach(label, tab);
        m.tabs.remove(&tab);
        if m.win(label).is_some_and(|w| w.tabs.is_empty()) {
            m.close_win(label);
            Some(m.wins.is_empty())
        } else {
            None
        }
    };
    match closed {
        None => notify(app, label),
        Some(last) => {
            window_gone(app, label);
            // The user closed the last tab there was: the next launch starts fresh.
            if last {
                crate::persist::forget(app);
            }
            if let Some(w) = app.get_webview_window(label) {
                let _ = w.destroy();
            }
        }
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
    inner(app).model().frontmost()
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
        } else {
            // It closes: a tab opened before it is gone goes elsewhere.
            win.leaving = true;
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
    let (source, label, at) = {
        let mut m = state.model();
        let Some(source) = m.wins.iter().find(|w| w.tabs.contains(&tab)).map(|w| w.label.clone()) else {
            return Ok(None);
        };
        let Some(win) = m.win(&source) else { return Ok(None) };
        if win.tabs.len() == 1 {
            return Ok(Some(source)); // already alone in its window
        }
        let at = win.tabs.iter().position(|t| *t == tab).unwrap_or(usize::MAX);
        let active = win.active;
        m.detach(&source, tab);
        let chosen = m.win(&source).and_then(|w| w.active);
        let label = m.create_win(vec![tab]);
        (source, label, (at, active, chosen))
    };
    if let Err(e) = open_window(app, &label, None, true) {
        // No new window: the tab goes back where it was.
        let back = {
            let mut m = state.model();
            // Anything opened in the new window meanwhile goes back with the tab.
            let others = m.take_win(&label, tab);
            let back = m.put_back(&source, tab, at.0, at.1, at.2);
            for other in others {
                match &back {
                    Some(back) => m.attach(back, other, usize::MAX),
                    None => drop(m.tabs.remove(&other)),
                }
            }
            back
        };
        if let Some(back) = back {
            notify(app, &back);
        }
        return Err(e);
    }
    notify(app, &source);
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
        crate::persist::save(app, true);
    }
}

pub(crate) fn bring_to_front<R: Runtime>(app: &AppHandle<R>, label: &str) {
    let mut m = inner(app).model();
    if let Some(pos) = m.wins.iter().position(|w| w.label == label) {
        let mut win = m.wins.remove(pos);
        // Focused again: it did not close after all (the app kept it open).
        win.leaving = false;
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
    if frontmost(app).is_none() && crate::persist::restore_saved(app) {
        // Another thread is opening the windows: the tab waits for them and
        // goes in the front one, not a window of its own. Not on the main
        // thread, which may be the one they need to open.
        let main = std::thread::current().name() == Some("main");
        let until = std::time::Instant::now() + std::time::Duration::from_secs(3);
        // All of them: the last to open is the one in front.
        while !main && inner(app).restoring.load(Ordering::SeqCst) {
            if std::time::Instant::now() >= until {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
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
        // The window closed meanwhile: the tab gets a window of its own.
        if m.win(&label).is_none() {
            drop(m);
            let (label, ids) = create_window(app, vec![tab], None, true)?;
            bring_up(app, &label);
            return Ok(ids[0]);
        }
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
        // The window closed meanwhile: the tabs get a window of their own.
        if m.win(&label).is_none() {
            drop(m);
            let (label, ids) = create_window(app, tabs, None, true)?;
            bring_up(app, &label);
            return Ok(ids);
        }
        let mut rest = tabs.into_iter();
        let mut ids = vec![];
        if replace_active {
            let active = m.win(&label).and_then(|w| w.active).filter(|id| m.tabs.contains_key(id));
            // The first new tab replaces the active one only if there is one.
            if let Some(id) = active {
                if let (Some(new), Some(tab)) = (rest.next(), m.tabs.get_mut(&id)) {
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
