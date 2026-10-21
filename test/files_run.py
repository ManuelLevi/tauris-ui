"""Tests the files component (web/files.js, web/files.css) in a headless browser.

Run:  python test/files_run.py [screenshot-folder]
Needs Python playwright and Google Chrome. Nothing touches the screen.
Exits non-zero when a check fails. With a folder, it saves screenshots at 2x:
the demo in light and dark, files hovering, adding, and the delete question.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
WEB = HERE.parent / "web"
DEMO = HERE / "files_demo.html"
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if SHOTS:
    SHOTS.mkdir(parents=True, exist_ok=True)
SIZE = {"width": 1000, "height": 560}
failures = []

# The colours of files.css, as computed styles report them.
ACCENT, WHITE, DIM, FG = "rgb(38, 117, 191)", "rgb(255, 255, 255)", "rgb(102, 106, 119)", "rgb(30, 31, 34)"
DARK_BG, DARK_SEL, DARK_FG = "rgb(47, 50, 52)", "rgb(47, 101, 202)", "rgb(223, 225, 229)"
PDF_RED, DOC_BLUE, DANGER = "rgb(180, 35, 42)", "rgb(37, 96, 168)", "rgb(209, 69, 59)"

# A starter template's plain rules (create-tauri-app and Vite have these).
TEMPLATE_CSS = """
  input, button { border-radius: 8px; border: 1px solid transparent; padding: 0.6em 1.2em; font-size: 1em;
    font-weight: 500; font-family: inherit; color: #0f0f0f; background-color: #ffffff; box-shadow: 0 2px 2px rgba(0, 0, 0, 0.2);
    transition: border-color 0.25s; outline: none; }
  button { cursor: pointer; }
  button:hover { border-color: #396cd8; }
  input:focus { border-color: #396cd8; }
  :root { font-family: Inter, Avenir, Helvetica, Arial, sans-serif; font-size: 16px; line-height: 24px; font-weight: 400; }
"""

# A small app built with DOM calls only, for the pages that load the library
# as the plugin delivers it (the strict policy page has no inline script).
BUILD = """host => {
  host.style.height = "300px";
  window.box = document.createElement("div");
  box.style.height = "100%";
  host.append(box);
  window.store = [
    { id: 1, name: "Board deck.pdf", size: 2516582, added: "2026-10-20", by: "sophie" },
    { id: 2, name: "Plan.docx", size: 120000, added: "2026-10-19", by: "manuel" },
  ];
  window.files = TaurisFiles.mount(box, { title: "Health", color: "#1baf7a", files: store,
    onOpen: () => {}, onRename: () => {}, onDelete: () => {},
    onAdd: async paths => paths.map((p, i) => ({ id: 10 + i, name: p.split("/").pop(), size: 1000 })) });
  return 0;
}"""

SIGNATURE = """() => {
  const props = ["padding-top", "padding-left", "border-top-width", "border-top-color", "border-radius", "box-shadow",
    "background-color", "color", "font-size", "font-weight", "height", "width", "line-height", "outline-style"];
  const sig = s => { const c = getComputedStyle(document.querySelector(s)); return Object.fromEntries(props.map(p => [p, c.getPropertyValue(p)])); };
  return Object.fromEntries([".tf-add", ".tf-q", ".tf-sort", ".tf-file .tf-cell", ".tf-kind", ".tf-title"].map(s => [s, sig(s)]));
}"""


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail != "" and not ok else ""))
    if not ok:
        failures.append(name)


def library_script():
    """files.js and menus.js as the plugin delivers them: with their stylesheets inside."""
    files = (WEB / "files.js").read_text().replace('"__TAURIS_FILES_CSS__"', json.dumps((WEB / "files.css").read_text()))
    menus = (WEB / "menus.js").read_text().replace('"__TAURIS_MENUS_CSS__"', json.dumps((WEB / "menus.css").read_text()))
    return files + "\n;\n" + menus


def fresh(browser, scheme="light", reduced_motion="no-preference"):
    page = browser.new_page(viewport=SIZE, device_scale_factor=2, color_scheme=scheme, locale="en-GB", reduced_motion=reduced_motion)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.goto(DEMO.as_uri())
    page.wait_for_selector(".tf-file")
    page.evaluate("window.uploadMs = 300")
    return page


def css(page, selector, prop, pseudo=None):
    return page.evaluate("([s, p, ps]) => getComputedStyle(document.querySelector(s), ps).getPropertyValue(p)", [selector, prop, pseudo])


def rect(page, selector):
    return page.evaluate("""s => { const r = document.querySelector(s).getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height }; }""", selector)


def names(page):
    return page.evaluate("[...document.querySelectorAll('.tf-file .tf-c-name')].map(c => c.textContent)")


def row(page, name):
    return page.locator(".tf-file", has_text=name)


def selected(page):
    return page.evaluate("demo.files.selected()?.name ?? null")


def message(page):
    return page.inner_text("#msg")


def idle(page):
    page.wait_for_function("document.querySelector('.tf-busy').hidden")


def shot(page, name):
    if SHOTS:
        page.screenshot(path=str(SHOTS / f"files_{name}.png"), animations="disabled")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")

    # ---------- the look ----------
    page = fresh(browser)
    shot(page, "light")
    check("header: the place, then Documents · 8 files · 187.6 MB",
          page.inner_text(".tf-title") == "Northwind Launch" and page.inner_text(".tf-sub") == "Documents · 8 files · 187.6 MB",
          (page.inner_text(".tf-title"), page.inner_text(".tf-sub")))
    check("header: a 15px bold heading after a colour chip",
          css(page, ".tf-title", "font-size") == "15px" and css(page, ".tf-title", "font-weight") == "600"
          and css(page, ".tf-chip", "background-color") == "rgb(42, 120, 214)" and rect(page, ".tf-chip")["w"] == 10)
    check("header: Add files… is a 22px button with an icon, the search field 26px",
          rect(page, ".tf-add")["h"] == 22 and page.inner_text(".tf-add") == "Add files…" and page.locator(".tf-add svg").count() == 1
          and rect(page, ".tf-search")["h"] == 26 and page.get_attribute(".tf-q", "placeholder") == "Search files")
    heads = page.evaluate("[...document.querySelectorAll('.tf-th')].map(t => [t.textContent, t.getBoundingClientRect().height])")
    check("columns: type, Name ▲, Size, Added, By, actions; the header row 23px",
          [h[0] for h in heads] == ["", "Name▲", "Size", "Added", "By", ""] and {h[1] for h in heads} == {23}, heads)
    heights = page.evaluate("[...document.querySelectorAll('.tf-file')].map(r => r.getBoundingClientRect().height)")
    check("rows: 25px, 12.5px text", set(heights) == {25} and css(page, ".tf-file .tf-cell", "font-size") == "12.5px", heights)
    check("sorted by name at first", names(page)[:3] == ["Brand assets.zip", "Budget 2027.xlsx", "Contract — signed.pdf"], names(page))
    kinds = page.evaluate("[...document.querySelectorAll('.tf-kind')].map(k => k.textContent)")
    check("badges: ZIP XLS PDF AUD TXT PPT IMG VID", kinds == ["ZIP", "XLS", "PDF", "AUD", "TXT", "PPT", "IMG", "VID"], kinds)
    badge = rect(page, ".tf-kind")
    check("badges: 30 x 18, monospace 9.5px", (badge["w"], badge["h"]) == (30, 18) and css(page, ".tf-kind", "font-size") == "9.5px")
    pdf = ".tf-file:nth-child(3) .tf-kind"
    check("badges: PDF in red with a light red border",
          css(page, pdf, "color") == PDF_RED and css(page, pdf, "border-top-color") == "color(srgb 0.705882 0.137255 0.164706 / 0.35)",
          (css(page, pdf, "color"), css(page, pdf, "border-top-color")))
    cells = page.evaluate("[...document.querySelector('.tf-file:nth-child(6)').cells || document.querySelector('.tf-file:nth-child(6)').children].map(c => c.textContent)")
    check("a row: badge, name, size, short date, who", cells[:5] == ["PPT", "Launch plan.pptx", "4.5 MB", "20 Oct", "sophie"], cells)
    sizes = page.evaluate("[...document.querySelectorAll('.tf-c-size.tf-cell')].map(c => c.textContent)")
    check("sizes in KB and MB", sizes == ["22 MB", "86 KB", "402 KB", "12.4 MB", "6 KB", "4.5 MB", "3.2 MB", "145 MB"], sizes)
    check("a date from another year shows the year", page.inner_text(".tf-file:nth-child(8) .tf-c-added") == "4 Nov 25")
    check("the date cell's tip has the full date", "2025" in (page.get_attribute(".tf-file:nth-child(8) .tf-c-added", "title") or ""))
    long_name = ".tf-file:nth-child(4) .tf-c-name"
    page.set_viewport_size({"width": 700, "height": 560})
    check("a long name ends in … and keeps the other columns",
          page.evaluate(f"(() => {{ const n = document.querySelector('{long_name} .tf-name'); return n.scrollWidth > n.clientWidth; }})()")
          and css(page, long_name + " .tf-name", "text-overflow") == "ellipsis" and page.get_attribute(long_name, "title").startswith("Customer interview")
          and rect(page, ".tf-file:nth-child(4) .tf-c-by")["x"] + rect(page, ".tf-file:nth-child(4) .tf-c-by")["w"] <= 700)
    page.set_viewport_size(SIZE)
    check("sizes right-aligned in tabular figures",
          css(page, ".tf-cell.tf-c-size", "text-align") == "right" and css(page, ".tf-cell.tf-c-size", "font-variant-numeric") == "tabular-nums")
    check("the row's buttons are hidden until the row is pointed at", css(page, ".tf-file:nth-child(2) .tf-acts", "opacity") == "0")
    page.hover(".tf-file:nth-child(2) .tf-c-name")
    page.wait_for_timeout(150)
    check("pointing at a row tints it and shows Open, Save a copy…, Rename, Delete",
          css(page, ".tf-file:nth-child(2) .tf-acts", "opacity") == "1"
          and css(page, ".tf-file:nth-child(2) .tf-cell", "background-color") == "rgb(241, 245, 251)"
          and page.evaluate("[...document.querySelectorAll('.tf-file:nth-child(2) .tf-ib')].map(b => b.title)") == ["Open", "Save a copy…", "Rename", "Delete"])
    page.click(".tf-file:nth-child(3) .tf-c-name")
    page.wait_for_timeout(150)
    sel = ".tf-file:nth-child(3)"
    check("a click selects: the row in the accent colour, white text, buttons shown",
          css(page, sel + " .tf-cell", "background-color") == ACCENT and css(page, sel + " .tf-cell", "color") == WHITE
          and css(page, sel + " .tf-kind", "color") == WHITE and css(page, sel + " .tf-acts", "opacity") == "1"
          and page.get_attribute(sel, "aria-selected") == "true" and selected(page) == "Contract — signed.pdf")
    check("the list is a grid that names the selected row",
          page.get_attribute(".tf-list", "role") == "grid" and page.get_attribute(".tf-list", "aria-activedescendant") == page.get_attribute(sel, "id")
          and page.evaluate("document.activeElement.classList.contains('tf-list')"))
    page.close()

    page = fresh(browser, "dark")
    page.click(".tf-file:nth-child(2) .tf-c-name")
    page.mouse.move(5, 540)
    page.wait_for_timeout(200)
    shot(page, "dark")
    check("dark: the list, the text and the selection follow the system",
          css(page, ".tf-panel", "background-color") == DARK_BG and css(page, ".tf-title", "color") == DARK_FG
          and css(page, ".tf-file:nth-child(2) .tf-cell", "background-color") == DARK_SEL
          and css(page, ".tf-file:nth-child(3) .tf-kind", "color") == "rgb(240, 122, 114)")
    page.evaluate("__emit('tauri://drag-enter', { paths: ['/a.pdf'] })")
    check("dark: accent text is the lighter ink, readable on the list (about 5:1, not 2.5:1)",
          css(page, ".tf-drop-title", "color") == "rgb(106, 166, 224)" and css(page, ".tf-arrow", "color") == "rgb(106, 166, 224)")
    page.close()

    # ---------- sorting and searching ----------
    page = fresh(browser)
    page.click(".tf-th.tf-c-size .tf-sort")
    check("Size: the biggest first, ▼", names(page)[0] == "Site visit.mov" and names(page)[-1] == "Kickoff notes.md"
          and page.get_attribute(".tf-th.tf-c-size", "aria-sort") == "descending" and page.text_content(".tf-th.tf-c-size") == "Size▼")
    page.click(".tf-th.tf-c-size .tf-sort")
    check("Size again: the smallest first, ▲", names(page)[0] == "Kickoff notes.md" and page.get_attribute(".tf-th.tf-c-size", "aria-sort") == "ascending")
    check("only the sorted column shows an arrow", page.get_attribute(".tf-th.tf-c-name", "aria-sort") == "none" and "▲" not in page.text_content(".tf-th.tf-c-name"))
    page.click(".tf-th.tf-c-added .tf-sort")
    check("Added: the newest first", names(page)[:2] == ["Launch plan.pptx", "Moodboard.heic"] and names(page)[-1] == "Site visit.mov", names(page))
    page.click(".tf-th.tf-c-by .tf-sort")
    by = page.evaluate("[...document.querySelectorAll('.tf-cell.tf-c-by')].map(c => c.textContent)")
    check("By: A to Z, then by name", by == sorted(by) and names(page)[0] == "Kickoff notes.md", (by, names(page)))
    page.focus(".tf-th.tf-c-name .tf-sort")
    page.keyboard.press("Enter")
    check("a header sorts from the keyboard and keeps the focus",
          names(page)[0] == "Brand assets.zip" and page.evaluate("document.activeElement.closest('.tf-th')?.dataset.col") == "name")
    page.fill(".tf-q", "PL")
    check("search: only the names that contain it, any case", names(page) == ["Launch plan.pptx"], names(page))
    check("search: the count still tells the whole place", page.inner_text(".tf-sub") == "Documents · 8 files · 187.6 MB")
    page.fill(".tf-q", "zzz")
    check("search: no match says so", page.inner_text(".tf-nomatch") == "No files match “zzz”." and page.locator(".tf-file").count() == 0)
    page.keyboard.press("Escape")
    check("search: Escape empties it", page.input_value(".tf-q") == "" and page.locator(".tf-file").count() == 8 and page.is_hidden(".tf-nomatch"))
    page.fill(".tf-q", "e")
    page.keyboard.press("ArrowDown")
    check("search: Down goes to the list and selects the first match",
          page.evaluate("document.activeElement.classList.contains('tf-list')") and selected(page) == names(page)[0])
    page.close()

    # ---------- columns keep their widths ----------
    page = fresh(browser)
    widths = """[...document.querySelectorAll('#files .tf-th')].map(t => Math.round(t.getBoundingClientRect().width))"""
    full = page.evaluate(widths)
    page.fill(".tf-q", "budget")
    one = page.evaluate(widths)
    page.fill(".tf-q", "zzz")
    none = page.evaluate(widths)
    check("the columns keep their widths with every row, one row, or none", full == one == none, (full, one, none))
    list_w = page.evaluate("Math.round(document.querySelector('#files .tf-list').clientWidth)")
    check("kind 44, size 84, added 88, by 110, the four buttons 110; the name takes the rest",
          full[0] == 44 and full[2:] == [84, 88, 110, 110] and full[1] == list_w - sum(full) + full[1], (full, list_w))
    page.fill(".tf-q", "")
    page.evaluate("demo.files.update({ onRename: null, onSaveAs: null })")
    check("fewer buttons, a narrower column", page.evaluate(widths)[-1] == 58, page.evaluate(widths))
    page.evaluate("document.getElementById('files').style.setProperty('--tf-by-w', '150px')")
    check("an app can set a column's width", page.evaluate(widths)[4] == 150)
    page.close()

    # ---------- the row menu's hooks ----------
    page = fresh(browser)
    page.evaluate("""window.ev = []; demo.files.update({ onMenuOpen: i => ev.push(['open', i.label, i.how]),
      onMenuClose: i => ev.push(['close', i.label, i.chosen]) })""")
    page.click(".tf-file:nth-child(2) .tf-c-name", button="right")
    page.keyboard.press("Escape")
    page.keyboard.press("Shift+F10")
    page.keyboard.press("Enter")
    page.wait_for_timeout(150)
    check("the row's menu tells onMenuOpen and onMenuClose, as the bar does",
          page.evaluate("ev") == [["open", "Budget 2027.xlsx", "mouse"], ["close", "Budget 2027.xlsx", False],
                                  ["open", "Budget 2027.xlsx", "keyboard"], ["close", "Budget 2027.xlsx", True]], page.evaluate("ev"))
    page.close()

    # ---------- keyboard ----------
    page = fresh(browser)
    page.focus(".tf-list")
    page.keyboard.press("ArrowDown")
    check("Down selects the first file", selected(page) == "Brand assets.zip")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    check("Down moves", selected(page) == "Contract — signed.pdf")
    page.keyboard.press("ArrowUp")
    check("Up moves back", selected(page) == "Budget 2027.xlsx")
    page.keyboard.press("End")
    check("End: the last", selected(page) == "Site visit.mov")
    page.keyboard.press("Home")
    check("Home: the first", selected(page) == "Brand assets.zip")
    page.keyboard.press("k")
    check("typing a letter jumps to the next name starting with it", selected(page) == "Kickoff notes.md")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    check("Enter opens, and the app's status line says so", page.evaluate("window.opened") == "Kickoff notes.md" and message(page) == "Opened Kickoff notes.md.")
    page.keyboard.press("Delete")
    check("Delete asks first, with the file's name, the red button focused",
          page.is_visible(".tf-ask") and page.inner_text(".tf-ask-text") == "Delete “Kickoff notes.md”? This cannot be undone."
          and page.evaluate("document.activeElement.classList.contains('tf-danger')") and css(page, ".tf-ask .tf-danger", "background-color") == DANGER)
    page.keyboard.press("Tab")
    check("Tab stays inside the question", page.evaluate("document.activeElement.textContent") == "Cancel")
    page.keyboard.press("Escape")
    check("Escape keeps the file and gives the focus back to the list",
          page.is_hidden(".tf-veil") and len(names(page)) == 8 and page.evaluate("document.activeElement.classList.contains('tf-list')"))
    page.keyboard.press("Meta+Backspace")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    check("⌘⌫ asks too; Enter deletes; the next file is selected",
          "Kickoff notes.md" not in names(page) and selected(page) == "Launch plan.pptx" and message(page) == "Deleted Kickoff notes.md."
          and page.inner_text(".tf-sub").startswith("Documents · 7 files"))
    check("after deleting, the list keeps the focus", page.evaluate("document.activeElement.classList.contains('tf-list')"))
    page.keyboard.press("PageDown")
    check("PageDown moves a page (to the end of a short list)", selected(page) == "Site visit.mov")
    page.close()

    # ---------- the row's buttons, double-click, the row menu ----------
    page = fresh(browser)
    page.dblclick(".tf-file:nth-child(2) .tf-c-name")
    page.wait_for_timeout(150)
    check("a double click opens", page.evaluate("window.opened") == "Budget 2027.xlsx")
    page.hover(".tf-file:nth-child(1)")
    page.click(".tf-file:nth-child(1) .tf-ib[data-act='saveAs']")
    page.wait_for_timeout(150)
    check("Save a copy…: the save dialog with the name filled in",
          page.evaluate("window.savedTo") == "/Users/m/Downloads/Brand assets.zip" and message(page) == "Saved a copy of Brand assets.zip."
          and page.evaluate("__calls.at(-1)") == ["plugin:tauris-ui|save_dialog", {"title": "Save a copy of Brand assets.zip", "name": "Brand assets.zip"}])
    page.evaluate("window.__cancelSave = true; document.getElementById('msg').textContent = ''")
    page.click(".tf-file:nth-child(1) .tf-ib[data-act='saveAs']")
    page.wait_for_timeout(150)
    check("Save a copy…: cancelling says nothing", message(page) == "")
    page.click(".tf-file:nth-child(5) .tf-c-name", button="right")
    page.wait_for_selector(".tmn-menu")
    items = page.evaluate("[...document.querySelectorAll('.tmn-menu .tmn-item, .tmn-menu .tmn-sep')].map(i => i.classList.contains('tmn-sep') ? '-' : i.querySelector('.tmn-label').textContent)")
    check("a right click selects the row and opens its menu", items == ["Open", "Save a copy…", "Rename", "-", "Delete"] and selected(page) == "Kickoff notes.md", items)
    page.click(".tmn-item:has-text('Rename')")
    check("Rename from the menu: the name becomes a field", page.locator(".tf-rename").count() == 1)
    page.keyboard.press("Escape")
    page.focus(".tf-list")
    page.keyboard.press("Shift+F10")
    check("Shift+F10 opens the row menu from the keyboard, its first item chosen",
          page.is_visible(".tmn-menu") and page.evaluate("document.activeElement.textContent").startswith("Open"))
    page.keyboard.press("Escape")
    check("Escape closes it, and the focus is back on the list",
          page.locator(".tmn-menu").count() == 0 and page.evaluate("document.activeElement.classList.contains('tf-list')"))
    page.close()

    # ---------- renaming ----------
    page = fresh(browser)
    page.click(".tf-file:nth-child(2) .tf-c-name")
    page.keyboard.press("F2")
    sel_range = page.evaluate("(() => { const i = document.querySelector('.tf-rename'); return [i.value, i.selectionStart, i.selectionEnd, document.activeElement === i]; })()")
    check("F2: the name becomes a field, its name without the extension selected", sel_range == ["Budget 2027.xlsx", 0, 11, True], sel_range)
    check("the field sits in the row: the row keeps its height", rect(page, ".tf-file:nth-child(2)")["h"] == 25)
    page.keyboard.type("Budget 2028")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    check("Enter renames", "Budget 2028.xlsx" in names(page) and page.locator(".tf-rename").count() == 0
          and selected(page) == "Budget 2028.xlsx" and message(page) == "Renamed Budget 2027.xlsx to Budget 2028.xlsx.")
    check("and gives the focus back to the list", page.evaluate("document.activeElement.classList.contains('tf-list')"))
    page.keyboard.press("F2")
    page.keyboard.press("Escape")
    check("Escape leaves the name as it was", "Budget 2028.xlsx" in names(page) and page.locator(".tf-rename").count() == 0)
    page.keyboard.press("F2")
    page.fill(".tf-rename", "  ")
    page.keyboard.press("Enter")
    check("an empty name is refused, and the field stays", message(page) == "Give the file a name." and page.locator(".tf-rename").count() == 1)
    page.fill(".tf-rename", "Brand assets.zip")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    check("a name the app refuses: its sentence, and the field stays",
          message(page) == "There is already a file called Brand assets.zip." and page.locator(".tf-rename").count() == 1
          and page.evaluate("document.activeElement.classList.contains('tf-rename')"))
    page.fill(".tf-rename", "Forecast.xlsx")
    page.evaluate("demo.store.push({ id: 99, name: 'Arrived meanwhile.txt', size: 10 }); demo.files.setFiles(demo.store.slice())")
    check("a new list while renaming waits", page.locator(".tf-rename").count() == 1 and "Arrived meanwhile.txt" not in names(page))
    page.click(".tf-title")
    page.wait_for_timeout(200)
    check("clicking away renames, then the waiting list shows",
          "Forecast.xlsx" in names(page) and "Arrived meanwhile.txt" in names(page) and page.locator(".tf-rename").count() == 0)
    page.close()

    # ---------- adding ----------
    page = fresh(browser)
    page.evaluate("window.uploadMs = 700")
    page.click(".tf-add")
    page.wait_for_selector(".tf-busy:not([hidden])")
    check("Add files…: the system's picker, titled with the place",
          page.evaluate("__calls[0]") == ["plugin:tauris-ui|pick_files", {"title": "Add files to Northwind Launch", "multiple": True}])
    check("while adding: a card with a 20-segment bar, and Add files… is off",
          page.inner_text(".tf-busy") == "Adding 2 files…" and page.locator(".tf-seg i").count() == 20
          and page.get_attribute(".tf-add", "aria-disabled") == "true"
          and css(page, ".tf-seg i:nth-child(5)", "animation-delay") == "0.24s")
    shot(page, "adding")
    idle(page)
    check("added: in the list, the first selected, flashing, and said",
          "Q3 board deck.pdf" in names(page) and "Studio floor plan.png" in names(page) and selected(page) == "Q3 board deck.pdf"
          and page.locator(".tf-file.tf-fresh").count() == 2 and message(page) == "Added 2 files to Northwind Launch."
          and page.inner_text(".tf-sub") == "Documents · 10 files · 190.4 MB")
    check("the flash is a short tint", css(page, ".tf-file.tf-fresh .tf-cell", "animation-name") == "tf-flash")
    page.wait_for_timeout(1500)
    check("the flash ends", page.locator(".tf-fresh").count() == 0)
    page.evaluate("window.__pick = []")
    page.click(".tf-add")
    page.wait_for_timeout(200)
    check("cancelling the picker adds nothing", page.locator(".tf-file").count() == 10 and page.is_hidden(".tf-busy"))
    page.close()

    # ---------- dropping ----------
    page = fresh(browser)
    page.evaluate("__emit('tauri://drag-enter', { paths: ['/Users/m/Term sheet.docx'], position: { x: 600, y: 600 } })")
    check("files over the window: a dashed zone says where they go",
          page.is_visible(".tf-drop") and page.inner_text(".tf-drop-title") == "Drop to add to Northwind Launch"
          and page.inner_text(".tf-drop-hint") == "Up to 50 MB per file")
    ring = (css(page, ".tf-drop", "outline-style"), css(page, ".tf-drop", "outline-width"), css(page, ".tf-drop", "outline-color"),
            css(page, ".tf-drop", "border-radius"), rect(page, ".tf-drop") == rect(page, ".tf-list"))
    check("the zone is a solid 2px ring in the accent round the whole list", ring == ("solid", "2px", ACCENT, "2px", True), ring)
    shot(page, "drop")
    page.evaluate("__emit('tauri://drag-leave', null)")
    check("they leave: the zone goes", page.is_hidden(".tf-drop"))
    page.evaluate("__emit('tauri://drag-enter', { paths: [], position: { x: 300, y: 300 } })")
    check("something that is not files shows no zone", page.is_hidden(".tf-drop"))
    page.evaluate("""__emit('tauri://drag-enter', { paths: ['/Users/m/Term sheet.docx'], position: { x: 300, y: 300 } });
      __emit('tauri://drag-over', { position: { x: 310, y: 300 } });
      __emit('tauri://drag-drop', { paths: ['/Users/m/Term sheet.docx'], position: { x: 310, y: 300 } })""")
    check("a drop: the zone goes and the busy card says what is coming", page.is_hidden(".tf-drop") and page.inner_text(".tf-busy") == "Adding 1 file…")
    idle(page)
    check("the dropped file is added, a DOC", row(page, "Term sheet.docx").count() == 1
          and row(page, "Term sheet.docx").locator(".tf-kind").inner_text() == "DOC" and message(page) == "Added Term sheet.docx to Northwind Launch.")
    page.evaluate("__emit('tauri://drag-drop', { paths: ['/Users/m/Contracts'], position: { x: 300, y: 300 } })")
    idle(page)
    page.wait_for_timeout(100)
    check("a folder: refused with the app's sentence", message(page) == "Contracts is a folder. Add files, not folders."
          and page.evaluate("document.getElementById('status').dataset.kind") == "error")
    page.evaluate("""__emit('tauri://drag-drop', { paths: ['/Users/m/One.pdf'], position: { x: 300, y: 300 } });
      __emit('tauri://drag-drop', { paths: ['/Users/m/Two.pdf'], position: { x: 300, y: 300 } })""")
    page.wait_for_timeout(450)
    one_only = row(page, "One.pdf").count() == 1 and row(page, "Two.pdf").count() == 0
    page.wait_for_timeout(500)
    check("two drops: one after the other", one_only and row(page, "Two.pdf").count() == 1)
    page.evaluate("demo.files.update({ dropArea: 'element' })")
    page.evaluate("__emit('tauri://drag-drop', { paths: ['/Users/m/Outside.pdf'], position: { x: 40, y: 20 } })")
    page.evaluate("__emit('tauri://drag-drop', { paths: ['/Users/m/Inside.pdf'], position: { x: 800, y: 600 } })")
    page.wait_for_timeout(500)
    check("dropArea element: only a drop over the component adds (positions in physical pixels)",
          row(page, "Outside.pdf").count() == 0 and row(page, "Inside.pdf").count() == 1)
    page.evaluate("document.getElementById('work').style.display = 'none'")
    page.evaluate("demo.files.update({ dropArea: 'window' }); __emit('tauri://drag-enter', { paths: ['/a.pdf'] })")
    check("a hidden component (another tab's) ignores drops", page.evaluate("document.querySelector('.tf-drop').hidden"))
    page.close()

    # ---------- empty, and another place ----------
    page = fresh(browser)
    page.click("#tb-docs")
    page.click(".tmn-item:has-text('Health')")
    check("an empty place: what it is for, and Add files…",
          page.inner_text(".tf-empty-title") == "No files in Health yet" and page.inner_text(".tf-empty-text").startswith("Shared files for this project")
          and page.inner_text(".tf-empty .tf-primary") == "Add files…" and css(page, ".tf-empty .tf-primary", "background-color") == ACCENT
          and page.is_hidden(".tf-list") and page.is_hidden(".tf-search") and page.inner_text(".tf-sub") == "Documents · 0 files")
    empty_head = rect(page, ".tf-head")["h"]
    page.click(".tf-empty .tf-primary")
    page.wait_for_selector(".tf-file")
    check("the header keeps its height when the search field appears", empty_head == rect(page, ".tf-head")["h"] == 26, (empty_head, rect(page, ".tf-head")["h"]))
    idle(page)
    check("adding from the empty state", page.locator(".tf-file").count() == 2 and message(page) == "Added 2 files to Health.")
    page.close()

    # ---------- options ----------
    page = fresh(browser)
    own = page.evaluate("""() => {
      const box = document.createElement('div'); box.style.height = '220px'; document.body.append(box);
      window.small = TaurisFiles.mount(box, { title: 'Inbox', files: [{ id: 'a', name: 'a.pdf', size: 1 }], columns: ['kind', 'name', 'size'],
        confirmDelete: false, labels: { add: 'Ajouter…' }, onOpen: () => {}, onAdd: () => [], onDelete: async () => { throw 'Not allowed.'; } });
      return [[...box.querySelectorAll('.tf-th')].map(t => t.className.replace('tf-th ', '')), [...box.querySelectorAll('.tf-file .tf-ib')].map(b => b.title),
        box.querySelector('.tf-add').textContent, box.querySelector('.tf-sub').textContent];
    }""")
    check("columns and actions: only the ones asked for", own[0] == ["tf-c-kind", "tf-c-name", "tf-c-size", "tf-c-acts"] and own[1] == ["Open", "Delete"], own)
    check("labels: any word can change; one file is \"1 file\"", own[2] == "Ajouter…" and own[3] == "1 file · 1 KB", own)
    edges = page.evaluate("""() => { const r = e => e.getBoundingClientRect(); const demoRoot = document.getElementById('files');
      const box = document.querySelectorAll('.tf')[1];
      const before = [r(demoRoot).bottom - r(demoRoot.querySelector('.tf-panel')).bottom];
      small.update({ header: false, onMessage: () => {} });
      return before.concat([r(box).top - r(box.querySelector('.tf-panel')).top, r(box).bottom - r(box.querySelector('.tf-panel')).bottom]); }""")
    check("with onMessage the list reaches the bottom; without the header it starts at the top (no empty gaps)", edges == [0, 0, 0], edges)
    page.evaluate("small.update({ header: true, onMessage: null })")
    page.evaluate("small.remove('a')")
    page.wait_for_timeout(100)
    check("without onMessage: the component's own line shows the app's refusal, in red",
          page.evaluate("document.querySelectorAll('.tf-status')[1].textContent") == "Not allowed."
          and page.evaluate("getComputedStyle(document.querySelectorAll('.tf-status')[1]).color") == DANGER
          and page.evaluate("document.querySelectorAll('.tf-veil')[1].hidden"))
    check("confirmDelete false: no question", page.evaluate("document.querySelectorAll('.tf-veil')[1].hidden"))
    page.evaluate("small.update({ confirmDelete: f => `Remove ${f.name} from the inbox?` }); void small.remove('a')")
    check("confirmDelete as a function: its own question", page.evaluate("document.querySelectorAll('.tf-ask-text')[1].textContent") == "Remove a.pdf from the inbox?")
    page.keyboard.press("Escape")
    plain = page.evaluate("""() => { const box = document.createElement('div'); document.body.append(box);
      const v = TaurisFiles.mount(box, { files: [{ id: 1, name: 'x.txt' }] });
      const r = [box.querySelector('.tf-add').hidden, box.querySelectorAll('.tf-c-acts').length, box.querySelector('.tf-title').textContent];
      v.destroy(); return r.concat([box.children.length, box.className]); }""")
    check("no onAdd: no Add button; no actions: no actions column; destroy empties it",
          plain == [True, 0, "Files", 0, ""], plain)
    same = page.evaluate("""() => { const first = document.querySelector('.tf-file'); demo.files.setFiles(demo.store.map(f => ({ ...f })));
      return document.querySelector('.tf-file') === first; }""")
    check("the same list again is not drawn again (a flash keeps going)", same)
    helpers = page.evaluate("""[TaurisFiles.kindOf({ name: 'a.KEY' }), TaurisFiles.kindOf({ name: 'scan', type: 'application/pdf' }),
      TaurisFiles.kindOf({ name: 'x.sketch' }), TaurisFiles.kindOf({ name: 'README' }), TaurisFiles.kindOf({ name: 'a.csv' }),
      TaurisFiles.formatSize(0), TaurisFiles.formatSize(1), TaurisFiles.formatSize(1047552), TaurisFiles.formatSize(1610612736)]""")
    check("kindOf and formatSize", helpers == ["PPT", "PDF", "SKE", "FILE", "XLS", "0 KB", "1 KB", "1,023 KB", "1.5 GB"], helpers)
    try:
        page.evaluate("TaurisFiles.mount(document.getElementById('files'))")
        check("a second mount on one element is refused", False)
    except Exception:
        check("a second mount on one element is refused", True)
    page.evaluate("demo.files.destroy(); __emit('tauri://drag-drop', { paths: ['/x/after.pdf'] })")
    page.wait_for_timeout(100)
    check("after destroy() drops are not heard", page.locator("#files .tf-file").count() == 0 and "after.pdf" not in json.dumps(page.evaluate("demo.store")))
    page.close()

    # ---------- edge cases: focus, races, destroy ----------
    page = fresh(browser)
    page.click(".tf-file:nth-child(4) .tf-c-name")
    page.keyboard.press("Shift+F10")
    page.keyboard.press("End")
    page.keyboard.press("Space")
    page.wait_for_timeout(100)
    check("Space on Delete in the row menu asks first (the same Space does not answer the question)",
          page.is_visible(".tf-ask") and len(names(page)) == 8)
    page.click(".tf-q")
    check("going to another field answers the question with no, and the focus stays there",
          page.is_hidden(".tf-veil") and len(names(page)) == 8 and page.evaluate("document.activeElement.classList.contains('tf-q')"))
    page.hover(".tf-file:nth-child(1)")
    page.click(".tf-file:nth-child(1) .tf-ib[data-act='open']")
    page.keyboard.press("ArrowDown")
    check("after a row's button, the keys still move in the list", selected(page) == "Budget 2027.xlsx")
    page.keyboard.press("F2")
    page.keyboard.type("Budget v2")
    page.click(".tf-q")
    page.wait_for_timeout(200)
    check("a rename saved by clicking another field leaves the focus in that field",
          "Budget v2.xlsx" in names(page) and page.evaluate("document.activeElement.classList.contains('tf-q')"))
    page.click(".tf-file:nth-child(2) .tf-c-name")
    page.keyboard.press("F2")
    page.keyboard.type("Half")
    page.evaluate("document.hasFocus = () => false; document.querySelector('.tf-rename').blur(); delete document.hasFocus")
    page.wait_for_timeout(100)
    check("switching to another app does not send a half-typed name", "Half.xlsx" not in names(page) and page.locator(".tf-rename").count() == 1)
    page.focus(".tf-rename")  # coming back to the app
    page.keyboard.press("Escape")
    calls = page.evaluate("""async () => { let n = 0; const id = demo.store[0].id;
      demo.files.update({ confirmDelete: false, onDelete: async f => { n++; await new Promise(r => setTimeout(r, 100)); keep(demo.store.filter(x => x.id !== f.id)); } });
      await Promise.all([demo.files.remove(id), demo.files.remove(id)]); return n; }""")
    check("one file is deleted once, however often Delete is pressed", calls == 1, calls)
    seen = page.evaluate("""() => { const seen = []; demo.files.update({ onSelect: f => seen.push(f ? f.name : null) });
      const f = demo.store[1]; demo.files.select(f.id); keep(demo.store.filter(x => x.id !== f.id));
      const after = demo.files.selected(); keep(demo.store.concat([f])); return [seen, after, demo.files.selected()]; }""")
    check("a selected file that leaves the list is no longer selected, and the app hears it",
          seen[0][-1] is None and seen[1] is None and seen[2] is None, seen)
    page.evaluate("demo.files.update({ dropArea: 'none' }); __emit('tauri://drag-drop', { paths: ['/x/Off.pdf'] })")
    page.wait_for_timeout(450)
    page.evaluate("demo.files.update({ dropArea: 'window' }); __emit('tauri://drag-drop', { paths: ['/x/On.pdf'] })")
    page.wait_for_timeout(450)
    check("dropArea can change after mounting", row(page, "Off.pdf").count() == 0 and row(page, "On.pdf").count() == 1)
    page.evaluate("document.getElementById('msg').textContent = 'before'; demo.files.addPaths(['/x/Late.pdf']); demo.files.destroy()")
    page.wait_for_timeout(500)
    check("a file still being added when the component goes says nothing afterwards", message(page) == "before")
    page.close()

    page = fresh(browser)
    page.click(".tf-file:nth-child(1) .tf-c-name", button="right")
    page.evaluate("demo.files.destroy()")
    check("destroy() closes the row menu", page.locator(".tmn-menu").count() == 0)
    page.close()

    # ---------- reduced motion ----------
    page = fresh(browser, reduced_motion="reduce")
    page.evaluate("__emit('tauri://drag-enter', { paths: ['/a.pdf'] })")
    check("reduced motion: the zone appears without moving", css(page, ".tf-drop", "animation-name") == "none")
    page.close()

    # ---------- as the plugin delivers it ----------
    page = browser.new_page(viewport={"width": 760, "height": 400}, device_scale_factor=2, locale="en-GB")
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.add_init_script(library_script())
    page.goto((HERE / "page.html").as_uri())
    check("no stylesheet is added before the component is used", page.evaluate("document.adoptedStyleSheets.length") == 0)
    page.evaluate("(" + BUILD + ")(document.body)")
    check("mounting adds its stylesheet once", page.evaluate("document.adoptedStyleSheets.length") == 1 and rect(page, ".tf-file")["h"] == 25)
    before = page.evaluate(SIGNATURE)
    page.add_style_tag(content=TEMPLATE_CSS)
    page.wait_for_timeout(100)
    after = page.evaluate(SIGNATURE)
    changed = {s: {k: (before[s][k], after[s][k]) for k in before[s] if before[s][k] != after[s][k]} for s in before}
    changed = {s: d for s, d in changed.items() if d}
    check("a starter template's input, button and text rules change nothing", not changed, changed)
    page.focus(".tf-q")
    check("the search field keeps its look when focused, under the template",
          css(page, ".tf-q", "border-top-width") == "0px" and css(page, ".tf-search", "border-top-color") == ACCENT)
    page.click(".tf-file .tf-c-name")
    page.keyboard.press("F2")
    look = (css(page, ".tf-rename", "border-top-color"), css(page, ".tf-rename", "border-radius"), rect(page, ".tf-file")["h"])
    check("the rename field keeps its look under the template", look == (ACCENT, "3px", 25), look)
    page.close()

    # ---------- under a strict content policy ----------
    page = browser.new_page(viewport={"width": 760, "height": 400}, device_scale_factor=2, locale="en-GB")
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.add_init_script("window.__csp = []; document.addEventListener('securitypolicyviolation', e => __csp.push(e.violatedDirective + ' ' + e.blockedURI));")
    page.add_init_script(library_script())
    page.goto((HERE / "csp.html").as_uri())
    page.evaluate("(" + BUILD + ")(document.getElementById('t'))")
    page.evaluate("files.addPaths(['/x/New.pdf'])")
    page.wait_for_timeout(200)
    page.click(".tf-file .tf-c-name", button="right")
    check("strict policy: the look, the chip, the bar and the menu are all there",
          css(page, ".tf-chip", "background-color") == "rgb(27, 175, 122)" and rect(page, ".tf-file")["h"] == 25
          and page.locator(".tf-file").count() == 3 and page.is_visible(".tmn-menu")
          and page.evaluate("getComputedStyle(document.querySelector('.tf-seg i:nth-child(3)')).animationDelay") == "0.12s")
    check("strict policy: no console errors and nothing refused", not errors and page.evaluate("__csp") == [], (errors, page.evaluate("__csp")))
    page.close()

    # ---------- a delete question and the light look, side by side with dark ----------
    if SHOTS:
        page = fresh(browser)
        page.click(".tf-file:nth-child(3) .tf-c-name")
        page.keyboard.press("Delete")
        shot(page, "ask")
        page.close()

    browser.close()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
