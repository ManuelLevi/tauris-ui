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
    // Page-side changes reach the hook too.
    let id = app.tabs().windows()[0].tabs[0].id;
    windows::update(app.handle(), id, "renamed".into(), Fields::new(), false);
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
    windows::forget_window(app.handle(), &second);
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
    assert!(handler.contains("InPlugin::enter()"), "on_event does not mark Tauri's lock");
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
    ] {
        assert!(!outside.contains(call), "on_event calls {call} itself; send it through after_event");
    }
}

// A page command in src/commands.rs: its name, whether it is async, its body.
struct Command {
    name: String,
    is_async: bool,
    body: String,
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
        out.push(Command {
            name,
            is_async: head.split_whitespace().any(|w| w == "async"),
            body: item[open..close].to_string(),
        });
        rest = &item[close..];
    }
    out
}

// Every plain (not async) page command runs inside Tauri's plugin lock and must say so.
#[test]
fn every_plain_command_marks_the_lock() {
    let all = commands();
    assert!(all.len() >= 15, "only {} commands found", all.len());
    for c in all.iter().filter(|c| !c.is_async) {
        assert!(c.body.contains("InPlugin::enter()"), "the command {} does not mark Tauri's lock", c.name);
    }
}

// The hook never runs twice at once, and calls keep their order: one waiting
// on the worker (from inside Tauri's lock) and one made right after by the app.
#[test]
fn the_hook_never_runs_twice_at_once() {
    let running = Arc::new(AtomicUsize::new(0));
    let most = Arc::new(AtomicUsize::new(0));
    let order = Arc::new(std::sync::Mutex::new(Vec::new()));
    let (r, m, o) = (running.clone(), most.clone(), order.clone());
    let app = app(quiet().on_change(move |_, label| {
        let now = r.fetch_add(1, Ordering::SeqCst) + 1;
        m.fetch_max(now, Ordering::SeqCst);
        std::thread::sleep(std::time::Duration::from_millis(30));
        o.lock().unwrap().push(label.to_string());
        r.fetch_sub(1, Ordering::SeqCst);
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
    assert_eq!(most.load(Ordering::SeqCst), 1, "two hook calls overlapped");
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
    let seen = calls.clone();
    let app = app(quiet().on_change(move |_, label| {
        seen.lock().unwrap().push(label.to_string());
    }));
    app.tabs().start().unwrap();
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    calls.lock().unwrap().clear();
    // Hold the hook back, as a page's command would be holding Tauri's lock.
    let gate = Arc::new(std::sync::Mutex::new(()));
    let held = gate.lock().unwrap();
    let g = gate.clone();
    windows::send(app.handle(), windows::Kind::Hook, Box::new(move |_| drop(g.lock())));
    {
        let _locked = windows::InPlugin::enter();
        windows::changed(app.handle(), "tabs-1");
        windows::changed(app.handle(), "tabs-2");
    }
    assert!(calls.lock().unwrap().is_empty(), "the hook ran inside Tauri's lock");
    drop(held);
    windows::settle(app.handle(), std::time::Duration::from_secs(2));
    assert_eq!(*calls.lock().unwrap(), ["tabs-1", "tabs-2"]);
    windows::changed(app.handle(), "tabs-3");
    assert_eq!(calls.lock().unwrap().len(), 3, "outside the lock the hook runs at once");
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
            std::thread::sleep(std::time::Duration::from_millis(100));
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
    assert!(took >= std::time::Duration::from_millis(450) && took < std::time::Duration::from_millis(900), "{took:?}");
    windows::after_event(app.handle(), |app| {
        let _ = app.tabs().new_window();
    });
    std::thread::sleep(std::time::Duration::from_millis(100));
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
    let app = app(quiet().on_change(move |_, _| {
        let now = r.fetch_add(1, Ordering::SeqCst) + 1;
        m.fetch_max(now, Ordering::SeqCst);
        std::thread::sleep(std::time::Duration::from_millis(40));
        c.fetch_add(1, Ordering::SeqCst);
        r.fetch_sub(1, Ordering::SeqCst);
    }));
    let handle = app.handle().clone();
    let other = handle.clone();
    let first = std::thread::spawn(move || windows::changed(&other, "a"));
    std::thread::sleep(std::time::Duration::from_millis(10));
    windows::changed(&handle, "b");
    first.join().unwrap();
    windows::settle(&handle, std::time::Duration::from_secs(2));
    assert_eq!(calls.load(Ordering::SeqCst), 2);
    assert_eq!(most.load(Ordering::SeqCst), 1, "two hook calls overlapped");
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
