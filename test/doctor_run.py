"""Tests for scripts/doctor.py: small apps, each set up right or wrong in one
way, and what the checker says about them.

    python test/doctor_run.py
"""
import json
import shutil
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
        dependency=None, capability=GOOD_CAP, conf_app=None, workspace=None, extra=None, conf=None, manifest=None,
        tsconfig=False, extra_tauri=None, root_files=None, no_page=False):
    """Writes a small app and runs the checker on it: (its output, exit code).
    `extra` adds page files, `extra_tauri` files under src-tauri/capabilities,
    `root_files` files next to src-tauri. The app is deleted afterwards."""
    root = Path(tempfile.mkdtemp(prefix="tauris-doctor-"))
    try:
        return checked(root, page, rust, dependency, capability, conf_app, workspace, extra, conf, manifest, tsconfig,
                       extra_tauri or {}, root_files or {}, no_page)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def checked(root, page, rust, dependency, capability, conf_app, workspace, extra, conf, manifest, tsconfig,
            extra_tauri, root_files, no_page):
    tauri = root / "src-tauri"
    (tauri / "src").mkdir(parents=True)
    (tauri / "capabilities").mkdir()
    (root / "dist").mkdir()
    dep = dependency or f'{{ path = "{LIBRARY}", version = "0.4" }}'
    (tauri / "Cargo.toml").write_text(manifest or f'[package]\nname = "x"\nversion = "0.1.0"\n[dependencies]\ntauris-ui = {dep}\n')
    if tsconfig:
        (root / "tsconfig.json").write_text("{}")
    if workspace:
        (root / "Cargo.toml").write_text(workspace)
    conf = {"app": conf_app or {"withGlobalTauri": True}, "build": {"frontendDist": "../dist"}, **(conf or {})}
    (tauri / "tauri.conf.json").write_text(json.dumps(conf))
    if capability is not None:
        (tauri / "capabilities" / "default.json").write_text(json.dumps(capability))
    (tauri / "src" / "main.rs").write_text(rust)
    if not no_page:
        (root / "dist" / "index.html").write_text(page)
    for name, text in extra_tauri.items():
        (tauri / "capabilities" / name).parent.mkdir(parents=True, exist_ok=True)
        (tauri / "capabilities" / name).write_text(text)
    for name, text in root_files.items():
        (root / name).write_text(text)
    for name, text in (extra or {}).items():
        (root / "dist" / name).write_text(text)
    run = subprocess.run([sys.executable, str(DOCTOR), str(root)], capture_output=True, text=True, encoding="utf-8")
    return run.stdout + run.stderr, run.returncode


out, code = app()
check("a good app is ready", code == 0 and "Ready" in out, out)

# ---------- comments, strings and regular expressions ----------
out, _ = app(page="<script>const base = url.replace(/\\/*$/, '');\nTaurisFiles.mount(el, { pick: f });\n/* later */\n</script>")
check("a `/*` inside a regular expression starts no comment", "components in use: files" in out, out)
out, _ = app(page="<script>s.replace(/'/g, ''); /* TaurisTabs.mount(x) */ const t = 'ok';\nTaurisFiles.mount(el, { pick: f })</script>")
check("a quote inside a regular expression starts no string (a commented-out mount stays out)", "tabs" not in out.split("components in use:")[1].split("\n")[0], out)
out, _ = app(page="<p>Don't panic</p><script>/* TaurisTabs.mount(x) */ TaurisFiles.mount(el, { pick: f })</script>")
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

# ---------- a sixth review ----------
TABS = "<script>TaurisTabs.mount(document.getElementById('strip'))</script>"
out, _ = app(page="<script>const h = `${a.map(x => `[l](https://e.com/${x})`)}`; TaurisFiles.mount(el, { pick: f });</script>")
check("a template inside a template's ${ } ends where it should", "components in use: files" in out, out)
out, _ = app(page="<script>const o = '<!--'; TaurisFiles.mount(el, { pick: f }); const c = '-->';</script>")
check("<!-- inside a script's string is not a comment", "components in use: files" in out, out)
out, _ = app(page="<script>TaurisFiles.mount(el, { pick: f })</script>", extra={"tabs.d.ts": (Path(__file__).parent.parent / "web" / "tabs.d.ts").read_text()})
check("copied typings are not the app using a component", "tabs" not in out.split("components in use:")[1].split("\n")[0], out)
out, _ = app(page="<script src='tabs.js'></script>", extra={"tabs.js": "TaurisTabs.mount(document.getElementById('strip'))"})
check("an app's own tabs.js that mounts the strip is not a copy of the library's", "own copy of the library's tabs.js" not in out, out)
out, _ = app(page="<script src='tabs.js'></script>", extra={"tabs.js": "window.TaurisTabs = { mount() {} }; const CSS = '__TAURIS_TABS_CSS__';"})
check("a copy of the library's tabs.js is found", "own copy of the library's tabs.js" in out, out)
out, code = app(capability=None)
check("an app with its own pick needs no capability for the picker", "no capability grants" not in out and code == 0, out)
out, code = app(page="<script>TaurisFiles.mount(el)</script>", dependency=f'{{ path = "{LIBRARY}", version = "0.4", features = ["files"] }}',
                capability={**GOOD_CAP, "windows": ["settings"]}, conf_app={"withGlobalTauri": True, "windows": [{"title": "x"}]})
check("a capability for other windows does not cover the app's", "does not cover the app's windows" in out and code == 1, out)
out, _ = app(capability={**GOOD_CAP, "windows": ["tabs-1"]}, page=TABS)
check("a capability for tabs-1 alone does not cover every tab window", "not the tab windows" in out, out)
for name, decl in [("a typed declaration", "const opts: TaurisFilesOptions<F> = { pick: f }; TaurisFiles.mount(el, opts)"),
                   ("a trailing comma", "const opts = { pick: f }; TaurisFiles.mount(el, opts,)"),
                   ("a spread", "const base = { pick: f }; const opts = { ...base, onAdd }; TaurisFiles.mount(el, opts)"),
                   ("a getter", "TaurisFiles.mount(el, { get pick() { return f } })")]:
    out, _ = app(page=f"<script>{decl}</script>")
    check(f"pick given through {name}", "own picker" in out, out)
for req, want in [(">0.4", False), ("<=0.4", True), ("<=1", None), ("<=0", True)]:
    if want is None:
        continue
    check(f'"{req}" read as Cargo does', accepts(req, "0.4.17") == want, accepts(req, "0.4.17"))
check('"<=1" takes 1.2.3', accepts("<=1", "1.2.3"))
out, code = app(manifest="[package\nname = x")
check("a Cargo.toml that cannot be read is said so, not a crash", "cannot be read" in out and code == 1 and "Traceback" not in out, out)
renamed = f'[package]\nname = "x"\nversion = "0.1.0"\n[dependencies]\nui = {{ package = "tauris-ui", path = "{LIBRARY}", version = "0.4" }}\n'
out, _ = app(manifest=renamed, rust="fn main() { tauri::Builder::default().plugin(ui::init(ui::Config::new())); }\n")
check("a renamed dependency (ui = { package = \"tauris-ui\" })", "ok    Cargo.toml depends on this tauris-ui" in out and "ok    the plugin is registered" in out, out)
for name, rust in [("init::<Wry>(...)", "fn main() { tauri::Builder::default().plugin(tauris_ui::init::<tauri::Wry>(tauris_ui::Config::new())); }\n"),
                   ("use tauris_ui as ui", "use tauris_ui as ui;\nfn main() { tauri::Builder::default().plugin(ui::init(ui::Config::new())); }\n"),
                   ("a raw byte string with // in it", 'fn main() { let s = br#"a//b"#; tauri::Builder::default().plugin(tauris_ui::init(tauris_ui::Config::new())); }\n')]:
    out, _ = app(rust=rust)
    check(f"the plugin found with {name}", "ok    the plugin is registered" in out, out)

# ---------- a seventh review ----------
out, _ = app(page="<script>TaurisFiles.mount(document.getElementById(`files-${tab.id}`), { pick: myPick })</script>")
check("a ${ } in the first argument is not the options", "own picker" in out, out)
out, code = app(page="<script>TaurisFiles.mount(el)</script>", dependency=f'{{ path = "{LIBRARY}", version = "0.4", features = ["files"] }}',
                capability={**GOOD_CAP, "windows": ["files"]}, conf_app={"withGlobalTauri": True, "windows": []},
                rust=GOOD_RUST + 'fn open(app: &tauri::App) { tauri::WebviewWindowBuilder::new(app, "files", tauri::WebviewUrl::default()); }\n'
                + "fn d() { tauri_plugin_dialog::init(); }\n",
                manifest=f'[package]\nname = "x"\nversion = "0.1.0"\n[dependencies]\ntauri-plugin-dialog = "2"\n'
                         f'tauris-ui = {{ path = "{LIBRARY}", version = "0.4", features = ["files"] }}\n')
check("a window the Rust code opens is one of the app's windows", "does not cover" not in out and code == 0, out)
out, code = app(page="<script>TaurisFiles.mount(el)</script>", rust=GOOD_RUST + "fn d() { tauri_plugin_dialog::init(); }\n",
                manifest=f'[package]\nname = "x"\nversion = "0.1.0"\n[features]\ndefault = ["tauris-ui/files"]\n[dependencies]\n'
                         f'tauri-plugin-dialog = "2"\ntauris-ui = {{ path = "{LIBRARY}", version = "0.4" }}\n')
check("the files feature turned on by the app's default features", 'the "files" feature is on' in out and code == 0, out)
root = Path(tempfile.mkdtemp(prefix="tauris-doctor-"))
try:
    (root / "src-tauri").mkdir()
    (root / "src-tauri" / "Cargo.toml").write_text(f'[package]\nname = "x"\n[dependencies]\ntauris-ui = {{ path = "{LIBRARY}", version = "0.4" }}\n')
    (root / "src-tauri" / "tauri.conf.json").write_text('{ "app": { "withGlobalTauri": true, }, }')
    run = subprocess.run([sys.executable, str(DOCTOR), str(root)], capture_output=True, text=True, encoding="utf-8")
    check("a tauri.conf.json that cannot be read is said so, not a crash",
          "cannot be read" in run.stdout and run.returncode == 1 and "Traceback" not in run.stdout + run.stderr, run.stdout + run.stderr)
finally:
    shutil.rmtree(root, ignore_errors=True)
nested = {"files": {"desktop/main.json": json.dumps(GOOD_CAP)}}
out, code = app(capability=None, page=TABS, extra_tauri=nested["files"],
                rust=GOOD_RUST + "fn s(app: &tauri::App) { app.tabs().start(); }\n")
check("a capability in a folder under capabilities/ counts", "grants tauris-ui:default to the tab windows" in out, out)
git = f'{{ git = "https://example.com/tauris-ui", version = "0.4" }}'
out, code = app(dependency=git, workspace='[workspace]\nmembers = ["src-tauri"]\n',
                root_files={"Cargo.lock": '[[package]]\nname = "tauris-ui"\nversion = "0.4.1"\n'})
check("the workspace's Cargo.lock is read", "locked to tauris-ui 0.4.1" in out and code == 1, out)

# ---------- what is wrong is said, and the exit code says so ----------
for name, kwargs, says in [
    ("a dependency path that leads nowhere", {"dependency": '{ path = "/nowhere", version = "0.4" }'}, "does not lead to tauris-ui"),
    ("an older version asked for", {"dependency": f'{{ path = "{LIBRARY}", version = "0.3" }}'}, "which needs changes in the app"),
    ("withGlobalTauri off", {"conf_app": {"withGlobalTauri": False}}, "dropped files are never heard"),
    ("the tauris-ui layer declared", {"page": "<style>@layer reset, tauris-ui;</style><script>TaurisFiles.mount(el, { pick: f })</script>"}, "declares the tauris-ui layer"),
    ("a capability only for main", {"page": TABS, "capability": {**GOOD_CAP, "windows": ["main"]}}, "not the tab windows"),
    ("the example's identifier", {"conf": {"identifier": "dev.tauris-ui.example"}}, "the example's identifier"),
    ("stale typings", {"tsconfig": True, "extra": {"files.d.ts": "// old\n"}}, "is out of date"),
    ("no typings", {"tsconfig": True, "extra": {"main.ts": "TaurisFiles.mount(el, { pick: f })"}}, "TypeScript code uses TaurisFiles but no file has its types"),
    ("tabs without start()", {"page": TABS}, "app.tabs().start() is never called"),
    ("tabs with withGlobalTauri off", {"page": TABS, "conf_app": {"withGlobalTauri": False}}, "FIX   app.withGlobalTauri is not true\n"),
    ("tabs used from Rust, no strip mounted", {"page": "<script>TaurisTree.mount(el, { data })</script>",
                                               "rust": GOOD_RUST + "fn s(app: &tauri::App) { app.tabs().start(); }\n"}, "no page calls TaurisTabs.mount"),
    ("no tauris-ui dependency", {"manifest": '[package]\nname = "x"\nversion = "0.1.0"\n[dependencies]\n'}, "has no tauris-ui dependency"),
    ("a newer version asked for", {"dependency": f'{{ path = "{LIBRARY}", version = "0.9" }}'}, "newer than this library"),
    ("the files feature without the dialog plugin", {"page": "<script>TaurisFiles.mount(el)</script>",
                                                     "dependency": f'{{ path = "{LIBRARY}", version = "0.4", features = ["files"] }}'}, "Cargo.toml does not depend on it"),
    ("the dialog plugin not registered", {"page": "<script>TaurisFiles.mount(el)</script>",
                                          "manifest": f'[package]\nname = "x"\nversion = "0.1.0"\n[dependencies]\ntauri-plugin-dialog = "2"\n'
                                                      f'tauris-ui = {{ path = "{LIBRARY}", version = "0.4", features = ["files"] }}\n'}, "the app does not register it"),
    ("the files feature off, no pick", {"page": "<script>TaurisFiles.mount(el)</script>"}, "needs tauris-ui's \"files\" feature"),
    ("no page files", {"no_page": True}, "found no page files"),
    ("a page that mounts nothing", {"page": "<p>Hello</p>"}, "no page mounts a tauris-ui component"),
    ("git, locked to an older version", {"dependency": '{ git = "https://example.com/tauris-ui", version = "0.4" }',
                                         "root_files": {"src-tauri/Cargo.lock": '[[package]]\nname = "tauris-ui"\nversion = "0.4.1"\n'}}, "locked to tauris-ui 0.4.1"),
]:
    out, code = app(**kwargs)
    check(f"{name}: said, and the checker exits 1", says in out and code == 1 and "to fix." in out, (code, out[-300:]))

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
