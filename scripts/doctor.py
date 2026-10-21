"""Checks that an app is set up to use tauris-ui, and whether it was built
with the current version of the library.

    python scripts/doctor.py <app folder>

<app folder> is the app's root (with src-tauri/ inside) or its src-tauri/.
Prints one line per check and exits 1 when something must be fixed.
Needs Python 3.11 or newer.
"""
import json
import re
import sys
import tomllib
from pathlib import Path

LIBRARY = Path(__file__).resolve().parent.parent
# The report has ⌘ and arrows in it; consoles that default to another encoding
# (Windows) must not crash on them.
sys.stdout.reconfigure(encoding="utf-8")


def read(path):
    return path.read_text(encoding="utf-8", errors="replace")


def code(text, quotes):
    """The text without its comments, so a commented-out line counts as absent."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in quotes:
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:  # not a comment after all (a regular expression, say): kept
                out.append(text[i:])
                break
            i = end + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def balanced(text, start, open_, close):
    """The text between the bracket at `start` and the one that closes it."""
    depth, i = 0, start
    while i < len(text):
        depth += {open_: 1, close: -1}.get(text[i], 0)
        i += 1
        if depth == 0:
            return text[start + 1:i - 1]
    return text[start + 1:]


def keys(obj):
    """The keys of an object literal's own level: `pick:`, `pick(` (a method), `{ pick }`."""
    level, depth = [], 0
    for c in obj:
        depth += 1 if c in "([{" else -1 if c in ")]}" else 0
        level.append(c if depth == 0 or (depth == 1 and c in "([{") else " ")
    flat = "".join(level)
    return set(re.findall(r"(?:^|[,{]|\basync)\s*([A-Za-z_$][\w$]*)\s*(?=[:(,]|$)", flat))


def own_picker(text):
    """Whether a TaurisFiles.mount call is given a pick option: in the object
    it is given, or in the object its variable is declared with."""
    for m in re.finditer(r"TaurisFiles\.mount\(", text):
        args = balanced(text, m.end() - 1, "(", ")")
        brace = args.find("{")
        if brace >= 0:
            if "pick" in keys(balanced(args, brace, "{", "}")):
                return True
            continue
        given = re.search(r",\s*([A-Za-z_$][\w$]*)\s*$", args)
        if not given:
            continue
        decl = re.search(rf"\b(?:const|let|var)\s+{re.escape(given.group(1))}\s*=\s*\{{", text)
        if decl and "pick" in keys(balanced(text, decl.end() - 1, "{", "}")):
            return True
    return False


def workspace_spec(tauri):
    """tauris-ui as the workspace's Cargo.toml gives it ([workspace.dependencies]),
    with its path made relative to the app."""
    for folder in [tauri, *tauri.parents]:
        manifest = folder / "Cargo.toml"
        if not manifest.is_file():
            continue
        data = tomllib.loads(read(manifest))
        spec = data.get("workspace", {}).get("dependencies", {}).get("tauris-ui")
        if spec is not None:
            spec = {"version": spec} if isinstance(spec, str) else dict(spec)
            if "path" in spec:
                spec["path"] = str((folder / spec["path"]).resolve())
            return spec
    return {}


def page_code(path):
    """A page file without its comments (HTML ones too)."""
    text = read(path)
    if path.suffix in {".html", ".vue", ".svelte"}:
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return code(text, "\"'`")


problems = []
notes = []


def ok(text):
    print(f"  ok    {text}")


def bad(text, fix):
    problems.append(text)
    print(f"  FIX   {text}\n        -> {fix}")


def note(text):
    notes.append(text)
    print(f"  note  {text}")


def library_version():
    match = re.search(r'^version\s*=\s*"([^"]+)"', (LIBRARY / "Cargo.toml").read_text(), re.M)
    return match.group(1) if match else "?"


def parts(version):
    return [int(p) for p in re.findall(r"\d+", version)[:3]] + [0, 0, 0]


def series(version):
    """The requirement that accepts every version compatible with `version`: "0.3" or "1"."""
    major, minor, _ = parts(version)[:3]
    return f"{major}.{minor}" if major == 0 else f"{major}"


def accepts(requirement, version):
    """Cargo's default (caret) rule: 0.x.y stays within 0.x; x.y.z stays within x."""
    want = requirement.lstrip("^= ")
    w, v = parts(want)[:3], parts(version)[:3]
    if w[0] != v[0]:
        return False
    if w[0] == 0 and w[1] != v[1]:
        return False
    return v >= w


def page_files(tauri, conf):
    """The page's files: the built folder, and for Vite-style apps the sources."""
    dist = conf.get("build", {}).get("frontendDist")
    places = [tauri.parent / "src", tauri.parent / "index.html"]
    if isinstance(dist, str) and not dist.startswith("http"):
        places.insert(0, (tauri / dist).resolve())
    kinds = {".html", ".js", ".mjs", ".ts", ".jsx", ".tsx", ".css", ".vue", ".svelte"}
    found = []
    for place in places:
        if place.is_file():
            found.append(place)
        elif place.is_dir():
            found += [p for p in place.rglob("*") if p.suffix in kinds and p.is_file()
                      and not {"node_modules", "dist", "target"} & set(p.relative_to(place).parts[:-1])]
    return found


def capabilities(tauri, app):
    """Every capability: (where it is, what it says)."""
    caps = []
    for path in sorted((tauri / "capabilities").glob("*")):
        try:
            if path.suffix == ".json":
                caps.append((path, json.loads(read(path))))
            elif path.suffix == ".toml":
                caps.append((path, tomllib.loads(read(path))))
        except (json.JSONDecodeError, tomllib.TOMLDecodeError):
            bad(f"{path.name} cannot be read", "fix the file")
    listed = app.get("security", {}).get("capabilities", [])
    # Identifiers listed in tauri.conf.json enable only those files.
    names = {c for c in listed if isinstance(c, str)}
    if names:
        caps = [(p, c) for p, c in caps if c.get("identifier") in names]
    for inline in listed:
        if isinstance(inline, dict):
            caps.append((tauri / "tauri.conf.json", inline))
    return caps


def find_src_tauri(root):
    if (root / "tauri.conf.json").is_file():
        return root
    if (root / "src-tauri" / "tauri.conf.json").is_file():
        return root / "src-tauri"
    return None


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1]).expanduser().resolve()
    tauri = find_src_tauri(root)
    if tauri is None:
        print(f"No tauri.conf.json in {root} or {root / 'src-tauri'}.")
        return 2
    print(f"tauris-ui {library_version()}: checking {tauri}\n")

    # 1. dependency: where it points, and which versions it accepts
    manifest_data = tomllib.loads((tauri / "Cargo.toml").read_text(encoding="utf-8"))
    current = library_version()
    sections = [manifest_data.get("dependencies", {})]
    sections += [t.get("dependencies", {}) for t in manifest_data.get("target", {}).values()]
    spec = next((d["tauris-ui"] for d in sections if "tauris-ui" in d), None)
    if spec is None:
        bad("Cargo.toml has no tauris-ui dependency",
            f'add under [dependencies]: tauris-ui = {{ path = "{LIBRARY}", version = "{series(current)}" }}')
    else:
        spec = {"version": spec} if isinstance(spec, str) else spec
        if spec.get("workspace") is True:
            spec = {**workspace_spec(tauri), **{k: v for k, v in spec.items() if k != "workspace"}}
        if spec.get("version") == "*":
            spec = {k: v for k, v in spec.items() if k != "version"}
        if "path" in spec:
            target = (tauri / spec["path"]).resolve()
            manifest = target / "Cargo.toml"
            if not manifest.is_file() or 'name = "tauris-ui"' not in manifest.read_text(encoding="utf-8"):
                bad(f"the dependency path {spec['path']} does not lead to tauris-ui", f'set path = "{LIBRARY}"')
            elif target != LIBRARY:
                note(f"the app uses the copy of tauris-ui at {target}, not {LIBRARY}")
            else:
                ok("Cargo.toml depends on this tauris-ui")
        elif "git" in spec:
            lock = tauri / "Cargo.lock"
            locked = re.search(r'name = "tauris-ui"\nversion = "([^"]+)"', read(lock)) if lock.is_file() else None
            if locked and parts(locked.group(1))[:3] < parts(current)[:3]:
                bad(f"the app is locked to tauris-ui {locked.group(1)} from git; this library is {current}",
                    "run `cargo update -p tauris-ui` in src-tauri (the build stops there if the new version needs app changes)")
            else:
                note(f"the app takes tauris-ui from git; compared with this copy ({current})")
        wanted = spec.get("version")
        if not wanted:
            bad("the dependency accepts any version, so a change that needs app changes goes unnoticed",
                f'add version = "{series(current)}" to the tauris-ui dependency')
        elif not accepts(wanted, current) and parts(wanted.lstrip("^= "))[:3] > parts(current)[:3]:
            bad(f'the app asks for tauris-ui "{wanted}", newer than this library ({current})',
                "update the library, or lower the requirement")
        elif not accepts(wanted, current):
            bad(f'the app asks for tauris-ui "{wanted}"; the library is now {current}, which needs changes in the app',
                f"read {LIBRARY / 'CHANGELOG.md'} from {wanted} to {current}, do every Upgrade step, "
                f'then set version = "{series(current)}"')
        else:
            ok(f'the app accepts the current library ("{wanted}" matches {current})')

    # Which components the app uses: tabs need the Rust side wired; the tree
    # view lives in the page and only needs the plugin to deliver it.
    conf = json.loads((tauri / "tauri.conf.json").read_text(encoding="utf-8"))
    app = conf.get("app", {})
    rust = "\n".join(code(read(p), '"') for p in (tauri / "src").rglob("*.rs"))
    files = page_files(tauri, conf)
    text = "\n".join(page_code(p) for p in files)
    uses_tabs = "TaurisTabs" in text or bool(re.search(r"\.tabs\(\)", rust))
    uses_tree = "TaurisTree" in text
    uses_terminal = "TaurisTerminal" in text
    uses_files = "TaurisFiles" in text
    uses_menus = "TaurisMenu" in text
    used = [name for name, on in (("tabs", uses_tabs), ("tree view", uses_tree), ("terminal", uses_terminal),
                                  ("files", uses_files), ("menus", uses_menus)) if on]
    if used:
        ok("components in use: " + ", ".join(used))
    elif files:
        bad("no page mounts a tauris-ui component",
            'TaurisTabs.mount(document.getElementById("strip")), TaurisTree.mount(element, { data }), TaurisFiles.mount(element), '
            'TaurisMenu.bar(nav, { menus }) or TaurisTerminal.mount(element)')
    else:
        bad("found no page files (looked in frontendDist, src/ and index.html)", "check build.frontendDist in tauri.conf.json")

    # 2. the plugin, which delivers every component
    if "tauris_ui::init(" in rust:
        ok("the plugin is registered")
    else:
        bad("the plugin is not registered", ".plugin(tauris_ui::init(tauris_ui::Config::new())) on tauri::Builder")

    # 3. tabs: Rust opens the windows, the menu, the capability, the strip
    if uses_tabs:
        if app.get("withGlobalTauri") is True:
            ok("withGlobalTauri is on")
        else:
            bad("app.withGlobalTauri is not true", 'set "app": { "withGlobalTauri": true } in tauri.conf.json')
        if app.get("windows"):
            note('tauri.conf.json opens its own windows; tab windows come from the plugin ("windows": [] unless you want another window)')
        else:
            ok("no windows in tauri.conf.json (the plugin opens them)")
        prefix_match = re.search(r'window_prefix\(\s*"([^"]*)"', rust)
        prefix = prefix_match.group(1) if prefix_match else "tabs-"
        if re.search(r"\.tabs\(\)\s*\.\s*start\(\)", rust):
            ok("app.tabs().start() opens the windows")
        else:
            bad("app.tabs().start() is never called", "call app.tabs().start()? in .setup(...)")
        if "default_menu(" in rust or "file_menu(" in rust or "menu_ids::" in rust:
            ok("the menu has the tab items (\u2318T \u2318N \u2318W)")
        elif re.search(r"\.tabs\(\)\s*\.\s*(close_active|new_tab|new_window)\(", rust):
            ok("the app's own menu calls app.tabs() for the tab items")
        else:
            note("no tauris_ui::default_menu / file_menu / menu_ids: \u2318T and \u2318W only work if your own menu calls app.tabs()")

        caps = capabilities(tauri, app)
        granting = [(p, c) for p, c in caps if "tauris-ui:default" in json.dumps(c.get("permissions", []))]
        if not granting:
            bad("no capability grants tauris-ui:default",
                'add "tauris-ui:default" to "permissions" in src-tauri/capabilities/default.json')
        else:
            covers = any(any(w == "*" or (w.endswith("*") and f"{prefix}1".startswith(w[:-1])) or w == f"{prefix}1"
                             for w in c.get("windows", [])) for _, c in granting)
            if covers:
                ok(f"a capability grants tauris-ui:default to the tab windows ({prefix}1, {prefix}2, ...)")
            else:
                names = ", ".join(json.dumps(c.get("windows", [])) for _, c in granting)
                bad(f"the capability with tauris-ui:default covers {names}, not the tab windows {prefix}1, {prefix}2, ...",
                    f'set "windows": ["{prefix}*"] (or ["*"]); otherwise the strip stays empty')
            if not any("allow-start-dragging" in json.dumps(c.get("permissions", [])) for _, c in granting):
                note('without "core:window:allow-start-dragging" the window cannot be dragged by its tab strip')
        if "TaurisTabs.mount" in text:
            ok("the page mounts the strip")
        else:
            bad("no page calls TaurisTabs.mount(...)", 'TaurisTabs.mount(document.getElementById("strip"))')
        if files and "--tt-strip-h" not in text:
            note("the strip is fixed at the top: give the page padding-top: var(--tt-strip-h)")

    # 4. files: drops and the picker reach Tauri from the page; the picker needs the feature and the dialog plugin
    if uses_files:
        if not uses_tabs:
            if app.get("withGlobalTauri") is True:
                ok("withGlobalTauri is on (the files component hears drops through it)")
            else:
                bad("app.withGlobalTauri is not true, so dropped files are never heard",
                    'set "app": { "withGlobalTauri": true } in tauri.conf.json')
            if any("tauris-ui:default" in json.dumps(c.get("permissions", [])) for _, c in capabilities(tauri, app)):
                ok("a capability grants tauris-ui:default (the system's picker)")
            else:
                bad("no capability grants tauris-ui:default, so Add files… cannot open the system's picker",
                    'add "tauris-ui:default" to "permissions" in src-tauri/capabilities/default.json')
        features = spec.get("features", []) if isinstance(spec, dict) else []
        if "files" in features:
            ok('the "files" feature is on (the system\'s picker and save dialog)')
            if not any("tauri-plugin-dialog" in d for d in sections):
                bad("the files feature needs the dialog plugin, and Cargo.toml does not depend on it",
                    'add tauri-plugin-dialog = "2" under [dependencies], and .plugin(tauri_plugin_dialog::init()) to tauri::Builder')
            elif "tauri_plugin_dialog::init(" in rust:
                ok("the dialog plugin is registered")
            else:
                bad("the files feature needs the dialog plugin, and the app does not register it",
                    ".plugin(tauri_plugin_dialog::init()) on tauri::Builder")
        elif own_picker(text):
            ok("the files component has its own picker (pick)")
        else:
            bad('Add files… opens the system\'s picker, which needs tauris-ui\'s "files" feature',
                'set features = ["files"] on the tauris-ui dependency (and register tauri_plugin_dialog), '
                "or give TaurisFiles.mount a pick option")

    # 5. the page's CSS and copies of the library's files
    for name, word in (("tabs.js", "TaurisTabs"), ("tree.js", "TaurisTree"), ("terminal.js", "TaurisTerminal"),
                       ("files.js", "TaurisFiles"), ("menus.js", "TaurisMenu")):
        if any(p.name == name and word in read(p) for p in files):
            bad(f"the app has its own copy of the library's {name}", "delete it: the plugin injects the page script")
    if re.search(r"@layer[^;{]*tauris-ui", text):
        bad("the app's CSS declares the tauris-ui layer",
            "remove it: it can put the library under the app's reset, and values set inside it lose anyway")
    elif re.search(r"@layer\s+[\w-]", text):
        note("the app's CSS uses layers: set the --tauris-*, --tt-*, --tv-*, --tf-*, --tmn-* and --tm-* variables outside every @layer block, "
             "or the library's defaults win")

    # TypeScript: an up-to-date copy of each component's types
    if (tauri.parent / "tsconfig.json").is_file():
        for name, word, on in (("tabs.d.ts", "TaurisTabs", uses_tabs), ("tree.d.ts", "TaurisTree", uses_tree),
                               ("terminal.d.ts", "TaurisTerminal", uses_terminal), ("files.d.ts", "TaurisFiles", uses_files),
                               ("menus.d.ts", "TaurisMenu", uses_menus)):
            if not on:
                continue
            types = LIBRARY / "web" / name
            copies = [p for p in tauri.parent.rglob(name)
                      if not {"node_modules", "target"} & set(p.parts) and p.resolve() != types]
            stale = [p for p in copies if read(p) != read(types)]
            in_ts = any(p.suffix in {".ts", ".tsx"} and word in read(p) for p in files)
            if stale:
                bad(f"the app's copy of {name} is out of date: {stale[0]}", f"copy {types} over it")
            elif in_ts and name not in text and not copies:
                bad(f"TypeScript code uses {word} but no file has its types",
                    f"copy {types} into the app (for example src/{name}); TypeScript picks it up from there")
            elif in_ts:
                ok(f"the page has the {word} types")

    # identity: a copied example must become its own app
    if conf.get("identifier") == "dev.tauris-ui.example" and LIBRARY not in tauri.parents:
        bad('the app still has the example\'s identifier "dev.tauris-ui.example", so it shares the example\'s saved tabs',
            "set your own identifier and productName in tauri.conf.json, and the package name in Cargo.toml")

    # 6. last build
    lock = tauri / "Cargo.lock"
    if lock.is_file():
        match = re.search(r'name = "tauris-ui"\nversion = "([^"]+)"', lock.read_text(encoding="utf-8"))
        built = match.group(1) if match else None
        if built is None:
            note("Cargo.lock has no tauris-ui yet: build the app once")
        elif built != current and spec is not None and "path" in spec:
            note(f"last built with tauris-ui {built}; the next build uses {current}")
    else:
        note("no Cargo.lock yet: build the app once")

    print()
    if problems:
        print(f"{len(problems)} to fix.")
        return 1
    print("Ready." + (f" {len(notes)} note(s) above." if notes else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
