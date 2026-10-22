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


# What may come right before a regular expression in JavaScript (and not
# before a division): a word like these, or one of these characters.
REGEX_AFTER_WORD = {"return", "typeof", "case", "do", "else", "in", "of", "void", "delete", "new", "throw", "yield",
                    "await", "instanceof"}
REGEX_AFTER = set("(,=:[!&|?{};+-*%<>~^")


def end_of_template(text, i):
    """Where the template literal starting at `i` ends: past its own backtick,
    with ${ ... } expressions (and templates inside them) skipped whole."""
    j, n = i + 1, len(text)
    while j < n:
        if text[j] == "\\":
            j += 2
        elif text[j] == "`":
            return j + 1
        elif text.startswith("${", j):
            depth, j = 1, j + 2
            while j < n and depth:
                c = text[j]
                if c == "`":
                    j = end_of_template(text, j)
                    continue
                if c in "\"'":
                    k = j + 1
                    while k < n and text[k] != c:
                        k += 2 if text[k] == "\\" else 1
                    j = k + 1
                    continue
                depth += {"{": 1, "}": -1}.get(c, 0)
                j += 1
        else:
            j += 1
    return n


def js_code(text):
    """JavaScript without its comments, so commented-out code counts as absent.
    Strings and regular expressions are kept whole: a quote or a `/*` inside
    one starts nothing."""
    out, i, n = [], 0, len(text)
    last, word = "", ""  # the last character that is not a space, and the word ending there
    while i < n:
        c = text[i]
        if c == "`":
            j = end_of_template(text, i)
            out.append(text[i:j])
            i, last, word = j, c, ""
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i, last, word = j + 1, c, ""
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                out.append(text[i:])
                break
            i = end + 2
        elif c == "/" and (last == "" or last in REGEX_AFTER or word in REGEX_AFTER_WORD):
            j, in_class = i + 1, False
            while j < n and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "[":
                    in_class = True
                elif text[j] == "]":
                    in_class = False
                elif text[j] == "/" and not in_class:
                    break
                j += 1
            j += 1
            while j < n and text[j].isalpha():  # flags
                j += 1
            out.append(text[i:j])
            i, last, word = j, "/", ""
        else:
            out.append(c)
            if not c.isspace():
                if c.isalnum() or c in "_$":
                    word = word + c if i > 0 and (text[i - 1].isalnum() or text[i - 1] in "_$") else c
                else:
                    word = ""
                last = c
            i += 1
    return "".join(out)


def rust_code(text):
    """Rust without its comments (nested ones too); strings, raw strings and
    character literals kept whole."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if text.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif text.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
        elif (raw := re.match(r'b?r(#*)"', text[i:])) and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")):
            close = '"' + raw.group(1)
            end = text.find(close, i + len(raw.group(0)))
            end = n if end < 0 else end + len(close)
            out.append(text[i:end])
            i = end
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif c == "'" and (char := re.match(r"'(?:\\(?:x[0-9a-fA-F]{2}|u\{[0-9a-fA-F]+\}|.)|[^\\'\n])'", text[i:])):
            out.append(char.group(0))
            i += len(char.group(0))
        else:
            out.append(c)
            i += 1
    return "".join(out)


def css_code(text):
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


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
    plain = re.findall(r"(?:^|[,{]|\basync|\bget|\bset)\s*([A-Za-z_$][\w$]*)\s*(?=[:(,]|$)", flat)
    quoted = re.findall(r"(?:^|[,{])\s*[\"']([A-Za-z_$][\w$]*)[\"']\s*(?=:)", flat)
    return set(plain + quoted)


def own_picker(text):
    """Whether a TaurisFiles.mount call is given a pick option: in the object
    it is given, or in the object its variable is declared with."""
    # TaurisFiles.mount(, TaurisFiles?.mount(, TaurisFiles.mount<MyFile>(
    for m in re.finditer(r"TaurisFiles\s*\??\.\s*mount\s*(?:<[^<>()]*>)?\s*\(", text):
        given = arguments(balanced(text, m.end() - 1, "(", ")"))
        options = given[1] if len(given) > 1 else ""
        if options.startswith("{"):
            if "pick" in keys(balanced(options, 0, "{", "}")):
                return True
        elif re.fullmatch(r"[A-Za-z_$][\w$]*", options) and has_pick(text, options):
            return True
    return False


def arguments(args):
    """A call's arguments (the text between its brackets), split at its own
    commas, not at those inside brackets."""
    found, depth, start = [], 0, 0
    for i, c in enumerate(args):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            found.append(args[start:i].strip())
            start = i + 1
    found.append(args[start:].strip())
    return found


def has_pick(text, name, seen=()):
    """Whether the object variable `name` is declared with a pick key, itself
    or through an object it spreads in ({ ...base })."""
    decl = re.search(rf"\b(?:const|let|var)\s+{re.escape(name)}\s*(?::[^=;]+)?=\s*\{{", text)
    if not decl or name in seen:
        return False
    body = balanced(text, decl.end() - 1, "{", "}")
    if "pick" in keys(body):
        return True
    return any(has_pick(text, base, seen + (name,)) for base in re.findall(r"\.\.\.\s*([A-Za-z_$][\w$]*)", body))


def manifest_of(folder):
    """A folder's Cargo.toml, read ({} when there is none, or it cannot be read)."""
    manifest = folder / "Cargo.toml"
    if not manifest.is_file():
        return {}
    try:
        return tomllib.loads(read(manifest))
    except tomllib.TOMLDecodeError:
        return {}


def lock_file(tauri):
    """The Cargo.lock the app is built with: its own, or its workspace's."""
    if (tauri / "Cargo.lock").is_file():
        return tauri / "Cargo.lock"
    for folder in tauri.parents:
        if "workspace" in manifest_of(folder):
            return folder / "Cargo.lock" if (folder / "Cargo.lock").is_file() else None
    return None


def window_labels(app, rust):
    """The labels of the windows the app opens: in tauri.conf.json, and from
    its Rust code (WebviewWindowBuilder::new(app, "label", ...))."""
    labels = [w.get("label", "main") for w in app.get("windows", []) if isinstance(w, dict)]
    labels += re.findall(r'(?:WebviewWindowBuilder::new|WebviewWindow::builder|WindowBuilder::new)\s*\(\s*[^,]*?,\s*"([^"]+)"', rust)
    return list(dict.fromkeys(labels))


def permissions(capability):
    return json.dumps(capability.get("permissions", []))


def listens(capability):
    """Whether a capability lets its windows listen for events (core:default has it)."""
    return any(f'"{p}"' in permissions(capability) for p in ("core:default", "core:event:default", "core:event:allow-listen"))


def feature_on(manifest_data, dependency, feature):
    """Whether the app's default features turn on `feature` of `dependency`,
    directly ("tauris-ui/files") or through a feature of its own."""
    table = manifest_data.get("features", {})
    seen, todo = set(), ["default"]
    while todo:
        name = todo.pop()
        if name in seen or not isinstance(table.get(name), list):
            continue
        seen.add(name)
        for item in table[name]:
            if item in (f"{dependency}/{feature}", f"{dependency}?/{feature}"):
                return True
            if isinstance(item, str) and "/" not in item and not item.startswith("dep:"):
                todo.append(item)
    return False


def workspace_spec(tauri):
    """tauris-ui as the workspace's Cargo.toml gives it ([workspace.dependencies]),
    with its path made relative to the app."""
    for folder in [tauri, *tauri.parents]:
        data = manifest_of(folder)
        spec = data.get("workspace", {}).get("dependencies", {}).get("tauris-ui")
        if spec is not None:
            spec = {"version": spec} if isinstance(spec, str) else dict(spec)
            if "path" in spec:
                spec["path"] = str((folder / spec["path"]).resolve())
            return spec
    return {}


def page_code(path):
    """A page file without its comments. In HTML (and Vue, Svelte) only the
    scripts are read as code: a quote in the page's text starts no string."""
    text = read(path)
    if path.suffix == ".css":
        return css_code(text)
    if path.suffix not in {".html", ".vue", ".svelte"}:
        return js_code(text)
    # HTML comments are left out of the page's markup, not out of its scripts
    # (where "<!--" can be text in a string).
    markup = lambda part: re.sub(r"<!--.*?-->", "", part, flags=re.S)
    out, at = [], 0
    for m in re.finditer(r"(<(script|style)\b[^>]*>)(.*?)(</\2\s*>)", text, flags=re.S | re.I):
        before = text[at:m.start(3)]
        if "<!--" in markup(before) or before.count("<!--") > before.count("-->"):
            continue  # this script sits inside a comment: it is skipped with it below
        out.append(markup(before))
        out.append(js_code(m.group(3)) if m.group(2).lower() == "script" else css_code(m.group(3)))
        at = m.end(3)
    out.append(markup(text[at:]))
    return "".join(out)


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
    """Whether Cargo's requirement takes this version: caret (the default),
    =, ~, *, x.*, >=, >, <, <=, and several joined by commas."""
    v = parts(version)[:3]
    for one in requirement.split(","):
        one = one.strip()
        op = re.match(r"(\^|=|~|>=|<=|>|<)?\s*(.*)", one)
        sign, want = op.group(1) or "^", op.group(2).strip()
        if want in ("", "*"):
            continue
        given = [int(x) for x in re.findall(r"\d+", want.split("*")[0])[:3]]
        w = given + [0] * (3 - len(given))
        n = len(given)
        if sign == "=" or "*" in want:
            if v[:n] != w[:n]:
                return False
        elif sign == "~":
            if v[:max(1, min(n, 2))] != w[:max(1, min(n, 2))] or v < w:
                return False
        elif sign == "^":
            # The first number that is not 0 (or the last one given) stays.
            keep = next((k + 1 for k in range(n) if w[k] != 0), n)
            if v[:keep] != w[:keep] or v < w:
                return False
        elif sign == ">" and n < 3:
            # ">0.4" is ">=0.5.0": past every 0.4.x.
            if v[:n] <= w[:n]:
                return False
        elif sign == "<=" and n < 3:
            # "<=0.4" takes every 0.4.x.
            if v[:n] > w[:n]:
                return False
        elif not {">=": v >= w, ">": v > w, "<=": v <= w, "<": v < w}[sign]:
            return False
    return True


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
    # Tauri reads every file under capabilities/, in folders too.
    for path in sorted((tauri / "capabilities").rglob("*")):
        try:
            if path.suffix == ".json":
                data = json.loads(read(path))
            elif path.suffix == ".toml":
                data = tomllib.loads(read(path))
            else:
                continue
        except (json.JSONDecodeError, tomllib.TOMLDecodeError):
            bad(f"{path.relative_to(tauri)} cannot be read", "fix the file")
            continue
        # One capability, a list of them, or { "capabilities": [...] }.
        if isinstance(data, dict) and isinstance(data.get("capabilities"), list) and "identifier" not in data:
            data = data["capabilities"]
        caps += [(path, c) for c in (data if isinstance(data, list) else [data]) if isinstance(c, dict)]
    listed = app.get("security", {}).get("capabilities", [])
    # A list in tauri.conf.json enables only what it lists (by identifier, or inline).
    names = {c for c in listed if isinstance(c, str)}
    if listed:
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
    try:
        manifest_data = tomllib.loads((tauri / "Cargo.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"  FIX   {tauri / 'Cargo.toml'} cannot be read: {e}")
        return 1
    current = library_version()
    sections = [manifest_data.get("dependencies", {})]
    sections += [t.get("dependencies", {}) for t in manifest_data.get("target", {}).values()]
    # tauris-ui = ..., or another name for it: ui = { package = "tauris-ui", ... }
    found = next(((key, d[key]) for d in sections for key in d
                  if key == "tauris-ui" or (isinstance(d[key], dict) and d[key].get("package") == "tauris-ui")), None)
    crate = found[0].replace("-", "_") if found else "tauris_ui"
    spec = found[1] if found else None
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
            lock = lock_file(tauri)
            locked = re.search(r'name = "tauris-ui"\nversion = "([^"]+)"', read(lock)) if lock else None
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
    try:
        conf = json.loads((tauri / "tauri.conf.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"  FIX   {tauri / 'tauri.conf.json'} cannot be read: {e}")
        return 1
    app = conf.get("app", {})
    rust = "\n".join(rust_code(read(p)) for p in (tauri / "src").rglob("*.rs"))
    files = page_files(tauri, conf)
    # Copied typings (tabs.d.ts...) name every component: they are not the app using them.
    text = "\n".join(page_code(p) for p in files if not p.name.endswith(".d.ts"))
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
    # tauris_ui::init(...), or init(...) after `use tauris_ui::init` (or `{init, ...}`).
    # Also under the name the app gave the crate (`use tauris_ui as ui`, a renamed
    # dependency), and with a runtime spelled out (init::<Wry>(...)).
    names = {crate, "tauris_ui"} | set(re.findall(r"\buse\s+(?:tauris_ui|" + re.escape(crate) + r")\s+as\s+(\w+)", rust))
    called = any(re.search(rf"\b{re.escape(n)}::init\s*(?:::<[^>]*>)?\s*\(", rust) for n in names)
    imported = any(re.search(rf"\buse\s+{re.escape(n)}::(?:init\b|\{{[^}}]*\binit\b)", rust) for n in names)
    if called or (imported and re.search(r"\.plugin\(\s*init\s*(?:::<[^>]*>)?\s*\(", rust)):
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
        # app.tabs().start(), or let tabs = app.tabs(); ... tabs.start()
        held = re.findall(r"\blet\s+(?:mut\s+)?(\w+)\s*(?::[^=;]+)?=\s*[\w.()&]*\.tabs\(\)\s*;", rust)
        if re.search(r"\.tabs\(\)\s*\.\s*start\(\)", rust) or any(re.search(rf"\b{v}\s*\.\s*start\(\)", rust) for v in held):
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
            # Every tab window (tabs-1, tabs-2, ...): a pattern, not one label.
            covers = any(any(w == "*" or (w.endswith("*") and f"{prefix}1".startswith(w[:-1]))
                             for w in c.get("windows") or c.get("webviews") or []) for _, c in granting)
            if covers:
                ok(f"a capability grants tauris-ui:default to the tab windows ({prefix}1, {prefix}2, ...)")
            else:
                names = ", ".join(json.dumps(c.get("windows") or c.get("webviews") or []) for _, c in granting)
                bad(f"the capability with tauris-ui:default covers {names}, not the tab windows {prefix}1, {prefix}2, ...",
                    f'set "windows": ["{prefix}*"] (or ["*"]); otherwise the strip stays empty')
            if not any("allow-start-dragging" in json.dumps(c.get("permissions", [])) for _, c in granting):
                note('without "core:window:allow-start-dragging" the window cannot be dragged by its tab strip')
            # The strip hears Rust (⌘T, a tab closed or moved) through events.
            tab_windows = [c for _, c in caps if any(w == "*" or (w.endswith("*") and f"{prefix}1".startswith(w[:-1]))
                                                     for w in c.get("windows") or c.get("webviews") or [])]
            if not any(listens(c) for c in tab_windows):
                bad("no capability lets the tab windows listen for events, so the strip never hears ⌘T or a tab closing",
                    'add "core:default" to the "permissions" of the capability for the tab windows')
        if re.search(r"TaurisTabs\s*\??\.\s*mount\s*\(", text):
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
            labels = window_labels(app, rust)
            reach = lambda c: any(pattern == "*" or pattern == label or (pattern.endswith("*") and label.startswith(pattern[:-1]))
                                  for pattern in c.get("windows") or c.get("webviews") or [] for label in labels)
            every = [c for _, c in capabilities(tauri, app)]
            granting = [c for c in every if "tauris-ui:default" in permissions(c)]
            # Dropped files reach the page as events, with or without the app's own pick
            # (windows not known: at least one capability must allow it).
            if not labels and any(listens(c) for c in every):
                pass
            elif labels and any(reach(c) and listens(c) for c in every):
                ok("a capability lets the app's windows listen for events (dropped files)")
            else:
                bad(f"no capability lets the app's windows ({', '.join(labels) or 'main'}) listen for events, so dropped files are never heard",
                    f'add "core:default" to "permissions" in a capability whose "windows" has {json.dumps((labels or ["main"])[0])}')
            # Only the system's picker needs tauris-ui:default: an app with its own pick does not.
            if own_picker(text):
                pass
            elif granting and not labels:
                note("could not tell which windows the app opens: the capability with tauris-ui:default must cover them")
            elif any(reach(c) for c in granting):
                ok("a capability grants tauris-ui:default to the app's windows (the system's picker)")
            elif granting:
                bad(f"the capability with tauris-ui:default does not cover the app's windows ({', '.join(labels)})",
                    f'add {json.dumps(labels[0])} to its "windows"')
            else:
                bad("no capability grants tauris-ui:default, so Add files… cannot open the system's picker",
                    'add "tauris-ui:default" to "permissions" in src-tauri/capabilities/default.json')
        features = spec.get("features", []) if isinstance(spec, dict) else []
        # Or turned on by the app's own default features: "tauris-ui/files", or a feature of its own that does.
        on_by_default = feature_on(manifest_data, found[0] if found else "tauris-ui", "files")
        if "files" in features or on_by_default:
            ok('the "files" feature is on (the system\'s picker and save dialog)')
            if not any("tauri-plugin-dialog" in d for d in sections):
                bad("the files feature needs the dialog plugin, and Cargo.toml does not depend on it",
                    'add tauri-plugin-dialog = "2" under [dependencies], and .plugin(tauri_plugin_dialog::init()) to tauri::Builder')
            elif any(re.search(rf"\b{re.escape(n)}::init\s*\(", rust)
                     for n in {"tauri_plugin_dialog"} | set(re.findall(r"\buse\s+tauri_plugin_dialog\s+as\s+(\w+)", rust))):
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
        # A copy defines the component (or still has the stylesheet's placeholder);
        # an app's own tabs.js that only mounts the strip is not one.
        if any(p.name == name and (f"window.{word} =" in read(p) or "__TAURIS_" in read(p)) for p in files):
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
            # A /// <reference path="…/files.d.ts" /> (a comment to everything else), or tsconfig's include.
            referenced = any(name in read(p) for p in files) or name in read(tauri.parent / "tsconfig.json")
            if stale:
                bad(f"the app's copy of {name} is out of date: {stale[0]}", f"copy {types} over it")
            elif in_ts and not referenced and not copies:
                bad(f"TypeScript code uses {word} but no file has its types",
                    f"copy {types} into the app (for example src/{name}); TypeScript picks it up from there")
            elif in_ts:
                ok(f"the page has the {word} types")

    # identity: a copied example must become its own app
    if conf.get("identifier") == "dev.tauris-ui.example" and LIBRARY not in tauri.parents:
        bad('the app still has the example\'s identifier "dev.tauris-ui.example", so it shares the example\'s saved tabs',
            "set your own identifier and productName in tauri.conf.json, and the package name in Cargo.toml")

    # 6. last build
    lock = lock_file(tauri)
    if lock:
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
