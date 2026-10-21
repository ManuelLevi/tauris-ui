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
    "close_asked",
];

fn main() {
    tauri_plugin::Builder::new(COMMANDS).build();
}
