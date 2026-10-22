"""Tests the tree view (web/tree.js, web/tree.css) in a headless browser.

Run:  python test/tree_run.py [screenshot-folder]
Needs Python playwright, Pillow and Google Chrome. Nothing touches the screen.
Exits non-zero when a check fails. With a folder, it saves screenshots at 2x:
the demo in dark and light mode, and close-ups of the connectors and boxes.
"""
import io
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
DEMO = HERE / "tree_demo.html"
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if SHOTS:
    SHOTS.mkdir(parents=True, exist_ok=True)
SIZE = {"width": 1100, "height": 820}
SCALE = 2
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail != "" and not ok else ""))
    if not ok:
        failures.append(name)


def fresh(browser, color_scheme="dark"):
    page = browser.new_page(viewport=SIZE, device_scale_factor=SCALE, color_scheme=color_scheme)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.goto(DEMO.as_uri())
    page.wait_for_selector(".tv-row")
    # Every event of both trees, as [tree, event, node id, extra].
    page.evaluate("""() => {
      window.__ev = [];
      for (const [name, tree] of Object.entries(demo)) {
        tree.on('select', e => __ev.push([name, 'select', e.node && e.node.id]));
        tree.on('toggle', e => __ev.push([name, 'toggle', e.node.id, e.expanded]));
        tree.on('activate', e => __ev.push([name, 'activate', e.node.id]));
        tree.on('change', e => __ev.push([name, 'change', e.node.id, e.column, e.value]));
      }
    }""")
    return page


def events(page, kind=None):
    ev = page.evaluate("window.__ev.splice(0)")
    return [e for e in ev if kind is None or e[1] == kind]


def row(page, key):
    return page.locator(f'.tv-row[data-key="{key}"]')


def selected(page, tree):
    return page.evaluate(f"demo.{tree}.selected() && demo.{tree}.selected().id")


def active_key(page):
    return page.evaluate("document.activeElement && document.activeElement.dataset && document.activeElement.dataset.key")


def expanded(page, key):
    return row(page, key).get_attribute("aria-expanded")


def rect(page, selector):
    return page.evaluate("""s => { const r = document.querySelector(s).getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height }; }""", selector)


def picture(page):
    return Image.open(io.BytesIO(page.screenshot())).convert("RGB")


def hex_rgb(text):
    text = text.strip().lstrip("#")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def dist(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def shot(page, name, clip=None, enlarge=0):
    """Saves a screenshot; with `enlarge`, also a copy with every pixel made that many times bigger."""
    if not SHOTS:
        return
    path = SHOTS / f"tree_{name}.png"
    page.screenshot(path=str(path), clip=clip)
    if enlarge:
        im = Image.open(path)
        im.resize((im.width * enlarge, im.height * enlarge), Image.NEAREST).save(SHOTS / f"tree_{name}_x{enlarge}.png")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")

    # ---------- screenshots ----------
    for scheme in ["dark", "light"]:
        page = fresh(browser, scheme)
        page.evaluate("demo.settings.focus()")  # settings shows a focused selection, the project an inactive one
        shot(page, scheme)
        top = rect(page, "#files")
        shot(page, f"{scheme}_connectors", {"x": top["x"], "y": top["y"], "width": 240, "height": 330})
        first = rect(page, '#files .tv-row')
        shot(page, f"{scheme}_boxes", {"x": first["x"], "y": first["y"], "width": 80, "height": 6 * 18}, enlarge=4)
        page.close()

    page = fresh(browser)
    page.evaluate("demo.settings.select('general.name'); demo.settings.focus()")
    page.keyboard.press("Enter")
    page.keyboard.type("Atlas Pro")
    shot(page, "dark_editing", {"x": rect(page, "#settings")["x"], "y": rect(page, "#settings")["y"], "width": 560, "height": 200})
    page.close()

    # ---------- structure and ARIA ----------
    page = fresh(browser)
    check("two trees with role=tree", page.locator('[role="tree"]').count() == 2)
    check("the trees are labelled", page.evaluate("[...document.querySelectorAll('[role=tree]')].map(t => t.getAttribute('aria-label'))") == ["Project files", "Settings"])
    aria = page.evaluate("""[...document.querySelectorAll('#files .tv-row')].map(r => ({
      role: r.getAttribute('role'), level: r.getAttribute('aria-level'), exp: r.getAttribute('aria-expanded'),
      sel: r.getAttribute('aria-selected'), set: r.getAttribute('aria-setsize'), pos: r.getAttribute('aria-posinset'),
      parent: r.classList.contains('tv-parent') }))""")
    check("every row is a treeitem with a level, size and position", all(a["role"] == "treeitem" and a["level"] and a["set"] and a["pos"] for a in aria))
    check("aria-expanded on folders only", all((a["exp"] is not None) == a["parent"] for a in aria))
    check("aria-selected on every row, true on one", all(a["sel"] in ("true", "false") for a in aria) and sum(a["sel"] == "true" for a in aria) == 1)
    check("levels follow the depth", row(page, "atlas-desktop/src-tauri/src/sync/queue.rs").get_attribute("aria-level") == "5")
    check("one row per tree in the Tab order (roving tabindex)",
          page.evaluate("[...document.querySelectorAll('[role=tree]')].map(t => t.querySelectorAll('.tv-row[tabindex=\"0\"]').length)") == [1, 1])
    edges = page.evaluate("[...document.querySelectorAll('#settings .tv-hcell')].map(c => [c.getAttribute('role'), c.tabIndex, c.getAttribute('aria-label')])")
    check("the column header is outside the tree, and each column's edge can be moved from the keyboard",
          page.evaluate("document.querySelector('#settings .tv-head').closest('[role=tree]')") is None
          and [e[0] for e in edges[:-1]] == ["separator"] * (len(edges) - 1) and edges[-1][0] is None and edges[0][1] == 0, edges)
    check("a true/false setting carries aria-checked", row(page, "general.login").get_attribute("aria-checked") == "true")

    heights = page.evaluate("[...document.querySelectorAll('.tv-row')].map(r => r.getBoundingClientRect().height)")
    check("rows are 18px high", set(heights) == {18}, set(heights))
    font = page.evaluate("getComputedStyle(document.querySelector('.tv-label')).fontSize")
    check("labels are 12px", font == "12px", font)
    b1 = rect(page, '.tv-row[data-key="atlas-desktop/src"] .tv-box')
    b2 = rect(page, '.tv-row[data-key="atlas-desktop/src/lib"] .tv-box')
    check("each level indents 16px", b2["x"] - b1["x"] == 16, (b1, b2))
    check("boxes are 9 x 9", b1["w"] == 9 and b1["h"] == 9, b1)
    geometry = page.evaluate("""[...document.querySelectorAll('.tv-row.tv-parent')].map(r => {
      const b = r.querySelector('.tv-box').getBoundingClientRect(), i = r.querySelector('.tv-indent').getBoundingClientRect();
      const y = r.getBoundingClientRect().y, d = Number(r.getAttribute('aria-level')) - 1;
      return { dx: b.x - i.x - d * 16, dy: b.y - y, whole: [b.x, b.y, i.x, y].every(Number.isInteger) }; })""")
    check("every box sits on its line column and row (whole pixels)",
          all(g == {"dx": 4, "dy": 5, "whole": True} for g in geometry), [g for g in geometry if g != {"dx": 4, "dy": 5, "whole": True}][:3])

    # ---------- the pixels: lines, boxes, sharpness ----------
    img = picture(page)
    line_rgb = hex_rgb(page.evaluate("getComputedStyle(document.getElementById('files')).getPropertyValue('--tv-line')"))
    files_x = rect(page, '#files .tv-indent')["x"]

    def px(x, y):  # the colour of the CSS pixel (x, y), from its top-left device pixel
        return img.getpixel((int(x * SCALE), int(y * SCALE)))

    def on(x, y, bg):
        return dist(px(x, y), bg) > 20

    def row_y(key):
        return rect(page, f'.tv-row[data-key="{key}"]')["y"]

    bg = px(files_x + 1, row_y("atlas-desktop/docs") + 1)
    # The line of the "src" level runs from below "src" down to "src-tauri".
    col = files_x + 16 + 8
    y0, y1 = row_y("atlas-desktop/src") + 18, row_y("atlas-desktop/src-tauri")
    dots = [on(col, y, bg) for y in range(int(y0), int(y1))]
    check("a long line is one unbroken dot pattern across rows", len(dots) > 200 and all(a != b for a, b in zip(dots, dots[1:])), dots[:40])
    check("the line is one pixel wide", not any(on(col - 1, y, bg) or on(col + 1, y, bg) for y in range(int(y0), int(y1))))
    sharp = [img.getpixel((int(col * SCALE) + dx, y)) for dx in (0, 1) for y in range(int(y0 * SCALE), int(y1 * SCALE))]
    check("line pixels are exactly line or background (sharp at 2x)", all(min(dist(c, bg), dist(c, line_rgb)) <= 2 for c in sharp),
          sorted({c for c in sharp if min(dist(c, bg), dist(c, line_rgb)) > 2})[:5])

    last = row_y("atlas-desktop/src/lib/store.js")
    col3 = files_x + 3 * 16 + 8
    check("a last child's line reaches its middle", any(on(col3, last + y, bg) for y in range(0, 10)))
    check("and stops there", not any(on(col3, last + y, bg) for y in range(10, 18)))
    mid_child = row_y("atlas-desktop/src/lib/format.js")
    check("a child with siblings below passes the line on", any(on(col3, mid_child + y, bg) for y in range(10, 18)))
    readme = row_y("atlas-desktop/README.md")
    check("the last top-level child ends the root's line", not any(on(files_x + 24, readme + y, bg) for y in range(10, 18)))
    root_y = row_y("atlas-desktop")
    check("a single root has no line above or below its box",
          not any(on(files_x + 8, root_y + y, bg) for y in list(range(0, 5)) + list(range(14, 18))))

    bx, by = b1["x"], b1["y"]
    check("the line touches the box from above and below", on(bx + 4, by - 1, bg) and on(bx + 4, by + 9, bg))
    check("the box is centred on the line", not on(bx + 3, by - 1, bg) and not on(bx + 5, by - 1, bg))
    glyph_row = [on(bx + i, by + 4, bg) for i in range(1, 8)]
    check("the minus is centred in the box", glyph_row == [False, True, True, True, True, True, False], glyph_row)
    check("the stub leaves the box on the minus's row", on(bx + 9, by + 4, bg) and not on(bx + 9, by + 3, bg) and not on(bx + 9, by + 5, bg))
    plus = rect(page, '.tv-row[data-key="atlas-desktop/docs"] .tv-box')
    check("a closed box shows a plus", [on(plus["x"] + 4, plus["y"] + i, bg) for i in range(1, 8)] == [False, True, True, True, True, True, False])
    border = {img.getpixel((int(bx * SCALE) + dx, int((by + 2) * SCALE) + dy)) for dx in (0, 1) for dy in range(0, 10)}
    check("the box border is one sharp colour", len(border) == 1, border)
    page.close()

    # ---------- keyboard ----------
    page = fresh(browser)
    page.evaluate("demo.files.focus()")
    check("focus starts on the selected row", active_key(page) == "atlas-desktop/src-tauri/src/sync/queue.rs", active_key(page))
    page.keyboard.press("ArrowDown")
    check("Down selects the next row", selected(page, "files") == "atlas-desktop/src-tauri/src/commands.rs")
    check("select event", events(page, "select") == [["files", "select", "atlas-desktop/src-tauri/src/commands.rs"]])
    check("focus follows the selection", active_key(page) == "atlas-desktop/src-tauri/src/commands.rs")
    page.keyboard.press("ArrowUp")
    page.keyboard.press("ArrowLeft")
    check("Left on a leaf goes to its parent", selected(page, "files") == "atlas-desktop/src-tauri/src/sync")
    events(page)
    page.keyboard.press("ArrowLeft")
    check("Left on an open folder closes it", expanded(page, "atlas-desktop/src-tauri/src/sync") == "false")
    check("toggle event on close", events(page, "toggle") == [["files", "toggle", "atlas-desktop/src-tauri/src/sync", False]])
    page.keyboard.press("ArrowRight")
    check("Right on a closed folder opens it", expanded(page, "atlas-desktop/src-tauri/src/sync") == "true")
    page.keyboard.press("ArrowRight")
    check("Right on an open folder goes to its first child", selected(page, "files") == "atlas-desktop/src-tauri/src/sync/conflict.rs")
    page.keyboard.press("Home")
    check("Home goes to the first row", selected(page, "files") == "atlas-desktop")
    page.keyboard.press("End")
    check("End goes to the last row", selected(page, "files") == "atlas-desktop/README.md")
    events(page)
    page.keyboard.press("Enter")
    check("Enter activates a row", events(page, "activate") == [["files", "activate", "atlas-desktop/README.md"]])
    page.evaluate("demo.files.select('atlas-desktop/.github')")
    page.keyboard.press("*")
    check("* opens everything below", expanded(page, "atlas-desktop/.github") == "true" and expanded(page, "atlas-desktop/.github/workflows") == "true")
    page.keyboard.press("-")
    check("- closes", expanded(page, "atlas-desktop/.github") == "false")
    page.keyboard.press("+")
    check("+ opens", expanded(page, "atlas-desktop/.github") == "true")
    page.keyboard.press("c")
    check("typing a letter jumps to the next row starting with it", selected(page, "files") == "atlas-desktop/src-tauri/capabilities", selected(page, "files"))
    page.keyboard.press("PageDown")
    check("PageDown moves a page", page.evaluate("Number(document.activeElement.style.top.replace('px', ''))") > 300)
    page.evaluate("demo.files.select(null)")
    events(page)
    page.keyboard.press(" ")
    check("Space selects the focused row", len(events(page, "select")) == 1 and selected(page, "files") is not None)
    tab0 = page.evaluate("[...document.querySelectorAll('#files .tv-row[tabindex=\"0\"]')].map(r => r.dataset.key)")
    check("still exactly one row in the Tab order, the focused one", tab0 == [active_key(page)], tab0)
    page.evaluate("demo.files.select('atlas-desktop/src-tauri/src/sync/queue.rs'); demo.files.collapse('atlas-desktop/src-tauri')")
    check("closing a parent of the selection selects the parent", selected(page, "files") == "atlas-desktop/src-tauri")
    page.close()

    # ---------- mouse ----------
    page = fresh(browser)
    box = rect(page, '.tv-row[data-key="atlas-desktop/docs"] .tv-box')
    page.mouse.click(box["x"] + 4, box["y"] + 4)
    check("clicking + opens the folder", expanded(page, "atlas-desktop/docs") == "true")
    check("and leaves the selection alone", selected(page, "files") == "atlas-desktop/src-tauri/src/sync/queue.rs")
    page.mouse.click(box["x"] + 4, box["y"] + 4)
    check("clicking - closes it", expanded(page, "atlas-desktop/docs") == "false")
    events(page)
    row(page, "atlas-desktop/.github").locator(".tv-label").dblclick()
    check("double-click opens a folder", expanded(page, "atlas-desktop/.github") == "true")
    check("double-click activates", ["files", "activate", "atlas-desktop/.github"] in events(page))
    row(page, "atlas-desktop/src/main.js").locator(".tv-label").click()
    check("a click selects", selected(page, "files") == "atlas-desktop/src/main.js")
    check("and focuses the row", active_key(page) == "atlas-desktop/src/main.js")
    page.close()

    # ---------- configuration editor ----------
    page = fresh(browser)
    page.evaluate("demo.settings.select('general.name'); demo.settings.focus()")
    page.keyboard.press("Enter")
    editor = page.locator("#settings .tv-editor")
    check("Enter opens an editor in the value cell", editor.count() == 1 and editor.get_attribute("type") == "text")
    r = rect(page, '.tv-row[data-key="general.name"]')
    e = rect(page, "#settings .tv-editor")
    check("the editor fits inside the row (the row keeps 18px)", r["h"] == 18 and e["h"] <= 18 and e["y"] >= r["y"] and e["y"] + e["h"] <= r["y"] + 18, (r, e))
    page.keyboard.press("Meta+A")
    page.keyboard.type("Atlas Pro")
    page.keyboard.press("Enter")
    check("text: Enter saves and emits change", events(page, "change") == [["settings", "change", "general.name", "value", "Atlas Pro"]])
    check("the editor closes and focus returns to the row", editor.count() == 0 and active_key(page) == "general.name")
    check("the cell shows the new value", row(page, "general.name").locator('.tv-cell[data-col="1"]').inner_text() == "Atlas Pro")
    page.keyboard.press("Enter")
    page.keyboard.type("x")
    page.keyboard.press("Escape")
    check("Escape cancels without a change", events(page, "change") == [] and page.evaluate("demo.settings.get('general.name').values.value") == "Atlas Pro")

    row(page, "appearance.fontSize").locator('.tv-cell[data-col="1"]').click()
    check("a click on a number opens a number editor", editor.get_attribute("type") == "number")
    page.keyboard.press("Meta+A")
    page.keyboard.type("14")
    page.keyboard.press("Enter")
    check("number: the value is a number", events(page, "change") == [["settings", "change", "appearance.fontSize", "value", 14]])
    page.keyboard.press("Enter")
    page.keyboard.press("Meta+A")
    page.keyboard.type("40")
    page.keyboard.press("Enter")
    check("number: kept within max", events(page, "change") == [["settings", "change", "appearance.fontSize", "value", 16]])
    page.keyboard.press("Enter")
    page.keyboard.press("Meta+A")
    page.keyboard.press("Backspace")
    page.keyboard.press("Enter")
    check("number: an empty field changes nothing", events(page, "change") == [])

    row(page, "general.login").locator(".tv-check").click()
    check("checkbox: a click flips it", events(page, "change") == [["settings", "change", "general.login", "value", False]])
    check("checkbox: aria-checked follows", row(page, "general.login").get_attribute("aria-checked") == "false")
    page.keyboard.press(" ")
    check("checkbox: Space flips it back", events(page, "change") == [["settings", "change", "general.login", "value", True]])

    row(page, "appearance.theme").locator('.tv-cell[data-col="1"]').click()
    check("select: a click opens a dropdown in the cell", page.locator("#settings select.tv-editor").count() == 1)
    page.locator("#settings select.tv-editor").select_option(label="Dark")
    check("select: picking saves it", events(page, "change") == [["settings", "change", "appearance.theme", "value", "Dark"]])
    check("select: the dropdown closes", page.locator("#settings select.tv-editor").count() == 0)

    page.evaluate("demo.settings.select('appearance.accent'); demo.settings.focus()")
    page.keyboard.press("Enter")
    page.keyboard.press("Meta+A")
    page.keyboard.type("#3E9FFF")
    page.keyboard.press("Enter")
    check("colour: a typed hex is saved, normalised", events(page, "change") == [["settings", "change", "appearance.accent", "value", "#3e9fff"]])
    page.keyboard.press("Enter")
    page.keyboard.press("Meta+A")
    page.keyboard.type("blue-ish")
    page.keyboard.press("Enter")
    check("colour: an invalid hex changes nothing", events(page, "change") == [])
    swatch = rect(page, '.tv-row[data-key="logging.colours.error"] .tv-swatch')
    page.mouse.click(swatch["x"] + 5, swatch["y"] + 5)
    picker = page.locator("#settings .tv-picker")
    check("colour: the swatch opens the system picker", picker.count() == 1 and picker.get_attribute("type") == "color")
    picker.evaluate("p => { p.value = '#ff6b6b'; p.dispatchEvent(new Event('input')); p.dispatchEvent(new Event('change')); }")
    check("colour: the picker's choice is saved", events(page, "change") == [["settings", "change", "logging.colours.error", "value", "#ff6b6b"]])
    swatch_bg = page.evaluate("getComputedStyle(document.querySelector('.tv-row[data-key=\"logging.colours.error\"] .tv-swatch')).backgroundColor")
    check("colour: the swatch shows it", swatch_bg == "rgb(255, 107, 107)", swatch_bg)
    groups = page.evaluate("demo.settings.edit('network')")
    check("a group row has nothing to edit", groups is False)
    page.close()

    # ---------- columns ----------
    page = fresh(browser)
    lefts = page.evaluate("""() => { const t = document.getElementById('settings');
      const head = [...t.querySelectorAll('.tv-hcell')].map(c => c.getBoundingClientRect().left);
      const rows = [...t.querySelectorAll('.tv-row')].map(r => [...r.children].map(c => c.getBoundingClientRect().left));
      return { head, rows }; }""")
    check("columns line up with the header", all(r == lefts["head"] for r in lefts["rows"]), lefts["head"])
    grip = rect(page, "#settings .tv-hcell .tv-grip")
    page.mouse.move(grip["x"] + 3, grip["y"] + 8)
    page.mouse.down()
    page.mouse.move(grip["x"] + 23, grip["y"] + 8, steps=4)
    page.mouse.move(grip["x"] + 43, grip["y"] + 8, steps=4)
    page.mouse.up()
    widths = page.evaluate("""() => { const t = document.getElementById('settings');
      return { head: t.querySelector('.tv-hcell').getBoundingClientRect().width,
               cells: [...t.querySelectorAll('.tv-row .tv-main')].map(c => c.getBoundingClientRect().width) }; }""")
    check("dragging a column edge resizes the column", widths["head"] == 270, widths["head"])
    check("every row's cell follows the header", set(widths["cells"]) == {270}, set(widths["cells"]))
    lefts2 = page.evaluate("""() => { const t = document.getElementById('settings');
      return [[...t.querySelectorAll('.tv-hcell')].map(c => c.getBoundingClientRect().left),
              ...[...t.querySelectorAll('.tv-row')].map(r => [...r.children].map(c => c.getBoundingClientRect().left))]; }""")
    check("columns still line up after resizing", all(r == lefts2[0] for r in lefts2))
    page.close()

    # ---------- thousands of rows ----------
    page = fresh(browser)
    perf = page.evaluate("""() => {
      const host = document.createElement('div');
      host.style.cssText = 'position:fixed;left:0;top:0;width:420px;height:400px;z-index:9';
      document.body.append(host);
      window.bigHost = host;
      const days = [];
      for (let d = 0; d < 60; d++) {
        const day = new Date(Date.UTC(2026, 6, 1 + d)).toISOString().slice(0, 10);
        const files = [];
        for (let f = 1; f <= 100; f++) files.push({ id: `${day}/scan-${String(f).padStart(4, '0')}.png`, label: `scan-${String(f).padStart(4, '0')}.png`, icon: 'image' });
        days.push({ id: day, label: day, icon: 'folder', children: files });
      }
      // The best of three runs: a busy test machine slows one run, not all three.
      let took = Infinity;
      for (let n = 0; n < 3; n++) {
        if (window.big) big.destroy();
        const started = performance.now();
        window.big = TaurisTree.mount(host, { data: [{ id: 'scans', label: 'Scans', icon: 'folder', children: days }] });
        big.expandAll();
        took = Math.min(took, performance.now() - started);
      }
      return { took, rows: host.querySelectorAll('.tv-row').length, items: host.querySelector('.tv-body').style.height };
    }""")
    check("6,061 rows: mount and expand all in under 150ms", perf["took"] < 150, perf)
    check("only the rows in view are drawn", perf["rows"] < 60, perf)
    check("the tree is as tall as every row", perf["items"] == f"{6061 * 18}px", perf)
    page.evaluate("big.focus()")
    page.keyboard.press("End")
    check("End reaches the last of thousands", page.evaluate("big.selected().id") == "2026-08-29/scan-0100.png")
    page.evaluate("bigHost.querySelector('.tv-scroll').scrollTop = 0")
    page.wait_for_timeout(100)
    check("scrolled away, the focused row stays focused", active_key(page) == "2026-08-29/scan-0100.png")
    check("and the rows at the top are drawn", page.locator('.tv-row[data-key="scans"]').count() == 1)
    page.evaluate("big.collapseAll()")
    check("collapse all leaves one row", page.evaluate("bigHost.querySelectorAll('.tv-row').length") == 1)
    page.close()

    # ---------- sorting ----------
    SORT_TREE = """opts => {
      const host = document.createElement('div');
      host.style.cssText = 'position:fixed;left:0;top:0;width:640px;height:300px;z-index:9';
      document.body.append(host);
      const day = (iso, shown) => ({ iso, shown });
      const c = (id, label, score, added, note) => ({ id, label, values: { score, added: added && added.shown, iso: added && added.iso, note } });
      window.sortData = () => [
        { id: 'short', label: 'Shortlist', expanded: true, children: [
          c('b169', 'Brian 169', 7, day('2026-10-21', '21 Oct 2026'), 'b'),
          c('b49', 'Brian 49', 12, day('2026-01-03', '3 Jan 2026'), 'a'),
          c('anna', 'anna', null, day('2026-03-15', '15 Mar 2026'), 'c'),
          c('zoe', 'Zoe', 3, null, 'd'),
        ] },
        { id: 'rej', label: 'Rejected', expanded: true, children: [c('carl', 'Carl', 5, null, ''), c('bea', 'bea', '', null, '')] },
      ];
      window.sortHost = host;
      window.st = TaurisTree.mount(host, { data: sortData(), label: 'Candidates', ...opts, columns: [
        { label: 'Candidate', width: 200 }, { label: 'Score', key: 'score', width: 80, align: 'right' },
        { label: 'Added', key: 'added', width: 120, sortValue: n => n.values?.iso },
        { label: 'Note', key: 'note', sortable: false } ] });
      window.sorts = [];
      st.on('sort', e => sorts.push(e));
      return 0;
    }"""
    order = lambda page: page.evaluate("[...sortHost.querySelectorAll('.tv-row')].sort((a, b) => parseFloat(a.style.top) - parseFloat(b.style.top)).map(r => r.dataset.key)")
    heads = lambda page: page.evaluate("[...sortHost.querySelectorAll('.tv-hcell')].map(c => [c.getAttribute('role'), c.tabIndex, c.querySelector('.tv-arrow')?.textContent ?? null])")
    head_cell = lambda i: f"#sortHost .tv-hcell:nth-child({i})"

    page = fresh(browser)
    page.evaluate("(" + SORT_TREE + ")({ sortable: true })")
    page.evaluate("sortHost.id = 'sortHost'")
    check("sortable: the headers are buttons in the Tab order; a column with sortable: false is not",
          heads(page) == [["button", 0, ""], ["button", 0, ""], ["button", 0, ""], [None, -1, None]]
          and page.get_attribute("#sortHost .tv-head", "aria-hidden") is None, heads(page))
    check("until a header is clicked, the data's own order", order(page) == ["short", "b169", "b49", "anna", "zoe", "rej", "carl", "bea"]
          and page.evaluate("st.sorting()") is None)
    page.click(head_cell(1))
    check("Candidate: A to Z among siblings, numbers in names as numbers, groups stay groups",
          order(page) == ["rej", "bea", "carl", "short", "anna", "b49", "b169", "zoe"], order(page))
    check("the sorted header shows ▲ and says its order", heads(page)[0][2] == "▲"
          and page.get_attribute(head_cell(1), "aria-label") == "Candidate, sorted ascending"
          and page.get_attribute(head_cell(2), "aria-label") == "Sort by Score")
    check("a sort event says the key and the direction", page.evaluate("sorts.splice(0)") == [{"key": "label", "up": True}])
    page.click(head_cell(1))
    check("a second click turns it round, ▼", order(page) == ["short", "zoe", "b169", "b49", "anna", "rej", "carl", "bea"]
          and heads(page)[0][2] == "▼" and page.evaluate("sorts.splice(0)") == [{"key": "label", "up": False}], order(page))
    page.click(head_cell(2))
    check("Score: numbers as numbers, empty last; groups without values keep their order",
          order(page) == ["short", "zoe", "b169", "b49", "anna", "rej", "carl", "bea"] and heads(page)[0][2] == "" and heads(page)[1][2] == "▲", order(page))
    page.click(head_cell(2))
    check("Score down: biggest first, empty still last", order(page) == ["short", "b49", "b169", "zoe", "anna", "rej", "carl", "bea"], order(page))
    page.click(head_cell(3))
    check("Added sorts by its sortValue (the ISO date), not the shown text", order(page)[:5] == ["short", "b49", "anna", "b169", "zoe"], order(page))
    page.evaluate("sorts.length = 0")
    page.click(head_cell(4))
    check("a column with sortable: false does nothing", order(page)[:5] == ["short", "b49", "anna", "b169", "zoe"] and page.evaluate("sorts.length") == 0)
    page.evaluate("sorts.length = 0")
    page.focus(head_cell(2))
    page.keyboard.press("Enter")
    s1 = page.evaluate("st.sorting()")
    page.keyboard.press("Space")
    s2 = page.evaluate("st.sorting()")
    check("from the keyboard: Enter sorts, Space turns it round", s1 == {"key": "score", "up": True} and s2 == {"key": "score", "up": False}, (s1, s2))
    page.evaluate("document.querySelector('#sortHost .tv-hcell:nth-child(2)').dispatchEvent(new KeyboardEvent('keyup', { key: ' ', bubbles: true }))")
    check("a Space that went down elsewhere does not sort", page.evaluate("st.sorting()") == {"key": "score", "up": False})
    page.evaluate("st.select('zoe'); st.focus()")
    page.evaluate("st.sort('label', true)")
    check("selection and focus stay on the same node after sorting",
          page.evaluate("st.selected().id") == "zoe" and active_key(page) == "zoe" and order(page)[-1] == "zoe")
    page.keyboard.press("ArrowUp")
    check("and the keys move through the new order", page.evaluate("st.selected().id") == "b169")
    page.evaluate("const d = sortData(); d[0].children.push({ id: 'aaron', label: 'Aaron', values: { score: 1 } }); st.setData(d)")
    check("setData keeps the order", order(page)[:4] == ["rej", "bea", "carl", "short"] and order(page)[4] == "aaron" and page.evaluate("st.sorting()") == {"key": "label", "up": True})
    check("sort() with a column that cannot sort is refused", page.evaluate("st.sort('note')") is False and page.evaluate("st.sorting()")["key"] == "label")
    page.evaluate("st.sort(null)")
    check("sort(null): back to the data's own order", order(page)[:6] == ["short", "b169", "b49", "anna", "zoe", "aaron"] and heads(page)[0][2] == "")
    grip = rect(page, "#sortHost .tv-hcell .tv-grip")
    page.mouse.move(grip["x"] + 3, grip["y"] + 8)
    page.mouse.down()
    page.mouse.move(grip["x"] + 30, grip["y"] + 8, steps=4)
    page.mouse.up()
    check("resizing a column does not sort it", page.evaluate("st.sorting()") is None)
    page.close()

    page = fresh(browser)
    page.evaluate("(" + SORT_TREE + ")({ sort: { key: 'score', up: false } })")
    page.evaluate("sortHost.id = 'sortHost'")
    check("a first sort: the tree opens in that order, and its headers sort",
          order(page)[:5] == ["short", "b49", "b169", "zoe", "anna"] and heads(page)[1] == ["button", 0, "▼"], (order(page), heads(page)))
    check("the demo's settings tree, with no sort options, has no sort buttons in its header",
          page.evaluate("document.querySelectorAll('#settings .tv-sortable').length") == 0)
    perf = page.evaluate("""() => {
      const host = document.createElement('div'); host.style.cssText = 'position:fixed;left:0;top:0;width:500px;height:400px;z-index:10';
      document.body.append(host);
      const kids = []; let seed = 7;
      for (let i = 0; i < 3200; i++) { seed = (seed * 48271) % 2147483647; kids.push({ id: 'c' + i, label: 'Candidate ' + (seed % 9000), values: { score: seed % 1000 } }); }
      const t = TaurisTree.mount(host, { sortable: true, data: [{ id: 'all', label: 'All', expanded: true, children: kids }],
        columns: [{ label: 'Name', width: 260 }, { label: 'Score', key: 'score' }] });
      // The best of three runs: a busy test machine slows one run, not all three.
      let bySore = Infinity, byName = Infinity;
      for (let n = 0; n < 3; n++) {
        const a = performance.now(); t.sort('score', false); bySore = Math.min(bySore, performance.now() - a);
        const b = performance.now(); t.sort('label'); byName = Math.min(byName, performance.now() - b);
      }
      const rows = [...host.querySelectorAll('.tv-row')].sort((x, y) => parseFloat(x.style.top) - parseFloat(y.style.top)).map(r => r.querySelector('.tv-label').textContent);
      return { bySore, byName, drawn: host.querySelectorAll('.tv-row').length, first: rows.slice(1, 3) }; }""")
    check("3,200 rows: sorting takes under 60ms, and only the rows in view are drawn",
          perf["bySore"] < 60 and perf["byName"] < 60 and perf["drawn"] < 60, perf)
    page.close()

    # ---------- selecting several rows ----------
    page = fresh(browser)
    page.click('#files .tv-row[data-key="atlas-desktop"] .tv-label')
    page.click('#files .tv-row[data-key="atlas-desktop/src"] .tv-label', modifiers=["ControlOrMeta"])
    check("without multiple, ⌘-click still selects one row", page.evaluate("demo.files.selection().length") == 1
          and page.get_attribute("#files .tv-body", "aria-multiselectable") is None)
    page.evaluate("(" + SORT_TREE + ")({ multiple: true })")
    page.evaluate("sortHost.id = 'sortHost'; window.selEv = []; st.on('select', e => selEv.push([e.node && e.node.id, e.nodes.map(n => n.id)])); 0")  # 0: evaluate would call the returned unsubscribe function
    picked = lambda: page.evaluate("st.selection().map(n => n.id)")
    page.click('#sortHost .tv-row[data-key="b169"] .tv-label')
    page.click('#sortHost .tv-row[data-key="zoe"] .tv-label', modifiers=["ControlOrMeta"])
    check("multiple: ⌘-click adds a row; both look selected; the tree says it can hold several",
          picked() == ["b169", "zoe"] and page.locator('#sortHost .tv-row[aria-selected="true"]').count() == 2
          and page.get_attribute("#sortHost .tv-body", "aria-multiselectable") == "true")
    check("the select event carries the focused node and every selected node", page.evaluate("selEv.at(-1)") == ["zoe", ["b169", "zoe"]])
    page.click('#sortHost .tv-row[data-key="carl"] .tv-label', modifiers=["Shift"])
    check("Shift-click selects every row shown from the last click, across groups",
          picked() == ["zoe", "rej", "carl"], picked())
    page.keyboard.press("Shift+ArrowDown")
    check("Shift+Down extends it", picked() == ["zoe", "rej", "carl", "bea"])
    page.keyboard.press("ControlOrMeta+a")
    check("⌘A selects every row shown", len(picked()) == 8)
    page.evaluate("st.collapse('short')")
    check("closing a group drops its hidden rows from the selection", picked() == ["short", "rej", "carl", "bea"], picked())
    page.evaluate("st.expand('short'); st.select(['b49', 'anna'])")
    check("select([ids]) picks several", picked() == ["b49", "anna"] and page.evaluate("st.selected().id") == "b49")
    page.evaluate("st.sort('label')")
    check("sorting keeps the selection", sorted(picked()) == ["anna", "b49"])
    page.keyboard.press("ArrowDown")
    check("a plain arrow goes back to one row", len(picked()) == 1)
    page.close()

    # ---------- selecting several: the edges a review found ----------
    page = fresh(browser)
    mac = page.evaluate("/Mac|iPhone|iPad/.test(navigator.platform)")
    page.evaluate("(" + SORT_TREE + ")({ multiple: true })")
    page.evaluate("sortHost.id = 'sortHost'; window.selEv = []; st.on('select', e => selEv.push([e.node && e.node.id, e.nodes.map(n => n.id)])); 0")
    page.evaluate("st.select(['b169', 'b49', 'zoe'])")
    page.evaluate("const d = sortData(); d[0].children = d[0].children.filter(c => c.id !== 'b169' && c.id !== 'b49'); st.setData(d)")
    check("setData that drops selected rows says so, and a row still selected takes the focus",
          page.evaluate("selEv.at(-1)") == ["zoe", ["zoe"]] and page.evaluate("st.selected().id") == "zoe")
    page.evaluate("st.setData(sortData()); st.select(['b169', 'b49', 'anna'])")
    page.click('#sortHost .tv-row[data-key="b169"] .tv-label', modifiers=["ControlOrMeta"])
    check("taking out the row with the focus moves it to the nearest selected row",
          page.evaluate("st.selection().map(n => n.id)") == ["b49", "anna"] and page.evaluate("st.selected().id") == "b49")
    if mac:
        page.click('#sortHost .tv-row[data-key="zoe"] .tv-label', modifiers=["Control"])
        check("on a Mac, Control-click (a right click) changes nothing", page.evaluate("st.selection().map(n => n.id)") == ["b49", "anna"])
    page.close()

    # ---------- a second review ----------
    page = fresh(browser)
    page.evaluate("(" + SORT_TREE + ")({ multiple: true })")
    page.evaluate("sortHost.id = 'sortHost'; window.selEv = []; st.on('select', e => selEv.push([e.node && e.node.id, e.nodes.map(n => n.id)])); 0")
    page.evaluate("st.select(['b49', 'zoe', 'b169']); st.focus()")
    page.evaluate("selEv.length = 0; const d = sortData(); d[0].children = d[0].children.filter(c => c.id !== 'b49'); st.setData(d)")
    check("setData without the focused row: the focus and the selection move to the same row, said once",
          page.evaluate("st.selected().id") == active_key(page) == "b169" and page.evaluate("selEv") == [["b169", ["b169", "zoe"]]],
          (page.evaluate("st.selected().id"), active_key(page), page.evaluate("selEv")))
    page.keyboard.press("ArrowDown")
    check("and Down goes on from there", page.evaluate("st.selected().id") == "anna")
    page.close()

    # ---------- a third review ----------
    page = fresh(browser)
    page.evaluate("(" + SORT_TREE + ")({})")
    page.evaluate("sortHost.id = 'sortHost'; window.selEv = []; st.on('select', e => selEv.push(e.node && e.node.id)); 0")
    page.evaluate("st.select('anna'); st.focus(); selEv.length = 0")
    page.evaluate("const d = sortData(); d[0].children = d[0].children.filter(c => c.id !== 'anna'); st.setData(d)")
    check("one selected row dropped by setData: the row now in its place takes the selection and the focus",
          page.evaluate("st.selected().id") == "zoe" == active_key(page) and page.evaluate("selEv") == ["zoe"], (page.evaluate("selEv"), active_key(page)))
    page.keyboard.press("ControlOrMeta+a")
    check("⌘A in a tree without multiple does not select the page's text", page.evaluate("String(window.getSelection())") == "")
    page.close()
    page = fresh(browser)
    page.evaluate("(" + SORT_TREE + ")({ multiple: true })")
    page.evaluate("sortHost.id = 'sortHost'; st.select('b169'); st.focus()")
    page.keyboard.press("ControlOrMeta+ArrowDown")
    page.keyboard.press("ControlOrMeta+ArrowDown")
    page.keyboard.press("ControlOrMeta+Space")
    picked = page.evaluate("st.selection().map(n => n.id)")
    check("tree, from the keyboard alone: ⌘↓ moves the focus, ⌘Space adds the row", picked == ["b169", "anna"] and active_key(page) == "anna", picked)
    ring = page.evaluate("getComputedStyle(document.querySelector('#sortHost .tv-row:focus')).boxShadow")
    check("with several selected, the row with the focus has a ring", ring != "none", ring)
    page.close()

    # ---------- a fourth review ----------
    page = fresh(browser)
    page.evaluate("(" + SORT_TREE + ")({ multiple: true })")
    page.evaluate("sortHost.id = 'sortHost'; st.select('b169'); st.focus()")
    page.evaluate("st.select(['b49', 'zoe'])")
    check("select([ids]) keeps the focus in the tree", page.evaluate("document.activeElement.closest('#sortHost') !== null"))
    page.evaluate("st.select(['nope'])")
    check("select([ids]) with ids the tree does not have changes nothing", page.evaluate("st.selection().map(n => n.id)") == ["b49", "zoe"])
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ControlOrMeta+ArrowDown")
    page.keyboard.press("Space")
    check("plain Space adds the row with the focus (a row without a checkbox)", len(page.evaluate("st.selection()")) == 2, page.evaluate("st.selection().map(n => n.id)"))
    page.close()
    page = fresh(browser)
    page.add_style_tag(content=":root { --tauris-hover: rgb(40, 40, 50); --tauris-sel-inactive: rgb(60, 70, 90); }")
    page.evaluate("demo.files.select('atlas-desktop'); document.body.focus()")
    inactive = page.evaluate("getComputedStyle(document.querySelector('#files .tv-row[aria-selected=\"true\"]')).backgroundColor")
    check("the selection of a tree without the focus has its own shared colour, not hover's", inactive == "rgb(60, 70, 90)", inactive)
    page.close()

    # ---------- a fifth review ----------
    page = fresh(browser)
    page.evaluate("(" + SORT_TREE + ")({ sortable: true })")
    page.evaluate("st.collapse('short'); st.setData(sortData())")
    check("setData: a folder the person closed stays closed, though its node says expanded: true", page.evaluate("st.isExpanded('short')") is False)
    page.evaluate("st.setData(sortData().concat([{ id: 'new', label: 'New', expanded: true, children: [{ id: 'n1', label: 'One' }] }]))")
    check("a node that is new opens as its expanded says", page.evaluate("st.isExpanded('new')") is True)
    page.evaluate("st.expand('short'); sortHost.querySelector('.tv-sortable').focus()")
    before = page.evaluate("getComputedStyle(sortHost).getPropertyValue('--tv-c0')")
    page.keyboard.press("Alt+ArrowRight")
    after = page.evaluate("getComputedStyle(sortHost).getPropertyValue('--tv-c0')")
    check("Alt+→ on a header makes its column wider", before.strip() == "200px" and after.strip() == "210px", (before, after))
    page.keyboard.press("Alt+ArrowLeft")
    page.keyboard.press("Alt+ArrowLeft")
    check("Alt+← narrower", page.evaluate("getComputedStyle(sortHost).getPropertyValue('--tv-c0')").strip() == "190px")
    page.close()
    page = fresh(browser)
    page.evaluate("demo.settings.select('general.name')")
    page.locator("#settings .tv-hcell").first.focus()
    w0 = page.evaluate("getComputedStyle(document.getElementById('settings')).getPropertyValue('--tv-c0')").strip()
    page.keyboard.press("ArrowRight")
    w1 = page.evaluate("getComputedStyle(document.getElementById('settings')).getPropertyValue('--tv-c0')").strip()
    check("a tree that does not sort: → on a column's edge makes it wider, and says its width",
          int(w1[:-2]) == int(w0[:-2]) + 10 and page.get_attribute("#settings .tv-hcell", "aria-valuenow") == w1[:-2], (w0, w1))
    page.evaluate("window.resizes = []; demo.settings.on('resize', e => resizes.push([e.index, e.width])); 0")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowLeft")
    g = page.locator("#settings .tv-grip").first.bounding_box()
    page.mouse.move(g["x"] + g["width"] / 2, g["y"] + g["height"] / 2)
    page.mouse.down()
    page.mouse.move(g["x"] + 40, g["y"] + 5, steps=4)
    page.mouse.up()
    got = page.evaluate("resizes")
    check("the resize event tells the app each new width (keys and a drag), to keep it",
          len(got) == 3 and got[0][0] == 0 and got[2][1] == page.evaluate("demo.settings.widths()[0]"), got)
    page.evaluate("demo.settings.setWidths([180, null])")
    check("setWidths gives the widths back", page.evaluate("demo.settings.widths()[0]") == 180
          and page.evaluate("getComputedStyle(document.getElementById('settings')).getPropertyValue('--tv-c0')").strip() == "180px")
    page.evaluate("demo.settings.select('general.name'); document.body.focus()")
    inactive = page.evaluate("""(() => { const r = document.querySelector('#settings .tv-row[aria-selected="true"]');
      const probe = document.createElement('span'); probe.style.color = 'var(--tv-muted)'; r.append(probe);
      const same = getComputedStyle(probe).color === getComputedStyle(r).color; const c = getComputedStyle(probe).color; probe.remove();
      return same || c; })()""")
    check("secondary text on a selection without the focus is as readable as its label", inactive is True, inactive)
    page.evaluate("demo.settings.edit('appearance.fontSize')")
    page.keyboard.press("Escape")
    check("edit(id): Escape comes back to that row", page.evaluate("document.activeElement.dataset.key") == "appearance.fontSize")
    page.close()

    page = fresh(browser)
    page.evaluate("""() => { const host = document.createElement('div'); host.style.cssText = 'position:fixed;left:0;top:0;width:500px;height:200px;z-index:9';
      document.body.append(host); window.edits = [];
      window.mk = () => [{ id: 'a', label: 'Name', values: { v: 'old', s: 3 } }, { id: 'b', label: 'Other', values: { v: '', s: '' } },
        { id: 'c', label: 'Third', values: { v: '', s: 1 } }];
      window.et = TaurisTree.mount(host, { data: mk(), sortable: true, columns: [{ label: 'Setting', width: 200 },
        { label: 'Value', key: 'v', editable: true, width: 120 },
        { label: 'Score', key: 's', compare: (a, b) => a.values.s - b.values.s }] });
      et.on('change', e => edits.push([e.node.id, e.value])); window.etHost = host; return 0; }""")
    page.evaluate("et.edit('a', 'v')")
    check("an editor's name says which row and which column", page.get_attribute(".tv-editor", "aria-label") == "Name, Value")
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type("new")
    page.evaluate("et.setData(mk())")
    check("setData while editing: the edit is saved first (a change event), not lost", page.evaluate("edits") == [["a", "new"]], page.evaluate("edits"))
    order = lambda: page.evaluate("[...etHost.querySelectorAll('.tv-row')].sort((x, y) => parseFloat(x.style.top) - parseFloat(y.style.top)).map(r => r.dataset.key)")
    page.evaluate("et.sort('s')")
    up = order()
    page.evaluate("et.sort('s', false)")
    down = order()
    check("a column with its own compare puts empty values last both ways", up == ["c", "a", "b"] and down == ["a", "c", "b"], (up, down))
    page.close()

    # ---------- one look for every component ----------
    page = fresh(browser)
    page.add_style_tag(content=":root { --tauris-accent: rgb(1, 2, 3); --tauris-bg: rgb(4, 5, 6); --tauris-fg: rgb(7, 8, 9); --tauris-chrome: rgb(10, 11, 12); --tauris-sel-bg: rgb(13, 14, 15); --tauris-font: Georgia, serif; }")
    page.evaluate("demo.files.select(demo.files.selected()?.id ?? 'atlas-desktop'); demo.files.focus()")
    look = page.evaluate("""() => { const t = document.getElementById('files'), c = getComputedStyle(t);
      return [c.backgroundColor, c.color, c.fontFamily, getComputedStyle(t.querySelector('.tv-row[aria-selected="true"]')).backgroundColor,
              getComputedStyle(document.querySelector('#settings .tv-head')).backgroundColor]; }""")
    check("the tree follows the shared --tauris-* colours and font",
          look == ["rgb(4, 5, 6)", "rgb(7, 8, 9)", "Georgia, serif", "rgb(13, 14, 15)", "rgb(10, 11, 12)"], look)
    page.close()

    # ---------- the app chooses light or dark ----------
    for os_mode, app_mode, bg in [("dark", "light", "rgb(255, 255, 255)"), ("light", "dark", "rgb(22, 22, 25)")]:
        page = fresh(browser, os_mode)
        page.evaluate(f"document.documentElement.dataset.taurisTheme = '{app_mode}'")
        bg_now = page.evaluate("getComputedStyle(document.getElementById('files')).backgroundColor")
        check(f"system {os_mode}, app {app_mode} (data-tauris-theme): the tree follows the app", bg_now == bg, bg_now)
        page.close()

    # ---------- API ----------
    page = fresh(browser)
    page.evaluate("demo.files.collapseAll()")
    check("collapseAll closes every folder", page.locator("#files .tv-row").count() == 1)
    page.evaluate("demo.files.expandAll()")
    check("expandAll opens every folder", page.locator('#files .tv-row[aria-expanded="false"]').count() == 0)
    page.evaluate("demo.files.collapse('atlas-desktop/src'); demo.files.expand('atlas-desktop/src')")
    check("expand and collapse by id", page.evaluate("demo.files.isExpanded('atlas-desktop/src')") is True)
    page.evaluate("demo.files.select('atlas-desktop/docs/architecture.md')")
    page.evaluate("demo.files.setData(JSON.parse(JSON.stringify(demo.files.get('atlas-desktop') ? [demo.files.get('atlas-desktop')] : [])))")
    check("setData keeps the selection and open folders", selected(page, "files") == "atlas-desktop/docs/architecture.md" and expanded(page, "atlas-desktop/.github") == "true")
    check("selected() returns the node", page.evaluate("demo.files.selected().label") == "architecture.md")
    try:
        page.evaluate("TaurisTree.mount(document.getElementById('files'))")
        check("a second mount on one element is refused", False)
    except Exception:
        check("a second mount on one element is refused", True)
    page.evaluate("demo.files.destroy()")
    check("destroy removes the tree", page.evaluate("document.getElementById('files').children.length") == 0
          and page.evaluate("document.getElementById('files').className") == "panel-tree")
    page.evaluate("window.again = TaurisTree.mount(document.getElementById('files'), { data: [{ id: 1, label: 'Inbox' }, { id: 2, label: 'Archive' }] }); again.on('select', e => window.__picked = e.node.label); 0")  # 0: evaluate would call the returned unsubscribe function
    page.evaluate("again.focus()")
    page.keyboard.press("ArrowDown")
    check("mount after destroy works, with number ids", page.evaluate("window.__picked") == "Archive")
    page.close()

    # ---------- light mode ----------
    page = fresh(browser, "light")
    bg = page.evaluate("getComputedStyle(document.getElementById('files')).backgroundColor")
    check("the default look follows light mode", bg == "rgb(255, 255, 255)", bg)
    page.close()

    browser.close()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
