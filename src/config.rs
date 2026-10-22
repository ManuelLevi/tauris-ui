use crate::model::NewTab;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;
use tauri::{AppHandle, Manager, Runtime, WebviewWindowBuilder, Wry};

pub(crate) type WindowHook<R> = dyn for<'a> Fn(WebviewWindowBuilder<'a, R, AppHandle<R>>) -> WebviewWindowBuilder<'a, R, AppHandle<R>>
    + Send
    + Sync;
pub(crate) type NewTabHook<R> = dyn Fn(&AppHandle<R>) -> NewTab + Send + Sync;
pub(crate) type LayoutHook<R> = dyn Fn(&AppHandle<R>) -> Option<PathBuf> + Send + Sync;
pub(crate) type ChangeHook<R> = dyn Fn(&AppHandle<R>, &str) + Send + Sync;

/// How the tabs behave. Every setting has a default; change only what you need.
pub struct Config<R: Runtime = Wry> {
    pub(crate) window_url: String,
    pub(crate) window_prefix: String,
    pub(crate) window_size: (f64, f64),
    pub(crate) min_window_size: (f64, f64),
    pub(crate) traffic_lights: Option<(f64, f64)>,
    pub(crate) window_hook: Option<Arc<WindowHook<R>>>,
    pub(crate) new_tab: Arc<NewTabHook<R>>,
    pub(crate) layout_file: Option<Arc<LayoutHook<R>>>,
    pub(crate) on_change: Option<Arc<ChangeHook<R>>>,
    pub(crate) drop_slack: (f64, f64),
    pub(crate) drag_opacity: f64,
    pub(crate) settle: Duration,
}

impl<R: Runtime> Default for Config<R> {
    fn default() -> Self {
        Config {
            window_url: "index.html".into(),
            window_prefix: "tabs-".into(),
            window_size: (1180.0, 760.0),
            min_window_size: (560.0, 360.0),
            traffic_lights: Some((16.0, 23.0)),
            window_hook: None,
            new_tab: Arc::new(|_| NewTab::new("New tab")),
            layout_file: Some(Arc::new(|app| app.path().app_data_dir().ok().map(|d| d.join("tabs.json")))),
            on_change: None,
            drop_slack: (10.0, 16.0),
            drag_opacity: 1.0,
            settle: Duration::from_secs(1),
        }
    }
}

impl Config<Wry> {
    /// The default settings, for an app on Tauri's usual runtime.
    pub fn new() -> Self {
        Self::default()
    }
}

impl<R: Runtime> Config<R> {
    /// The page every tab window loads (default "index.html").
    pub fn window_url(mut self, url: &str) -> Self {
        self.window_url = url.into();
        self
    }

    /// Tab windows are labelled `<prefix>1`, `<prefix>2`, ... (default "tabs-").
    /// The window capability must cover them: `"windows": ["tabs-*"]`.
    pub fn window_prefix(mut self, prefix: &str) -> Self {
        self.window_prefix = prefix.into();
        self
    }

    /// Size of a new window, in logical pixels (default 1180 x 760).
    pub fn window_size(mut self, width: f64, height: f64) -> Self {
        self.window_size = (width, height);
        self
    }

    /// The smallest a window can be made, in logical pixels (default 560 x 360).
    pub fn min_window_size(mut self, width: f64, height: f64) -> Self {
        self.min_window_size = (width, height);
        self
    }

    /// Puts the window's own title bar back, with the tab strip below it. By
    /// default the tabs sit in the title bar, level with the window buttons.
    pub fn native_title_bar(mut self) -> Self {
        self.traffic_lights = None;
        self
    }

    /// Where the macOS window buttons sit when the tabs are in the title bar:
    /// `x` from the left edge, `y` to the buttons' centre (default 16, 23,
    /// level with the default tabs). The strip leaves room for them.
    pub fn window_buttons_at(mut self, x: f64, y: f64) -> Self {
        self.traffic_lights = Some((x, y));
        self
    }

    /// Dresses every tab window: title, background, anything the builder offers.
    pub fn window(
        mut self,
        hook: impl for<'a> Fn(WebviewWindowBuilder<'a, R, AppHandle<R>>) -> WebviewWindowBuilder<'a, R, AppHandle<R>>
            + Send
            + Sync
            + 'static,
    ) -> Self {
        self.window_hook = Some(Arc::new(hook));
        self
    }

    /// The tab the + button, ⌘T and a new window start with (default "New tab").
    pub fn new_tab(mut self, make: impl Fn(&AppHandle<R>) -> NewTab + Send + Sync + 'static) -> Self {
        self.new_tab = Arc::new(make);
        self
    }

    /// Where the layout is remembered between runs (default: `tabs.json` in the
    /// app's data folder). Return None to remember nothing.
    pub fn layout_file(mut self, file: impl Fn(&AppHandle<R>) -> Option<PathBuf> + Send + Sync + 'static) -> Self {
        self.layout_file = Some(Arc::new(file));
        self
    }

    /// Remember no layout: the app always starts on one new window.
    pub fn no_layout(mut self) -> Self {
        self.layout_file = None;
        self
    }

    /// Called with a window's label after anything about its tabs changes:
    /// opened, closed, moved, activated, or a title or field updated (from
    /// Rust or from the page). A change the app makes from its own code reaches
    /// the hook at once, on that thread. One made inside Tauri's plugin lock
    /// (the plugin's own events, the page's commands) or by a window job (⌘N,
    /// ⌘T, the Dock click) reaches it a moment later on a worker thread, so the
    /// hook may open windows there too (and must not need the main thread).
    /// Calls never overlap and keep their order (a change made while earlier
    /// calls wait reaches the hook after them, on the worker); a window that
    /// already has a call waiting gets no second one. It may use `app.tabs()`.
    /// Changes it makes directly do not call it again; a window it closes is
    /// reported once that window is gone.
    pub fn on_change(mut self, hook: impl Fn(&AppHandle<R>, &str) + Send + Sync + 'static) -> Self {
        self.on_change = Some(Arc::new(hook));
        self
    }

    /// How far above and below another window's strip a dragged tab still
    /// counts as on it (default 10 and 16 pixels).
    pub fn drop_slack(mut self, above: f64, below: f64) -> Self {
        self.drop_slack = (above, below);
        self
    }

    /// How see-through the window is while a tab is dragged out in it:
    /// 1.0 opaque (default) down to 0.2.
    pub fn drag_opacity(mut self, opacity: f64) -> Self {
        self.drag_opacity = opacity.clamp(0.2, 1.0);
        self
    }
}
