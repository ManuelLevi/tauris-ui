//! Helpers for apps that keep files, the Rust side of the files component
//! (`TaurisFiles` in the page): names and types, a check before a path is
//! stored, and, with the `files` feature, the system's pickers and opening a
//! file with its default app.
//!
//! ```ignore
//! // A command the page's onAdd calls with dropped or picked paths.
//! #[tauri::command]
//! async fn add_files(paths: Vec<String>) -> Result<Vec<MyFile>, String> {
//!     let mut added = Vec::new();
//!     for p in paths {
//!         // "Contracts is a folder. Add files, not folders." comes back as the error.
//!         let file = tauris_ui::files::inspect(&p, Some(50 * 1024 * 1024))?;
//!         added.push(store(file).await?);
//!     }
//!     Ok(added)
//! }
//! ```

use serde::Serialize;
use std::path::{Path, PathBuf};
#[cfg(feature = "files")]
use tauri::{AppHandle, Manager};
use tauri::{Runtime, WebviewWindow};

/// The MIME type for a file name, from its extension (`application/octet-stream` when unknown).
pub fn mime_for(name: &str) -> &'static str {
    let ext = name.rsplit_once('.').map(|(_, e)| e.to_ascii_lowercase()).unwrap_or_default();
    match ext.as_str() {
        "pdf" => "application/pdf",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        "heic" => "image/heic",
        "heif" => "image/heif",
        "avif" => "image/avif",
        "tif" | "tiff" => "image/tiff",
        "bmp" => "image/bmp",
        "svg" => "image/svg+xml",
        "mp4" | "m4v" => "video/mp4",
        "mov" => "video/quicktime",
        "webm" => "video/webm",
        "mp3" => "audio/mpeg",
        "m4a" => "audio/mp4",
        "aac" => "audio/aac",
        "wav" => "audio/wav",
        "flac" => "audio/flac",
        "ogg" => "audio/ogg",
        "txt" => "text/plain",
        "md" => "text/markdown",
        "csv" => "text/csv",
        "tsv" => "text/tab-separated-values",
        "html" | "htm" => "text/html",
        "json" => "application/json",
        "xml" => "application/xml",
        "rtf" => "application/rtf",
        "zip" => "application/zip",
        "gz" | "tgz" => "application/gzip",
        "tar" => "application/x-tar",
        "7z" => "application/x-7z-compressed",
        "doc" => "application/msword",
        "docx" => "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls" => "application/vnd.ms-excel",
        "xlsx" => "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "ppt" => "application/vnd.ms-powerpoint",
        "pptx" => "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "odt" => "application/vnd.oasis.opendocument.text",
        "ods" => "application/vnd.oasis.opendocument.spreadsheet",
        "odp" => "application/vnd.oasis.opendocument.presentation",
        "pages" => "application/vnd.apple.pages",
        "numbers" => "application/vnd.apple.numbers",
        "key" => "application/vnd.apple.keynote",
        _ => "application/octet-stream",
    }
}

/// A file name that is safe to create on disk, on every system: no folders,
/// no characters Windows refuses, none of Windows' device names (CON, NUL,
/// COM1…, which get a "_" in front), no control characters, no leading dot,
/// at most 200 characters (the extension is kept). Empty becomes "file".
pub fn safe_name(name: &str) -> String {
    let swapped: String =
        name.chars()
            .map(|c| {
                if c.is_control() || matches!(c, '/' | '\\' | ':' | '*' | '?' | '"' | '<' | '>' | '|') {
                    '-'
                } else {
                    c
                }
            })
            .collect();
    let trimmed = swapped.trim().trim_start_matches('.').trim_end_matches(['.', ' ']).to_string();
    if trimmed.is_empty() {
        return "file".into();
    }
    // Windows keeps these names for devices, with any extension ("con.txt" too).
    let stem = trimmed.split('.').next().unwrap_or("").trim_end().to_ascii_uppercase();
    let device = matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        || (stem.len() == 4
            && (stem.starts_with("COM") || stem.starts_with("LPT"))
            && stem.as_bytes()[3].is_ascii_digit()
            && stem.as_bytes()[3] != b'0');
    let trimmed = if device { format!("_{trimmed}") } else { trimmed };
    if trimmed.chars().count() <= 200 {
        return trimmed;
    }
    match trimmed.rsplit_once('.') {
        Some((stem, ext)) if !ext.is_empty() && ext.chars().count() <= 10 => {
            let keep = 200 - ext.chars().count() - 1;
            format!("{}.{ext}", stem.chars().take(keep).collect::<String>().trim_end())
        }
        _ => trimmed.chars().take(200).collect(),
    }
}

/// A size as the files component shows it: "0 KB", "240 KB", "2.4 MB", "1.2 GB".
pub fn size_text(bytes: u64) -> String {
    const KB: f64 = 1024.0;
    const MB: f64 = 1024.0 * 1024.0;
    const GB: f64 = 1024.0 * MB;
    let n = bytes as f64;
    if bytes == 0 {
        "0 KB".into()
    } else if n < MB {
        format!("{} KB", grouped(((n / KB).round() as u64).max(1)))
    } else if n < GB {
        format!("{} MB", one_decimal(n / MB))
    } else {
        format!("{} GB", one_decimal(n / GB))
    }
}

fn grouped(n: u64) -> String {
    let digits = n.to_string();
    let mut out = String::new();
    for (i, c) in digits.chars().enumerate() {
        if i > 0 && (digits.len() - i).is_multiple_of(3) {
            out.push(',');
        }
        out.push(c);
    }
    out
}

fn one_decimal(v: f64) -> String {
    let tenths = (v * 10.0).round() as u64;
    if tenths.is_multiple_of(10) {
        grouped(tenths / 10)
    } else {
        format!("{}.{}", grouped(tenths / 10), tenths % 10)
    }
}

/// A file checked before an app stores it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FileInfo {
    pub path: PathBuf,
    /// The file's own name ("Board deck.pdf").
    pub name: String,
    /// Bytes.
    pub size: u64,
    /// From the extension; see [`mime_for`].
    pub mime: &'static str,
}

/// Checks a dropped or picked path. A folder, a missing file, or a file over
/// `max_bytes` comes back as a sentence to show the person, such as
/// "Contracts is a folder. Add files, not folders." The page component shows
/// it when the app's onAdd fails with it.
pub fn inspect(path: impl AsRef<Path>, max_bytes: Option<u64>) -> Result<FileInfo, String> {
    let path = path.as_ref();
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| path.display().to_string());
    if path.is_dir() {
        return Err(format!("{name} is a folder. Add files, not folders."));
    }
    if !path.is_file() {
        return Err(format!("{name} could not be found."));
    }
    let size = match std::fs::metadata(path) {
        Ok(meta) => meta.len(),
        Err(_) => return Err(format!("{name} could not be read.")),
    };
    if let Some(max) = max_bytes {
        if size > max {
            return Err(format!("{name} is larger than {}.", size_text(max)));
        }
    }
    let mime = mime_for(&name);
    Ok(FileInfo { path: path.to_path_buf(), name, size, mime })
}

// ---------- the system's dialogs and opening (the "files" feature) ----------

#[cfg(not(feature = "files"))]
const NO_FEATURE: &str = "The file dialogs need tauris-ui's \"files\" feature: \
    tauris-ui = { ..., features = [\"files\"] } in the app's Cargo.toml.";

#[cfg(feature = "files")]
const NO_DIALOG_PLUGIN: &str = "The file dialogs need the dialog plugin: add tauri-plugin-dialog = \"2\" \
    to the app's Cargo.toml and .plugin(tauri_plugin_dialog::init()) to its tauri::Builder.";

/// The system's file picker, in front of the focused window: the paths the
/// person chose, or none if they cancel. Needs the `files` feature and the
/// dialog plugin (`.plugin(tauri_plugin_dialog::init())`).
#[cfg(feature = "files")]
pub async fn pick_files<R: Runtime>(app: &AppHandle<R>, title: &str) -> Result<Vec<PathBuf>, String> {
    pick(app, focused(app), Some(title), true).await
}

/// The system's save dialog with `name` filled in: the chosen path, or None
/// if the person cancels. Needs the `files` feature and the dialog plugin.
#[cfg(feature = "files")]
pub async fn save_dialog<R: Runtime>(app: &AppHandle<R>, title: &str, name: &str) -> Result<Option<PathBuf>, String> {
    save(app, focused(app), Some(title), Some(name)).await
}

/// Opens a file with the system's default app for it. Needs the `files` feature.
///
/// The page cannot call this: a page that could open any path could start
/// any program. The app opens the files it knows, from its own command.
#[cfg(feature = "files")]
pub fn open_path(path: impl AsRef<Path>) -> Result<(), String> {
    let path = path.as_ref();
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| path.display().to_string());
    if !path.exists() {
        return Err(format!("{name} could not be found."));
    }
    open::that_detached(path).map_err(|e| format!("Couldn't open {name}: {e}"))
}

#[cfg(feature = "files")]
fn focused<R: Runtime>(app: &AppHandle<R>) -> Option<WebviewWindow<R>> {
    app.webview_windows().into_values().find(|w| w.is_focused().unwrap_or(false))
}

#[cfg(feature = "files")]
pub(crate) fn dialogs<R: Runtime>(app: &AppHandle<R>) -> Result<tauri_plugin_dialog::FileDialogBuilder<R>, String> {
    use tauri_plugin_dialog::DialogExt;
    if app.try_state::<tauri_plugin_dialog::Dialog<R>>().is_none() {
        return Err(NO_DIALOG_PLUGIN.into());
    }
    Ok(app.dialog().file())
}

// The dialog answers on its own thread; the wait for it happens off the async runtime.
#[cfg(feature = "files")]
async fn answer<T: Send + 'static>(rx: std::sync::mpsc::Receiver<T>) -> Option<T> {
    tauri::async_runtime::spawn_blocking(move || rx.recv().ok()).await.ok().flatten()
}

#[cfg(feature = "files")]
pub(crate) async fn pick<R: Runtime>(
    app: &AppHandle<R>,
    parent: Option<WebviewWindow<R>>,
    title: Option<&str>,
    multiple: bool,
) -> Result<Vec<PathBuf>, String> {
    let mut dialog = dialogs(app)?;
    if let Some(title) = title {
        dialog = dialog.set_title(title);
    }
    if let Some(window) = &parent {
        dialog = dialog.set_parent(window);
    }
    let (tx, rx) = std::sync::mpsc::channel();
    if multiple {
        dialog.pick_files(move |files| {
            let _ = tx.send(files.unwrap_or_default());
        });
    } else {
        dialog.pick_file(move |file| {
            let _ = tx.send(file.into_iter().collect());
        });
    }
    let chosen = answer(rx).await.unwrap_or_default();
    Ok(chosen.into_iter().filter_map(|f| f.into_path().ok()).collect())
}

#[cfg(feature = "files")]
pub(crate) async fn save<R: Runtime>(
    app: &AppHandle<R>,
    parent: Option<WebviewWindow<R>>,
    title: Option<&str>,
    name: Option<&str>,
) -> Result<Option<PathBuf>, String> {
    let mut dialog = dialogs(app)?;
    if let Some(title) = title {
        dialog = dialog.set_title(title);
    }
    if let Some(name) = name {
        dialog = dialog.set_file_name(safe_name(name));
    }
    if let Some(window) = &parent {
        dialog = dialog.set_parent(window);
    }
    let (tx, rx) = std::sync::mpsc::channel();
    dialog.save_file(move |path| {
        let _ = tx.send(path);
    });
    Ok(answer(rx).await.flatten().and_then(|p| p.into_path().ok()))
}

// What the page's commands run (src/commands.rs). Without the feature they
// say how to turn it on, so a page that uses the picker gets a clear message.
pub(crate) async fn pick_for_page<R: Runtime>(
    window: WebviewWindow<R>,
    title: Option<String>,
    multiple: bool,
) -> Result<Vec<String>, String> {
    #[cfg(feature = "files")]
    {
        let app = window.app_handle().clone();
        let paths = pick(&app, Some(window), title.as_deref(), multiple).await?;
        Ok(paths.into_iter().map(|p| p.to_string_lossy().into_owned()).collect())
    }
    #[cfg(not(feature = "files"))]
    {
        let _ = (window, title, multiple);
        Err(NO_FEATURE.into())
    }
}

pub(crate) async fn save_for_page<R: Runtime>(
    window: WebviewWindow<R>,
    title: Option<String>,
    name: Option<String>,
) -> Result<Option<String>, String> {
    #[cfg(feature = "files")]
    {
        let app = window.app_handle().clone();
        let path = save(&app, Some(window), title.as_deref(), name.as_deref()).await?;
        Ok(path.map(|p| p.to_string_lossy().into_owned()))
    }
    #[cfg(not(feature = "files"))]
    {
        let _ = (window, title, name);
        Err(NO_FEATURE.into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn types_from_names() {
        assert_eq!(mime_for("Board deck.PDF"), "application/pdf");
        assert_eq!(mime_for("plan.v2.xlsx"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        assert_eq!(mime_for("photo.HEIC"), "image/heic");
        assert_eq!(mime_for("no-extension"), "application/octet-stream");
        assert_eq!(mime_for(".hidden"), "application/octet-stream");
    }

    #[test]
    fn safe_names() {
        assert_eq!(safe_name("../a/b:c"), "-a-b-c");
        assert_eq!(safe_name("a\\b*c?d\"e<f>g|h"), "a-b-c-d-e-f-g-h");
        assert_eq!(safe_name("line\nbreak.txt"), "line-break.txt");
        assert_eq!(safe_name("   "), "file");
        assert_eq!(safe_name("..."), "file");
        assert_eq!(safe_name("report. "), "report");
        assert_eq!(safe_name("Ação — plan €480.pdf"), "Ação — plan €480.pdf");
        assert_eq!(safe_name("CON.txt"), "_CON.txt");
        assert_eq!(safe_name("nul"), "_nul");
        assert_eq!(safe_name("com1.log"), "_com1.log");
        assert_eq!(safe_name("console.txt"), "console.txt");
        assert_eq!(safe_name("COM0.txt"), "COM0.txt");
        let long = format!("{}.pdf", "x".repeat(300));
        let cut = safe_name(&long);
        assert_eq!(cut.chars().count(), 200);
        assert!(cut.ends_with(".pdf"));
    }

    #[test]
    fn sizes_read_as_the_page_shows_them() {
        assert_eq!(size_text(0), "0 KB");
        assert_eq!(size_text(1), "1 KB");
        assert_eq!(size_text(389_120), "380 KB");
        assert_eq!(size_text(1_047_552), "1,023 KB");
        assert_eq!(size_text(2_516_582), "2.4 MB");
        assert_eq!(size_text(50 * 1024 * 1024), "50 MB");
        assert_eq!(size_text(1536 * 1024 * 1024), "1.5 GB");
    }

    #[test]
    fn inspect_refuses_folders_missing_and_large_files() {
        let dir = std::env::temp_dir().join(format!("tauris-ui-files-{}", std::process::id()));
        let folder = dir.join("Contracts");
        std::fs::create_dir_all(&folder).unwrap();
        let file = dir.join("Term sheet.docx");
        std::fs::write(&file, vec![7u8; 3000]).unwrap();

        let info = inspect(&file, None).unwrap();
        assert_eq!(info.name, "Term sheet.docx");
        assert_eq!(info.size, 3000);
        assert_eq!(info.mime, "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
        assert_eq!(inspect(&folder, None).unwrap_err(), "Contracts is a folder. Add files, not folders.");
        assert_eq!(inspect(dir.join("nope.pdf"), None).unwrap_err(), "nope.pdf could not be found.");
        assert_eq!(inspect(&file, Some(2048)).unwrap_err(), "Term sheet.docx is larger than 2 KB.");
        assert!(inspect(&file, Some(3000)).is_ok());

        std::fs::remove_dir_all(&dir).ok();
    }
}
