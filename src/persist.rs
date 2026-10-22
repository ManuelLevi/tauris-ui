// Remembering: the windows, their tabs and where each window sits are saved a
// moment after every change and when the app quits, and come back when the app
// opens again or is reopened after its last window closed. Closing the last
// window keeps the layout, so the app reopens as it was.

use crate::model::{Frame, NewTab, Tab};
use crate::windows::{default_tab, inner, open_window};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
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

// The app's layout_file can be called inside Tauri's plugin lock (⌘W on the
// last tab, quitting): a panic there must not unwind through Tauri.
fn layout_file<R: Runtime>(app: &AppHandle<R>) -> Option<PathBuf> {
    let file = inner(app).config.layout_file.as_ref()?;
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| file(app))) {
        Ok(path) => path,
        Err(payload) => {
            std::mem::forget(payload); // its drop could panic too
            eprintln!("tauris-ui: the app's layout_file panicked; the layout is not saved");
            None
        }
    }
}

// Opens the remembered windows, or one new window when there are none; then
// keeps saving. A second call does nothing.
pub(crate) fn start<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    if inner(app).started.swap(true, Ordering::SeqCst) {
        return Ok(());
    }
    // A start that failed (no window could open) can be tried again.
    if let Err(e) = restore(app) {
        inner(app).started.store(false, Ordering::SeqCst);
        return Err(e);
    }
    // Writes a crash left half done, a minute old or more: of no use, and they hold tab titles.
    if let Some(file) = layout_file(app) {
        for f in half_written(&file, Some(Duration::from_secs(60))) {
            let _ = fs::remove_file(f);
        }
    }
    let app = app.clone();
    // No thread to be had: the layout is still saved at quit and when the last window closes.
    let saving = thread::Builder::new().name("tauris-ui save".into()).spawn(move || loop {
        thread::sleep(Duration::from_millis(500));
        save(&app, false);
    });
    if saving.is_err() {
        eprintln!("tauris-ui: no thread to save the layout as it changes; it is saved at quit");
    }
    Ok(())
}

// The Dock icon was clicked with no window open: the remembered windows come
// back (only in an app that uses tabs, i.e. called start()), on the windows'
// worker (this runs inside Tauri's lock).
#[cfg(any(target_os = "macos", test))]
pub(crate) fn reopened<R: Runtime>(app: &AppHandle<R>) {
    if inner(app).started.load(Ordering::SeqCst) {
        crate::windows::after_event(app, |app| {
            let _ = restore(app);
        });
    }
}

// Opens the remembered windows, or one new window when there are none. Does
// nothing while windows of tabs are open.
pub(crate) fn restore<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    if crate::windows::window_count(app) > 0 {
        return Ok(());
    }
    // The new window too is opened by one caller only.
    let Some(_one) = Restoring::claim(app) else { return Ok(()) };
    if crate::windows::window_count(app) == 0 && !open_saved(app) {
        crate::windows::create_window(app, vec![default_tab(app)], None, true)?;
    }
    Ok(())
}

// One restore at a time: two callers that both found no window (a Dock click
// and the app's own open_or_focus) must not each open them all. Never waited
// for here: the other one may need this thread to open its windows.
struct Restoring(&'static AtomicBool);

impl Restoring {
    fn claim<R: Runtime>(app: &AppHandle<R>) -> Option<Self> {
        let flag = &inner(app).restoring;
        // `then`, not `then_some`: a guard made and dropped would clear the flag.
        (!flag.swap(true, Ordering::SeqCst)).then(|| Restoring(flag))
    }
}

impl Drop for Restoring {
    fn drop(&mut self) {
        self.0.store(false, Ordering::SeqCst);
    }
}

// Opens the remembered windows, frontmost last; false when there are none
// (true when another caller is opening them already).
// An unreadable file is kept aside as `<name>.unreadable` so it is not lost
// when the next layout is saved.
pub(crate) fn restore_saved<R: Runtime>(app: &AppHandle<R>) -> bool {
    // Another caller is opening them: they are on their way (true), and no
    // other window should open in their place.
    let Some(_one) = Restoring::claim(app) else { return true };
    if crate::windows::window_count(app) > 0 {
        return true;
    }
    open_saved(app)
}

// The remembered windows open (the caller holds the restore). Not while
// quitting: none could open, and the file is left as it is for the next launch.
fn open_saved<R: Runtime>(app: &AppHandle<R>) -> bool {
    if crate::windows::quitting(app) {
        return false;
    }
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
        // A window remembered on a screen no longer attached opens centred
        // (with its size, maximized if it was), and is remembered there.
        let frame = w.frame.map(|f| Frame { centre: !on_screen(app, &f), ..f });
        if let Some(win) = inner(app).model().win(&label) {
            win.frame = frame;
        }
        match open_window(app, &label, frame, i + 1 == count) {
            Ok(_) => {
                opened += 1;
                crate::windows::changed(app, &label);
            }
            Err(_) => inner(app).model().remove_win(&label),
        }
    }
    // The file's windows are back: a save at once still to be tried again
    // would add the ones that closed to them a second time.
    if opened > 0 {
        inner(app).retry_now.store(false, Ordering::SeqCst);
        // Nor would a quit a moment later add them: they are back.
        inner(app).model().closing.clear();
    }
    // Remembered windows that could not open are kept aside, not lost when the
    // windows that did open are saved.
    if opened == 0 && count > 0 {
        let _ = fs::rename(&file, file.with_extension("unopened"));
    } else if opened < count {
        let _ = fs::copy(&file, file.with_extension("unopened"));
    }
    opened > 0
}

// Files a save writes aside (`<file>.<process>.tmp`) and a crash left behind;
// with `older`, only those not touched for that long (another copy of the app
// may be writing its own).
fn half_written(file: &std::path::Path, older: Option<Duration>) -> Vec<PathBuf> {
    let (Some(dir), Some(name)) = (file.parent(), file.file_name().map(|n| n.to_string_lossy().to_string())) else {
        return vec![];
    };
    let Ok(entries) = fs::read_dir(dir) else { return vec![] };
    entries
        .filter_map(Result::ok)
        .filter(|e| {
            let n = e.file_name().to_string_lossy().to_string();
            n.starts_with(&format!("{name}.")) && n.ends_with(".tmp")
        })
        .filter(|e| {
            older.is_none_or(|age| {
                e.metadata().and_then(|m| m.modified()).ok().and_then(|t| t.elapsed().ok()).is_some_and(|t| t >= age)
            })
        })
        .map(|e| e.path())
        .collect()
}

// A screen: x, y, width and height.
type Screen = (f64, f64, f64, f64);

#[cfg(test)]
thread_local! {
    // The screens a test says there are (the test runtime cannot list any).
    pub(crate) static TEST_SCREENS: std::cell::RefCell<Option<Vec<Screen>>> = const { std::cell::RefCell::new(None) };
}

fn on_screen<R: Runtime>(app: &AppHandle<R>, f: &Frame) -> bool {
    #[cfg(test)]
    if let Some(screens) = TEST_SCREENS.with(|s| s.borrow().clone()) {
        return within(f, &screens);
    }
    // A runtime that cannot list its screens (the test runtime cannot) knows none.
    let monitors = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| app.available_monitors()))
        .ok()
        .and_then(Result::ok)
        .unwrap_or_default();
    let screens: Vec<Screen> = monitors
        .iter()
        .map(|m| {
            let (p, s) =
                (m.position().to_logical::<f64>(m.scale_factor()), m.size().to_logical::<f64>(m.scale_factor()));
            (p.x, p.y, s.width, s.height)
        })
        .collect();
    within(f, &screens)
}

// Whether a window's title bar (a point just inside its top left) is on one of
// these screens (x, y, width, height). No screens known (some systems report
// none): nothing is off one.
fn within(f: &Frame, screens: &[Screen]) -> bool {
    screens.is_empty()
        || screens
            .iter()
            .any(|&(x, y, w, h)| f.x + 40.0 >= x && f.x + 40.0 <= x + w && f.y + 10.0 >= y && f.y + 10.0 <= y + h)
}

// The user closed every tab: nothing is remembered, so tab titles (which can
// be people's names) do not come back at the next launch.
pub(crate) fn forget<R: Runtime>(app: &AppHandle<R>) {
    let state = inner(app);
    let _writing = state.save_lock();
    {
        let mut m = state.model();
        // A window opened meanwhile (⌘N right after the last tab closed): it is remembered.
        if !m.wins.is_empty() {
            return;
        }
        m.saved();
        m.closing.clear();
        state.retry_now.store(false, Ordering::SeqCst);
    }
    // The copies kept aside go too, and a write a crash left half done: they hold tab titles as well.
    if let Some(file) = layout_file(app) {
        for f in [file.with_extension("unopened"), file.with_extension("unreadable")]
            .into_iter()
            .chain(half_written(&file, None))
        {
            let _ = fs::remove_file(f);
        }
        let _ = fs::remove_file(file);
    }
}

// Saves the layout: once it has settled, or at once with `now`. Never an
// empty one, so closing the last window keeps what it showed.
pub(crate) fn save<R: Runtime>(app: &AppHandle<R>, now: bool) {
    let state = inner(app);
    // One save at a time, from deciding what to write to the file being in place.
    let _writing = state.save_lock();
    // A save at once that failed is tried again as one, windows closed then included.
    let retry = state.retry_now.load(Ordering::SeqCst);
    let now = now || retry;
    let saved: Vec<SavedWin> = {
        let mut m = state.model();
        // Windows closed longer ago than a quit takes are of no use to any
        // save (but to the retry of the one that was due when they closed).
        if !retry {
            m.closing.retain(|c| c.at.elapsed() < QUIT_BURST);
        }
        let due = match (m.changed_at, m.unsaved_since) {
            (Some(last), Some(first)) => now || last.elapsed() >= state.config.settle || first.elapsed() >= MAX_WAIT,
            _ => false,
        };
        // While remembered windows are opening, the file still holds them all.
        if !due || state.restoring.load(Ordering::SeqCst) {
            return;
        }
        m.saved();
        state.retry_now.store(false, Ordering::SeqCst);
        // Windows closed a moment ago are kept only by a save at once (the app
        // quitting closes them one by one); a save after a pause leaves them out.
        let mut closed: Vec<&crate::model::Closed> = m.closing.iter().filter(|_| now).collect();
        closed.sort_by_key(|c| c.order); // stable: the same place keeps the order they closed in
        let just_closed = closed.into_iter().map(|c| SavedWin {
            active: c.win.active.and_then(|a| c.win.tabs.iter().position(|t| *t == a)).unwrap_or(0),
            tabs: c.tabs.clone(),
            frame: c.win.frame,
        });
        // A window still opening may never show (the app is quitting): left out.
        let open = m.wins.iter().filter(|w| !w.opening).map(|w| SavedWin {
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
    // Written aside then moved over, so a crash never leaves half a file, and
    // on the disk before the move, so a power cut never leaves an empty one.
    // Readable by the owner only: tab titles can be people's names. The name
    // aside is this process's own: two copies of the app never write one file.
    let tmp = file.with_extension(format!("json.{}.tmp", std::process::id()));
    let written = {
        use std::io::Write;
        let mut options = fs::OpenOptions::new();
        options.write(true).create(true).truncate(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        options.open(&tmp).and_then(|mut f| {
            f.write_all(text.as_bytes())?;
            f.sync_all()
        })
    };
    if written.is_ok() && fs::rename(&tmp, &file).is_ok() {
        // The move is on the disk too.
        #[cfg(unix)]
        if let Some(dir) = file.parent() {
            let _ = fs::File::open(dir).and_then(|d| d.sync_all());
        }
        return;
    }
    // Not written: the changes stay unsaved, so the next round tries again,
    // and a save at once is tried again as one.
    let _ = fs::remove_file(&tmp);
    if now {
        state.retry_now.store(true, Ordering::SeqCst);
    }
    state.model().changed();
}

#[cfg(test)]
mod tests {
    use super::{within, SavedWin};
    use crate::model::Frame;

    #[test]
    fn a_window_is_on_a_screen_by_its_title_bar() {
        let f = |x, y| Frame { x, y, width: 900.0, height: 700.0, maximized: false, centre: false };
        let screens = [(0.0, 0.0, 1440.0, 900.0), (1440.0, -200.0, 2560.0, 1440.0)];
        assert!(within(&f(100.0, 50.0), &screens));
        assert!(within(&f(2000.0, -150.0), &screens), "on the second screen, above the first");
        assert!(!within(&f(5000.0, 50.0), &screens), "on a screen no longer attached");
        assert!(!within(&f(-900.0, 50.0), &screens), "its title bar off the left edge");
        assert!(within(&f(5000.0, 50.0), &[]), "no screens known: nothing is off one");
    }

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
