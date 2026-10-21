// The tab lists. Rust owns every window's tabs; pages ask for their own state.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::HashMap;
use std::time::Instant;

/// The app's own data on a tab (what it shows, what was typed, ...).
pub type Fields = Map<String, Value>;

// Keys a tab carries itself. An app's field of the same name would clash with
// them in the JSON, so such fields are dropped.
const RESERVED: [&str; 2] = ["id", "title"];

pub(crate) fn clean(mut fields: Fields) -> Fields {
    for key in RESERVED {
        fields.remove(key);
    }
    fields
}

/// A tab as pages see it: an id, a title and whatever fields the app keeps on it.
/// The fields sit next to `id` and `title` in the JSON, so `tab.view` in a page
/// is `fields["view"]` here. `id` and `title` cannot be used as field names.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Tab {
    /// Unique among the app's tabs; given by the library.
    pub id: u64,
    /// What the strip shows.
    pub title: String,
    /// The app's own data on the tab.
    #[serde(flatten)]
    pub fields: Fields,
}

impl Tab {
    /// One of the app's fields, if the tab has it.
    pub fn get(&self, key: &str) -> Option<&Value> {
        self.fields.get(key)
    }

    /// One of the app's fields as text: `tab.str("view") == Some("users")`.
    /// None when the tab has no such field or it is not text.
    pub fn str(&self, key: &str) -> Option<&str> {
        self.fields.get(key).and_then(Value::as_str)
    }
}

/// A tab to be created.
#[derive(Clone, Debug)]
pub struct NewTab {
    /// What the strip shows.
    pub title: String,
    /// The app's own data on the tab.
    pub fields: Fields,
}

impl NewTab {
    /// A tab with this title and no fields.
    pub fn new(title: impl Into<String>) -> Self {
        NewTab { title: title.into(), fields: Fields::new() }
    }

    /// Sets one field of the tab. `id` and `title` are reserved and ignored.
    pub fn with(mut self, key: &str, value: impl Into<Value>) -> Self {
        if !RESERVED.contains(&key) {
            self.fields.insert(key.to_string(), value.into());
        }
        self
    }
}

#[derive(Default)]
pub(crate) struct Strip {
    pub height: f64,
    pub mids: Vec<f64>,
}

pub(crate) struct Win {
    pub label: String,
    pub tabs: Vec<u64>,
    pub active: Option<u64>,
    pub strip: Strip,
    // Where it was last seen, in logical pixels; None until moved or resized.
    pub frame: Option<Frame>,
    // The page asks before a tab closes (it has an onBeforeClose), as set by
    // its newest mount (`guard_seq`).
    pub guarded: bool,
    pub guard_seq: u64,
    // The page agreed to close the whole window.
    pub may_close: bool,
    // When the page was last asked to close the window, and whether it has
    // answered that it is asking its tabs. A page that never answers (hung,
    // crashed) cannot keep its window open.
    pub close_asked_at: Option<Instant>,
    pub close_seen: bool,
}

#[derive(Clone, Copy, Serialize, Deserialize)]
pub(crate) struct Frame {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
    #[serde(default)]
    pub maximized: bool,
}

pub(crate) struct Drag {
    pub tab: u64,
    pub window: String,
    pub grab: (f64, f64),
    pub hover: Option<(String, usize)>,
}

// A window that has just closed, kept for a moment: when the app quits, every
// window closes within milliseconds, and the saved layout must still hold them.
pub(crate) struct Closed {
    pub win: Win,
    pub tabs: Vec<Tab>,
    pub at: Instant,
}

pub(crate) struct Model {
    prefix: String,
    next_tab: u64,
    next_win: u64,
    pub tabs: HashMap<u64, Tab>,
    // Most recently focused window last.
    pub wins: Vec<Win>,
    pub drag: Option<Drag>,
    // When the layout last changed and is not saved yet, and when the oldest
    // unsaved change happened (a save never waits longer than a few seconds).
    pub changed_at: Option<Instant>,
    pub unsaved_since: Option<Instant>,
    pub closing: Vec<Closed>,
    // The user closed the last tab there was: nothing is left to remember.
    pub emptied: bool,
}

impl Model {
    pub fn new(prefix: &str) -> Self {
        Model {
            prefix: prefix.to_string(),
            next_tab: 0,
            next_win: 0,
            tabs: HashMap::new(),
            wins: Vec::new(),
            drag: None,
            changed_at: None,
            unsaved_since: None,
            closing: Vec::new(),
            emptied: false,
        }
    }

    pub fn changed(&mut self) {
        let now = Instant::now();
        self.changed_at = Some(now);
        self.unsaved_since.get_or_insert(now);
    }

    // The layout has been written (or forgotten).
    pub fn saved(&mut self) {
        self.changed_at = None;
        self.unsaved_since = None;
    }

    pub fn win(&mut self, label: &str) -> Option<&mut Win> {
        self.wins.iter_mut().find(|w| w.label == label)
    }

    pub fn create_tab(&mut self, tab: NewTab) -> u64 {
        self.next_tab += 1;
        let id = self.next_tab;
        self.tabs.insert(id, Tab { id, title: tab.title, fields: clean(tab.fields) });
        id
    }

    pub fn create_win(&mut self, tabs: Vec<u64>) -> String {
        self.next_win += 1;
        let label = format!("{}{}", self.prefix, self.next_win);
        let active = tabs.first().copied();
        self.wins.push(Win {
            label: label.clone(),
            tabs,
            active,
            strip: Strip::default(),
            frame: None,
            guarded: false,
            guard_seq: 0,
            may_close: false,
            close_asked_at: None,
            close_seen: false,
        });
        self.changed();
        label
    }

    // Forgets a window and the tabs in it.
    pub fn remove_win(&mut self, label: &str) {
        if let Some(pos) = self.wins.iter().position(|w| w.label == label) {
            let win = self.wins.remove(pos);
            for tab in win.tabs {
                self.tabs.remove(&tab);
            }
        }
    }

    // A window closed: it leaves the open windows but is kept for a moment.
    pub fn close_win(&mut self, label: &str) {
        let Some(pos) = self.wins.iter().position(|w| w.label == label) else { return };
        let win = self.wins.remove(pos);
        let tabs = win.tabs.iter().filter_map(|id| self.tabs.remove(id)).collect();
        self.closing.push(Closed { win, tabs, at: Instant::now() });
        self.changed();
    }

    // Takes a tab out of a window and picks the neighbour as the new active tab.
    pub fn detach(&mut self, label: &str, tab: u64) {
        let Some(win) = self.win(label) else { return };
        let Some(pos) = win.tabs.iter().position(|t| *t == tab) else { return };
        win.tabs.remove(pos);
        if win.active == Some(tab) {
            let next = pos.min(win.tabs.len().saturating_sub(1));
            win.active = win.tabs.get(next).copied();
        }
    }

    pub fn attach(&mut self, label: &str, tab: u64, index: usize) {
        let Some(win) = self.win(label) else { return };
        let index = index.min(win.tabs.len());
        win.tabs.insert(index, tab);
        win.active = Some(tab);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn model() -> Model {
        Model::new("t")
    }

    #[test]
    fn reserved_fields_are_dropped() {
        let tab = NewTab::new("a").with("id", 7).with("title", "x").with("view", "home");
        assert_eq!(tab.fields.len(), 1);
        let mut m = model();
        let id = m.create_tab(NewTab { title: "b".into(), fields: serde_json::from_str(r#"{"id":9,"q":1}"#).unwrap() });
        assert!(!m.tabs[&id].fields.contains_key("id"));
        assert!(m.tabs[&id].fields.contains_key("q"));
    }

    #[test]
    fn a_tab_serialises_flat_and_reads_back() {
        let tab =
            Tab { id: 3, title: "T".into(), fields: serde_json::from_str(r#"{"view":"home","query":""}"#).unwrap() };
        let json = serde_json::to_string(&tab).unwrap();
        assert_eq!(json.matches("\"id\"").count(), 1);
        let back: Tab = serde_json::from_str(&json).unwrap();
        assert_eq!(back.fields["view"], "home");
    }

    #[test]
    fn fields_are_read_without_panicking() {
        let tab = Tab { id: 1, title: "T".into(), fields: serde_json::from_str(r#"{"view":"users","n":3}"#).unwrap() };
        assert_eq!(tab.str("view"), Some("users"));
        assert_eq!(tab.str("missing"), None);
        assert_eq!(tab.str("n"), None);
        assert_eq!(tab.get("n").and_then(Value::as_u64), Some(3));
    }

    #[test]
    fn windows_are_labelled_with_the_prefix() {
        let mut m = model();
        let a = m.create_tab(NewTab::new("a"));
        assert_eq!(m.create_win(vec![a]), "t1");
        assert_eq!(m.create_win(vec![]), "t2");
    }

    #[test]
    fn detaching_the_active_tab_picks_a_neighbour() {
        let mut m = model();
        let ids: Vec<u64> = (0..3).map(|i| m.create_tab(NewTab::new(format!("{i}")))).collect();
        let w = m.create_win(ids.clone());
        m.win(&w).unwrap().active = Some(ids[1]);
        m.detach(&w, ids[1]);
        assert_eq!(m.win(&w).unwrap().tabs, vec![ids[0], ids[2]]);
        assert_eq!(m.win(&w).unwrap().active, Some(ids[2]));
        m.detach(&w, ids[2]);
        assert_eq!(m.win(&w).unwrap().active, Some(ids[0]));
    }

    #[test]
    fn attach_activates_and_clamps_the_index() {
        let mut m = model();
        let a = m.create_tab(NewTab::new("a"));
        let b = m.create_tab(NewTab::new("b"));
        let w = m.create_win(vec![a]);
        m.attach(&w, b, 99);
        assert_eq!(m.win(&w).unwrap().tabs, vec![a, b]);
        assert_eq!(m.win(&w).unwrap().active, Some(b));
    }

    #[test]
    fn a_closed_window_is_kept_for_a_moment() {
        let mut m = model();
        let a = m.create_tab(NewTab::new("a"));
        let w = m.create_win(vec![a]);
        m.close_win(&w);
        assert!(m.wins.is_empty() && m.tabs.is_empty());
        assert_eq!(m.closing.len(), 1);
        assert_eq!(m.closing[0].tabs[0].title, "a");
    }

    #[test]
    fn removing_a_window_forgets_its_tabs() {
        let mut m = model();
        let a = m.create_tab(NewTab::new("a"));
        let w = m.create_win(vec![a]);
        m.remove_win(&w);
        assert!(m.wins.is_empty() && m.tabs.is_empty());
    }
}
