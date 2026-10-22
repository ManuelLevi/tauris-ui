const COMMANDS: &[&str] = &[
    "window_state",
    "new_tab",
    "close_tab",
    "activate_tab",
    "move_tab",
    "update_tab",
    "report_strip",
    "drag_out",
    "open_tab",
    "set_close_guard",
    "close_window",
    "move_to_new_window",
    "other_windows",
    "move_to_window",
    "ask",
    "close_asked",
    "pick_files",
    "save_dialog",
    "dialog_window_open",
    "dialog_window_spec",
    "dialog_window_ready",
    "dialog_window_send",
    "dialog_window_reply",
    "dialog_window_close",
];

fn main() {
    tauri_plugin::Builder::new(COMMANDS).build();
    // On Windows a program that links Tauri starts only with the common
    // controls' manifest (STATUS_ENTRYPOINT_NOT_FOUND without it); real apps get
    // it from tauri-build. The library's own tests get it here. (Only programs
    // of this package are linked with it: an app using the library is not.)
    let windows = std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows")
        && std::env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc");
    let manifest =
        std::path::Path::new(&std::env::var("CARGO_MANIFEST_DIR").unwrap_or_default()).join("test/windows.manifest");
    if windows && manifest.is_file() {
        println!("cargo:rerun-if-changed={}", manifest.display());
        println!("cargo:rustc-link-arg=/MANIFEST:EMBED");
        println!("cargo:rustc-link-arg=/MANIFESTINPUT:{}", manifest.display());
    }
}
