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
    windows::drain(app.handle(), std::time::Duration::from_secs(2));
    let before = calls.load(Ordering::SeqCst);
    app.tabs().open(NewTab::new("X")).unwrap();
    windows::drain(app.handle(), std::time::Duration::from_secs(2));
    assert_eq!(calls.load(Ordering::SeqCst), before + 1);
    // Page-side changes reach the hook too.
    let id = app.tabs().windows()[0].tabs[0].id;
    windows::update(app.handle(), id, "renamed".into(), Fields::new(), false);
    windows::drain(app.handle(), std::time::Duration::from_secs(2));
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
    windows::drain(app.handle(), std::time::Duration::from_secs(2));
    heard.lock().unwrap().clear();
    windows::forget_window(app.handle(), &second);
    windows::drain(app.handle(), std::time::Duration::from_secs(2));
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
    // The hook runs on the worker: the panic is caught there, and the next change still reaches it.
    let handle = app.handle().clone();
    windows::changed(&handle, "x");
    windows::changed(&handle, "x");
    windows::drain(&handle, std::time::Duration::from_secs(2));
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
    let source = include_str!("commands.rs");
    // Every #[tauri::command], sync or async.
    let mut defined: Vec<String> = source
        .split("#[tauri::command]")
        .skip(1)
        .map(|s| s.split(" fn ").nth(1).expect("a command function").split(['<', '(']).next().unwrap().to_string())
        .collect();
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
// (the Dock click, ⌘N). Only the real event loop shows the freeze, so this
// checks the source: whatever can open a window runs through after_event.
#[test]
fn the_event_handler_opens_no_window_itself() {
    let source = include_str!("lib.rs");
    let from = source.find(".on_event(|app, event|").expect("the plugin's on_event");
    let to = from + source[from..].find(".build()").expect("the end of on_event");
    let handler = &source[from..to];
    let opens = ["new_tab()", "new_window()", "persist::restore(", "open_or_focus(", "create_window("];
    let lines: Vec<&str> = handler.lines().collect();
    for (i, line) in lines.iter().enumerate() {
        if let Some(call) = opens.iter().find(|call| line.contains(*call)) {
            let before = &lines[i.saturating_sub(2)..i];
            assert!(before.iter().any(|l| l.contains("after_event(")), "{call} runs inside on_event: {line}");
        }
    }
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

// The app's hook never runs where the change happened: that can be inside the
// plugin's on_event or a page's command, where Tauri holds its plugin lock and
// a hook that opened a window would freeze the app. It runs on the worker, in order.
#[test]
fn the_hook_runs_after_the_change_in_order() {
    let calls = Arc::new(std::sync::Mutex::new(Vec::new()));
    let seen = calls.clone();
    let app = app(quiet().on_change(move |_, label| {
        seen.lock().unwrap().push(label.to_string());
    }));
    app.tabs().start().unwrap();
    windows::drain(app.handle(), std::time::Duration::from_secs(2));
    calls.lock().unwrap().clear();
    // Hold the hook back, as a page's command would be holding Tauri's lock.
    let gate = Arc::new(std::sync::Mutex::new(()));
    let held = gate.lock().unwrap();
    let g = gate.clone();
    windows::after_event(app.handle(), move |_| drop(g.lock()));
    windows::changed(app.handle(), "tabs-1");
    windows::changed(app.handle(), "tabs-2");
    assert!(calls.lock().unwrap().is_empty(), "the hook ran where the change happened");
    drop(held);
    windows::drain(app.handle(), std::time::Duration::from_secs(2));
    assert_eq!(*calls.lock().unwrap(), ["tabs-1", "tabs-2"]);
}

// Quitting waits (a moment at most) for the hook to hear the last changes.
#[test]
fn quitting_waits_for_the_last_hook_calls() {
    let app = app(quiet());
    let done = Arc::new(AtomicUsize::new(0));
    let d = done.clone();
    windows::after_event(app.handle(), move |_| {
        std::thread::sleep(std::time::Duration::from_millis(100));
        d.fetch_add(1, Ordering::SeqCst);
    });
    windows::drain(app.handle(), std::time::Duration::from_secs(2));
    assert_eq!(done.load(Ordering::SeqCst), 1);
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
    windows::drain(app.handle(), std::time::Duration::from_secs(2));
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
