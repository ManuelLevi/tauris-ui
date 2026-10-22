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
    // ".pdf" alone is a hidden file named "pdf", with no extension.
    let ext = Path::new(name).extension().map(|e| e.to_string_lossy().to_ascii_lowercase()).unwrap_or_default();
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
/// no characters Windows refuses, none of Windows' device names (CON, PRN,
/// AUX, NUL, CONIN$, CONOUT$, COM0–9 and LPT0–9 with ¹²³ too, which get a
/// "_" in front), no control characters, no invisible characters (such as a
/// right-to-left mark that makes "fdp.exe" read as "exe.pdf"), no leading dot
/// or space, no trailing dot or space, at most 200 characters and 255 bytes
/// (the extension is kept). Empty becomes "file".
pub fn safe_name(name: &str) -> String {
    // Spaces, dots and control characters at either end go first, so a name
    // that ends in a tab keeps its extension ("report.pdf\t" is "report.pdf").
    let edge = |c: char| c == '.' || c.is_whitespace() || c.is_control() || invisible(c);
    let swapped: String = name
        .trim_start_matches(edge)
        .trim_end_matches(edge)
        .chars()
        .filter(|c| !invisible(*c))
        .map(|c| {
            let breaks = c.is_control() || matches!(c, '\u{2028}' | '\u{2029}');
            if breaks || matches!(c, '/' | '\\' | ':' | '*' | '?' | '"' | '<' | '>' | '|') {
                '-'
            } else {
                c
            }
        })
        .collect();
    let trimmed = swapped.trim_start_matches(edge).trim_end_matches(edge).to_string();
    if trimmed.is_empty() {
        return "file".into();
    }
    // Most disks allow 255 bytes; 200 characters keeps full paths short.
    const CHARS: usize = 200;
    const BYTES: usize = 255;
    // Cut first, then the device check on what is left ("CON" and spaces cut
    // down to "CON.txt" is still caught); one character fewer makes room for its "_".
    let cut = |room: usize| -> String {
        if trimmed.chars().count() <= CHARS - room && trimmed.len() <= BYTES - room {
            return trimmed.clone();
        }
        match trimmed.rsplit_once('.') {
            Some((stem, ext)) if !ext.is_empty() && ext.chars().count() <= 10 => {
                let kept = head(stem, CHARS - room - ext.chars().count() - 1, BYTES - room - ext.len() - 1);
                format!("{}.{ext}", kept.trim_end_matches(edge))
            }
            _ => head(&trimmed, CHARS - room, BYTES - room).trim_end_matches(edge).to_string(),
        }
    };
    let name = cut(0);
    if is_device(&name) {
        format!("_{}", cut(1))
    } else {
        name
    }
}

// Windows keeps these names for devices, with any extension ("con.txt" too).
fn is_device(name: &str) -> bool {
    let stem = name.split('.').next().unwrap_or("").trim_end().to_uppercase();
    let numbered = |prefix: &str| {
        stem.strip_prefix(prefix).is_some_and(|n| {
            let mut chars = n.chars();
            matches!((chars.next(), chars.next()), (Some(c), None) if c.is_ascii_digit() || matches!(c, '¹' | '²' | '³'))
        })
    };
    matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL" | "CONIN$" | "CONOUT$") || numbered("COM") || numbered("LPT")
}

// Characters that show nothing but change how a name reads (direction
// marks, zero-width and blank letters, tags). U+FE0F stays: emoji need it.
fn invisible(c: char) -> bool {
    matches!(c, '\u{00AD}' | '\u{034F}' | '\u{061C}' | '\u{115F}' | '\u{1160}' | '\u{17B4}' | '\u{17B5}' | '\u{180E}'
        | '\u{200B}'..='\u{200F}' | '\u{202A}'..='\u{202E}' | '\u{2060}'..='\u{2064}' | '\u{2066}'..='\u{206F}'
        | '\u{2800}' | '\u{3164}' | '\u{FEFF}' | '\u{FFA0}' | '\u{FFF9}'..='\u{FFFB}' | '\u{E0000}'..='\u{E007F}')
}

// The start of `s`: at most `chars` characters and `bytes` bytes, never half a character.
fn head(s: &str, chars: usize, bytes: usize) -> &str {
    let mut end = 0;
    for (n, c) in s.chars().enumerate() {
        if n == chars || end + c.len_utf8() > bytes {
            break;
        }
        end += c.len_utf8();
    }
    &s[..end]
}

/// A size as the files component shows it: "0 KB", "240 KB", "2.4 MB", "1.2 GB".
pub fn size_text(bytes: u64) -> String {
    const KB: f64 = 1024.0;
    const MB: f64 = 1024.0 * 1024.0;
    const GB: f64 = 1024.0 * MB;
    let n = bytes as f64;
    let kb = ((n / KB).round() as u64).max(1);
    if bytes == 0 {
        "0 KB".into()
    } else if kb < 1024 {
        format!("{} KB", grouped(kb))
    } else if (n / MB * 10.0).round() < 10240.0 {
        // Up a unit where the rounded number would read 1,024.
        format!("{} MB", one_decimal(n / MB))
    } else {
        format!("{} GB", one_decimal(n / GB))
    }
}

// A limit as a sentence says it: as size_text when that is exact ("2 KB",
// "1.5 MB"), otherwise in bytes ("1,500 bytes"), so a file over the limit
// never shows the limit's own size.
fn limit_text(bytes: u64) -> String {
    const KB: u64 = 1024;
    const MB: u64 = 1024 * KB;
    const GB: u64 = 1024 * MB;
    let exact = match bytes {
        b if b < KB => false,
        b if b < MB => b % KB == 0,
        b if b < GB => (b * 10) % MB == 0,
        b => (b * 10) % GB == 0,
    };
    match bytes {
        1 => "1 byte".into(),
        b if exact => size_text(b),
        b => format!("{} bytes", grouped(b)),
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

// How a message names a path: its file name ("The file" for an empty path).
fn name_of(path: &Path) -> String {
    match path.file_name() {
        Some(n) => n.to_string_lossy().into_owned(),
        None if path.as_os_str().is_empty() => "The file".into(),
        None => path.display().to_string(),
    }
}

/// Checks a dropped or picked path. A folder, a missing file, or a file over
/// `max_bytes` comes back as a sentence to show the person, such as
/// "Contracts is a folder. Add files, not folders." The page component shows
/// it when the app's onAdd fails with it.
pub fn inspect(path: impl AsRef<Path>, max_bytes: Option<u64>) -> Result<FileInfo, String> {
    let path = path.as_ref();
    let name = name_of(path);
    let meta = match std::fs::metadata(path) {
        Ok(meta) => meta,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Err(format!("{name} could not be found.")),
        // There, but behind a folder the person may not look in.
        Err(_) => return Err(format!("{name} could not be read.")),
    };
    if meta.is_dir() {
        // A macOS package: one document to the person (TextEdit's .rtfd, Pages, Keynote), a folder on disk.
        let ext = Path::new(&name).extension().map(|e| e.to_string_lossy().to_ascii_lowercase()).unwrap_or_default();
        if ["rtfd", "pages", "key", "numbers", "bundle"].contains(&ext.as_str())
            || path.join("Contents").is_dir()
            || path.join("index.xml").is_file()
        {
            return Err(format!(
                "{name} is a package (a document saved as a folder). Export it as a single file, or zip it."
            ));
        }
        return Err(format!("{name} is a folder. Add files, not folders."));
    }
    if !meta.is_file() {
        // A device or a pipe, such as /dev/null.
        return Err(format!("{name} is not a file that can be added."));
    }
    // Seen, but not readable (no permission): adding it would fail later.
    if std::fs::File::open(path).is_err() {
        return Err(format!("{name} could not be read."));
    }
    // A shortcut (a Finder alias, a Windows or web shortcut) points at a file
    // on the sender's own disk: the file itself is what to add.
    let ext = Path::new(&name).extension().map(|e| e.to_string_lossy().to_ascii_lowercase()).unwrap_or_default();
    if ["lnk", "url", "webloc", "inetloc", "fileloc"].contains(&ext.as_str()) || is_alias(&head_bytes(path)) {
        return Err(format!("{name} is a shortcut. Add the file itself."));
    }
    let size = meta.len();
    if let Some(max) = max_bytes {
        if size > max {
            return Err(format!("{name} is larger than {}.", limit_text(max)));
        }
    }
    let mime = mime_for(&name);
    Ok(FileInfo { path: path.to_path_buf(), name, size, mime })
}

// The first bytes of a file (fewer if it is shorter, none if it cannot be read).
fn head_bytes(path: &Path) -> Vec<u8> {
    use std::io::Read;
    let mut head = Vec::with_capacity(16);
    let _ = std::fs::File::open(path).and_then(|f| f.take(16).read_to_end(&mut head));
    head
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
/// A file that is a program, or would run one ("Q3 plan.command", an `.exe`,
/// a shortcut), is not opened, nor is a folder: shared files come from
/// other people.
#[cfg(feature = "files")]
pub fn open_path(path: impl AsRef<Path>) -> Result<(), String> {
    let path = path.as_ref();
    let name = name_of(path);
    if !path.exists() {
        return Err(format!("{name} could not be found."));
    }
    if path.is_dir() {
        return Err(format!("{name} is a folder, not a file."));
    }
    if runs_something(path) {
        return Err(format!("{name} could be a program, so it is not opened."));
    }
    open::that_detached(path).map_err(|e| format!("Couldn't open {name}: {e}"))
}

// A Finder alias: bookmark data, "book" then "mark".
fn is_alias(head: &[u8]) -> bool {
    head.len() >= 12 && &head[..4] == b"book" && &head[8..12] == b"mark"
}

// A script ("#!"), or an ELF or Mach-O program.
#[cfg(all(unix, any(feature = "files", test)))]
fn starts_as_program(head: &[u8]) -> bool {
    const MAGIC: [&[u8]; 6] =
        [b"#!", b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"];
    MAGIC.iter().any(|m| head.starts_with(m)) || head.starts_with(b"\xca\xfe\xba\xbe")
}

// Files the system would run, install, mount or open a program or web page
// from, rather than show: by the name of what a link points at (Windows
// ignores trailing dots and spaces; the list holds at least everything
// Outlook blocks, and remote desktop files and disk images), a Finder alias,
// and, on Unix, a file marked executable that has no extension or starts as a
// program. Web pages (.html, .svg) open in the browser, which runs them in its
// sandbox, as a link would.
#[cfg(any(feature = "files", test))]
fn runs_something(path: &Path) -> bool {
    let target = std::fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
    let name =
        target.file_name().map(|n| n.to_string_lossy().trim_end_matches(['.', ' ']).to_string()).unwrap_or_default();
    // Read where something below looks at it (not on Windows, outside the tests).
    #[cfg(any(unix, test))]
    let head = head_bytes(&target);
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        // Marked executable: a program when it has no extension (the system
        // runs it by its mark), or when it starts as one (a script's "#!", an
        // ELF or Mach-O binary). A document with an extension opens by its type
        // (every file on a USB stick or a network share is marked).
        let marked = std::fs::metadata(&target).is_ok_and(|m| m.is_file() && m.permissions().mode() & 0o111 != 0);
        let no_extension = !name.get(1..).is_some_and(|n| n.contains('.'));
        if marked && (no_extension || starts_as_program(&head)) {
            return true;
        }
    }
    // A Finder alias is an ordinary file (not a link) that macOS follows to
    // whatever it points at, whatever it is called.
    #[cfg(any(target_os = "macos", test))]
    if is_alias(&head) {
        return true;
    }
    #[rustfmt::skip]
    const PROGRAMS: &[&str] = &[
        "app", "command", "tool", "terminal", "workflow", "action", "service", "scpt", "scptd", "applescript", "osax",
        "pkg", "mpkg", "dmg", "webloc", "inetloc", "fileloc", "shortcut", "prefpane", "saver", "kext", "plugin",
        "bundle", "qlgenerator", "mdimporter", "wdgt", "mobileconfig", "provisionprofile", "configprofile",
        "safariextz", "crx", "xpi", "sh", "bash", "zsh", "csh", "ksh", "fish", "py", "pyc", "pyo", "pyw", "pyz", "pyzw",
        "pl", "rb", "jar", "class", "desktop", "run", "appimage", "deb", "rpm", "snap", "flatpakref", "flatpakrepo",
        "exe", "com", "bat", "cmd", "scr", "msi", "msp", "mst", "msu", "msix", "msixbundle", "appx", "appxbundle",
        "appinstaller", "cab", "cpl", "ps1", "ps1xml", "ps2", "ps2xml", "psc1", "psc2", "psd1", "psm1", "msh", "msh1",
        "msh2", "mshxml", "msh1xml", "msh2xml", "vb", "vbe", "vbp", "vbs", "js", "jse", "ws", "wsb", "wsc", "wsf",
        "wsh", "sct", "hta", "htc", "lnk", "url", "website", "scf", "reg", "inf", "ins", "isp", "its", "application",
        "appref-ms", "appcontent-ms", "settingcontent-ms", "library-ms", "search-ms", "searchconnector-ms", "xbap",
        "xnk", "diagcab", "gadget", "grp", "hlp", "hpj", "chm", "cnt", "msc", "ops", "osd", "pcd", "pif", "plg", "prf",
        "prg", "printerexport", "jnlp", "iso", "img", "vhd", "vhdx", "cer", "crt", "der", "theme", "one", "tmp", "asp",
        "aspx", "asx", "bas", "bgi", "fxp", "ade", "adp", "mad", "maf", "mag", "mam", "maq", "mar", "mas", "mat", "mau",
        "mav", "maw", "mcf", "mda", "mdb", "mde", "mdt", "mdw", "mdz", "accde", "accdr", "accda", "docm", "dotm",
        "xlsm", "xltm", "xlam", "xla", "xll", "ppam", "ppa", "pptm", "potm", "sldm", "wll", "iqy", "slk", "vsmacros",
        "vsw", "webpnp",
        "shs", "shb", "psdm1", "ppsm", "xlm", "xlsb", "themepack", "deskthemepack", "onepkg", "afploc", "ftploc",
        "rdp", "sparseimage", "sparsebundle", "cdr", "toast", "mht", "mhtml",
        "ipa", "vncloc", "mailloc", "atloc", "newsloc", "pst",
    ];
    let ext = Path::new(&name).extension().map(|e| e.to_string_lossy().to_ascii_lowercase()).unwrap_or_default();
    PROGRAMS.contains(&ext.as_str())
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

/// A yes/no question as the system's alert (TaurisDialog.confirm with
/// `native: true`): true for `ok`. Needs the `files` feature and the dialog plugin.
pub(crate) async fn ask_for_page<R: Runtime>(
    window: WebviewWindow<R>,
    title: String,
    message: String,
    ok: String,
    cancel: String,
    warning: bool,
) -> Result<bool, String> {
    #[cfg(feature = "files")]
    {
        use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
        let app = window.app_handle().clone();
        if app.try_state::<tauri_plugin_dialog::Dialog<R>>().is_none() {
            return Err(NO_DIALOG_PLUGIN.into());
        }
        let kind = if warning { MessageDialogKind::Warning } else { MessageDialogKind::Info };
        let (tx, rx) = std::sync::mpsc::channel();
        app.dialog()
            .message(message)
            .title(title)
            .kind(kind)
            .buttons(MessageDialogButtons::OkCancelCustom(ok, cancel))
            .parent(&window)
            .show(move |yes| {
                let _ = tx.send(yes);
            });
        Ok(answer(rx).await.unwrap_or(false))
    }
    #[cfg(not(feature = "files"))]
    {
        let _ = (window, title, message, ok, cancel, warning);
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
        assert_eq!(mime_for(".pdf"), "application/octet-stream");
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
        assert_eq!(safe_name("COM0.txt"), "_COM0.txt");
        assert_eq!(safe_name("lpt²"), "_lpt²");
        assert_eq!(safe_name("CONIN$"), "_CONIN$");
        assert_eq!(safe_name("conout$.log"), "_conout$.log");
        assert_eq!(safe_name("COM10.txt"), "COM10.txt");
        // A long name cut down to a device name is caught after the cut.
        let padded = format!("CON{}x.txt", " ".repeat(250));
        assert!(safe_name(&padded).starts_with('_'), "{}", safe_name(&padded));
        let spaced = format!("{} {}", "x".repeat(199), "y".repeat(20));
        assert!(!safe_name(&spaced).ends_with(' '));
        let long = format!("{}.pdf", "x".repeat(300));
        let cut = safe_name(&long);
        assert_eq!(cut.chars().count(), 200);
        assert!(cut.ends_with(".pdf"));
        // Four bytes a character: the byte limit cuts first.
        let wide = safe_name(&format!("{}.txt", "𝄞".repeat(100)));
        assert!(wide.len() <= 255 && wide.ends_with(".txt") && !wide.contains('\u{FFFD}'), "{wide}");
        assert_eq!(safe_name("invoice\u{202E}fdp.exe"), "invoicefdp.exe");
        assert_eq!(safe_name("zero\u{200B}width.txt"), "zerowidth.txt");
        assert_eq!(safe_name(". a"), "a");
        assert_eq!(safe_name("report.pdf\t"), "report.pdf");
        assert_eq!(safe_name("\tnotes.txt\n"), "notes.txt");
        assert_eq!(safe_name("a\u{2028}b.txt"), "a-b.txt");
        assert_eq!(safe_name("a\u{3164}\u{E0041}.txt"), "a.txt");
        assert_eq!(safe_name("ok\u{FE0F}.txt"), "ok\u{FE0F}.txt");
        assert_eq!(safe_name(" . report.pdf . "), "report.pdf");
    }

    #[test]
    fn sizes_read_as_the_page_shows_them() {
        assert_eq!(size_text(0), "0 KB");
        assert_eq!(size_text(1), "1 KB");
        assert_eq!(size_text(389_120), "380 KB");
        assert_eq!(size_text(1_047_552), "1,023 KB");
        assert_eq!(size_text(1_048_575), "1 MB");
        assert_eq!(size_text(1024 * 1024 * 1024 - 1), "1 GB");
        assert_eq!(size_text(2_516_582), "2.4 MB");
        assert_eq!(size_text(50 * 1024 * 1024), "50 MB");
        assert_eq!(size_text(1536 * 1024 * 1024), "1.5 GB");
    }

    // What open_path refuses, before anything is opened.
    #[cfg(feature = "files")]
    #[test]
    fn open_path_refuses_folders_and_programs() {
        let dir = std::env::temp_dir().join(format!("tauris-ui-open-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        assert_eq!(open_path("").unwrap_err(), "The file could not be found.");
        assert_eq!(open_path(dir.join("gone.pdf")).unwrap_err(), "gone.pdf could not be found.");
        assert_eq!(
            open_path(&dir).unwrap_err(),
            format!("{} is a folder, not a file.", dir.file_name().unwrap().to_string_lossy())
        );
        let program = dir.join("Q3 plan.command");
        std::fs::write(&program, "x").unwrap();
        // Checked first: a guard that let it through would make the next line run it.
        assert!(runs_something(&program));
        assert_eq!(open_path(&program).unwrap_err(), "Q3 plan.command could be a program, so it is not opened.");
        std::fs::remove_dir_all(&dir).ok();
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
        // A macOS package is one document to the person, a folder on disk.
        let rtfd = dir.join("Notes.rtfd");
        std::fs::create_dir_all(&rtfd).unwrap();
        assert_eq!(
            inspect(&rtfd, None).unwrap_err(),
            "Notes.rtfd is a package (a document saved as a folder). Export it as a single file, or zip it."
        );
        // A shortcut is not the file: a Windows one, and a Finder alias named like a document.
        let lnk = dir.join("Report - Shortcut.lnk");
        std::fs::write(&lnk, "L").unwrap();
        assert_eq!(inspect(&lnk, None).unwrap_err(), "Report - Shortcut.lnk is a shortcut. Add the file itself.");
        let alias = dir.join("Invoice alias.pdf");
        std::fs::write(&alias, b"book\0\0\0\0mark\0\0\0\0the rest").unwrap();
        assert_eq!(inspect(&alias, None).unwrap_err(), "Invoice alias.pdf is a shortcut. Add the file itself.");
        assert_eq!(inspect(&file, Some(2048)).unwrap_err(), "Term sheet.docx is larger than 2 KB.");
        assert_eq!(inspect(&file, Some(100)).unwrap_err(), "Term sheet.docx is larger than 100 bytes.");
        assert_eq!(inspect(&file, Some(1500)).unwrap_err(), "Term sheet.docx is larger than 1,500 bytes.");
        assert_eq!(limit_text(1536 * 1024), "1.5 MB");
        assert_eq!(limit_text(2_000_000), "2,000,000 bytes");
        assert_eq!(inspect("", None).unwrap_err(), "The file could not be found.");
        #[cfg(unix)]
        assert_eq!(inspect("/dev/null", None).unwrap_err(), "null is not a file that can be added.");
        // A file that cannot be read is said so now, not when the app copies it.
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let locked = dir.join("locked.txt");
            std::fs::write(&locked, "x").unwrap();
            std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o000)).unwrap();
            // Root reads anything: only checked for everyone else.
            if std::fs::File::open(&locked).is_err() {
                assert_eq!(inspect(&locked, None).unwrap_err(), "locked.txt could not be read.");
            }
            std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o644)).unwrap();
        }
        assert!(runs_something(Path::new("Q3 plan.command")) && runs_something(Path::new("setup.EXE")));
        assert!(runs_something(Path::new("a.exe. ")) && runs_something(Path::new("Budget.xlsm")));
        assert!(!runs_something(Path::new("Board deck.pdf")) && !runs_something(Path::new("notes")));
        for name in [
            "Q3.xll",
            "x.scf",
            "disk.iso",
            "a.vhdx",
            "go.appref-ms",
            "p.settingcontent-ms",
            "n.one",
            "Doc.fileloc",
            "Q3 results.ppsm",
            "x.xlm",
            "x.xlsb",
            "x.shs",
            "x.shb",
            "x.psdm1",
            "x.themepack",
            "x.deskthemepack",
            "x.onepkg",
            "x.afploc",
            "x.ftploc",
            "Board.rdp",
            "x.sparseimage",
            "x.cdr",
            "x.toast",
            "x.mht",
            "Game.ipa",
            "Office.vncloc",
            "x.mailloc",
            "Mail.pst",
        ] {
            assert!(runs_something(Path::new(name)), "{name}");
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            // A program with no extension, and a link named like a document pointing at one.
            let tool = dir.join("tool");
            std::fs::write(&tool, "#!/bin/sh\n").unwrap();
            std::fs::set_permissions(&tool, std::fs::Permissions::from_mode(0o755)).unwrap();
            assert!(runs_something(&tool));
            // A Finder alias named like a document: macOS would open what it points at.
            let alias = dir.join("Invoice (alias).pdf");
            std::fs::write(&alias, b"book\0\0\0\0mark\0\0\0\0the rest of the bookmark").unwrap();
            assert!(runs_something(&alias));
            // Documents marked executable (every file on a USB stick is) still open, whatever their
            // kind; a script with an extension does not.
            for doc in ["Logo.psd", "Holiday.mkv", "Book.epub"] {
                let f = dir.join(doc);
                std::fs::write(&f, "data").unwrap();
                std::fs::set_permissions(&f, std::fs::Permissions::from_mode(0o777)).unwrap();
                assert!(!runs_something(&f), "{doc}");
            }
            let script = dir.join("notes.yaml");
            std::fs::write(&script, "#!/bin/sh\necho hi\n").unwrap();
            std::fs::set_permissions(&script, std::fs::Permissions::from_mode(0o755)).unwrap();
            assert!(runs_something(&script));
            // A document marked executable (every file on a USB stick is) still opens.
            let board = dir.join("Board.pdf");
            std::fs::write(&board, "%PDF").unwrap();
            std::fs::set_permissions(&board, std::fs::Permissions::from_mode(0o700)).unwrap();
            assert!(!runs_something(&board));
            let run = dir.join("run.command");
            std::fs::write(&run, "x").unwrap();
            let link = dir.join("Invoice.pdf");
            let _ = std::fs::remove_file(&link);
            std::os::unix::fs::symlink(&run, &link).unwrap();
            assert!(runs_something(&link));
        }
        assert!(inspect(&file, Some(3000)).is_ok());

        std::fs::remove_dir_all(&dir).ok();
    }
}
