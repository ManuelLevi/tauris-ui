"""Tests for scripts/doctor.py: small apps, each set up right or wrong in one
way, and what the checker says about them.

    python test/doctor_run.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
LIBRARY = HERE.parent
DOCTOR = LIBRARY / "scripts" / "doctor.py"
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail != "" and not ok else ""))
    if not ok:
        failures.append(name)


GOOD_RUST = "fn main() { tauri::Builder::default().plugin(tauris_ui::init(tauris_ui::Config::new())); }\n"
GOOD_CAP = {"identifier": "default", "windows": ["*"], "permissions": ["core:default", "tauris-ui:default"]}


def app(page="<script>TaurisFiles.mount(document.body, { pick: async () => [] })</script>", rust=GOOD_RUST,
        dependency=None, capability=GOOD_CAP, conf_app=None, workspace=None, extra=None):
    """Writes a small app and runs the checker on it: (its output, exit code)."""
    root = Path(tempfile.mkdtemp(prefix="tauris-doctor-"))
    tauri = root / "src-tauri"
    (tauri / "src").mkdir(parents=True)
    (tauri / "capabilities").mkdir()
    (root / "dist").mkdir()
    dep = dependency or f'{{ path = "{LIBRARY}", version = "0.4" }}'
    (tauri / "Cargo.toml").write_text(f'[package]\nname = "x"\nversion = "0.1.0"\n[dependencies]\ntauris-ui = {dep}\n')
    if workspace:
        (root / "Cargo.toml").write_text(workspace)
    conf = {"app": conf_app or {"withGlobalTauri": True}, "build": {"frontendDist": "../dist"}}
    (tauri / "tauri.conf.json").write_text(json.dumps(conf))
    if capability is not None:
        (tauri / "capabilities" / "default.json").write_text(json.dumps(capability))
    (tauri / "src" / "main.rs").write_text(rust)
    (root / "dist" / "index.html").write_text(page)
    for name, text in (extra or {}).items():
        (root / "dist" / name).write_text(text)
    run = subprocess.run([sys.executable, str(DOCTOR), str(root)], capture_output=True, text=True, encoding="utf-8")
    return run.stdout + run.stderr, run.returncode


out, code = app()
check("a good app is ready", code == 0 and "Ready" in out, out)

# ---------- comments, strings and regular expressions ----------
out, _ = app(page="<script>const base = url.replace(/\\/*$/, '');\nTaurisFiles.mount(el, { pick: f });\n/* later */\n</script>")
check("a `/*` inside a regular expression starts no comment", "components in use: files" in out, out)
out, _ = app(page="<script>s.replace(/'/g, '');\n// TaurisTabs.mount(x)\nconst t = 'ok';\nTaurisFiles.mount(el, { pick: f })</script>")
check("a quote inside a regular expression starts no string (a commented-out mount stays out)", "tabs" not in out.split("components in use:")[1].split("\n")[0], out)
out, _ = app(page="<p>Don't panic</p>\n<script>\n// TaurisTabs.mount(x)\nTaurisFiles.mount(el, { pick: f })\n</script>")
check("a quote in the page's text starts no string", "tabs" not in out.split("components in use:")[1].split("\n")[0], out)
out, _ = app(page="<!-- <script>TaurisTabs.mount(x)</script> --><script>TaurisFiles.mount(el, { pick: f })</script>")
check("HTML comments are left out", "tabs" not in out.split("components in use:")[1].split("\n")[0], out)
out, _ = app(rust="fn main() { let q = '\"';\n// .plugin(tauris_ui::init(tauris_ui::Config::new()))\nlet s = \"x\"; let _: &'static str = s; }\n")
check("Rust: a quote in a character literal starts no string (a commented-out plugin stays out)", "the plugin is not registered" in out, out)
out, _ = app(rust="/* outer /* inner */ .plugin(tauris_ui::init(x)) */ fn main() {}\n")
check("Rust: nested comments", "the plugin is not registered" in out, out)
out, _ = app(rust="use tauris_ui::{init, Config};\nfn main() { tauri::Builder::default().plugin(init(Config::new())); }\n")
check("Rust: init imported with `use` counts", "ok    the plugin is registered" in out, out)

# ---------- the pick option ----------
for name, page in [("TypeScript's mount<F>(...)", "TaurisFiles.mount<MyFile>(el, { pick: async () => [] })"),
                   ("a quoted key", "TaurisFiles.mount(el, { \"pick\": async () => [] })"),
                   ("TaurisFiles?.mount", "window.TaurisFiles?.mount(el, { pick: f })"),
                   ("a method", "TaurisFiles.mount(el, { async pick() { return [] } })"),
                   ("a variable declared with it", "const o = { pick: async () => [] }; TaurisFiles.mount(el, o)")]:
    out, _ = app(page=f"<script>{page}</script>")
    check(f"pick given as {name}", "own picker" in out, out)
for name, page in [("a call to a function named pick", "TaurisFiles.mount(el, { onAdd: p => pick(p) })"),
                   ("pick deeper in the options", "TaurisFiles.mount(el, { labels: { pick: 'x' } })"),
                   ("a semicolon-less page with pick elsewhere", "const opts = { onAdd: p => p }\nTaurisFiles.mount(document.body, opts)\nfunction pick(x){return x}")]:
    out, _ = app(page=f"<script>{page}</script>")
    check(f"no pick option: {name}", "own picker" not in out and "needs tauris-ui's \"files\" feature" in out, out)

# ---------- capabilities ----------
out, _ = app(capability=[GOOD_CAP], page="<script>TaurisTabs.mount(document.getElementById('strip'))</script>")
check("a capability file holding a list", "grants tauris-ui:default to the tab windows" in out, out)
out, _ = app(capability={"capabilities": [GOOD_CAP]}, page="<script>TaurisTabs.mount(document.getElementById('strip'))</script>")
check('a capability file holding { "capabilities": [...] }', "grants tauris-ui:default to the tab windows" in out, out)
out, _ = app(capability={**{k: v for k, v in GOOD_CAP.items() if k != "windows"}, "webviews": ["tabs-*"]},
             page="<script>TaurisTabs.mount(document.getElementById('strip'))</script>")
check("a capability for webviews covers the tab windows", "grants tauris-ui:default to the tab windows" in out, out)
inline_only = {"withGlobalTauri": True, "security": {"capabilities": [{"identifier": "inline", "windows": ["other"], "permissions": ["core:default"]}]}}
out, _ = app(conf_app=inline_only, page="<script>TaurisTabs.mount(document.getElementById('strip'))</script>")
check("a list in tauri.conf.json enables only what it lists, inline ones too", "FIX   no capability grants tauris-ui:default" in out, out)
listed = {"withGlobalTauri": True, "security": {"capabilities": ["default"]}}
out, _ = app(conf_app=listed, page="<script>TaurisTabs.mount(document.getElementById('strip'))</script>")
check("a capability listed by its identifier counts", "grants tauris-ui:default to the tab windows" in out, out)

# ---------- versions ----------
sys.path.insert(0, str(DOCTOR.parent))
doctor = {"__name__": "doctor", "__file__": str(DOCTOR)}
exec(DOCTOR.read_text(encoding="utf-8").split("def main():")[0], doctor)
accepts = doctor["accepts"]
cases = [("0.4", "0.4.16", True), ("0", "0.4.16", True), ("0.*", "0.4.16", True), ("=0.4.1", "0.4.16", False),
         ("=0.4", "0.4.16", True), ("0.4.17", "0.4.16", False), ("0.3", "0.4.16", False), ("^0.4.2", "0.4.16", True),
         ("~0.4", "0.4.16", True), ("~0.4.17", "0.4.16", False), (">=0.4, <0.5", "0.4.16", True), (">=0.5", "0.4.16", False),
         ("1", "1.9.0", True), ("1", "2.0.0", False), ("0.0.3", "0.0.4", False)]
wrong = [(r, v) for r, v, want in cases if accepts(r, v) != want]
check("version requirements read as Cargo reads them", not wrong, wrong)
out, _ = app(dependency=f'{{ path = "{LIBRARY}", version = "*" }}')
check('version "*" counts as no version', "accepts any version" in out, out)
out, _ = app(dependency="{ workspace = true }", workspace=f'[workspace]\nmembers = ["src-tauri"]\n[workspace.dependencies]\ntauris-ui = {{ path = "{LIBRARY}", version = "0.4" }}\n')
check("{ workspace = true } is read from the workspace", "ok    Cargo.toml depends on this tauris-ui" in out, out)

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
