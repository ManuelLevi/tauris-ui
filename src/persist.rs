// Remembering: the windows, their tabs and where each window sits are saved a
// moment after every change and when the app quits, and come back when the app
// opens again or is reopened after its last window closed. Closing the last
// window keeps the layout, so the app reopens as it was.

use crate::model::{Frame, NewTab, Tab};
use crate::windows::{default_tab, inner, open_window};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::Ordering;
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Runtime};

// How long a closed window still counts as open, so a quit (which closes every
// window within milliseconds) saves them all.
const QUIT_BURST: Duration = Duration::from_millis(600);
// A save waits for the changes to settle, but never longer than this, so
// steady typing is still saved.
const MAX_WAIT: Duration = Duration::from_secs(5);

#[derive(Serialize, Deserialize)]
struct SavedWin {
    tabs: Vec<Tab>,
    active: usize,
    frame: Option<Frame>,
}

fn layout_file<R: Runtime>(app: &AppHandle<R>) -> Option<PathBuf> {
    inner(app).config.layout_file.as_ref().and_then(|f| f(app))
}

// Opens the remembered windows, or one new window when there are none; then
// keeps saving. A second call does nothing.
pub(crate) fn start<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    if inner(app).started.swap(true, Ordering::SeqCst) {
        return Ok(());
    }
    restore(app)?;
    let app = app.clone();
    thread::spawn(move || loop {
        thread::sleep(Duration::from_millis(500));
        save(&app, false);
    });
    Ok(())
}

// Opens the remembered windows, or one new window when there are none. Does
// nothing while windows of tabs are open.
pub(crate) fn restore<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    if crate::windows::window_count(app) > 0 {
        return Ok(());
    }
    if !restore_saved(app) {
        crate::windows::create_window(app, vec![default_tab(app)], None, true)?;
    }
    Ok(())
}

// Opens the remembered windows, frontmost last; false when there are none.
// An unreadable file is kept aside as `<name>.unreadable` so it is not lost
// when the next layout is saved.
pub(crate) fn restore_saved<R: Runtime>(app: &AppHandle<R>) -> bool {
    let Some(file) = layout_file(app).filter(|f| f.is_file()) else { return false };
    let saved: Vec<SavedWin> = match fs::read_to_string(&file).map(|t| serde_json::from_str(&t)) {
        Ok(Ok(saved)) => saved,
        _ => {
            let _ = fs::rename(&file, file.with_extension("unreadable"));
            return false;
        }
    };
    let saved: Vec<SavedWin> = saved.into_iter().filter(|w| !w.tabs.is_empty()).collect();
    let count = saved.len();
    let mut opened = 0;
    for (i, w) in saved.into_iter().enumerate() {
        let label = {
            let mut m = inner(app).model();
            let ids: Vec<u64> = w
                .tabs
                .iter()
                .map(|t| m.create_tab(NewTab { title: t.title.clone(), fields: t.fields.clone() }))
                .collect();
            let label = m.create_win(ids.clone());
            if let Some(win) = m.win(&label) {
                win.active = ids.get(w.active).copied().or(win.active);
                win.frame = w.frame;
            }
            label
        };
        // A window remembered on a screen no longer attached opens centred.
        let frame = w.frame.filter(|f| on_screen(app, f));
        match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| open_window(app, &label, frame, i + 1 == count)))
        {
            Ok(Ok(_)) => {
                opened += 1;
                crate::windows::changed(app, &label);
            }
            Ok(Err(_)) => inner(app).model().remove_win(&label),
            // The app's window hook panicked: no window, so no record of one.
            Err(panic) => {
                inner(app).model().remove_win(&label);
                std::panic::resume_unwind(panic);
            }
        }
    }
    opened > 0
}

fn on_screen<R: Runtime>(app: &AppHandle<R>, f: &Frame) -> bool {
    let Ok(monitors) = app.available_monitors() else { return true };
    monitors.iter().any(|m| {
        let (p, s) = (m.position().to_logical::<f64>(m.scale_factor()), m.size().to_logical::<f64>(m.scale_factor()));
        f.x + 40.0 >= p.x && f.x + 40.0 <= p.x + s.width && f.y + 10.0 >= p.y && f.y + 10.0 <= p.y + s.height
    })
}

// The user closed every tab: nothing is remembered, so tab titles (which can
// be people's names) do not come back at the next launch.
pub(crate) fn forget<R: Runtime>(app: &AppHandle<R>) {
    let state = inner(app);
    let _writing = state.save_lock();
    {
        let mut m = state.model();
        m.saved();
        m.closing.clear();
    }
    if let Some(file) = layout_file(app) {
        let _ = fs::remove_file(file);
    }
}

// Saves the layout: once it has settled, or at once with `now`. Never an
// empty one, so closing the last window keeps what it showed.
pub(crate) fn save<R: Runtime>(app: &AppHandle<R>, now: bool) {
    let state = inner(app);
    // One save at a time, from deciding what to write to the file being in place.
    let _writing = state.save_lock();
    let saved: Vec<SavedWin> = {
        let mut m = state.model();
        let due = match (m.changed_at, m.unsaved_since) {
            (Some(last), Some(first)) => now || last.elapsed() >= state.config.settle || first.elapsed() >= MAX_WAIT,
            _ => false,
        };
        if !due {
            return;
        }
        m.saved();
        m.closing.retain(|c| c.at.elapsed() < QUIT_BURST);
        let just_closed = m.closing.iter().map(|c| SavedWin {
            active: c.win.active.and_then(|a| c.win.tabs.iter().position(|t| *t == a)).unwrap_or(0),
            tabs: c.tabs.clone(),
            frame: c.win.frame,
        });
        let open = m.wins.iter().map(|w| SavedWin {
            tabs: w.tabs.iter().filter_map(|id| m.tabs.get(id).cloned()).collect(),
            active: w.active.and_then(|a| w.tabs.iter().position(|t| *t == a)).unwrap_or(0),
            frame: w.frame,
        });
        // The frontmost window is saved last, so it opens in front.
        just_closed.chain(open).filter(|w| !w.tabs.is_empty()).collect()
    };
    if saved.is_empty() {
        return;
    }
    let (Some(file), Ok(text)) = (layout_file(app), serde_json::to_string(&saved)) else { return };
    if let Some(dir) = file.parent() {
        let _ = fs::create_dir_all(dir);
    }
    // Written aside then moved over, so a crash never leaves half a file.
    // Readable by the owner only: tab titles can be people's names.
    let tmp = file.with_extension("json.tmp");
    let written = {
        use std::io::Write;
        let mut options = fs::OpenOptions::new();
        options.write(true).create(true).truncate(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        options.open(&tmp).and_then(|mut f| f.write_all(text.as_bytes()))
    };
    if written.is_ok() {
        let _ = fs::rename(&tmp, &file);
    }
}

#[cfg(test)]
mod tests {
    use super::SavedWin;

    #[test]
    fn a_saved_layout_reads_back_with_the_apps_fields() {
        let text = r#"[{"tabs":[{"id":4,"title":"Users","query":"","view":"view:users","env":"staging"}],"active":0,"frame":{"x":10.0,"y":20.0,"width":1180.0,"height":760.0}}]"#;
        let saved: Vec<SavedWin> = serde_json::from_str(text).unwrap();
        assert_eq!(saved[0].tabs[0].title, "Users");
        assert_eq!(saved[0].tabs[0].fields["env"], "staging");
        let again = serde_json::to_string(&saved).unwrap();
        let back: Vec<SavedWin> = serde_json::from_str(&again).unwrap();
        assert_eq!(back[0].tabs[0].fields["view"], "view:users");
        assert_eq!(back[0].frame.unwrap().width, 1180.0);
    }
}
