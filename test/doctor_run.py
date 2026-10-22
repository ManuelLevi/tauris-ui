"""Tests for scripts/doctor.py: small apps, each set up right or wrong in one
way, and what the checker says about them.

    python test/doctor_run.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
LIBRARY = HERE.parent
# As TOML and JSON take it on every system (a Windows path's backslashes would be escapes).
LIB = LIBRARY.as_posix()
# The series this library is in ("0.4" for 0.4.21): what a good app asks for.
SERIES = ".".join(re.search(r'^version = "([^"]+)"', (LIBRARY / "Cargo.toml").read_text(), re.M).group(1).split(".")[:2])
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
        tsconfig=False, extra_tauri=None, root_files=None, no_page=False, conf_name="tauri.conf.json"):
    """Writes a small app and runs the checker on it: (its output, exit code).
    `extra` adds page files, `extra_tauri` files under src-tauri/capabilities,
    `root_files` files next to src-tauri. The app is deleted afterwards."""
    root = Path(tempfile.mkdtemp(prefix="tauris-doctor-"))
    try:
        return checked(root, page, rust, dependency, capability, conf_app, workspace, extra, conf, manifest, tsconfig,
                       extra_tauri or {}, root_files or {}, no_page, conf_name)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def checked(root, page, rust, dependency, capability, conf_app, workspace, extra, conf, manifest, tsconfig,
            extra_tauri, root_files, no_page, conf_name):
    tauri = root / "src-tauri"
    (tauri / "src").mkdir(parents=True)
    (tauri / "capabilities").mkdir()
    (root / "dist").mkdir()
    dep = dependency or f'{{ path = "{LIB}", version = "{SERIES}" }}'
    (tauri / "Cargo.toml").write_text(manifest or f'[package]\nname = "x"\nversion = "0.1.0"\n[dependencies]\ntauris-ui = {dep}\n')
    if tsconfig:
        (root / "tsconfig.json").write_text("{}")
    if workspace:
        (root / "Cargo.toml").write_text(workspace)
    conf = {"app": conf_app or {"withGlobalTauri": True}, "build": {"frontendDist": "../dist"}, **(conf or {})}
    if conf_name == "Tauri.toml":
        (tauri / conf_name).write_text("[app]\nwithGlobalTauri = " + str(conf["app"].get("withGlobalTauri", False)).lower()
                                       + '\n[build]\nfrontendDist = "../dist"\n')
    elif conf_name.endswith(".json5"):
        (tauri / conf_name).write_text("// the app's settings\n{\n  app: { withGlobalTauri: " + json.dumps(conf["app"].get("withGlobalTauri", False))
                                       + ', },\n  build: { frontendDist: "../dist", },\n}\n')
    else:
        (tauri / conf_name).write_text(json.dumps(conf))
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
out, _ = app(dependency=f'{{ path = "{LIB}", version = "*" }}')
check('version "*" counts as no version', "accepts any version" in out, out)
out, _ = app(dependency="{ workspace = true }", workspace=f'[workspace]\nmembers = ["src-tauri"]\n[workspace.dependencies]\ntauris-ui = {{ path = "{LIB}", version = "{SERIES}" }}\n')
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
out, code = app(capability={"identifier": "default", "windows": ["*"], "permissions": ["core:default"]}, conf_app={"withGlobalTauri": True, "windows": [{"title": "x"}]})
check("an app with its own pick needs no tauris-ui:default for the picker", "no capability grants" not in out and code == 0, out)
out, code = app(capability=None, conf_app={"withGlobalTauri": True, "windows": [{"title": "x"}]})
check("but its windows must listen for events, or dropped files are never heard", "listen for events, so dropped files" in out and code == 1, out)
out, code = app(page="<script>TaurisFiles.mount(el)</script>", dependency=f'{{ path = "{LIB}", version = "{SERIES}", features = ["files"] }}',
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
out, code = app(extra_tauri={"broken.json": '{ "identifier": "x", }', "more/broken.toml": "identifier = "})
check("a capability file that cannot be read is said so (JSON and TOML, in a folder too), not a crash",
      "broken.json cannot be read" in out and "broken.toml cannot be read" in out and code == 1 and "Traceback" not in out, out)
renamed = f'[package]\nname = "x"\nversion = "0.1.0"\n[dependencies]\nui = {{ package = "tauris-ui", path = "{LIB}", version = "{SERIES}" }}\n'
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
out, code = app(page="<script>TaurisFiles.mount(el)</script>", dependency=f'{{ path = "{LIB}", version = "{SERIES}", features = ["files"] }}',
                capability={**GOOD_CAP, "windows": ["files"]}, conf_app={"withGlobalTauri": True, "windows": []},
                rust=GOOD_RUST + 'fn open(app: &tauri::App) { tauri::WebviewWindowBuilder::new(app, "files", tauri::WebviewUrl::default()); }\n'
                + "fn d() { tauri_plugin_dialog::init(); }\n",
                manifest=f'[package]\nname = "x"\nversion = "0.1.0"\n[dependencies]\ntauri-plugin-dialog = "2"\n'
                         f'tauris-ui = {{ path = "{LIB}", version = "{SERIES}", features = ["files"] }}\n')
check("a window the Rust code opens is one of the app's windows", "does not cover" not in out and code == 0, out)
out, code = app(page="<script>TaurisFiles.mount(el)</script>", rust=GOOD_RUST + "fn d() { tauri_plugin_dialog::init(); }\n",
                manifest=f'[package]\nname = "x"\nversion = "0.1.0"\n[features]\ndefault = ["tauris-ui/files"]\n[dependencies]\n'
                         f'tauri-plugin-dialog = "2"\ntauris-ui = {{ path = "{LIB}", version = "{SERIES}" }}\n')
check("the files feature turned on by the app's default features", 'the "files" feature is on' in out and code == 0, out)
root = Path(tempfile.mkdtemp(prefix="tauris-doctor-"))
try:
    (root / "src-tauri").mkdir()
    (root / "src-tauri" / "Cargo.toml").write_text(f'[package]\nname = "x"\n[dependencies]\ntauris-ui = {{ path = "{LIB}", version = "{SERIES}" }}\n')
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
git = f'{{ git = "https://example.com/tauris-ui", version = "{SERIES}" }}'
out, code = app(dependency=git, workspace='[workspace]\nmembers = ["src-tauri"]\n',
                root_files={"Cargo.lock": '[[package]]\nname = "tauris-ui"\nversion = "0.4.1"\n'})
check("the workspace's Cargo.lock is read", "locked to tauris-ui 0.4.1" in out and code == 1, out)

# ---------- an eighth review ----------
START = "fn s(app: &tauri::App) { app.tabs().start(); }\n"
out, code = app(page=TABS, rust=GOOD_RUST + START, capability={**GOOD_CAP, "permissions": ["tauris-ui:default"]})
check("tabs: a capability without core:default leaves the strip deaf: said", "listen for events, so the strip" in out and code == 1, out)
out, _ = app(page="<script>window.TaurisTabs?.mount(document.getElementById('strip'))</script>", rust=GOOD_RUST + START)
check("window.TaurisTabs?.mount(...) mounts the strip", "ok    the page mounts the strip" in out, out)
out, _ = app(page=TABS, rust=GOOD_RUST + "fn s(app: &tauri::App) { let tabs = app.tabs(); tabs.start(); }\n")
check("let tabs = app.tabs(); tabs.start() starts them", "ok    app.tabs().start()" in out, out)
out, code = app(page="<script>TaurisFiles.mount(el)</script>", rust=GOOD_RUST + "use tauri_plugin_dialog as dialog;\nfn d() { dialog::init(); }\n",
                manifest=f'[package]\nname = "x"\nversion = "0.1.0"\n[features]\ndefault = ["native-files"]\nnative-files = ["tauris-ui/files"]\n'
                         f'[dependencies]\ntauri-plugin-dialog = "2"\ntauris-ui = {{ path = "{LIB}", version = "{SERIES}" }}\n',
                conf_app={"withGlobalTauri": True, "windows": [{"title": "x"}]})
check("the files feature through a feature of the app's own, and the dialog plugin under another name",
      'the "files" feature is on' in out and "ok    the dialog plugin is registered" in out and code == 0, out)
out, code = app(tsconfig=True, extra={"main.ts": f'/// <reference path="{LIB}/web/files.d.ts" />\nTaurisFiles.mount(el, {{ pick: f }})'})
check("TypeScript types through a /// <reference> to the library's own", "no file has its types" not in out and code == 0, out)

# ---------- a tenth review ----------
SPREAD = "const base = { pick: f }; TaurisFiles.mount(el, { ...base, onAdd })"
for name, page, want in [
    ("pick through an inline spread", SPREAD, True),
    ("pick in React's useMemo", "const options = useMemo(() => ({ pick, onAdd }), []); TaurisFiles.mount(el, options)", True),
    ("one mount with pick, another without", "TaurisFiles.mount(a, { pick: f }); TaurisFiles.mount(b, { onAdd })", False),
    ("its own pick, and TaurisFiles.saveDialog", "TaurisFiles.mount(a, { pick: f }); TaurisFiles.saveDialog({ name: 'x' })", False),
]:
    out, _ = app(page=f"<script>{page}</script>")
    check(f"{name}: {'its own picker' if want else 'the system’s dialogs needed'}", ("own picker" in out) == want, out[-300:])
out, _ = app(rust="use tauris_ui::*;\nfn main() { tauri::Builder::default().plugin(init(Config::new())); }\n")
check("use tauris_ui::*; then init(...)", "ok    the plugin is registered" in out, out[-300:])
granular = {"identifier": "default", "windows": ["*"], "permissions": ["core:default"] + [f"tauris-ui:allow-{c}" for c in
            ("window-state", "new-tab", "open-tab", "close-tab", "activate-tab", "move-tab", "update-tab", "report-strip", "drag-out",
             "set-close-guard", "close-asked", "close-window", "move-to-new-window")]}
out, _ = app(page=TABS, rust=GOOD_RUST + START, capability=granular)
check("the plugin's commands granted one by one count", "no capability grants" not in out and "grants tauris-ui:default to the tab windows" in out, out[-300:])
out, _ = app(rust=GOOD_RUST + "struct B; impl B { fn tabs(&self) {} }\nfn s(b: B) { b.tabs(); }\n")
check("an app's own tabs() is not the library's", "app.tabs().start() is never called" not in out, out[-300:])
root = Path(tempfile.mkdtemp(prefix="tauris-doctor-"))
try:
    (root / "src-tauri" / "src").mkdir(parents=True)
    (root / "src-tauri" / "Cargo.toml").write_bytes(f'[package]\nname = "x"\nauthors = ["Jos\xe9"]\n[dependencies]\ntauris-ui = {{ path = "{LIB}", version = "{SERIES}" }}\n'.encode("latin-1"))
    (root / "src-tauri" / "Tauri.toml").write_text('[app]\nwithGlobalTauri = true\n')
    run = subprocess.run([sys.executable, str(DOCTOR), str(root)], capture_output=True, text=True, encoding="utf-8")
    check("a Tauri.toml is read; a Cargo.toml not in UTF-8 is said so, not a crash",
          "Traceback" not in run.stdout + run.stderr and "cannot be read" in run.stdout and run.returncode == 1, run.stdout + run.stderr)
finally:
    shutil.rmtree(root, ignore_errors=True)

# ---------- an eleventh review ----------
scoped = {**GOOD_CAP, "permissions": GOOD_CAP["permissions"] + [{"identifier": "fs:allow-read-file", "allow": [{"path": "$APPDATA/**"}]}]}
out, code = app(page=TABS, rust=GOOD_RUST + START, capability=scoped)
check("a permission written as an object (a scope) is read, not a crash", "Traceback" not in out and "grants tauris-ui:default to the tab windows" in out, out[-300:])
out, code = app(page="<script>TaurisFiles.mount(el, { pick: myPick, onOpen })</script>", dependency=f'{{ path = "{LIB}", version = "{SERIES}", features = ["files"] }}')
check("the files feature with the app's own pick (open_path alone) needs no dialog plugin", "dialog plugin" not in out and code == 0, out[-300:])
out, code = app(page="<script>const r=document.body,n={pick:async()=>[],onAdd:async e=>e};window.TaurisFiles.mount(r,n);</script>")
check("a minified page (const r=…,n={pick}) has its own pick", "own picker" in out and code == 0, out[-300:])
out, code = app(page="<script>TaurisFiles.mount(el, options())</script>")
check("options from a call: said it cannot be told, not a FIX", "could not tell whether every TaurisFiles.mount" in out and "needs tauris-ui's" not in out, out[-300:])
TABS_FILES = TABS + "<script>TaurisFiles.mount(el)</script>"
tabs_only = {**GOOD_CAP, "permissions": ["core:default"] + [f"tauris-ui:allow-{c}" for c in
             ("window-state", "new-tab", "open-tab", "close-tab", "activate-tab", "move-tab", "update-tab", "report-strip", "drag-out",
              "set-close-guard", "close-asked", "close-window", "move-to-new-window")]}
out, code = app(page=TABS_FILES, rust=GOOD_RUST + START + "fn d() { tauri_plugin_dialog::init(); }\n", capability=tabs_only,
                manifest=f'[package]\nname = "x"\nversion = "0.1.0"\n[dependencies]\ntauri-plugin-dialog = "2"\n'
                         f'tauris-ui = {{ path = "{LIB}", version = "{SERIES}", features = ["files"] }}\n')
check("tabs and files: the tab windows without the picker's permission is said", "grants the system's picker" in out and code == 1, out[-300:])
out, code = app(conf_app={"withGlobalTauri": True, "windows": [{"title": "x", "dragDropEnabled": False}]})
check("dropping switched off for a window is said", "dropping files is switched off" in out and code == 1, out[-300:])
to_json = doctor["json5_to_json"]
cases = ["{ app: { withGlobalTauri: true }, // the strip needs it\n}", "{ productName: 'Docs', }", '{ productName: "Board, minutes: 2026" /* a note */ }']
read = [json.loads(to_json(c)) for c in cases]
check("JSON5: a comment at a line's end, single quotes, and a colon inside a string", read == [{"app": {"withGlobalTauri": True}}, {"productName": "Docs"},
      {"productName": "Board, minutes: 2026"}], read)

for name in ("Tauri.toml", "tauri.conf.json5"):
    out, code = app(conf_name=name)
    check(f"an app set up with {name} is read", code == 0 and "Ready" in out, out[-300:])


def toml_app(toml, page, rust):
    """An app set up with Tauri.toml as Tauri's docs write it (kebab-case), its page in ui/."""
    root = Path(tempfile.mkdtemp(prefix="tauris-doctor-"))
    try:
        tauri = root / "src-tauri"
        (tauri / "src").mkdir(parents=True)
        (tauri / "capabilities").mkdir()
        (root / "ui").mkdir()
        (tauri / "Cargo.toml").write_text(f'[package]\nname = "x"\nversion = "0.1.0"\n[dependencies]\ntauris-ui = {{ path = "{LIB}", version = "{SERIES}" }}\n')
        (tauri / "Tauri.toml").write_text(toml)
        (tauri / "capabilities" / "default.json").write_text(json.dumps(GOOD_CAP))
        (tauri / "src" / "main.rs").write_text(rust)
        (root / "ui" / "index.html").write_text(page)
        run = subprocess.run([sys.executable, str(DOCTOR), str(root)], capture_output=True, text=True, encoding="utf-8")
        return run.stdout + run.stderr, run.returncode
    finally:
        shutil.rmtree(root, ignore_errors=True)


out, code = toml_app('[app]\nwith-global-tauri = true\n[build]\nfrontend-dist = "../ui"\n[plugins.deep-link]\ndesktop = { schemes = ["x"] }\n',
                     "<script>TaurisTabs.mount(document.getElementById('strip'))</script>",
                     "use tauris_ui::TabsExt;\n" + GOOD_RUST + "fn s(app: &tauri::App) { app.tabs().start(); }\n")
check("Tauri.toml in kebab-case (with-global-tauri, frontend-dist) is read: Ready", code == 0 and "Ready" in out, out[-400:])
out, code = toml_app('[app]\nwith-global-tauri = true\n[[app.windows]]\nlabel = "main"\ndrag-drop-enabled = false\n[build]\nfrontend-dist = "../ui"\n',
                     "<script>TaurisFiles.mount(el, { pick: myPick })</script>", GOOD_RUST)
check("Tauri.toml's drag-drop-enabled = false is caught", "dropping files is switched off (main)" in out and code == 1, out[-400:])

# The window prefix from a const or static, or from something the checker cannot read.
PREFIXED = "fn main() { tauri::Builder::default().plugin(tauris_ui::init(tauris_ui::Config::new().window_prefix(ARG))); }\n" + START
out, code = app(page=TABS, rust='const PREFIX: &str = "doc-";\n' + PREFIXED.replace("ARG", "PREFIX"), capability={**GOOD_CAP, "windows": ["tabs-*"]})
check("window_prefix(PREFIX) read from its const: a capability for tabs-* does not cover doc-1", "not the tab windows doc-1" in out and code == 1, out[-400:])
out, code = app(page=TABS, rust="static P: &'static str = \"doc-\";\n" + PREFIXED.replace("ARG", "P"), capability={**GOOD_CAP, "windows": ["doc-*"]})
check("window_prefix(P) read from its static: a capability for doc-* covers the tab windows", "to the tab windows (doc-1" in out, out[-400:])
out, code = app(page=TABS, rust=PREFIXED.replace("ARG", "&prefix()"), capability={**GOOD_CAP, "windows": ["tabs-*"]})
check("window_prefix given something it cannot read: said, not taken as tabs-", "cannot read" in out and "to the tab windows (tabs-1" not in out, out[-400:])

# The plugin's commands granted one by one, without the two for "Move to".
ONE_BY_ONE = [f"tauris-ui:allow-{c}" for c in ("window-state", "new-tab", "open-tab", "close-tab", "activate-tab", "move-tab", "update-tab", "report-strip",
                                                 "drag-out", "set-close-guard", "close-asked", "close-window", "move-to-new-window")]
out, code = app(page=TABS, rust=GOOD_RUST + START, capability={**GOOD_CAP, "permissions": ["core:default", *ONE_BY_ONE]})
check("commands granted one by one without Move to's: it works, and the missing menu is noted", code == 0 and 'no "Move to" another window' in out, out[-400:])
out, code = app(page=TABS, rust=GOOD_RUST + START, capability={**GOOD_CAP, "permissions": ["core:default", *ONE_BY_ONE, "tauris-ui:allow-other-windows", "tauris-ui:allow-move-to-window"]})
check("and with them, nothing is noted about it", code == 0 and "Move to" not in out, out[-400:])

# Config::components: a page using a component left out.
COMPONENTS = "fn main() { tauri::Builder::default().plugin(tauris_ui::init(tauris_ui::Config::new().components(&[ARG]))); }\n"
out, code = app(page="<script>TaurisFiles.mount(el, { pick: f }); TaurisTree.mount(t, { data })</script>",
                rust=COMPONENTS.replace("ARG", "tauris_ui::Component::Files"))
check("Config::components without the tree, a page mounting it: said", "leaves it out, so the pages have no TaurisTree" in out and code == 1, out[-400:])
out, code = app(page="<script>TaurisFiles.mount(el, { pick: f }); TaurisMenu.bar(nav, { menus })</script>",
                rust=COMPONENTS.replace("ARG", "Component::Files"))
check("Config::components with the files: the menus come with them", "leaves it out" not in out and code == 0, out[-400:])
out, code = app(rust="fn main() { tauri::Builder::default().plugin(tauris_ui::init(tauris_ui::Config::new().components(&ALL))); }\n")
check("Config::components given a list it cannot read: noted", "cannot read" in out and code == 0, out[-400:])

# A capability for some systems only.
HERE_OS = {"darwin": "macOS", "win32": "windows"}.get(sys.platform, "linux")
ELSEWHERE = "windows" if HERE_OS != "windows" else "linux"
out, code = app(page=TABS, rust=GOOD_RUST + START, capability={**GOOD_CAP, "platforms": [ELSEWHERE]})
check("a capability only for another system grants nothing here (and is noted)",
      "no capability grants tauris-ui:default" in out and f'"platforms": ["{ELSEWHERE}"]' in out and code == 1, out[-400:])
out, code = app(page=TABS, rust=GOOD_RUST + START, capability={**GOOD_CAP, "platforms": [HERE_OS]})
check("a capability only for this system works here, and the others are noted", code == 0 and "its windows get none of it" in out, out[-400:])
out, code = app(conf={"bundle": {"macOS": {"minimumSystemVersion": "11.0"}}})
check("macOS 11 or later asked for: no note about the engine", code == 0 and "WebKit is older" not in out, out[-400:])

# ---------- every note is said when it applies ----------
WINDOWS = {"withGlobalTauri": True, "windows": [{"title": "x"}]}
TABS_APP = {"page": TABS, "rust": GOOD_RUST + START}
other_copy = Path(tempfile.mkdtemp(prefix="tauris-copy-"))
(other_copy / "Cargo.toml").write_text('[package]\nname = "tauris-ui"\nversion = "0.4.0"\n')
for name, kwargs, says in [
    ("a lock without tauris-ui", {"root_files": {"src-tauri/Cargo.lock": "# nothing yet\n"}}, "Cargo.lock has no tauris-ui yet"),
    ("no lock", {}, "no Cargo.lock yet"),
    ("macOS before 11", {}, "whose WebKit is older than the components need"),
    ("macOS 10.15 asked for", {"conf": {"bundle": {"macOS": {"minimumSystemVersion": "10.15"}}}}, "installs on macOS 10.15"),
    ("windows not known", {"page": "<script>TaurisFiles.mount(el)</script>"}, "could not tell which windows the app opens"),
    ("no default menu", TABS_APP, "no tauris_ui::default_menu"),
    ("layers", {"page": "<style>@layer reset { p { margin: 0 } }</style><script>TaurisFiles.mount(el, { pick: f })</script>"}, "the app's CSS uses layers"),
    ("the strip's padding", TABS_APP, "give the page padding-top"),
    ("an older build", {"root_files": {"src-tauri/Cargo.lock": '[[package]]\nname = "tauris-ui"\nversion = "0.3.0"\n'}}, "last built with tauris-ui 0.3.0"),
    ("git", {"dependency": f'{{ git = "https://example.com/tauris-ui", version = "{SERIES}" }}'}, "the app takes tauris-ui from git"),
    ("another copy", {"dependency": f'{{ path = "{other_copy.as_posix()}", version = "{SERIES}" }}'}, "the app uses the copy of tauris-ui at"),
    ("its own windows", {**TABS_APP, "conf_app": WINDOWS}, "tauri.conf.json opens its own windows"),
    ("no dragging permission", TABS_APP, "core:window:allow-start-dragging"),
]:
    out, _ = app(**kwargs)
    check(f"note: {name}", says in out, out[-400:])
shutil.rmtree(other_copy, ignore_errors=True)
out, code = app(page="<script>TaurisFiles.mount(el)</script>", conf_app=WINDOWS,
                capability={"identifier": "default", "windows": ["*"], "permissions": ["core:default"]},
                dependency=f'{{ path = "{LIB}", version = "{SERIES}", features = ["files"] }}')
check("the picker without tauris-ui:default: said, exit 1", "so Add files… cannot open the system's picker" in out and code == 1, out[-400:])

# ---------- what is wrong is said, and the exit code says so ----------
for name, kwargs, says in [
    ("a dependency path that leads nowhere", {"dependency": f'{{ path = "/nowhere", version = "{SERIES}" }}'}, "does not lead to tauris-ui"),
    ("an older version asked for", {"dependency": f'{{ path = "{LIB}", version = "0.3" }}'}, "which needs changes in the app"),
    ("withGlobalTauri off", {"conf_app": {"withGlobalTauri": False}}, "dropped files are never heard"),
    ("the tauris-ui layer declared", {"page": "<style>@layer reset, tauris-ui;</style><script>TaurisFiles.mount(el, { pick: f })</script>"}, "declares the tauris-ui layer"),
    ("a capability only for main", {"page": TABS, "capability": {**GOOD_CAP, "windows": ["main"]}}, "not the tab windows"),
    ("the example's identifier", {"conf": {"identifier": "dev.tauris-ui.example"}}, "the example's identifier"),
    ("stale typings", {"tsconfig": True, "extra": {"files.d.ts": "// old\n"}}, "is out of date"),
    ("no typings", {"tsconfig": True, "extra": {"main.ts": "TaurisFiles.mount(el, { pick: f })"}}, "TypeScript code uses TaurisFiles but no file has its types"),
    ("tabs without start()", {"page": TABS}, "app.tabs().start() is never called"),
    ("tabs with withGlobalTauri off", {"page": TABS, "conf_app": {"withGlobalTauri": False}}, "FIX   app.withGlobalTauri is not true\n"),
    ("tabs used from Rust, no strip mounted", {"page": "<script>TaurisTree.mount(el, { data })</script>",
                                               "rust": "use tauris_ui::TabsExt;\n" + GOOD_RUST + "fn s(app: &tauri::App) { app.tabs().start(); }\n"}, "no page calls TaurisTabs.mount"),
    ("no tauris-ui dependency", {"manifest": '[package]\nname = "x"\nversion = "0.1.0"\n[dependencies]\n'}, "has no tauris-ui dependency"),
    ("a newer version asked for", {"dependency": f'{{ path = "{LIB}", version = "0.9" }}'}, "newer than this library"),
    ("the files feature without the dialog plugin", {"page": "<script>TaurisFiles.mount(el)</script>",
                                                     "dependency": f'{{ path = "{LIB}", version = "{SERIES}", features = ["files"] }}'}, "Cargo.toml does not depend on it"),
    ("the dialog plugin not registered", {"page": "<script>TaurisFiles.mount(el)</script>",
                                          "manifest": f'[package]\nname = "x"\nversion = "0.1.0"\n[dependencies]\ntauri-plugin-dialog = "2"\n'
                                                      f'tauris-ui = {{ path = "{LIB}", version = "{SERIES}", features = ["files"] }}\n'}, "the app does not register it"),
    ("the files feature off, no pick", {"page": "<script>TaurisFiles.mount(el)</script>"}, "needs tauris-ui's \"files\" feature"),
    ("no page files", {"no_page": True}, "found no page files"),
    ("a page that mounts nothing", {"page": "<p>Hello</p>"}, "no page mounts a tauris-ui component"),
    ("git, locked to an older version", {"dependency": f'{{ git = "https://example.com/tauris-ui", version = "{SERIES}" }}',
                                         "root_files": {"src-tauri/Cargo.lock": '[[package]]\nname = "tauris-ui"\nversion = "0.4.1"\n'}}, "locked to tauris-ui 0.4.1"),
]:
    out, code = app(**kwargs)
    check(f"{name}: said, and the checker exits 1", says in out and code == 1 and "to fix." in out, (code, out[-300:]))

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
