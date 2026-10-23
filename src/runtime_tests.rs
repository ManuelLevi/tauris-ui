// The window logic on Tauri's test runtime: real apps and windows, no screen.

use crate::model::{Fields, NewTab};
use crate::{init, persist, windows, Config, TabsExt};
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use tauri::test::{mock_builder, mock_context, noop_assets, MockRuntime};
use tauri::{App, Manager};

fn app(config: Config<MockRuntime>) -> App<MockRuntime> {
    mock_builder().plugin(init(config)).build(mock_context(noop_assets())).expect("test app")
}

fn quiet() -> Config<MockRuntime> {
    Config::default().no_layout().new_tab(|_| NewTab::new("Home").with("view", "home"))
}

fn temp_file(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("tauris-ui-test-{}-{}", std::process::id(), name));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir.join("tabs.json")
}

fn titles(app: &App<MockRuntime>) -> Vec<Vec<String>> {
    app.tabs().windows().iter().map(|w| w.tabs.iter().map(|t| t.title.clone()).collect()).collect()
}

#[test]
fn start_opens_one_window_with_the_starting_tab() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    app.tabs().start().unwrap(); // a second call does nothing
    assert_eq!(titles(&app), vec![vec!["Home"]]);
    assert_eq!(app.tabs().frontmost().as_deref(), Some("tabs-1"));
}

#[test]
fn tabs_open_in_the_frontmost_window_and_become_active() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let users = app.tabs().open(NewTab::new("Users").with("view", "users")).unwrap();
    let w = &app.tabs().windows()[0];
    assert_eq!(w.tabs.len(), 2);
    assert_eq!(w.active, Some(users));
    // The same view is brought forward, not opened twice; a tab without the field is skipped.
    let again = app.tabs().open_or_focus(NewTab::new("Users"), |t| t.str("view") == Some("users")).unwrap();
    assert_eq!(again, users);
    assert_eq!(app.tabs().windows()[0].tabs.len(), 2);
}

#[test]
fn open_many_can_take_over_the_active_tab() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let ids = app.tabs().open_many(vec![NewTab::new("A"), NewTab::new("B")], true).unwrap();
    assert_eq!(titles(&app), vec![vec!["A", "B"]]);
    assert_eq!(app.tabs().windows()[0].active, ids.last().copied());
}

#[test]
fn closing_activating_and_updating_tabs() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let a = app.tabs().open(NewTab::new("A")).unwrap();
    let b = app.tabs().open(NewTab::new("B")).unwrap();
    app.tabs().activate_tab(a);
    assert_eq!(app.tabs().windows()[0].active, Some(a));
    app.tabs().close_tab(a);
    assert_eq!(titles(&app), vec![vec!["Home", "B"]]);
    let fields: Fields = serde_json::from_str(r#"{"id": 99, "title": "x", "query": "abc"}"#).unwrap();
    app.tabs().update_tab(b, "B2", fields);
    let tab = app.tabs().windows()[0].tabs.iter().find(|t| t.id == b).cloned().unwrap();
    assert_eq!(tab.title, "B2");
    assert_eq!(tab.str("query"), Some("abc"));
    assert!(tab.get("id").is_none() && tab.get("title").is_none());
}

#[test]
fn a_window_cannot_touch_another_windows_tab() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let second = app.tabs().new_window().unwrap();
    let theirs = app.tabs().windows().iter().find(|w| w.label == second).unwrap().tabs[0].id;
    let handle = app.handle();
    assert!(!windows::owns(handle, "tabs-1", theirs));
    windows::remove_tab(handle, "tabs-1", theirs);
    windows::move_tab(handle, "tabs-1", theirs, 0);
    assert_eq!(titles(&app), vec![vec!["Home"], vec!["Home"]]);
}

#[test]
fn on_change_fires_and_does_not_call_itself_again() {
    let calls = Arc::new(AtomicUsize::new(0));
    let seen = calls.clone();
    let config = quiet().on_change(move |app, _label| {
        seen.fetch_add(1, Ordering::SeqCst);
        // A change made from the hook must not call the hook again.
        let _ = app.tabs().new_tab();
    });
    let app = app(config);
    app.tabs().start().unwrap();
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    let before = calls.load(Ordering::SeqCst);
    app.tabs().open(NewTab::new("X")).unwrap();
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    assert_eq!(calls.load(Ordering::SeqCst), before + 1);
    // Page-side changes (inside Tauri's lock) reach the hook too, on its worker.
    let id = app.tabs().windows()[0].tabs[0].id;
    {
        let _locked = windows::InPlugin::enter();
        windows::update(app.handle(), id, "renamed".into(), Fields::new(), false);
    }
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    assert_eq!(calls.load(Ordering::SeqCst), before + 2);
}

#[test]
fn the_layout_comes_back_after_a_restart() {
    let file = temp_file("restart");
    let path = file.clone();
    let first = app(quiet().layout_file(move |_| Some(path.clone())));
    first.tabs().start().unwrap();
    first.tabs().open(NewTab::new("Users").with("view", "users")).unwrap();
    first.tabs().new_window_with(NewTab::new("Report").with("id_of_report", 7)).unwrap();
    persist::save(first.handle(), true);

    let path = file.clone();
    let second = app(quiet().layout_file(move |_| Some(path.clone())));
    second.tabs().start().unwrap();
    assert_eq!(titles(&second), vec![vec!["Home", "Users"], vec!["Report"]]);
    let users = &second.tabs().windows()[0].tabs[1];
    assert_eq!(users.str("view"), Some("users"));
    assert_eq!(second.tabs().windows()[0].active, Some(users.id));
}

#[test]
fn quitting_keeps_every_window() {
    let file = temp_file("quit");
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    app.tabs().new_window_with(NewTab::new("Second")).unwrap();
    app.tabs().new_window_with(NewTab::new("Third")).unwrap();
    // A quit closes every window within milliseconds.
    for label in ["tabs-1", "tabs-2", "tabs-3"] {
        windows::forget_window(app.handle(), label);
    }
    let saved: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&file).unwrap()).unwrap();
    assert_eq!(saved.as_array().unwrap().len(), 3);
}

#[test]
fn an_unreadable_layout_is_kept_aside() {
    let file = temp_file("unreadable");
    std::fs::write(&file, "{ not json").unwrap();
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    assert_eq!(titles(&app), vec![vec!["Home"]]);
    assert!(file.with_extension("unreadable").is_file());
}

// A save that failed (a full disk) is tried again: the changes stay unsaved.
#[test]
fn a_layout_that_could_not_be_written_is_written_next_time() {
    let file = temp_file("retry");
    // A folder where the file goes: writing it fails.
    std::fs::create_dir_all(&file).unwrap();
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    app.tabs().open(NewTab::new("Users")).unwrap();
    persist::save(app.handle(), true);
    assert!(file.is_dir());
    std::fs::remove_dir(&file).unwrap();
    persist::save(app.handle(), true);
    assert!(file.is_file(), "the second save did not happen");
}

// Remembered windows that all fail to open are kept aside, not overwritten
// by the new window's layout.
#[test]
fn remembered_windows_that_cannot_open_are_kept_aside() {
    let file = temp_file("unopened");
    let path = file.clone();
    let first = app(quiet().layout_file(move |_| Some(path.clone())));
    first.tabs().start().unwrap();
    first.tabs().open(NewTab::new("Users")).unwrap();
    persist::save(first.handle(), true);
    let fail = Arc::new(std::sync::atomic::AtomicBool::new(true));
    let path = file.clone();
    let second = app(quiet().layout_file(move |_| Some(path.clone())).window(move |w| {
        if fail.swap(false, Ordering::SeqCst) {
            panic!("the remembered window failed");
        }
        w
    }));
    second.tabs().start().unwrap();
    assert_eq!(titles(&second), [["Home"]]);
    let aside: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(file.with_extension("unopened")).unwrap()).unwrap();
    assert_eq!(aside[0]["tabs"].as_array().unwrap().len(), 2, "the remembered layout was not kept");
}

// One remembered window of two fails to open: the whole layout is kept aside,
// so the next save does not lose that window's tabs.
#[test]
fn a_remembered_window_that_cannot_open_is_kept_aside() {
    let file = temp_file("one-unopened");
    let path = file.clone();
    let first = app(quiet().layout_file(move |_| Some(path.clone())));
    first.tabs().start().unwrap();
    first.tabs().new_window_with(NewTab::new("Report")).unwrap();
    persist::save(first.handle(), true);
    let fail = Arc::new(std::sync::atomic::AtomicBool::new(true));
    let path = file.clone();
    let second = app(quiet().layout_file(move |_| Some(path.clone())).window(move |w| {
        if fail.swap(false, Ordering::SeqCst) {
            panic!("the first remembered window failed");
        }
        w
    }));
    second.tabs().start().unwrap();
    assert_eq!(titles(&second), [["Report"]]);
    let aside: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(file.with_extension("unopened")).unwrap()).unwrap();
    assert_eq!(aside.as_array().unwrap().len(), 2, "the window that failed was not kept");
}

// A save after a pause leaves out a window closed a moment ago (it does not
// come back after a crash); the save as the app quits keeps it.
#[test]
fn only_the_save_at_quit_keeps_a_window_just_closed() {
    let file = temp_file("just-closed");
    let path = file.clone();
    let mut config = quiet().layout_file(move |_| Some(path.clone()));
    config.settle = std::time::Duration::ZERO;
    let app = app(config);
    app.tabs().start().unwrap();
    app.tabs().new_window_with(NewTab::new("Second")).unwrap();
    windows::forget_window(app.handle(), "tabs-2");
    persist::save(app.handle(), false);
    let saved: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&file).unwrap()).unwrap();
    assert_eq!(saved.as_array().unwrap().len(), 1, "a window closed a moment ago came back");
    windows::forget_window(app.handle(), "tabs-1");
    let saved: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&file).unwrap()).unwrap();
    assert_eq!(saved.as_array().unwrap().len(), 2, "quitting lost a window");
}

// Closing the last tab forgets the layout, unless a window opened meanwhile.
#[test]
fn forgetting_keeps_a_window_opened_meanwhile() {
    let file = temp_file("forget-guard");
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    persist::save(app.handle(), true);
    assert!(file.is_file());
    persist::forget(app.handle());
    assert!(file.is_file(), "a layout with a window open was deleted");
}

// A restore already on its way: nothing else opens a window of its own.
#[test]
fn a_restore_on_its_way_opens_no_other_window() {
    let app = app(quiet());
    windows::inner(app.handle()).restoring.store(true, Ordering::SeqCst);
    persist::restore(app.handle()).unwrap();
    assert_eq!(app.tabs().window_count(), 0);
    windows::inner(app.handle()).restoring.store(false, Ordering::SeqCst);
}

// A tab dropped onto another window's strip lands there, with anything the
// app had put in the dragged window; that window leaves the layout.
#[test]
fn a_dropped_tab_lands_in_the_window_under_it() {
    let heard = Arc::new(std::sync::Mutex::new(Vec::new()));
    let h = heard.clone();
    let app = app(quiet().on_change(move |_, label| h.lock().unwrap().push(label.to_string())));
    app.tabs().start().unwrap();
    let moving = app.tabs().new_window_with(NewTab::new("Report")).unwrap();
    let report = app.tabs().windows()[1].tabs[0].id;
    let extra = {
        let mut m = windows::inner(app.handle()).model();
        let extra = m.create_tab(NewTab::new("Extra"));
        m.win(&moving).unwrap().tabs.push(extra);
        m.drag = Some(crate::model::Drag { tab: report, window: moving.clone(), grab: (0.0, 0.0), hover: None });
        extra
    };
    let window = app.get_webview_window(&moving).unwrap();
    crate::drag::finish(app.handle(), &window, report, Some(("tabs-1".into(), 0)));
    assert_eq!(titles(&app), [["Report", "Home", "Extra"]]);
    assert!(app.tabs().tab(extra).is_some());
    assert_eq!(app.tabs().windows()[0].active, Some(report));
    // The app hears of both windows: the one the tab went to, and the one that went.
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    let heard = heard.lock().unwrap();
    assert!(heard.contains(&"tabs-1".to_string()) && heard.contains(&moving), "{heard:?}");
}

// While remembered windows are opening, nothing overwrites the file.
#[test]
fn nothing_is_saved_while_windows_are_restored() {
    let file = temp_file("restoring");
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    app.tabs().open(NewTab::new("Users")).unwrap();
    windows::inner(app.handle()).restoring.store(true, Ordering::SeqCst);
    persist::save(app.handle(), true);
    assert!(!file.is_file(), "saved while restoring");
    windows::inner(app.handle()).restoring.store(false, Ordering::SeqCst);
    persist::save(app.handle(), true);
    assert!(file.is_file(), "the save after the restore did not happen");
}

// A start whose window could not open can be tried again.
#[test]
fn a_start_that_failed_can_be_tried_again() {
    let fail = Arc::new(std::sync::atomic::AtomicBool::new(true));
    let f = fail.clone();
    let app = app(quiet().window(move |w| {
        if f.swap(false, Ordering::SeqCst) {
            panic!("the first window failed");
        }
        w
    }));
    assert!(app.tabs().start().is_err());
    app.tabs().start().unwrap();
    assert_eq!(titles(&app), [["Home"]]);
}

#[test]
fn a_tab_moves_to_a_new_window_of_its_own() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let report = app.tabs().open(NewTab::new("Report")).unwrap();
    let label = app.tabs().move_to_new_window(report).unwrap().unwrap();
    assert_eq!(titles(&app), vec![vec!["Home"], vec!["Report"]]);
    // A tab alone in its window stays where it is.
    assert_eq!(app.tabs().move_to_new_window(report).unwrap(), Some(label));
    assert_eq!(app.tabs().move_to_new_window(999).unwrap(), None);
}

#[test]
fn closing_every_tab_forgets_the_layout() {
    let file = temp_file("emptied");
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    persist::save(app.handle(), true);
    assert!(file.is_file());
    let only = app.tabs().windows()[0].tabs[0].id;
    app.tabs().close_tab(only);
    windows::forget_window(app.handle(), "tabs-1"); // the window closing, as Tauri reports it
    assert!(!file.exists(), "the closed tab's title must not come back");
}

#[test]
fn a_page_with_on_before_close_is_asked_before_its_window_closes() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let handle = app.handle();
    assert!(!windows::ask_before_window_closes(handle, "tabs-1"));
    windows::set_guard(handle, "tabs-1", true, 1);
    assert!(windows::ask_before_window_closes(handle, "tabs-1"));
    windows::close_window_agreed(handle, "tabs-1");
    assert!(!windows::ask_before_window_closes(handle, "tabs-1"), "once agreed, it closes without asking again");
}

#[test]
fn steady_changes_are_saved_within_a_few_seconds() {
    let file = temp_file("steady");
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    app.tabs().open(NewTab::new("Typing")).unwrap();
    // Changes keep coming (never settling), but the first unsaved one is old.
    {
        let mut m = windows::inner(app.handle()).model();
        m.changed();
        m.unsaved_since = Some(std::time::Instant::now() - std::time::Duration::from_secs(6));
    }
    persist::save(app.handle(), false);
    assert!(std::fs::read_to_string(&file).unwrap().contains("Typing"));
}

#[test]
fn the_newest_mount_decides_the_close_guard_and_a_reload_clears_it() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let handle = app.handle();
    windows::set_guard(handle, "tabs-1", true, 2);
    windows::set_guard(handle, "tabs-1", false, 1); // a late message from an older mount
    assert!(windows::ask_before_window_closes(handle, "tabs-1"));
    windows::page_loading(handle, "tabs-1");
    assert!(!windows::ask_before_window_closes(handle, "tabs-1"), "a reloading page cannot answer");
    windows::set_guard(handle, "tabs-1", true, 1); // the reloaded page mounts again from 1
    assert!(windows::ask_before_window_closes(handle, "tabs-1"));
}

#[test]
fn closing_from_rust_respects_the_guard_when_asked_to() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let a = app.tabs().open(NewTab::new("A")).unwrap();
    let b = app.tabs().open(NewTab::new("B")).unwrap();
    windows::set_guard(app.handle(), "tabs-1", true, 1);
    app.tabs().request_close_tab(a); // the page is asked; nothing closes yet
    assert!(app.tabs().tab(a).is_some());
    app.tabs().close_tab(b); // closes at once
    assert!(app.tabs().tab(b).is_none());
    assert_eq!(
        app.tabs().open_in("tabs-1", NewTab::new("C")).map(|id| app.tabs().tab(id).unwrap().title),
        Some("C".into())
    );
    assert_eq!(app.tabs().open_in("nope", NewTab::new("D")), None);
}

#[test]
fn on_change_hears_about_a_window_closing() {
    let heard = Arc::new(std::sync::Mutex::new(Vec::<String>::new()));
    let log = heard.clone();
    let app = app(quiet().on_change(move |_, label| log.lock().unwrap().push(label.to_string())));
    app.tabs().start().unwrap();
    let second = app.tabs().new_window().unwrap();
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    heard.lock().unwrap().clear();
    {
        let _locked = windows::InPlugin::enter(); // as the Destroyed event runs it
        windows::forget_window(app.handle(), &second);
    }
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    assert_eq!(*heard.lock().unwrap(), vec![second]);
}

#[test]
fn a_page_that_never_answers_cannot_keep_its_window_open() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let handle = app.handle();
    windows::set_guard(handle, "tabs-1", true, 1);
    assert!(windows::ask_before_window_closes(handle, "tabs-1"));
    // A page that answers keeps being asked.
    windows::close_asked(handle, "tabs-1");
    assert!(windows::ask_before_window_closes(handle, "tabs-1"));
    // One that stays silent past the limit lets the next press close the window.
    windows::inner(handle).model().win("tabs-1").unwrap().close_asked_at =
        Some(std::time::Instant::now() - windows::UNANSWERED);
    assert!(!windows::ask_before_window_closes(handle, "tabs-1"));
}

#[test]
fn a_panicking_hook_is_called_again_next_time() {
    let calls = Arc::new(AtomicUsize::new(0));
    let seen = calls.clone();
    let app = app(quiet().on_change(move |_, _| {
        if seen.fetch_add(1, Ordering::SeqCst) == 0 {
            panic!("the app's hook failed once");
        }
    }));
    let handle = app.handle().clone();
    // The panic stops at the hook: the change that called it carries on.
    let first = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| windows::changed(&handle, "x")));
    assert!(first.is_ok());
    windows::changed(&handle, "x");
    assert_eq!(calls.load(Ordering::SeqCst), 2);
}

#[test]
fn restored_windows_reach_on_change() {
    let file = temp_file("restored-hook");
    let path = file.clone();
    let first = app(quiet().layout_file(move |_| Some(path.clone())));
    first.tabs().start().unwrap();
    persist::save(first.handle(), true);
    let heard = Arc::new(AtomicUsize::new(0));
    let count = heard.clone();
    let path = file.clone();
    let second = app(quiet().layout_file(move |_| Some(path.clone())).on_change(move |_, _| {
        count.fetch_add(1, Ordering::SeqCst);
    }));
    second.tabs().start().unwrap();
    windows::settle(second.handle(), std::time::Duration::from_secs(2));
    assert_eq!(heard.load(Ordering::SeqCst), 1);
}

// A page command needs four matching entries: the function, the
// generate_handler! list, build.rs (which makes its permission) and the
// default permission set.
#[test]
fn every_command_is_registered_and_allowed() {
    fn names_between(text: &str, start: &str, end: &str) -> Vec<String> {
        let from = text.find(start).expect(start) + start.len();
        let to = from + text[from..].find(end).expect(end);
        text[from..to]
            .split(',')
            .map(|s| {
                s.trim().trim_matches('"').trim_start_matches("commands::").replace("allow-", "").replace('-', "_")
            })
            .filter(|s| !s.is_empty())
            .collect()
    }
    let mut built = names_between(include_str!("../build.rs"), "COMMANDS: &[&str] = &[", "];");
    let mut handled = names_between(include_str!("lib.rs"), "generate_handler![", "]");
    let mut allowed = names_between(include_str!("../permissions/default.toml"), "permissions = [", "]");
    // Every #[tauri::command], sync or async, however it is written.
    let mut defined: Vec<String> = commands().into_iter().map(|c| c.name).collect();
    for list in [&mut built, &mut handled, &mut allowed, &mut defined] {
        list.sort();
    }
    assert_eq!(built, defined, "build.rs COMMANDS");
    assert_eq!(handled, defined, "generate_handler! in lib.rs");
    assert_eq!(allowed, defined, "permissions/default.toml");
}

#[test]
fn the_page_script_carries_every_component_and_its_stylesheet() {
    let script = crate::page_script(&quiet());
    for placeholder in ["TABS_CSS", "TABS_VERSION", "TREE_CSS", "TERMINAL_CSS", "FILES_CSS", "MENUS_CSS"] {
        assert!(!script.contains(&format!("__TAURIS_{placeholder}__")), "{placeholder} is not filled in");
    }
    for global in ["TaurisTabs", "TaurisTree", "TaurisTerminal", "TaurisFiles", "TaurisMenu"] {
        assert!(script.contains(&format!("window.{global} = ")), "{global} is missing");
    }
    for variable in ["--tt-strip-h", "--tv-row-h", "--tm-font", "--tf-row-h", "--tmn-item-h"] {
        assert!(script.contains(variable), "the stylesheet with {variable} is missing");
    }
}

// The page's file pickers say what the app is missing, instead of failing silently.
#[test]
fn the_file_pickers_say_what_the_app_is_missing() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let window = app.get_webview_window("tabs-1").expect("a tab window");
    let picked = tauri::async_runtime::block_on(crate::files::pick_for_page(window.clone(), None, true));
    let saved = tauri::async_runtime::block_on(crate::files::save_for_page(window, None, Some("a.pdf".into())));
    #[cfg(not(feature = "files"))]
    let wanted = "\"files\" feature";
    #[cfg(feature = "files")]
    let wanted = "tauri_plugin_dialog::init()";
    assert!(picked.unwrap_err().contains(wanted));
    assert!(saved.unwrap_err().contains(wanted));
}

// With the dialog plugin registered, the pickers find it.
#[cfg(feature = "files")]
#[test]
fn the_file_pickers_find_the_dialog_plugin() {
    let app = mock_builder()
        .plugin(init(quiet()))
        .plugin(tauri_plugin_dialog::init())
        .build(mock_context(noop_assets()))
        .expect("test app");
    assert!(crate::files::dialogs(app.handle()).is_ok());
}

// Tauri runs the plugin's on_event while it holds its plugin lock, and opening
// a window takes that lock: a window opened inside the handler freezes the app
// (the Dock click, ⌘N). Only the real event loop shows the freeze (CI runs
// test/freeze_check), so this checks the source: outside after_event(...), the
// handler calls nothing that can open a window, and it marks the lock.
#[test]
fn the_event_handler_opens_no_window_itself() {
    let source = include_str!("lib.rs");
    let from = source.find(".on_event(|app, event|").expect("the plugin's on_event");
    let to = from + source[from..].find(".build()").expect("the end of on_event");
    let handler = &source[from..to];
    // The guard is the first statement and is kept (a `let _ =` would drop it at once).
    let body = &handler[handler.find('{').expect("the handler's body") + 1..];
    assert!(
        body.trim_start().starts_with("let _locked = windows::InPlugin::enter();"),
        "on_event does not mark Tauri's lock"
    );
    assert!(handler.contains("RunEvent::Exit => exiting(app)"), "quitting does not wait for the hook");
    // Everything inside after_event( ... ) runs later, on the worker: take it out.
    let mut outside = String::new();
    let mut rest = handler;
    while let Some(at) = rest.find("after_event(") {
        outside.push_str(&rest[..at]);
        let mut depth = 0;
        let mut end = rest.len();
        for (i, c) in rest[at..].char_indices() {
            match c {
                '(' => depth += 1,
                ')' => {
                    depth -= 1;
                    if depth == 0 {
                        end = at + i + 1;
                        break;
                    }
                }
                _ => {}
            }
        }
        rest = &rest[end..];
    }
    outside.push_str(rest);
    for call in [
        "new_tab(",
        "new_window(",
        "new_window_with(",
        ".open(",
        "open_or_focus(",
        "open_many(",
        "open_in(",
        "restore(",
        "create_window(",
        "open_window(",
        "move_to_new_window(",
        "restore_saved(",
        ".start(",
        "drag::start(",
    ] {
        assert!(!outside.contains(call), "on_event calls {call} itself; send it through after_event");
    }
}

// A page command in src/commands.rs: its name, whether it is async, its body.
struct Command {
    name: String,
    is_async: bool,
    body: String,
    // What the page passes (Tauri fills in the window, the app and state).
    params: Vec<String>,
}

// The text between the bracket at the start of `text` and the one closing it.
fn inside(text: &str, open: char, close: char) -> &str {
    let mut depth = 0;
    for (i, c) in text.char_indices() {
        if c == open {
            depth += 1;
        } else if c == close {
            depth -= 1;
            if depth == 0 {
                return &text[1..i];
            }
        }
    }
    &text[1..]
}

// Splits at the commas of this level, not those inside brackets.
fn top_level(text: &str) -> Vec<String> {
    let (mut out, mut depth, mut start) = (Vec::new(), 0, 0);
    for (i, c) in text.char_indices() {
        match c {
            '(' | '[' | '{' | '<' => depth += 1,
            ')' | ']' | '}' | '>' => depth -= 1,
            ',' if depth == 0 => {
                out.push(text[start..i].trim().to_string());
                start = i + 1;
            }
            _ => {}
        }
    }
    out.push(text[start..].trim().to_string());
    out.into_iter().filter(|p| !p.is_empty()).collect()
}

// Reads every #[tauri::command ...] item, whatever its visibility or attribute arguments.
fn commands() -> Vec<Command> {
    let source = include_str!("commands.rs");
    let mut out = Vec::new();
    let mut rest = source;
    while let Some(at) = rest.find("#[tauri::command") {
        let after = &rest[at..];
        let attr_end = after.find(']').expect("the end of the attribute") + 1;
        let item = &after[attr_end..];
        let fn_at = item.find("fn ").expect("a command function");
        let head = &item[..fn_at];
        let name: String = item[fn_at + 3..].chars().take_while(|c| c.is_alphanumeric() || *c == '_').collect();
        let open = item.find('{').expect("a body");
        let mut depth = 0;
        let mut close = item.len();
        for (i, c) in item[open..].char_indices() {
            match c {
                '{' => depth += 1,
                '}' => {
                    depth -= 1;
                    if depth == 0 {
                        close = open + i + 1;
                        break;
                    }
                }
                _ => {}
            }
        }
        let signature = &item[fn_at..open];
        let args = signature.find('(').map_or("", |at| inside(&signature[at..], '(', ')'));
        let params = top_level(args)
            .into_iter()
            .filter_map(|p| {
                let (name, ty) = p.split_once(':')?;
                let given = ["WebviewWindow", "AppHandle", "Window<", "Webview<", "State<"];
                (!given.iter().any(|g| ty.contains(g))).then(|| name.trim().to_string())
            })
            .collect();
        out.push(Command {
            name,
            is_async: head.split_whitespace().any(|w| w == "async"),
            body: item[open..close].to_string(),
            params,
        });
        rest = &item[close..];
    }
    out
}

// What the pages call is a command Rust has, with the arguments it takes
// (the page's camelCase is Rust's snake_case). A renamed command or argument
// would pass every page test, whose stand-in for Rust answers anything.
#[test]
fn the_pages_call_the_commands_rust_has() {
    let all = commands();
    let mut seen = 0;
    for (page, source) in [("tabs.js", include_str!("../web/tabs.js")), ("files.js", include_str!("../web/files.js"))] {
        let code: String = source.lines().filter(|l| !l.trim_start().starts_with("//")).collect::<Vec<_>>().join("\n");
        for start in ["call(\"", "invoke(\""] {
            let mut rest = code.as_str();
            while let Some(at) = rest.find(start) {
                let after = &rest[at + start.len()..];
                let name = &after[..after.find('"').expect("the command's name ends")];
                let tail = after[name.len() + 1..].trim_start();
                let keys: Vec<String> = match tail.strip_prefix(',').map(str::trim_start) {
                    Some(obj) if obj.starts_with('{') => top_level(inside(obj, '{', '}'))
                        .iter()
                        .map(|k| k.split(':').next().unwrap().trim().to_string())
                        .map(|k| {
                            k.chars()
                                .flat_map(|c| {
                                    if c.is_ascii_uppercase() {
                                        vec!['_', c.to_ascii_lowercase()]
                                    } else {
                                        vec![c]
                                    }
                                })
                                .collect()
                        })
                        .collect(),
                    _ => vec![],
                };
                let command = all.iter().find(|c| c.name == name);
                assert!(command.is_some(), "{page} calls {name}, which Rust does not have");
                let mut want = command.unwrap().params.clone();
                let mut got = keys.clone();
                want.sort();
                got.sort();
                assert_eq!(got, want, "{page} calls {name} with other arguments than Rust takes");
                seen += 1;
                rest = &after[name.len()..];
            }
        }
    }
    assert!(seen >= 15, "only {seen} calls found");
}

// Every plain (not async) page command runs inside Tauri's plugin lock and must say so.
#[test]
fn every_plain_command_marks_the_lock() {
    let all = commands();
    assert!(all.len() >= 15, "only {} commands found", all.len());
    // The guard is the first statement and is kept (a `let _ =` would drop it at once).
    for c in all.iter().filter(|c| !c.is_async) {
        assert!(
            c.body[1..].trim_start().starts_with("let _locked = windows::InPlugin::enter();"),
            "the command {} does not start by marking Tauri's lock",
            c.name
        );
    }
}

// An async command that changes tabs (dragging one out, moving one to a new
// window) sends the app's hook to its worker, like a plain command.
#[test]
fn every_async_command_that_moves_tabs_defers_the_hook() {
    let moving: Vec<_> = commands()
        .into_iter()
        .filter(|c| c.is_async && (c.body.contains("drag::") || c.body.contains("windows::move_to_new_window")))
        .collect();
    assert!(moving.len() >= 2, "only {} such commands found", moving.len());
    for c in moving {
        assert!(
            c.body[1..].trim_start().starts_with("let _later = windows::DeferHook::enter();"),
            "the command {} does not start by deferring the hook",
            c.name
        );
    }
}

// Hook calls keep their order: one waiting on the worker (from inside Tauri's
// lock) and one made right after by the app.
#[test]
fn the_hook_calls_keep_their_order() {
    let order = Arc::new(std::sync::Mutex::new(Vec::new()));
    let o = order.clone();
    let app = app(quiet().on_change(move |_, label| {
        std::thread::sleep(std::time::Duration::from_millis(30));
        o.lock().unwrap().push(label.to_string());
    }));
    app.tabs().start().unwrap();
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    order.lock().unwrap().clear();
    {
        let _locked = windows::InPlugin::enter();
        windows::changed(app.handle(), "first");
    }
    windows::changed(app.handle(), "second");
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    // (Both run on the hook's worker: what this shows is their order.)
    assert_eq!(*order.lock().unwrap(), ["first", "second"]);
}

fn eventually(what: &str, ok: impl Fn() -> bool) {
    for _ in 0..200 {
        if ok() {
            return;
        }
        std::thread::sleep(std::time::Duration::from_millis(10));
    }
    panic!("{what} did not happen within 2s");
}

// Inside Tauri's plugin lock (the plugin's on_event, a page's plain command)
// the hook runs a moment later, on the worker, in order: a hook that opened a
// window there would freeze the app. Outside it, it runs at once, as before.
#[test]
fn the_hook_runs_after_the_change_in_order() {
    let calls = Arc::new(std::sync::Mutex::new(Vec::new()));
    let threads = Arc::new(std::sync::Mutex::new(Vec::new()));
    let (seen, on) = (calls.clone(), threads.clone());
    let app = app(quiet().on_change(move |_, label| {
        seen.lock().unwrap().push(label.to_string());
        on.lock().unwrap().push(std::thread::current().id());
    }));
    app.tabs().start().unwrap();
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    calls.lock().unwrap().clear();
    threads.lock().unwrap().clear();
    // Nothing waits on the worker: only the lock sends these there.
    {
        let _locked = windows::InPlugin::enter();
        windows::changed(app.handle(), "tabs-1");
        windows::changed(app.handle(), "tabs-2");
    }
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    assert_eq!(*calls.lock().unwrap(), ["tabs-1", "tabs-2"]);
    let here = std::thread::current().id();
    assert!(threads.lock().unwrap().iter().all(|t| *t != here), "the hook ran inside Tauri's lock");
    threads.lock().unwrap().clear();
    windows::changed(app.handle(), "tabs-3");
    assert_eq!(calls.lock().unwrap().len(), 3, "outside the lock the hook runs at once");
    assert_eq!(*threads.lock().unwrap(), [std::thread::current().id()]);
}

// Quitting waits (half a second at most) for the hook to hear the last changes.
#[test]
fn quitting_waits_for_the_last_hook_calls() {
    let app = app(quiet());
    let done = Arc::new(AtomicUsize::new(0));
    let d = done.clone();
    windows::send(
        app.handle(),
        windows::Kind::Hook,
        Box::new(move |_| {
            // A little work, well inside the half second a quit waits (a busy machine has room).
            std::thread::sleep(std::time::Duration::from_millis(20));
            d.fetch_add(1, Ordering::SeqCst);
        }),
    );
    crate::exiting(app.handle());
    assert_eq!(done.load(Ordering::SeqCst), 1);
}

// ...but half a second at most, and no new window opens once quitting began.
#[test]
fn quitting_waits_half_a_second_at_most() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    windows::send(
        app.handle(),
        windows::Kind::Hook,
        Box::new(|_| std::thread::sleep(std::time::Duration::from_secs(2))),
    );
    let started = std::time::Instant::now();
    crate::exiting(app.handle());
    let took = started.elapsed();
    // Half a second, not the hook's two (a busy test machine may add a little).
    assert!(took >= std::time::Duration::from_millis(450) && took < std::time::Duration::from_millis(1500), "{took:?}");
    windows::after_event(app.handle(), |app| {
        let _ = app.tabs().new_window();
    });
    // Every job done (or dropped) before looking: no window opened.
    windows::settle(app.handle(), std::time::Duration::from_secs(3));
    assert_eq!(app.tabs().window_count(), 1, "a window opened while quitting");
}

// A slow hook never holds up ⌘N: window jobs have a worker of their own, and
// the hook calls they cause wait on the hook's worker, not on theirs.
#[test]
fn a_slow_hook_does_not_hold_up_a_new_window() {
    let gate = Arc::new(std::sync::Mutex::new(()));
    let stuck = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let (g, b) = (gate.clone(), stuck.clone());
    let app = app(quiet().on_change(move |_, _| {
        if b.load(Ordering::SeqCst) {
            drop(g.lock());
        }
    }));
    app.tabs().start().unwrap();
    // From here the hook is stuck in its first call until the gate opens.
    let held = gate.lock().unwrap();
    stuck.store(true, Ordering::SeqCst);
    let done = Arc::new(AtomicUsize::new(0));
    for _ in 0..2 {
        let d = done.clone();
        windows::after_event(app.handle(), move |app| {
            let _ = app.tabs().new_window();
            d.fetch_add(1, Ordering::SeqCst);
        });
    }
    eventually("both ⌘N while the hook is stuck", || done.load(Ordering::SeqCst) == 2);
    assert_eq!(app.tabs().window_count(), 3);
    drop(held);
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
}

// A hook that panics is the app's bug: the tabs carry on, on every thread.
#[test]
fn a_hook_that_panics_stops_nothing() {
    let file = temp_file("panicking-hook");
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())).on_change(|_, _| panic!("the app's hook failed")));
    app.tabs().start().unwrap();
    let report = app.tabs().open(NewTab::new("Report")).unwrap();
    assert_eq!(titles(&app), [["Home", "Report"]]);
    persist::save(app.handle(), true);
    assert!(file.is_file(), "the layout was not saved");
    // Closing every tab still closes the window and forgets the layout.
    for id in [app.tabs().windows()[0].tabs[0].id, report] {
        windows::remove_tab(app.handle(), "tabs-1", id);
    }
    assert_eq!(app.tabs().window_count(), 0);
    assert!(!file.is_file(), "the layout was not forgotten");
}

// Two threads changing tabs at once: the hook still runs one call at a time.
#[test]
fn the_hook_never_runs_twice_at_once_across_threads() {
    let running = Arc::new(AtomicUsize::new(0));
    let most = Arc::new(AtomicUsize::new(0));
    let calls = Arc::new(AtomicUsize::new(0));
    let (r, m, c) = (running.clone(), most.clone(), calls.clone());
    // The first call ("a") holds on until the second ("b") has been made.
    let second_made = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let s = second_made.clone();
    let app = app(quiet().on_change(move |_, label| {
        let now = r.fetch_add(1, Ordering::SeqCst) + 1;
        m.fetch_max(now, Ordering::SeqCst);
        if label == "a" {
            while !s.load(Ordering::SeqCst) {
                std::thread::sleep(std::time::Duration::from_millis(2));
            }
        }
        c.fetch_add(1, Ordering::SeqCst);
        r.fetch_sub(1, Ordering::SeqCst);
    }));
    let handle = app.handle().clone();
    let other = handle.clone();
    let first = std::thread::spawn(move || windows::changed(&other, "a"));
    eventually("the first call", || running.load(Ordering::SeqCst) == 1);
    windows::changed(&handle, "b");
    second_made.store(true, Ordering::SeqCst);
    first.join().unwrap();
    windows::settle(&handle, std::time::Duration::from_secs(2));
    assert_eq!(calls.load(Ordering::SeqCst), 2);
    assert_eq!(most.load(Ordering::SeqCst), 1, "two hook calls overlapped");
}

// Changes to one window while its hook call waits add no calls: the hook
// reads the tabs as they are when it runs.
#[test]
fn changes_to_a_window_waiting_for_the_hook_add_no_calls() {
    let calls = Arc::new(AtomicUsize::new(0));
    let gate = Arc::new(std::sync::Mutex::new(()));
    let (c, g) = (calls.clone(), gate.clone());
    let app = app(quiet().on_change(move |_, _| {
        drop(g.lock());
        c.fetch_add(1, Ordering::SeqCst);
    }));
    let held = gate.lock().unwrap();
    {
        let _locked = windows::InPlugin::enter();
        for _ in 0..6 {
            windows::changed(app.handle(), "tabs-1");
        }
    }
    drop(held);
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    // One call running when the others came, and one more for them all.
    let made = calls.load(Ordering::SeqCst);
    assert!((1..=2).contains(&made), "{made} calls");
}

// Quitting also waits for a hook call running on another thread (an async command's).
#[test]
fn quitting_waits_for_a_hook_call_on_another_thread() {
    let done = Arc::new(AtomicUsize::new(0));
    let d = done.clone();
    let app = app(quiet().on_change(move |_, _| {
        std::thread::sleep(std::time::Duration::from_millis(150));
        d.fetch_add(1, Ordering::SeqCst);
    }));
    let handle = app.handle().clone();
    let caller = std::thread::spawn(move || windows::changed(&handle, "tabs-1"));
    // The hook has begun on the other thread (it holds the hook's lock).
    eventually("the hook to begin", || windows::inner(app.handle()).hook.try_lock().is_err());
    crate::exiting(app.handle());
    assert_eq!(done.load(Ordering::SeqCst), 1, "the app quit in the middle of the hook");
    caller.join().unwrap();
}

// A job whose panic cannot even be dropped does not stop the worker.
#[test]
fn a_panic_that_panics_when_dropped_does_not_stop_the_worker() {
    struct Bomb;
    impl Drop for Bomb {
        fn drop(&mut self) {
            panic!("dropped");
        }
    }
    let app = app(quiet());
    windows::after_event(app.handle(), |_| std::panic::panic_any(Bomb));
    // The bomb has gone off before the next job is sent: that job finds the same worker.
    windows::settle(app.handle(), std::time::Duration::from_secs(1));
    std::thread::sleep(std::time::Duration::from_millis(20));
    let done = Arc::new(AtomicUsize::new(0));
    let d = done.clone();
    windows::after_event(app.handle(), move |_| {
        d.fetch_add(1, Ordering::SeqCst);
    });
    eventually("the job after it", || done.load(Ordering::SeqCst) == 1);
    windows::settle(app.handle(), std::time::Duration::from_secs(1));
}

// Merged calls keep the place of the newest: changes to a, b, then a again
// reach the hook as b, then a.
#[test]
fn merged_hook_calls_keep_the_newest_place() {
    let order = Arc::new(std::sync::Mutex::new(Vec::new()));
    let gate = Arc::new(std::sync::Mutex::new(()));
    let (o, g) = (order.clone(), gate.clone());
    let app = app(quiet().on_change(move |_, label| {
        drop(g.lock());
        o.lock().unwrap().push(label.to_string());
    }));
    let held = gate.lock().unwrap();
    {
        let _locked = windows::InPlugin::enter();
        windows::changed(app.handle(), "x");
    }
    eventually("the first call to begin", || windows::inner(app.handle()).hook.try_lock().is_err());
    {
        let _locked = windows::InPlugin::enter();
        for label in ["a", "b", "a"] {
            windows::changed(app.handle(), label);
        }
    }
    drop(held);
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    assert_eq!(*order.lock().unwrap(), ["x", "b", "a"]);
}

// An async page command (dragging a tab out, moving it to a new window) runs
// the app's hook on its worker, not on the async runtime's thread.
#[test]
fn async_page_commands_defer_the_hook() {
    let threads = Arc::new(std::sync::Mutex::new(Vec::new()));
    let t = threads.clone();
    let app = app(quiet().on_change(move |_, _| t.lock().unwrap().push(std::thread::current().id())));
    app.tabs().start().unwrap();
    app.tabs().open(NewTab::new("Report")).unwrap();
    threads.lock().unwrap().clear();
    {
        let _later = windows::DeferHook::enter();
        windows::changed(app.handle(), "tabs-1");
    }
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    let here = std::thread::current().id();
    assert!(!threads.lock().unwrap().is_empty() && threads.lock().unwrap().iter().all(|id| *id != here));
}

// A window still opening takes no tab: if it fails, the tab would go with it.
#[test]
fn a_window_still_opening_takes_no_tab() {
    let app = app(quiet());
    let label = windows::inner(app.handle()).model().create_win(vec![]);
    assert_eq!(windows::add_tab(app.handle(), &label, NewTab::new("Late"), false), None);
}

// A tab opened while another thread restores the windows waits for all of
// them and goes in the front one, rather than opening a window of its own.
#[test]
fn a_tab_opened_during_a_restore_goes_to_the_restored_window() {
    let app = app(quiet());
    windows::inner(app.handle()).restoring.store(true, Ordering::SeqCst);
    let handle = app.handle().clone();
    let restorer = std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_millis(100));
        windows::create_window(&handle, vec![NewTab::new("Behind")], None, false).unwrap();
        std::thread::sleep(std::time::Duration::from_millis(100));
        windows::create_window(&handle, vec![NewTab::new("Front")], None, true).unwrap();
        windows::inner(&handle).restoring.store(false, Ordering::SeqCst);
    });
    app.tabs().open(NewTab::new("Late")).unwrap();
    restorer.join().unwrap();
    assert_eq!(titles(&app), [vec!["Behind"], vec!["Front", "Late"]]);
}

// ⌘N with no window open: the remembered windows come back behind the new
// one, so the next save does not remember the new window alone.
#[test]
fn a_new_window_with_none_open_brings_back_the_remembered_ones() {
    let file = temp_file("new-window");
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    app.tabs().open(NewTab::new("Users")).unwrap();
    windows::forget_window(app.handle(), "tabs-1"); // the last window closed
    assert_eq!(app.tabs().window_count(), 0);
    let label = app.tabs().new_window().unwrap();
    assert_eq!(titles(&app), [vec!["Home", "Users"], vec!["Home"]]);
    assert_eq!(app.tabs().frontmost(), Some(label));
}

// A window whose close went ahead takes no new tab: it would go with it.
#[test]
fn a_window_about_to_close_takes_no_new_tab() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let second = app.tabs().new_window().unwrap();
    assert!(!windows::ask_before_window_closes(app.handle(), &second));
    assert_eq!(app.tabs().frontmost().as_deref(), Some("tabs-1"));
    assert_eq!(app.tabs().open_in(&second, NewTab::new("Late")), None);
    app.tabs().open(NewTab::new("Late")).unwrap();
    assert_eq!(titles(&app), [vec!["Home", "Late"], vec!["Home"]]);
    // Focused again: the app kept it open after all.
    windows::bring_to_front(app.handle(), &second);
    assert_eq!(app.tabs().frontmost(), Some(second));
}

// The save made when the last window closes failed: it is tried again as
// one, with that window still in it.
#[test]
fn a_failed_save_of_the_last_window_is_tried_again_with_it() {
    let file = temp_file("retry-now");
    std::fs::create_dir_all(&file).unwrap(); // writing the file fails
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    app.tabs().open(NewTab::new("Users")).unwrap();
    windows::forget_window(app.handle(), "tabs-1");
    assert!(file.is_dir());
    std::fs::remove_dir(&file).unwrap();
    std::thread::sleep(std::time::Duration::from_millis(700)); // longer than a quit takes
    persist::save(app.handle(), false);
    let text = std::fs::read_to_string(&file).expect("the save was not tried again");
    assert!(text.contains("Users"), "{text}");
}

// Closing the last tab forgets the copies kept aside too: they hold titles.
#[test]
fn forgetting_the_layout_removes_the_copies_kept_aside() {
    let file = temp_file("forget-aside");
    for aside in ["unopened", "unreadable"] {
        std::fs::write(file.with_extension(aside), "[]").unwrap();
    }
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    persist::save(app.handle(), true);
    let only = app.tabs().windows()[0].tabs[0].id;
    app.tabs().close_tab(only);
    assert!(!file.exists());
    assert!(!file.with_extension("unopened").exists() && !file.with_extension("unreadable").exists());
}

// The last tab closed from the app's own code, and a hook that opens a tab
// when it hears of it: the old layout does not come back.
#[test]
fn a_hook_opening_a_tab_after_the_last_one_closed_brings_no_old_layout_back() {
    let file = temp_file("forget-first");
    let path = file.clone();
    let opened = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let o = opened.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())).on_change(move |app, _| {
        if app.tabs().window_count() == 0 && !o.swap(true, Ordering::SeqCst) {
            app.tabs().open(NewTab::new("Fresh")).unwrap();
        }
    }));
    app.tabs().start().unwrap();
    app.tabs().open(NewTab::new("Old")).unwrap();
    persist::save(app.handle(), true);
    let ids: Vec<u64> = app.tabs().windows()[0].tabs.iter().map(|t| t.id).collect();
    for id in ids {
        app.tabs().close_tab(id);
    }
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    assert_eq!(titles(&app), [["Fresh"]]);
}

// A hung page: presses of the close button a second apart still close the
// window two seconds after the first.
#[test]
fn pressing_close_again_does_not_restart_the_wait_for_a_hung_page() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    if let Some(w) = windows::inner(app.handle()).model().win("tabs-1") {
        w.guarded = true;
    }
    assert!(windows::ask_before_window_closes(app.handle(), "tabs-1"));
    std::thread::sleep(std::time::Duration::from_millis(1200));
    assert!(windows::ask_before_window_closes(app.handle(), "tabs-1"), "asked again at 1.2 s");
    std::thread::sleep(std::time::Duration::from_millis(1000));
    assert!(
        !windows::ask_before_window_closes(app.handle(), "tabs-1"),
        "the third press, 2.2 s after the first, still waits"
    );
}

// The app's own close handler kept a window open: it takes tabs again.
#[test]
fn a_window_the_app_kept_open_takes_tabs_again() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let second = app.tabs().new_window().unwrap();
    assert!(!windows::ask_before_window_closes(app.handle(), &second));
    assert_eq!(app.tabs().open_in(&second, NewTab::new("Late")), None);
    eventually("the window to take tabs again", || app.tabs().open_in(&second, NewTab::new("Later")).is_some());
}

// Quitting: a window asked for then is not recorded, nor saved.
#[test]
fn no_window_opens_or_is_saved_once_quitting() {
    let file = temp_file("quit-new");
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    windows::begin_exit(app.handle());
    assert!(app.tabs().new_window().is_err());
    assert_eq!(app.tabs().window_count(), 1);
    // A window recorded but still opening is left out of the save.
    let opening = {
        let mut m = windows::inner(app.handle()).model();
        let tab = m.create_tab(NewTab::new("Never shown"));
        m.create_win(vec![tab])
    };
    persist::save(app.handle(), true);
    let saved: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&file).unwrap()).unwrap();
    assert_eq!(saved.as_array().map(Vec::len), Some(1), "{opening} was saved");
}

// Quitting with windows open saves them all.
#[test]
fn quitting_saves_the_windows_open() {
    let file = temp_file("quit-save");
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    app.tabs().open(NewTab::new("Users")).unwrap();
    app.tabs().new_window().unwrap();
    crate::exiting(app.handle());
    let saved: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&file).unwrap()).unwrap();
    assert_eq!(saved.as_array().map(Vec::len), Some(2));
    assert!(saved.to_string().contains("Users"));
}

// The Dock click after the last window closed (the plugin's Reopen event):
// the remembered windows come back, on the worker; in an app that never
// called start(), nothing opens.
#[test]
fn the_dock_click_brings_back_the_windows_after_the_last_one_closed() {
    let other = app(quiet());
    let file = temp_file("dock");
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    app.tabs().open(NewTab::new("Users")).unwrap();
    windows::forget_window(app.handle(), "tabs-1");
    assert_eq!(app.tabs().window_count(), 0);
    {
        let _locked = windows::InPlugin::enter(); // as on_event runs it
        persist::reopened(app.handle());
    }
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    assert_eq!(titles(&app), [["Home", "Users"]]);
    persist::reopened(other.handle());
    windows::settle(other.handle(), std::time::Duration::from_secs(2));
    assert_eq!(other.tabs().window_count(), 0, "a window opened in an app that does not use tabs");
}

// A layout_file that panics (inside Tauri's lock, at times) saves nothing and stops nothing.
#[test]
fn a_layout_file_that_panics_saves_nothing() {
    let app = app(quiet().layout_file(|_| panic!("no data folder")));
    app.tabs().start().unwrap();
    app.tabs().open(NewTab::new("Users")).unwrap();
    persist::save(app.handle(), true);
    let only = app.tabs().windows()[0].tabs.iter().map(|t| t.id).collect::<Vec<_>>();
    for id in only {
        app.tabs().close_tab(id);
    }
    assert_eq!(app.tabs().window_count(), 0);
}

// A remembered window comes back where it was, its size and maximized state
// too (the test runtime knows no screens: none is off one).
#[test]
fn a_remembered_frame_comes_back() {
    let file = temp_file("frame-back");
    std::fs::write(
        &file,
        r#"[{"tabs":[{"id":1,"title":"Users"}],"active":0,"frame":{"x":40.0,"y":60.0,"width":900.0,"height":700.0,"maximized":true}}]"#,
    )
    .unwrap();
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    let label = app.tabs().frontmost().unwrap();
    let frame = windows::inner(app.handle()).model().win(&label).and_then(|w| w.frame);
    assert_eq!(
        frame.map(|f| (f.x, f.y, f.width, f.height, f.maximized, f.centre)),
        Some((40.0, 60.0, 900.0, 700.0, true, false))
    );
}

// A tab opened while another thread restores the windows, after the first of
// them opened: it still waits for all of them and goes in the front one.
#[test]
fn a_tab_opened_midway_through_a_restore_goes_to_the_front_window() {
    let app = app(quiet());
    windows::inner(app.handle()).restoring.store(true, Ordering::SeqCst);
    let handle = app.handle().clone();
    let restorer = std::thread::spawn(move || {
        windows::create_window(&handle, vec![NewTab::new("Behind")], None, false).unwrap();
        std::thread::sleep(std::time::Duration::from_millis(200));
        windows::create_window(&handle, vec![NewTab::new("Front")], None, true).unwrap();
        windows::inner(&handle).restoring.store(false, Ordering::SeqCst);
    });
    std::thread::sleep(std::time::Duration::from_millis(80)); // "Behind" is open
    app.tabs().open(NewTab::new("Late")).unwrap();
    restorer.join().unwrap();
    assert_eq!(titles(&app), [vec!["Behind"], vec!["Front", "Late"]]);
}

// Three windows closing together, in any order: the one that was in front
// comes back in front.
#[test]
fn three_windows_closed_together_keep_their_order_in_front() {
    let file = temp_file("order3");
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    let b = app.tabs().new_window().unwrap();
    let c = app.tabs().new_window().unwrap();
    for (label, title) in [("tabs-1", "A"), (b.as_str(), "B"), (c.as_str(), "C")] {
        let id = app.tabs().windows().iter().find(|w| w.label == label).unwrap().tabs[0].id;
        app.tabs().update_tab(id, title, Fields::new());
    }
    for label in [b.as_str(), "tabs-1", c.as_str()] {
        windows::forget_window(app.handle(), label);
    }
    let saved: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&file).unwrap()).unwrap();
    let order: Vec<&str> = saved.as_array().unwrap().iter().map(|w| w["tabs"][0]["title"].as_str().unwrap()).collect();
    assert_eq!(order, ["A", "B", "C"]);
}

// A layout file of any name: a write a crash left half done is found and removed.
#[test]
fn a_half_written_layout_of_any_name_is_removed() {
    let file = temp_file("anyname").with_file_name("layout.state");
    let half = file.with_file_name("layout.state.99999.tmp");
    std::fs::write(&half, "[").unwrap();
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    persist::save(app.handle(), true);
    assert!(file.is_file(), "saved under its own name");
    let only = app.tabs().windows()[0].tabs[0].id;
    app.tabs().close_tab(only);
    assert!(!half.exists());
}

// A close the page agreed to, which the app then refused (a window hidden to
// the tray instead): the next close asks the page again.
#[test]
fn a_close_the_app_refused_asks_the_page_again_next_time() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    if let Some(w) = windows::inner(app.handle()).model().win("tabs-1") {
        w.guarded = true;
        w.may_close = true; // the page said yes
    }
    assert!(!windows::ask_before_window_closes(app.handle(), "tabs-1"));
    eventually("the window to take tabs again", || windows::inner(app.handle()).model().takes_tabs("tabs-1"));
    assert!(windows::ask_before_window_closes(app.handle(), "tabs-1"), "the page was not asked again");
}

// A window remembered on a screen no longer there opens centred, keeping its
// size and whether it was maximized.
#[test]
fn a_window_whose_screen_is_gone_opens_centred_with_its_size() {
    let file = temp_file("off-screen");
    std::fs::write(
        &file,
        r#"[{"tabs":[{"id":1,"title":"Users"}],"active":0,"frame":{"x":3000.0,"y":60.0,"width":900.0,"height":700.0,"maximized":true}}]"#,
    )
    .unwrap();
    persist::TEST_SCREENS.with(|s| *s.borrow_mut() = Some(vec![(0.0, 0.0, 1440.0, 900.0)]));
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    persist::TEST_SCREENS.with(|s| *s.borrow_mut() = None);
    let label = app.tabs().frontmost().unwrap();
    let frame = windows::inner(app.handle()).model().win(&label).and_then(|w| w.frame);
    assert_eq!(frame.map(|f| (f.width, f.height, f.maximized, f.centre)), Some((900.0, 700.0, true, true)));
}

// Windows that closed together (a quit) come back in front of each other as
// they were, whatever order they closed in.
#[test]
fn windows_closed_together_keep_their_order_in_front() {
    let file = temp_file("order");
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    let second = app.tabs().new_window().unwrap();
    app.tabs().update_tab(app.tabs().windows()[1].tabs[0].id, "Front", Fields::new());
    // The front window closes first, then the one behind.
    windows::forget_window(app.handle(), &second);
    windows::forget_window(app.handle(), "tabs-1");
    let saved: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&file).unwrap()).unwrap();
    assert_eq!(saved[1]["tabs"][0]["title"], "Front", "{saved}");
}

// The windows a restore brought back are not added again by a quit a moment later.
#[test]
fn a_quit_right_after_a_restore_saves_each_window_once() {
    let file = temp_file("once");
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    app.tabs().open(NewTab::new("Users")).unwrap();
    windows::forget_window(app.handle(), "tabs-1");
    app.tabs().restore().unwrap();
    persist::save(app.handle(), true);
    let saved: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&file).unwrap()).unwrap();
    assert_eq!(saved.as_array().map(Vec::len), Some(1), "{saved}");
}

// A write a crash left half done goes when the layout is forgotten.
#[test]
fn forgetting_the_layout_removes_a_half_written_one() {
    let file = temp_file("half");
    let half = file.with_extension("json.99999.tmp");
    std::fs::write(&half, "[{\"tabs\":[{\"id\":1,\"title\":\"Anna\"}]").unwrap();
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    let only = app.tabs().windows()[0].tabs[0].id;
    app.tabs().close_tab(only);
    assert!(!half.exists());
}

// Where each window sits is saved with it (the test runtime knows no
// screens, so only the saving is checked here).
#[test]
fn a_frame_is_saved_with_its_window() {
    let file = temp_file("frame");
    let path = file.clone();
    let app = app(quiet().layout_file(move |_| Some(path.clone())));
    app.tabs().start().unwrap();
    let frame = crate::model::Frame { x: 40.0, y: 60.0, width: 900.0, height: 700.0, maximized: true, centre: false };
    if let Some(w) = windows::inner(app.handle()).model().win("tabs-1") {
        w.frame = Some(frame);
    }
    app.tabs().open(NewTab::new("More")).unwrap();
    persist::save(app.handle(), true);
    let saved: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&file).unwrap()).unwrap();
    assert_eq!(saved[0]["frame"]["width"], 900.0);
    assert_eq!(saved[0]["frame"]["maximized"], true);
}

// A window the hook closes (by closing its last tab) is reported to the hook
// once it is done.
#[test]
fn a_window_the_hook_closes_is_reported_to_it() {
    let calls = Arc::new(std::sync::Mutex::new(Vec::new()));
    let close = Arc::new(std::sync::Mutex::new(None::<u64>));
    let (c, x) = (calls.clone(), close.clone());
    let app = app(quiet().on_change(move |app, label| {
        let count = app.tabs().windows().iter().find(|w| w.label == label).map_or(0, |w| w.tabs.len());
        c.lock().unwrap().push((label.to_string(), count));
        let take = x.lock().unwrap().take();
        if let Some(id) = take {
            app.tabs().close_tab(id);
        }
    }));
    app.tabs().start().unwrap();
    let second = app.tabs().new_window().unwrap();
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    let lone = app.tabs().windows().iter().find(|w| w.label == second).unwrap().tabs[0].id;
    *close.lock().unwrap() = Some(lone);
    let home = app.tabs().windows()[0].tabs[0].id;
    calls.lock().unwrap().clear();
    app.tabs().update_tab(home, "Home 2", Fields::new());
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    assert_eq!(*calls.lock().unwrap(), [("tabs-1".to_string(), 1), (second, 0)]);
}

// Debug builds stop a window opened inside Tauri's plugin lock at once.
#[cfg(debug_assertions)]
#[test]
#[should_panic(expected = "inside Tauri's plugin lock")]
fn a_window_opened_inside_the_lock_is_caught() {
    let app = app(quiet());
    let _locked = windows::InPlugin::enter();
    let _ = windows::open_window(app.handle(), "tabs-9", None, true);
}

// The last tab closed, then ⌘T before the window is gone: the tab gets a new
// window, and the layout is not lost.
#[test]
fn a_tab_opened_while_the_last_window_closes_gets_a_new_window() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let only = app.tabs().windows()[0].tabs[0].id;
    windows::remove_tab(app.handle(), "tabs-1", only);
    let late = app.tabs().open(NewTab::new("Late")).unwrap();
    assert!(app.tabs().tab(late).is_some(), "the tab went into the closing window");
    assert_eq!(titles(&app), [["Late"]]);
}

// open_many replacing the active tab where there is none loses no tab.
#[test]
fn open_many_without_an_active_tab_loses_nothing() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    windows::inner(app.handle()).model().win("tabs-1").unwrap().active = None;
    app.tabs().open_many(vec![NewTab::new("A"), NewTab::new("B")], true).unwrap();
    assert_eq!(titles(&app), [["Home", "A", "B"]]);
}

// A window whose opening panicked (the app's window hook) leaves no record
// behind, so later tabs do not go into a window nobody sees.
#[test]
fn a_window_that_failed_to_open_leaves_no_record() {
    let fail = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let f = fail.clone();
    let app = app(quiet().window(move |w| {
        if f.load(Ordering::SeqCst) {
            panic!("the app's window hook failed");
        }
        w
    }));
    app.tabs().start().unwrap();
    fail.store(true, Ordering::SeqCst);
    windows::after_event(app.handle(), |app| {
        let _ = app.tabs().new_window();
    });
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    assert_eq!(app.tabs().window_count(), 1);
    assert_eq!(app.tabs().windows().len(), 1);
}

// A job that panics does not stop the ones after it (⌘N, ⌘T, the Dock click).
#[test]
fn a_job_that_panics_does_not_stop_the_worker() {
    let app = app(quiet());
    let done = Arc::new(AtomicUsize::new(0));
    windows::after_event(app.handle(), |_| panic!("a hook failed"));
    let d = done.clone();
    windows::after_event(app.handle(), move |_| {
        d.fetch_add(1, Ordering::SeqCst);
    });
    eventually("the job after the panic", || done.load(Ordering::SeqCst) == 1);
}

// Each stylesheet has its second colour mode twice: for the system's setting
// and for data-tauris-theme. The two copies must say the same thing.
#[test]
fn the_colour_modes_chosen_by_the_app_match_the_systems() {
    for (name, css, mode, other) in [
        ("tabs", include_str!("../web/tabs.css"), "light", "dark"),
        ("tree", include_str!("../web/tree.css"), "light", "dark"),
        ("files", include_str!("../web/files.css"), "dark", "light"),
        ("menus", include_str!("../web/menus.css"), "dark", "light"),
    ] {
        let body = |start: &str| -> Vec<String> {
            let from = css.find(start).unwrap_or_else(|| panic!("{name}: no {start}")) + start.len();
            let to = from + css[from..].find('}').expect("the end of the block");
            css[from..to].lines().map(str::trim).filter(|l| !l.is_empty()).map(String::from).collect()
        };
        let system = body(&format!(":root:not([data-tauris-theme=\"{other}\"]) {{"));
        let chosen = body(&format!(":root[data-tauris-theme=\"{mode}\"] {{"));
        assert!(!system.is_empty(), "{name}: the {mode} block is empty");
        assert_eq!(system, chosen, "{name}: the two {mode} blocks differ");
    }
}

// Moving a tab to a new window whose opening panicked puts the tab back and
// leaves no window record (later tabs would go into a window nobody sees).
#[test]
fn a_tab_moved_to_a_window_that_failed_to_open_comes_back() {
    let fail = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let f = fail.clone();
    let app = app(quiet().window(move |w| {
        if f.load(Ordering::SeqCst) {
            panic!("the app's window hook failed");
        }
        w
    }));
    app.tabs().start().unwrap();
    let report = app.tabs().open(NewTab::new("Report")).unwrap();
    app.tabs().open(NewTab::new("Notes")).unwrap();
    fail.store(true, Ordering::SeqCst);
    assert!(app.tabs().move_to_new_window(report).is_err());
    assert_eq!(app.tabs().window_count(), 1);
    // A tab from the middle goes back to the middle, and the active tab stays active.
    assert_eq!(titles(&app), [["Home", "Report", "Notes"]]);
    let w = &app.tabs().windows()[0];
    assert_eq!(app.tabs().tab(w.active.unwrap()).unwrap().title, "Notes");
}

// Only the components the app names go in its pages; the files table brings
// the menus (its row menu).
#[test]
fn only_the_components_asked_for_go_in_the_pages() {
    use crate::Component;
    let has = |script: &str| {
        [
            "TaurisTabs",
            "TaurisTree",
            "TaurisTerminal",
            "TaurisFiles",
            "TaurisMenu",
            "TaurisSidebar",
            "TaurisFinder",
            "TaurisDialog",
            "TaurisReorder",
            "TaurisGlance",
            "TaurisTable",
            "TaurisStatus",
        ]
        .map(|name| script.contains(&format!("window.{name} = ")))
    };
    assert_eq!(has(&crate::page_script(&quiet())), [true; 12]);
    assert_eq!(
        has(&crate::page_script(&quiet().components(&[Component::Tabs]))),
        [true, false, false, false, false, false, false, false, false, false, false, false]
    );
    let files = crate::page_script(&quiet().components(&[Component::Tree, Component::Files]));
    assert_eq!(has(&files), [false, true, false, true, true, false, false, false, false, false, false, false]);
    assert!(files.len() < crate::page_script(&quiet()).len());
}

// "Move to" another window: the tab goes to the end of that strip, active
// there; a window left with no tab closes. The page's list names the other
// windows by their active tab, the one in front first.
#[test]
fn a_tab_moves_into_another_window() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let a = app.tabs().windows()[0].label.clone();
    let second = app.tabs().open_in(&a, NewTab::new("Notes")).unwrap();
    let b = app.tabs().new_window_with(NewTab::new("Report")).unwrap();
    assert_eq!(
        windows::other_windows(app.handle(), &a).iter().map(|w| (w.label.clone(), w.title.clone())).collect::<Vec<_>>(),
        vec![(b.clone(), "Report".to_string())]
    );
    assert!(!app.tabs().move_to_window(second, &a), "already there");
    assert!(!app.tabs().move_to_window(second, "nowhere"));
    assert!(app.tabs().move_to_window(second, &b));
    assert_eq!(titles(&app), vec![vec!["Home".to_string()], vec!["Report".to_string(), "Notes".to_string()]]);
    let in_b = app.tabs().windows().into_iter().find(|w| w.label == b).unwrap();
    assert_eq!(in_b.active, Some(second));
    // The last tab of a window moved away: that window closes.
    let home = app.tabs().windows()[0].tabs[0].id;
    assert!(app.tabs().move_to_window(home, &b));
    assert_eq!(app.tabs().window_count(), 1);
    assert_eq!(titles(&app), vec![vec!["Report".to_string(), "Notes".to_string(), "Home".to_string()]]);
    assert!(windows::other_windows(app.handle(), &b).is_empty());
}

// The native feel goes in the pages only when the app asks for it.
#[test]
fn the_native_feel_is_in_the_pages_only_when_asked_for() {
    assert!(!crate::page_script(&quiet()).contains("__taurisNativeFeel"));
    assert!(crate::page_script(&quiet().native_feel()).contains("__taurisNativeFeel"));
    assert!(crate::page_script(&quiet().components(&[]).native_feel()).contains("__taurisNativeFeel"));
}

// A dialog in a window of its own: its page reads what to show, it talks only to the window that asked (and that window
// only to its own dialogs), and it goes when that window goes.
#[test]
fn a_dialog_window_belongs_to_the_window_that_asked() {
    let app = app(quiet());
    app.tabs().start().unwrap();
    let owner = app.get_webview_window("tabs-1").unwrap();
    let label =
        crate::dialogs::open(app.handle(), &owner, r#"{"kind":"form"}"#.into(), "Edit Task".into(), 440.0).unwrap();
    assert!(label.starts_with("tauris-dialog-"));
    assert!(app.get_webview_window(&label).is_some(), "the dialog's window"); // (the test runtime keeps no visibility: hidden-until-sized is not seen here)
    assert_eq!(crate::dialogs::spec(&label).as_deref(), Some(r#"{"kind":"form"}"#));
    assert_eq!(crate::dialogs::spec("tabs-1"), None, "a tab window is no dialog");
    assert!(crate::dialogs::send(app.handle(), &label, serde_json::json!({ "type": "done" })).is_ok());
    assert!(
        crate::dialogs::send(app.handle(), "tabs-1", serde_json::json!({})).is_err(),
        "only a dialog sends to its asker"
    );
    assert!(crate::dialogs::reply(app.handle(), "tabs-1", &label, serde_json::json!({ "type": "answer" })).is_ok());
    assert!(
        crate::dialogs::reply(app.handle(), "tabs-2", &label, serde_json::json!({})).is_err(),
        "another window cannot reach it"
    );
    assert!(crate::dialogs::close(&owner).is_err(), "a tab window does not close as a dialog");
    // (The test runtime runs no event loop: what follows a close, the asker told and a
    // dialog going with its window, is not seen here.)
    let dialog = app.get_webview_window(&label).unwrap();
    assert!(crate::dialogs::close(&dialog).is_ok(), "a dialog closes itself");
}

// With warm_dialogs, a dialog's window stays after its dialog, hidden and waiting, and the next dialog
// of the same window is handed to it (no window made); while it shows one, another gets a window of its own.
#[test]
fn a_kept_dialog_window_is_handed_the_next_dialog() {
    let app = app(quiet().warm_dialogs());
    app.tabs().start().unwrap();
    let owner = app.get_webview_window("tabs-1").unwrap();
    let first =
        crate::dialogs::open(app.handle(), &owner, r#"{"kind":"form"}"#.into(), "New Project".into(), 440.0).unwrap();
    let dialog = app.get_webview_window(&first).unwrap();
    assert!(crate::dialogs::close(&dialog).is_ok(), "its dialog done");
    assert!(app.get_webview_window(&first).is_some(), "the window stays");
    assert_eq!(crate::dialogs::spec(&first), None, "it waits for the next dialog");
    let next = crate::dialogs::open(app.handle(), &owner, r#"{"kind":"about"}"#.into(), "About".into(), 420.0).unwrap();
    assert_eq!(next, first, "the next dialog is handed to it");
    assert_eq!(crate::dialogs::spec(&first).as_deref(), Some(r#"{"kind":"about"}"#));
    let other = crate::dialogs::open(app.handle(), &owner, r#"{"kind":"form"}"#.into(), "Edit".into(), 440.0).unwrap();
    assert_ne!(other, first, "a window showing a dialog is not handed another");
}
