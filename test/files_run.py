"""Tests the files component (web/files.js, web/files.css) in a headless browser.

Run:  python test/files_run.py [screenshot-folder]
Needs Python playwright and Google Chrome. Nothing touches the screen.
Exits non-zero when a check fails. With a folder, it saves screenshots at 2x:
the demo in light and dark, files hovering, adding, and the delete question.
"""
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from engine import WEBKIT, launch

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
PDF_RED, DOC_BLUE, DANGER = "rgb(180, 35, 42)", "rgb(37, 96, 168)", "rgb(184, 58, 49)"

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


def ink(page):
    """The accent as lines, as this page works it out (from the accent, where the engine can)."""
    return page.evaluate("""(() => { const s = document.createElement('span'); s.style.color = 'var(--tf-accent-ink)';
      document.querySelector('.tf').append(s); const c = getComputedStyle(s).color; s.remove(); return c; })()""")


def contrasts(browser, pairs):
    """The contrast of each [colour, colour] pair, in sRGB as drawn."""
    page = browser.new_page()
    out = page.evaluate("""(pairs) => { const rgb = c => { const d = document.createElement('div'); d.style.color = c; document.body.append(d);
        const v = getComputedStyle(d).color; d.remove(); const cv = document.createElement('canvas').getContext('2d'); cv.fillStyle = v; cv.fillRect(0, 0, 1, 1);
        return [...cv.getImageData(0, 0, 1, 1).data].slice(0, 3); };
      const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
      const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
      return pairs.map(([a, b]) => ratio(a, b)); }""", pairs)
    page.close()
    return out


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
    # CI runs the Chromium of the pinned Playwright (the same browser every day); here, Chrome.
    browser = launch(p)

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
          rect(page, ".tf-add")["h"] == 22 and page.inner_text(".tf-add").strip() == "Add files…" and page.locator(".tf-add svg").count() == 1
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
    # The demo's file was added a day ago, whatever today is.
    # As the page writes it: with the year when it is another year (on 1 January).
    yesterday = page.evaluate("""(() => { const d = new Date(Date.now() - 86400000);
      const year = d.getFullYear() === new Date().getFullYear() ? {} : { year: '2-digit' };
      return new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', ...year }).format(d); })()""")
    check("a row: badge, name, size, short date, who", cells[:5] == ["PPT", "Launch plan.pptx", "4.5 MB", yesterday, "sophie"], cells)
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
          and css(page, ".tf-file:nth-child(3) .tf-kind", "color") == "rgb(246, 150, 144)")
    page.evaluate("__emit('tauri://drag-enter', { paths: ['/a.pdf'] })")
    pair = [css(page, ".tf-drop-title", "color"), css(page, ".tf-panel", "background-color")]
    same = css(page, ".tf-arrow", "color") == pair[0] == ink(page)
    page.close()
    ratio = contrasts(browser, [pair])[0]
    check("dark: accent text is the lighter ink, readable on the list (about 5:1, not 2.5:1)", same and ratio >= 4.5, (pair, ratio))

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
    check("search: the count says how many of the place's files show, and their size",
          page.inner_text(".tf-sub").startswith("Documents · 1 of 8 files · ") and "187.6 MB" not in page.inner_text(".tf-sub"), page.inner_text(".tf-sub"))
    page.fill(".tf-q", "zzz")
    check("search: no match says so", page.inner_text(".tf-nomatch-text") == "No files match “zzz”." and page.locator(".tf-file").count() == 0)
    page.click(".tf-nomatch .tf-clear")
    check("its Clear search button empties the search and goes back to the field",
          page.input_value(".tf-q") == "" and len(names(page)) == 8 and page.evaluate("document.activeElement.classList.contains('tf-q')"))
    page.fill(".tf-q", "zzz")
    page.keyboard.press("Escape")
    check("search: Escape empties it", page.input_value(".tf-q") == "" and page.locator(".tf-file").count() == 8 and page.is_hidden(".tf-nomatch"))
    page.fill(".tf-q", "e")
    page.keyboard.press("ArrowDown")
    check("search: Down goes to the list and selects the first match",
          page.evaluate("document.activeElement.classList.contains('tf-list')") and selected(page) == names(page)[0])
    page.close()

    # ---------- names sort as in Finder ----------
    page = fresh(browser)
    page.evaluate("""demo.files.setFiles(["Q3 plan 2.md", "Q3 plan.pdf", "Q3 plan.md", "Q3 plan 10.md", "q3 Plan 1.md", ".env", "README"]
      .map((name, i) => ({ id: 100 + i, name, size: 1, added: new Date().toISOString(), by: "sophie" })))""")
    want = [".env", "Q3 plan.md", "Q3 plan.pdf", "q3 Plan 1.md", "Q3 plan 2.md", "Q3 plan 10.md", "README"]
    check("by name: the name without its extension first, then the extension; numbers as numbers", names(page) == want, names(page))
    page.click(".tf-th.tf-c-name .tf-sort")
    check("by name, Z to A: the same order turned around", names(page) == want[::-1], names(page))
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

    # ---------- one look for every component ----------
    page = fresh(browser)
    page.add_style_tag(content=":root { --tauris-accent: rgb(1, 2, 3); --tauris-bg: rgb(4, 5, 6); --tauris-fg: rgb(7, 8, 9); --tauris-chrome: rgb(10, 11, 12); --tauris-sel-bg: rgb(13, 14, 15); --tauris-font: Georgia, serif; }")
    page.click(".tf-file:nth-child(2) .tf-c-name")
    page.click(".tmn-title:text-is('File')")
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(150)
    look = page.evaluate("""() => { const c = s => getComputedStyle(document.querySelector(s));
      return [c('.tf-panel').backgroundColor, c('.tf-title').color, c('.tf').fontFamily, c('.tf-file:nth-child(2) .tf-cell').backgroundColor,
              c('.tf-th').backgroundColor, c('.tmn-bar').backgroundColor, c('.tmn-menu').backgroundColor, c('.tmn-item:focus').backgroundColor,
              c('.tmn-menu').fontFamily]; }""")
    check("files and menus follow the shared --tauris-* colours and font",
          look == ["rgb(4, 5, 6)", "rgb(7, 8, 9)", "Georgia, serif", "rgb(13, 14, 15)", "rgb(10, 11, 12)", "rgb(10, 11, 12)",
                   "rgb(4, 5, 6)", "rgb(13, 14, 15)", "Georgia, serif"], look)
    page.close()

    # ---------- the app chooses light or dark ----------
    for os_mode, app_mode, panel, pdf, menu_bg in [("dark", "light", "rgb(255, 255, 255)", PDF_RED, "rgb(255, 255, 255)"),
                                                   ("light", "dark", DARK_BG, "rgb(246, 150, 144)", "rgb(47, 50, 52)")]:
        page = fresh(browser, os_mode)
        page.evaluate(f"document.documentElement.dataset.taurisTheme = '{app_mode}'")
        page.click(".tmn-title:text-is('File')")
        look = page.evaluate("""() => [getComputedStyle(document.querySelector('.tf-panel')).backgroundColor,
          getComputedStyle(document.querySelector('.tf-file:nth-child(3) .tf-kind')).color, getComputedStyle(document.querySelector('.tmn-menu')).backgroundColor]""")
        check(f"system {os_mode}, app {app_mode} (data-tauris-theme): the files and menus follow the app", look == [panel, pdf, menu_bg], look)
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
    check("Delete asks first, with the file's name, the safe answer (Cancel) focused",
          page.is_visible(".tf-ask") and page.inner_text(".tf-ask-text") == "Delete “Kickoff notes.md”? This cannot be undone."
          and page.evaluate("document.activeElement.textContent") == "Cancel" and css(page, ".tf-ask .tf-danger", "background-color") == DANGER
          and page.get_attribute(".tf-ask", "aria-modal") is None and page.evaluate("document.querySelector('.tf-list').inert")
          and not page.evaluate("document.querySelector('.tf-head').inert"))
    page.keyboard.press("Tab")
    check("Tab stays inside the question", page.evaluate("document.activeElement.textContent") == "Delete")
    page.keyboard.press("Tab")
    check("and goes round it", page.evaluate("document.activeElement.textContent") == "Cancel")
    page.keyboard.press("Escape")
    check("Escape keeps the file and gives the focus back to the list",
          page.is_hidden(".tf-veil") and len(names(page)) == 8 and page.evaluate("document.activeElement.classList.contains('tf-list')"))
    # ⌘⌫ on a Mac; elsewhere Ctrl+Backspace deletes a word, so Delete.
    erase = "Meta+Backspace" if page.evaluate("/Mac|iPhone|iPad/.test(navigator.platform)") else "Delete"
    page.keyboard.press(erase)
    page.keyboard.press("Enter")
    check("Enter on the focused Cancel keeps the file", len(names(page)) == 8 and page.is_hidden(".tf-veil"))
    page.keyboard.press(erase)
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    check("⌘⌫ (Delete off a Mac) asks too; Tab and Enter delete; the next file is selected",
          "Kickoff notes.md" not in names(page) and selected(page) == "Launch plan.pptx" and message(page) == "Deleted Kickoff notes.md."
          and page.inner_text(".tf-sub").startswith("Documents · 7 files"))
    check("after deleting, the list keeps the focus", page.evaluate("document.activeElement.classList.contains('tf-list')"))
    page.keyboard.press("PageDown")
    check("PageDown moves a page (to the end of a short list)", selected(page) == "Site visit.mov")
    page.close()

    # ---------- selecting several files ----------
    page = fresh(browser)
    page.evaluate("""window.picks = []; window.opens = [];
      demo.files.update({ onSelect: (f, all) => picks.push([f ? f.name : null, all.map(x => x.name)]),
        onOpen: async f => { opens.push(f.name); } })""")
    sel_names = lambda: page.evaluate("demo.files.selection().map(f => f.name)")
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.click(".tf-file:nth-child(3) .tf-c-name", modifiers=["ControlOrMeta"])
    check("⌘-click adds a file to the selection; both rows look selected",
          sel_names() == ["Brand assets.zip", "Contract — signed.pdf"]
          and page.locator('.tf-file[aria-selected="true"]').count() == 2 and page.get_attribute(".tf-list", "aria-multiselectable") == "true")
    check("the app hears the file with the focus and every selected file",
          page.evaluate("picks.at(-1)") == ["Contract — signed.pdf", ["Brand assets.zip", "Contract — signed.pdf"]])
    page.click(".tf-file:nth-child(1) .tf-c-name", modifiers=["ControlOrMeta"])
    check("⌘-click again takes it out", sel_names() == ["Contract — signed.pdf"])
    page.click(".tf-file:nth-child(5) .tf-c-name", modifiers=["Shift"])
    check("Shift-click selects the range from the last click (as in Finder and Explorer)", sel_names() == names(page)[:5], sel_names())
    page.keyboard.press("Shift+ArrowDown")
    check("Shift+Down extends it", len(sel_names()) == 6 and page.evaluate("demo.files.selected().name") == "Launch plan.pptx")
    page.keyboard.press("ArrowDown")
    check("Down alone goes back to one file", sel_names() == ["Moodboard.heic"])
    page.keyboard.press("ControlOrMeta+a")
    check("⌘A selects every file shown", len(sel_names()) == 8)
    page.fill(".tf-q", "pdf")
    check("a search hides some: only the shown ones count as selected", sel_names() == ["Contract — signed.pdf"])
    page.fill(".tf-q", "")
    page.evaluate("demo.files.select([3, 2, 7])")
    page.focus(".tf-list")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    check("select([ids]) picks several; Enter opens them all, one after the other",
          page.evaluate("opens.splice(0)") == ["Brand assets.zip", "Budget 2027.xlsx", "Contract — signed.pdf"] and message(page) == "Opened 3 files.")
    page.click(".tf-file:nth-child(2) .tf-c-name", button="right")
    menu = page.evaluate("[...document.querySelectorAll('.tmn-menu .tmn-item')].map(i => [i.querySelector('.tmn-label').textContent, i.getAttribute('aria-disabled') === 'true'])")
    check("a right click on the selection keeps it; Save a copy and Rename are off for several",
          menu == [["Open", False], ["Save a copy…", True], ["Rename", True], ["Delete", False]] and len(sel_names()) == 3, menu)
    page.click(".tmn-item:has-text('Delete')")
    check("Delete asks once, for all of them", page.inner_text(".tf-ask-text") == "Delete 3 files? This cannot be undone.")
    page.click(".tf-ask .tf-danger")
    page.wait_for_timeout(400)
    check("the red button deletes all three; the file after them is selected",
          names(page) == ["Customer interview — Maria Okafor, Lisbon office, recorded with consent.m4a", "Kickoff notes.md", "Launch plan.pptx", "Moodboard.heic", "Site visit.mov"]
          and sel_names() == [names(page)[0]] and message(page) == "Deleted 3 files.", (names(page), sel_names()))
    page.evaluate("window.__pick = ['/x/One.pdf', '/x/Two.pdf']; window.uploadMs = 50")
    page.click(".tf-add")
    page.wait_for_function("demo.files.selection().length === 2")
    check("files just added are all selected", sel_names() == ["One.pdf", "Two.pdf"])
    page.evaluate("demo.files.update({ multiple: false })")
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.click(".tf-file:nth-child(2) .tf-c-name", modifiers=["ControlOrMeta"])
    check("multiple: false keeps one file at a time", len(sel_names()) == 1 and page.get_attribute(".tf-list", "aria-multiselectable") == "false")
    page.close()

    # ---------- selecting several: the edges a review found ----------
    page = fresh(browser)
    mac = page.evaluate("/Mac|iPhone|iPad/.test(navigator.platform)")
    sel_names = lambda: page.evaluate("demo.files.selection().map(f => f.name)")
    off_by_default = page.evaluate("""() => { const box = document.createElement('div'); document.body.append(box);
      const v = TaurisFiles.mount(box, { files: [{ id: 1, name: 'a.txt' }, { id: 2, name: 'b.txt' }] });
      v.select([1, 2]); v.selectAll(); const n = v.selection().length; const flag = box.querySelector('.tf-list').getAttribute('aria-multiselectable');
      v.destroy(); box.remove(); return [n, flag]; }""")
    check("selecting several is off unless the app turns it on; select([..]) and selectAll() then keep one", off_by_default == [1, "false"], off_by_default)
    page.evaluate("demo.files.update({ confirmDelete: f => `Delete “${f.name}”? (the app asks)` }); demo.files.select([3, 2, 7])")
    page.focus(".tf-list")
    page.keyboard.press("Delete")
    check("an app's own question written for one file never stands for several: the library asks about all of them",
          page.inner_text(".tf-ask-text") == "Delete 3 files? This cannot be undone.")
    page.keyboard.press("Escape")
    page.evaluate("demo.files.update({ labels: { confirmDeleteMany: files => `Remove ${files.length} from the project?` } })")
    page.keyboard.press("Delete")
    check("for several files the app words its question with labels.confirmDeleteMany", page.inner_text(".tf-ask-text") == "Remove 3 from the project?")
    page.keyboard.press("Escape")
    page.evaluate("demo.files.update({ confirmDelete: true })")
    page.click(".tf-file:nth-child(3) .tf-c-name", modifiers=["ControlOrMeta"])
    check("taking out the file with the focus moves the focus to the nearest selected file; the keys still work",
          sel_names() == ["Brand assets.zip", "Budget 2027.xlsx"] and page.evaluate("demo.files.selected().name") == "Budget 2027.xlsx"
          and page.get_attribute(".tf-list", "aria-activedescendant") is not None)
    page.click(".tf-file:nth-child(3) .tf-c-name")
    page.fill(".tf-q", "deck")
    page.wait_for_timeout(50)
    page.fill(".tf-q", "pdf")
    page.focus(".tf-list")
    page.keyboard.press("ControlOrMeta+a")
    check("⌘A after a search: the focus is on a file shown, so the keys work", page.evaluate("demo.files.selected()?.name") in ("Contract — signed.pdf",)
          and sel_names() == ["Contract — signed.pdf"])
    page.fill(".tf-q", "")
    page.evaluate("demo.files.select([1, 2, 3]); demo.files.update({ multiple: false })")
    check("turning multiple off keeps the file with the focus only", len(sel_names()) == 1)
    page.close()

    # ---------- a second review ----------
    page = fresh(browser)
    page.evaluate("window.picks = []; demo.files.update({ onSelect: (f, all) => picks.push([f ? f.name : null, all.map(x => x.name)]) })")
    page.click(".tf-file:nth-child(4) .tf-c-name")
    page.fill(".tf-q", "pdf")
    check("a search that hides every selected file tells the app: nothing to act on", page.evaluate("picks.at(-1)") == [None, []], page.evaluate("picks"))
    page.fill(".tf-q", "")
    page.evaluate("demo.files.update({ multiple: false })")
    page.focus(".tf-list")
    page.keyboard.press("ControlOrMeta+a")
    check("⌘A in the list never selects the page's text", page.evaluate("String(window.getSelection())") == "")
    page.close()

    # ---------- a third review ----------
    page = fresh(browser)
    page.evaluate("""window.got = []; demo.files.update({ onOpen: async f => got.push(f.url), onSelect: (f, all) => { window.last = [f && f.url, all.map(x => x.url)]; } })""")
    page.evaluate("demo.files.select([1, 2]); demo.files.setFiles(demo.store.map(f => ({ ...f, url: 'v2' })))")
    page.focus(".tf-list")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    check("new objects with the same look: every callback gets the new ones",
          page.evaluate("got") == ["v2", "v2"] and page.evaluate("demo.files.selection().every(f => f.url === 'v2')"), page.evaluate("got"))
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("ControlOrMeta+ArrowDown")
    page.keyboard.press("ControlOrMeta+ArrowDown")
    page.keyboard.press("ControlOrMeta+Space")
    names_now = page.evaluate("demo.files.selection().map(f => f.name)")
    check("from the keyboard alone: ⌘↓ moves the focus without selecting, ⌘Space adds that file",
          names_now == ["Brand assets.zip", "Contract — signed.pdf"], names_now)
    ring = page.evaluate("getComputedStyle(document.querySelector('.tf-file.tf-focused .tf-cell')).boxShadow")
    plain = page.evaluate("getComputedStyle(document.querySelector('.tf-file:not(.tf-focused)[aria-selected=\"true\"] .tf-cell')).boxShadow")
    check("with several selected, the file with the focus has a ring the others do not", ring != "none" and plain == "none", (ring, plain))
    page.keyboard.press("ControlOrMeta+ArrowUp")
    ring2 = page.evaluate("getComputedStyle(document.querySelector('.tf-file.tf-focused .tf-cell')).boxShadow")
    check("the focus on a file that is not selected shows the ring too", ring2 != "none" and page.get_attribute(".tf-file.tf-focused", "aria-selected") == "false")
    page.keyboard.press("Delete")
    check("the delete question is named by its text", page.evaluate(
        "document.getElementById(document.querySelector('.tf-ask').getAttribute('aria-labelledby')).textContent") == page.inner_text(".tf-ask-text"))
    page.keyboard.press("Escape")
    page.focus(".tf-th.tf-c-name .tf-sort")
    page.keyboard.press("ControlOrMeta+a")
    check("⌘A on a column header does not select the page's text", page.evaluate("String(window.getSelection())") == "")
    page.close()

    # ---------- a fourth review ----------
    page = fresh(browser)
    page.evaluate("""window.got = []; demo.files.update({ confirmDelete: true, onDelete: async f => { got.push(['delete', f.url]); keep(demo.store.filter(x => x.id !== f.id)); },
      onOpen: async f => got.push(['open', f.url]) })""")
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("Delete")
    page.evaluate("demo.files.setFiles(demo.store.map(f => ({ ...f, url: 'v2' })))")
    page.click(".tf-ask .tf-danger")
    page.wait_for_timeout(200)
    page.click(".tf-file:nth-child(1) .tf-c-name", button="right")
    page.evaluate("demo.files.setFiles(demo.store.map(f => ({ ...f, url: 'v3' })))")
    page.click(".tmn-item:has-text('Open')")
    page.wait_for_timeout(200)
    check("a new list while the question or the menu is open: the action gets the newest objects",
          page.evaluate("got") == [["delete", "v2"], ["open", "v3"]], page.evaluate("got"))
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("ControlOrMeta+ArrowDown")
    page.keyboard.press("Delete")
    check("Delete acts on the selected file, not on one that only has the focus",
          page.inner_text(".tf-ask-text") == f"Delete “{names(page)[0]}”? This cannot be undone.")
    page.keyboard.press("Escape")
    page.keyboard.press("Space")
    check("plain Space adds the file with the focus (⌘Space is the system's on a Mac)", len(page.evaluate("demo.files.selection()")) == 2)
    page.keyboard.press("Space")
    check("Space again takes it out", len(page.evaluate("demo.files.selection()")) == 1)
    check("selected() is the selected file, even when the focus is on another", page.evaluate("demo.files.selected().name") == names(page)[0])
    page.close()
    page = browser.new_page(viewport=SIZE, device_scale_factor=2, locale="en-GB", forced_colors="active")
    page.goto(DEMO.as_uri())
    page.wait_for_selector(".tf-file")
    page.click(".tf-file:nth-child(2) .tf-c-name")
    border = page.evaluate("getComputedStyle(document.querySelector('.tf-file.tf-focused .tf-cell')).borderTopStyle")
    check("Windows high contrast: the row with the focus has a ring drawn with borders", border == "solid", border)
    page.close()

    # ---------- a fifth review ----------
    page = fresh(browser)
    page.evaluate("""window.picks = 0; demo.files.update({ pick: async () => { picks++; await new Promise(r => setTimeout(r, 150)); return []; } });
      demo.files.add(); demo.files.add(); 0""")
    page.wait_for_timeout(250)
    check("add() twice while the picker is open: one picker", page.evaluate("picks") == 1, page.evaluate("picks"))
    page.evaluate("""window.got = []; demo.files.update({ confirmDelete: false, onDelete: async f => { got.push(f.url ?? 'v1');
      if (got.length === 1) demo.files.setFiles(demo.files.files().filter(x => x.id !== f.id).map(x => ({ ...x, url: 'v2' }))); } }); 0""")
    page.evaluate("demo.files.select([demo.files.files()[0].id, demo.files.files()[1].id])")
    page.focus(".tf-list")
    page.keyboard.press("Delete")
    page.wait_for_timeout(200)
    check("deleting several: each file is the app's newest object when its turn comes", page.evaluate("got") == ["v1", "v2"], page.evaluate("got"))
    page.evaluate("demo.files.select(null)")
    page.focus(".tf-list")
    page.keyboard.press("c")
    first = selected(page)
    page.keyboard.press("c")
    second = selected(page)
    check("the same letter again steps to the next file starting with it",
          first != second and first[0] == "C" and second[0] == "C", (first, second))
    page.close()

    page = fresh(browser)
    page.evaluate("demo.files.update({ onRename: () => new Promise(r => setTimeout(r, 200)) }); 0")
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("F2")
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type("Zed.pdf")
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    page.wait_for_timeout(350)
    check("Escape while the app is renaming: its answer is waited for, and the new name shows", "Zed.pdf" in names(page), names(page))
    page.evaluate("window.heard = []; demo.files.update({ onSelect: f => heard.push(f && f.name) }); 0")
    page.click(".tf-file:nth-child(2) .tf-c-name")
    page.evaluate("const id = demo.files.selected().id; demo.files.setFiles(demo.files.files().map(x => x.id === id ? { ...x, name: 'Renamed.pdf' } : x))")
    check("onSelect hears a new name for the same selected file", page.evaluate("heard.at(-1)") == "Renamed.pdf", page.evaluate("heard"))
    page.fill(".tf-q", "zzz")
    page.evaluate("demo.files.update({ search: false })")
    check("a search the person cannot see hides no file", len(names(page)) == len(page.evaluate("demo.files.files()")), names(page))
    page.evaluate("demo.files.update({ search: true })")
    page.evaluate("demo.files.select(null)")
    page.focus(".tf-list")
    page.keyboard.press("Shift+F10")
    check("Shift+F10 with no file chosen: the first file's menu, and that file selected",
          page.locator(".tmn-menu").count() == 1 and selected(page) == names(page)[0], selected(page))
    page.keyboard.press("Escape")
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("Delete")
    check("while the delete question is open, the files under it cannot be reached", page.evaluate("document.querySelector('.tf-list').inert") is True)
    page.keyboard.press("Escape")
    check("and can again once it is answered", page.evaluate("!document.querySelector('.tf-list').inert && document.activeElement.classList.contains('tf-list')"))
    page.close()

    page = fresh(browser)
    page.evaluate("""() => { const host = document.createElement('div'); host.id = 'second';
      host.style.cssText = 'position:fixed;right:0;bottom:0;width:300px;height:200px;z-index:5';
      document.body.append(host); window.second = [];
      window.secondFiles = TaurisFiles.mount(host, { onAdd: async p => { second.push(...p); return []; } }); return 0; }""")
    count = len(page.evaluate("demo.files.files()"))
    r = rect(page, "#second")
    page.evaluate("p => __emit('tauri://drag-drop', { paths: ['/x/Over.pdf'], position: p })", {"x": (r["x"] + 20) * 2, "y": (r["y"] + 20) * 2})
    page.wait_for_timeout(500)
    check("two components that take the window's drops: a drop over the second is the second's only",
          page.evaluate("second") == ["/x/Over.pdf"] and len(page.evaluate("demo.files.files()")) == count, page.evaluate("second"))
    page.evaluate("__emit('tauri://drag-drop', { paths: ['/x/Else.pdf'], position: { x: 10, y: 10 } })")
    page.wait_for_timeout(500)
    check("a drop over neither is the first mounted one's", "Else.pdf" in names(page) and page.evaluate("second") == ["/x/Over.pdf"])
    page.evaluate("window.picks = 0; demo.files.update({ pick: async () => { picks++; return []; } }); demo.files.destroy(); demo.files.add(); 0")
    page.wait_for_timeout(50)
    check("after destroy(), add() opens no picker", page.evaluate("picks") == 0)
    page.close()

    # ---------- a sixth review ----------
    page = fresh(browser)
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("Delete")
    page.click(".tf-ask-text")
    check("a click on the delete question's own text keeps the question open", page.is_visible(".tf-ask"))
    page.keyboard.press("Escape")
    page.evaluate("demo.files.select(null)")
    page.focus(".tf-list")
    page.keyboard.type("Launch p")
    check("typing a name with a space in it finds it", selected(page) == "Launch plan.pptx", selected(page))
    page.evaluate("window.renamed = []; demo.files.update({ confirmDelete: false, onRename: async (f, n) => renamed.push(n) }); 0")
    page.click(".tf-file:nth-child(2) .tf-c-name")
    page.keyboard.press("F2")
    page.keyboard.type("x")
    second = names(page)[2]
    page.evaluate("id => { demo.files.remove(id); return 0; }", page.evaluate("demo.files.files().find(f => f.name === %r).id" % second))
    page.wait_for_timeout(150)
    page.evaluate("demo.files.addPaths(['/Users/m/Added while renaming.pdf']); 0")
    page.wait_for_timeout(450)
    page.keyboard.press("Escape")
    page.wait_for_timeout(50)
    now = names(page)
    check("a file deleted while another is renamed stays gone; one added meanwhile shows, selected, once the rename ends",
          second not in now and "Added while renaming.pdf" in now and selected(page) == "Added while renaming.pdf", (now, selected(page)))
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("F2")
    page.keyboard.type("gone")
    page.evaluate("demo.files.destroy()")
    page.wait_for_timeout(100)
    check("destroy() while a name is being edited renames nothing", not any("gone" in n for n in page.evaluate("renamed")), page.evaluate("renamed"))
    page.evaluate("demo.files.dragDrop({ type: 'enter', paths: ['/x.pdf'] })")
    check("after destroy() a fed drag event changes nothing", not page.evaluate("document.getElementById('files').classList.contains('tf-dropping')"))
    page.close()

    page = fresh(browser)
    page.evaluate("""demo.files.update({ multiple: false, files: Array.from({ length: 100 }, (_, i) => ({ id: i + 1, name: `File ${String(i).padStart(3, '0')}.txt`, size: 10 })) })""")
    page.focus(".tf-list")
    page.keyboard.press("Space")
    check("Space never scrolls the list a page", page.evaluate("document.querySelector('.tf-list').scrollTop") == 0)
    page.focus(".tf-q")
    page.evaluate("document.querySelector('.tf-q').dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', isComposing: true, bubbles: true }))")
    check("arrows while an input method is composing stay in the search field", page.evaluate("document.activeElement.classList.contains('tf-q')"))
    page.close()

    # Reduced motion: the colours are read without their short fade.
    page = browser.new_page(viewport=SIZE, device_scale_factor=2, locale="en-GB", forced_colors="active", color_scheme="dark", reduced_motion="reduce")
    page.goto(DEMO.as_uri())
    page.wait_for_selector(".tf-file")
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("Shift+ArrowDown")
    hc = page.evaluate("""(() => { const row = document.querySelector('.tf-file.tf-focused .tf-cell');
      const badge = document.querySelector('.tf-file[aria-selected="true"] .tf-kind');
      return [getComputedStyle(row).borderTopColor === getComputedStyle(row).backgroundColor, getComputedStyle(badge).color === getComputedStyle(row).color]; })()""")
    check("Windows high contrast: the focused row's ring shows on a selection, and the badge takes the selection's text colour", hc == [False, True], hc)
    page.close()

    # ---------- the sort headers from the keyboard ----------
    page = fresh(browser)
    check("the sort headers are not Tab stops", page.evaluate("[...document.querySelectorAll('.tf-sort')].every(b => b.tabIndex === -1)"))
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("ArrowUp")
    on_header = page.evaluate("document.activeElement.classList.contains('tf-sort') && document.activeElement.closest('.tf-th').dataset.col")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter")
    sorted_by = page.evaluate("document.querySelector('.tf-th[aria-sort=\"ascending\"], .tf-th[aria-sort=\"descending\"]').dataset.col")
    page.keyboard.press("ArrowDown")
    check("↑ from the first file reaches the headers; → and Enter sort by the next one; ↓ goes back to the files",
          on_header == "name" and sorted_by == "size" and page.evaluate("document.activeElement.classList.contains('tf-list')"), (on_header, sorted_by))
    page.close()

    # ---------- a seventh review ----------
    page = fresh(browser)
    seen = page.evaluate("""() => { const host = document.createElement('div'); document.body.append(host); window.calls = [];
      const v = TaurisFiles.mount(host, { files: [{ id: 1, name: 'a.pdf' }], onSelect: () => calls.push(v.selected()) }); return calls.length; }""")
    check("onSelect is not called while mount() runs (nothing changed yet)", seen == 0, seen)
    page.evaluate("demo.files.update({ multiple: false }); demo.files.addPaths(['/x/One.pdf', '/x/Two.pdf']); 0")
    page.wait_for_timeout(500)
    check("without multiple, adding several files selects one", len(page.evaluate("demo.files.selection()")) == 1, page.evaluate("demo.files.selection().map(f => f.name)"))
    page.evaluate("window.opens = 0; demo.files.update({ onOpen: async () => { opens++; } }); 0")
    page.focus(".tf-list")
    page.evaluate("""() => { const g = document.querySelector('.tf-list');
      for (let n = 0; n < 4; n++) g.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', repeat: n > 0, bubbles: true })); return 0; }""")
    page.wait_for_timeout(100)
    check("holding Enter opens once", page.evaluate("opens") == 1, page.evaluate("opens"))
    page.keyboard.press("Alt+Delete")
    page.keyboard.press("Shift+Delete")
    check("Delete with ⌥ or ⇧ held asks nothing", page.is_hidden(".tf-veil"))
    check("the row's buttons are left to the mouse (the keys reach every action)",
          page.evaluate("[...document.querySelectorAll('.tf-acts')].every(a => a.getAttribute('aria-hidden') === 'true')"))
    page.close()

    page = fresh(browser)
    page.evaluate("""demo.files.setFiles([{ id: 'r10', name: 'Report 10.pdf' }, { id: 'r2', name: 'Report 2.pdf' }, { id: 'r1', name: 'Report 1.pdf' },
      { id: 'e2', name: 'résumé.pdf' }, { id: 'e1', name: 'resume.pdf' }])""")
    order1 = names(page)
    page.evaluate("demo.files.setFiles(demo.files.files().slice().reverse())")
    check("names equal but for accents keep one order, whatever order they came in", names(page) == order1, (order1, names(page)))
    page.evaluate("demo.files.select('r2')")
    page.focus(".tf-list")
    page.keyboard.type("report 1")
    check("a whole name typed finds that name (not the next one after the selection)", selected(page) == "Report 1.pdf", selected(page))
    page.keyboard.press("q")
    page.keyboard.press("Space")
    check("Space after a letter that matched nothing scrolls nothing", page.evaluate("document.querySelector('.tf-list').scrollTop") == 0)
    page.evaluate("window.renamed = []; demo.files.update({ confirmDelete: false, onRename: async (f, n) => renamed.push(n), onDelete: async () => {} }); 0")
    page.evaluate("demo.files.rename('r1')")
    page.keyboard.type("x")
    page.evaluate("""document.querySelector('.tf-rename').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true }))""")
    check("Enter that confirms an input method's text does not save the name", page.locator(".tf-rename").count() == 1 and page.evaluate("renamed") == [])
    ok = page.evaluate("demo.files.remove('r1').then(() => true, () => false)")
    check("deleting the file being renamed ends the rename and works", ok and "Report 1.pdf" not in names(page) and page.locator(".tf-rename").count() == 0, names(page))
    page.close()

    page = fresh(browser)
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("Delete")
    page.click(".tf-ask-text")
    page.keyboard.press("Enter")
    check("after a click on the question's text, Enter goes to Cancel (not to nothing)",
          page.is_visible(".tf-ask") and page.evaluate("document.activeElement.textContent") == "Cancel")
    page.keyboard.press("Escape")
    page.close()

    # ---------- an eighth review ----------
    page = fresh(browser)
    page.evaluate("""demo.files.setFiles([{ id: 'a', name: 'Relatório 2026.pdf' }, { id: 'b', name: 'Joa\u0303o.txt' }, { id: 'c', name: 'ąbc.pdf' }, { id: 'd', name: 'Other.pdf' }])""")
    page.fill(".tf-q", "relatorio")
    check("search ignores accents", names(page) == ["Relatório 2026.pdf"], names(page))
    page.fill(".tf-q", "João")
    check("and Unicode forms (a decomposed name found by a typed one)", len(names(page)) == 1, names(page))
    page.fill(".tf-q", "zzz")
    check("a search that matches nothing takes the list out of the Tab order", page.evaluate("document.querySelector('.tf-list').tabIndex") == -1)
    page.fill(".tf-q", "pdf")
    page.keyboard.press("Enter")
    check("Enter in the search goes into the list, on the first match", page.evaluate("document.activeElement.classList.contains('tf-list')") and selected(page) is not None)
    page.evaluate("demo.files.select(null); window.opens = 0; demo.files.update({ onOpen: async () => { opens++; } }); 0")
    page.evaluate("demo.files.select('d')")
    page.keyboard.press("Shift+Enter")
    check("Shift+Enter opens nothing (only plain Enter does)", page.evaluate("opens") == 0)
    page.fill(".tf-q", "")
    page.focus(".tf-list")
    # AltGr is Windows's (Ctrl+Alt there); WebKit's events take no modifierAltGraph.
    if not WEBKIT:
        page.evaluate("""document.querySelector('.tf-list').dispatchEvent(new KeyboardEvent('keydown', { key: 'ą', ctrlKey: true, altKey: true, modifierAltGraph: true, bubbles: true }))""")
        check("a letter made with AltGr (Ctrl+Alt) still jumps to its name", selected(page) == "ąbc.pdf", selected(page))
    check("the row's buttons make no column for screen readers",
          page.evaluate("document.querySelectorAll('[role=columnheader][aria-label=\"Actions\"], .tf-c-acts[role=gridcell]').length") == 0)
    page.evaluate("demo.files.select('d')")
    page.evaluate("demo.files.update({ title: 'Other place', files: [{ id: 'x', name: 'x.pdf' }, { id: 'y', name: 'y.pdf' }] })")
    check("a list replaced for another place leaves nothing selected", page.evaluate("demo.files.selection().length") == 0)
    page.evaluate("""window.tries = 0; demo.files.update({ multiple: true, confirmDelete: false, files: ['1', '2', '3', '4'].map(n => ({ id: n, name: `File ${n}.pdf` })),
      onDelete: async f => { if (f.id === '2') throw 'File 2 is in use.'; } }); demo.files.selectAll(); 0""")
    page.focus(".tf-list")
    page.keyboard.press("Delete")
    page.wait_for_timeout(150)
    check("a delete that fails among several: that file takes the selection, to try again", selected(page) == "File 2.pdf", selected(page))
    page.evaluate("demo.files.update({ onOpen: () => Promise.reject() }); demo.files.open('2'); 0")
    page.wait_for_timeout(100)
    check("an empty refusal says nothing (no \"undefined\")", "undefined" not in message(page), message(page))
    page.close()

    page = fresh(browser)
    page.evaluate("window.tries = 0; demo.files.update({ onRename: async () => { tries++; throw 'Taken.'; } }); 0")
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("F2")
    page.keyboard.type("x")
    page.evaluate("""() => { const i = document.querySelector('.tf-rename');
      for (let n = 0; n < 5; n++) i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', repeat: n > 0, bubbles: true })); return 0; }""")
    page.wait_for_timeout(100)
    check("holding Enter in the rename field asks the app once", page.evaluate("tries") == 1, page.evaluate("tries"))
    page.keyboard.press("Escape")
    page.fill(".tf-q", "plan")
    page.evaluate("demo.files.update({ multiple: true }); demo.files.addPaths(['/x/b.txt', '/x/plan2.pdf']); 0")
    page.wait_for_timeout(700)
    check("files added while a search is on: the focus is on one that is shown",
          page.evaluate("document.querySelector('.tf-file.tf-focused .tf-c-name')?.textContent") == "plan2.pdf",
          page.evaluate("document.querySelector('.tf-file.tf-focused .tf-c-name')?.textContent"))
    page.close()

    page = fresh(browser)
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("Delete")
    page.click(".tf-ask-text")
    page.keyboard.press("Tab")
    check("Tab from the question's text goes to Cancel, not Delete", page.evaluate("document.activeElement.textContent") == "Cancel")
    page.keyboard.press("Escape")
    page.evaluate("""() => { const a = document.createElement('div'); a.id = 'other'; a.style.cssText = 'height: 100px'; document.body.append(a);
      window.otherGot = []; window.other = TaurisFiles.mount(a, { dropArea: 'element', onAdd: async p => { otherGot.push(...p); return []; } }); return 0; }""")
    page.evaluate("demo.files.update({ dropArea: 'element' }); demo.files.dragDrop({ type: 'drop', paths: ['/x/Fed.pdf'] }); other.dragDrop({ type: 'drop', paths: ['/x/Fed.pdf'] }); 0")
    page.wait_for_timeout(500)
    check("a drop fed with no position goes to one component, not to each", (("Fed.pdf" in names(page)) + (len(page.evaluate("otherGot")) == 1)) == 1,
          (names(page), page.evaluate("otherGot")))
    page.close()

    # ---------- a Mac's keys, on any machine (the page is told it runs on a Mac) ----------
    page = browser.new_page(viewport=SIZE, device_scale_factor=2, locale="en-GB")
    page.add_init_script("Object.defineProperty(Navigator.prototype, 'platform', { get: () => 'MacIntel' })")
    page.goto(DEMO.as_uri())
    page.wait_for_selector(".tf-file")
    sel_names = lambda: page.evaluate("demo.files.selection().map(f => f.name)")
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("Control+Backspace")
    page.keyboard.press("Control+Meta+Backspace")
    check("on a Mac, ⌃⌫ and ⌃⌘⌫ are not ⌘⌫: nothing asks", page.is_hidden(".tf-veil"))
    page.keyboard.press("Meta+Backspace")
    check("and ⌘⌫ asks", page.is_visible(".tf-ask"))
    page.keyboard.press("Escape")
    page.keyboard.press("Control+Meta+a")
    page.keyboard.press("Control+a")
    check("on a Mac, ⌃⌘A and ⌃A select nothing more", len(sel_names()) == 1, sel_names())
    page.click(".tf-file:nth-child(3) .tf-c-name", modifiers=["Control", "Meta"])
    check("⌃⌘-click is not ⌘-click: it adds nothing", len(sel_names()) <= 1, sel_names())
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("Control+Meta+ArrowDown")
    check("⌃⌘↓ is not ⌘↓: the focus does not move alone, leaving the selection behind",
          page.evaluate("document.querySelector('.tf-file.tf-focused')?.getAttribute('aria-selected')") != "false")
    page.keyboard.press("Meta+a")
    check("⌘A selects every file", len(sel_names()) == 8, sel_names())
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.click(".tf-file:nth-child(2) .tf-c-name", modifiers=["Meta"])
    page.click(".tf-file:nth-child(1) .tf-c-name", modifiers=["Control"])
    # macOS itself sends the menu event for a Control-click; elsewhere the test does.
    if page.locator(".tmn-menu").count() == 0:
        page.dispatch_event(".tf-file:nth-child(1) .tf-c-name", "contextmenu", {"button": 2, "ctrlKey": True})
    check("on a Mac, Control-click is a right click: the selection stays, and its menu acts on both",
          len(sel_names()) == 2 and page.locator(".tmn-menu").count() == 1
          and page.get_attribute(".tmn-item:has-text('Rename')", "aria-disabled") == "true", sel_names())
    page.keyboard.press("Escape")
    page.close()

    # ---------- and Windows' and Linux's (the page is told it runs on Linux) ----------
    page = browser.new_page(viewport=SIZE, device_scale_factor=2, locale="en-GB")
    page.add_init_script("Object.defineProperty(Navigator.prototype, 'platform', { get: () => 'Linux x86_64' })")
    page.goto(DEMO.as_uri())
    page.wait_for_selector(".tf-file")
    sel_names = lambda: page.evaluate("demo.files.selection().map(f => f.name)")
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.keyboard.press("Control+Backspace")
    check("elsewhere, Ctrl+Backspace (a word, in a field) deletes nothing", page.is_hidden(".tf-veil"))
    page.keyboard.press("Delete")
    check("and Delete asks", page.is_visible(".tf-ask"))
    page.keyboard.press("Escape")
    page.keyboard.press("Control+a")
    check("Ctrl+A selects every file", len(sel_names()) == 8, sel_names())
    page.click(".tf-file:nth-child(1) .tf-c-name")
    page.click(".tf-file:nth-child(3) .tf-c-name", modifiers=["Control"])
    check("Ctrl-click adds a file", len(sel_names()) == 2, sel_names())
    page.close()

    # ---------- the row's buttons, double-click, the row menu ----------
    page = fresh(browser)
    page.dblclick(".tf-file:nth-child(2) .tf-c-name")
    # The demo's onOpen takes 80ms; a slow machine takes longer.
    page.wait_for_function("window.opened !== undefined", timeout=3000)
    check("a double click opens", page.evaluate("window.opened") == "Budget 2027.xlsx", page.evaluate("window.opened"))
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
          page.inner_text(".tf-busy").strip() == "Adding 2 files…" and page.locator(".tf-seg i").count() == 20
          and page.get_attribute(".tf-add", "aria-disabled") == "true"
          and css(page, ".tf-seg i:nth-child(5)", "animation-delay") == "0.24s")
    shot(page, "adding")
    idle(page)
    check("added: in the list, the first selected, flashing, and said",
          "Q3 board deck.pdf" in names(page) and "Studio floor plan.png" in names(page) and selected(page) == "Q3 board deck.pdf"
          and page.locator(".tf-file.tf-fresh").count() == 2 and message(page) == "Added 2 files to Northwind Launch."
          and page.inner_text(".tf-sub") == "Documents · 10 files · 190.4 MB")
    check("the flash is a short tint; on a selected row a darker one, so its text stays readable",
          css(page, ".tf-file.tf-fresh .tf-cell", "animation-name") == "tf-flash-selected")
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
    check("the zone is a solid 2px ring in the accent round the whole list", ring == ("solid", "2px", ink(page), "2px", True), ring)
    shot(page, "drop")
    page.evaluate("__emit('tauri://drag-leave', null)")
    check("they leave: the zone goes", page.is_hidden(".tf-drop"))
    page.evaluate("__emit('tauri://drag-enter', { paths: [], position: { x: 300, y: 300 } })")
    check("something that is not files shows no zone", page.is_hidden(".tf-drop"))
    page.evaluate("""__emit('tauri://drag-enter', { paths: ['/Users/m/Term sheet.docx'], position: { x: 300, y: 300 } });
      __emit('tauri://drag-over', { position: { x: 310, y: 300 } });
      __emit('tauri://drag-drop', { paths: ['/Users/m/Term sheet.docx'], position: { x: 310, y: 300 } })""")
    check("a drop: the zone goes and the busy card says what is coming", page.is_hidden(".tf-drop") and page.inner_text(".tf-busy").strip() == "Adding 1 file…")
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
      TaurisFiles.formatSize(0), TaurisFiles.formatSize(1), TaurisFiles.formatSize(1047552), TaurisFiles.formatSize(1610612736),
      TaurisFiles.formatSize(1048575), TaurisFiles.formatSize(1073741823)]""")
    check("kindOf and formatSize (never \"1,024 KB\")", helpers == ["PPT", "PDF", "SKE", "FILE", "XLS", "0 KB", "1 KB", "1,023 KB", "1.5 GB",
                                                           "1 MB", "1 GB"], helpers)
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
      const f = demo.store[1]; demo.files.select(f.id); seen.length = 0; keep(demo.store.filter(x => x.id !== f.id));
      const after = demo.files.selected(); return [seen, f.name, after && after.name]; }""")
    check("a selected file that leaves the app's list hands the selection to the file now in its place, and the app hears it",
          seen[0] == [seen[2]] and seen[2] not in (None, seen[1]), seen)
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
          css(page, ".tf-q", "border-top-width") == "0px" and css(page, ".tf-search", "border-top-color") == ink(page))
    page.click(".tf-file .tf-c-name")
    page.keyboard.press("F2")
    look = (css(page, ".tf-rename", "border-top-color"), css(page, ".tf-rename", "border-radius"), rect(page, ".tf-file")["h"])
    check("the rename field keeps its look under the template", look == (ink(page), "3px", 25), look)
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

    # ---------- an eighth review: a place switched while something is under way ----------
    MOUNT = """(opts) => { const host = document.createElement('div'); host.style.height = '400px'; document.body.prepend(host);
      const files = w => ['Plan.docx', 'Budget.xlsx', 'Notes.md'].map(n => ({ id: n, name: n, where: w, size: 1000 }));
      window.A = files('A'); window.B = files('B'); window.log = [];
      window.wait = ms => new Promise(r => setTimeout(r, ms));
      window.v = TaurisFiles.mount(host, { title: 'A', files: A, multiple: true, ...opts }); return 0; }"""
    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("v.update({ confirmDelete: false, onDelete: async f => { log.push(f.where + '/' + f.name); await wait(60); } }); v.selectAll(); v.focus(); 0")
    page.keyboard.press("Delete")
    page.wait_for_timeout(20)
    page.evaluate("v.update({ title: 'B', files: B }); 0")
    page.wait_for_timeout(400)
    got = page.evaluate("log")
    check("several files being deleted, then another place shown: none of its files is deleted",
          got and all(g.startswith("A/") for g in got) and len(page.evaluate("v.files()")) == 3, got)
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("v.update({ onRename: async (f, n) => { log.push(f.where + '/' + f.name); } }); v.rename('Plan.docx'); 0")
    page.keyboard.type("Plan 2")
    page.evaluate("v.update({ title: 'B', files: B }); 0")
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    check("a rename open when another place is shown ends, and renames nothing", page.evaluate("log") == [] and page.locator(".tf-rename").count() == 0,
          page.evaluate("log"))
    page.evaluate("v.update({ title: 'A', files: A, onDelete: async f => { log.push(f.where + '/' + f.name); } }); v.remove('Plan.docx'); 0")
    page.wait_for_selector(".tf-veil:not([hidden])")
    page.evaluate("v.update({ title: 'B', files: B }); 0")
    check("the delete question closes when another place is shown", page.is_hidden(".tf-veil"))
    page.wait_for_timeout(50)
    check("and deletes nothing", page.evaluate("log") == [], page.evaluate("log"))
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("""v.update({ onAdd: async p => { log.push('A:' + p.map(x => x.split('/').pop())); await wait(150); return p.map(x => ({ id: 'n-' + x, name: x.split('/').pop() })); } });
      v.addPaths(['/x/one.pdf']); v.addPaths(['/x/two.pdf']);
      setTimeout(() => v.update({ title: 'B', files: B, onAdd: async p => { log.push('B:' + p); return []; } }), 40); 0""")
    page.wait_for_timeout(700)
    check("drops wait their turn, but go where they were dropped, and do not join the next place's list",
          page.evaluate("log") == ["A:one.pdf", "A:two.pdf"] and page.evaluate("v.files().map(f => f.where)") == ["B", "B", "B"],
          (page.evaluate("log"), page.evaluate("v.files().map(f => f.name)")))
    page.evaluate("v.update({ onAdd: async p => { log.push('C:' + p); await wait(100); return []; } }); log.length = 0; v.addPaths(['/x/a.pdf']); v.addPaths(['/x/b.pdf']); v.destroy(); 0")
    page.wait_for_timeout(400)
    check("a drop still waiting when the component is removed is not sent", len(page.evaluate("log")) <= 1, page.evaluate("log"))
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("v.update({ confirmDelete: false, onDelete: async f => { log.push(f.name); await wait(60); } }); v.selectAll(); v.focus(); 0")
    page.keyboard.press("Delete")
    page.wait_for_timeout(90)
    page.keyboard.press("Delete")
    page.wait_for_timeout(500)
    got = page.evaluate("log")
    check("Delete again while several files go deletes each of them once", sorted(got) == ["Budget.xlsx", "Notes.md", "Plan.docx"], got)
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("const n = document.createElement('input'); n.id = 'notes'; document.body.append(n); v.update({ onDelete: async () => { await wait(150); } }); v.select('Plan.docx'); v.focus(); 0")
    page.keyboard.press("Delete")
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    page.wait_for_timeout(30)
    page.focus("#notes")
    page.wait_for_timeout(300)
    check("a delete that ends after the person went to a field of the app's leaves the focus there",
          page.evaluate("document.activeElement.id") == "notes", page.evaluate("document.activeElement.className"))
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("v.select('Plan.docx'); const h = document.querySelector('.tf'); h.style.setProperty('--tf-sel-fg', '#111111'); h.style.setProperty('--tf-accent-ink', '#b34700'); v.focus(); 0")
    edge = page.evaluate("getComputedStyle(document.querySelector('.tf .tf-file[aria-selected=true] .tf-kind')).borderTopColor")
    halo = page.evaluate("getComputedStyle(document.querySelector('.tf .tf-panel')).boxShadow")
    check("colours set on the component's element reach the edges and the focus halo worked out from them",
          ("17, 17, 17" in edge or "0.0666" in edge) and ("179, 71, 0" in halo or "0.70" in halo), (edge, halo))
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("v.select(['Plan.docx', 'Budget.xlsx']); v.focus(); 0")
    page.keyboard.press("ControlOrMeta+ArrowDown")
    page.evaluate("v.update({ multiple: false }); 0")
    sel = page.evaluate("v.selection().map(f => f.name)")
    check("turning multiple off keeps a selected file, not one that only had the focus", len(sel) == 1 and sel[0] in ("Plan.docx", "Budget.xlsx"), sel)
    page.evaluate("v.search('Plan'); v.select('Notes.md'); 0")
    check("select() of a file the search hides shows it (the search is cleared)",
          page.evaluate("v.selected()?.name") == "Notes.md" and page.input_value(".tf-q") == "", page.evaluate("v.selected()?.name"))
    page.evaluate("window.seen = []; v.update({ onSelect: f => seen.push(f && f.note) }); v.setFiles(A.map(f => ({ ...f, note: 'new' }))); 0")
    check("new objects for the selected file reach onSelect (the app's own fields may have changed)", page.evaluate("seen").count("new") == 1,
          page.evaluate("seen"))
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("v.update({ onOpen: async () => {}, onRename: async () => {}, onDelete: async () => {}, onSaveAs: async () => {} }); 0")
    # The accessibility tree as Chromium builds it (its debugging protocol; WebKit has none here).
    if not WEBKIT:
        cdp = page.context.new_cdp_session(page)
        tree = cdp.send("Accessibility.getFullAXTree")["nodes"]
        row_names = [n["name"]["value"] for n in tree if n.get("role", {}).get("value") == "row" and n.get("name", {}).get("value", "").startswith("Budget")]
        check("a row is named by what it shows, not by its buttons too", row_names and all("Open" not in r and "Rename" not in r for r in row_names), row_names)
    live = page.evaluate("[document.querySelector('.tf-live')].map(n => [n.getAttribute('role'), n.hidden, n.textContent])")
    page.evaluate("v.search('zzz'); 0")
    page.wait_for_timeout(600)  # it speaks once the typing stops
    check("the region a screen reader hears is there before it speaks, then says the search found nothing",
          live == [["status", False, ""]] and page.evaluate("document.querySelector('.tf-live').textContent") == "No files match “zzz”.",
          (live, page.evaluate("document.querySelector('.tf-live').textContent")))
    page.evaluate("v.search(''); v.select(['Plan.docx', 'Budget.xlsx', 'Notes.md']); v.focus(); 0")
    page.keyboard.press("Shift+F10")
    check("the row menu for several files is named for all of them",
          page.evaluate("document.querySelector('.tmn-menu')?.getAttribute('aria-label')") == "3 files",
          page.evaluate("document.querySelector('.tmn-menu')?.getAttribute('aria-label')"))
    page.keyboard.press("Escape")
    page.evaluate("v.setFiles([{ id: 1, name: 'Anexo.pdf' }, { id: 2, name: 'João notes.pdf' }, { id: 3, name: 'Łódź.pdf' }, { id: 4, name: 'Mało.pdf' }]); v.focus(); 0")
    typed = page.evaluate("""() => { const g = document.querySelector('.tf-list'); const k = key => g.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
      k('j'); k('o'); k('Dead'); k('ã'); const one = v.selected()?.name; k('Escape');
      return new Promise(r => setTimeout(() => { k('m'); k('a'); k('AltGraph'); k('ł'); r([one, v.selected()?.name]); }, 800)); }""")
    check("typing a name with an accent key or AltGr on the way still finds it", typed == ["João notes.pdf", "Mało.pdf"], typed)
    # Hidden, so only the component's own work is timed (not the browser drawing 20,000 rows).
    many = page.evaluate("""() => { const all = Array.from({ length: 20000 }, (_, i) => ({ id: i, name: 'File ' + i + '.pdf', size: i }));
      const host = document.createElement('div'); host.style.display = 'none'; document.body.append(host);
      const w = TaurisFiles.mount(host, { multiple: true, files: all });
      const t = performance.now(); w.select(all.map(f => f.id)); const took = performance.now() - t; w.destroy(); return took; }""")
    check("selecting 20,000 files by id takes one pass, not one per file", many < 300, many)
    again = page.evaluate("""() => { const first = document.querySelector('.tf-file'); v.search('File 1'); v.search(''); return document.querySelector('.tf-file') === first; }""")
    check("a search keeps the rows that were drawn (only what changed is drawn again)", again)
    page.close()

    # ---------- a ninth review ----------
    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("""v.update({ confirmDelete: false, onDelete: async f => { await wait(20); window.A = A.filter(x => x.id !== f.id); v.setFiles(A); } });
      v.selectAll(); v.focus(); 0""")
    page.keyboard.press("Delete")
    page.wait_for_timeout(400)
    check("deleting every file (the app sending its empty list) says so, and the focus stays in the component",
          "Deleted 3 files." in page.evaluate("document.querySelector('.tf-status').textContent")
          and page.evaluate("document.activeElement.closest('.tf') !== null"), (page.evaluate("document.querySelector('.tf-status').textContent"),
                                                                              page.evaluate("document.activeElement.className")))
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("""v.update({ onOpen: async f => { log.push(f.where + '/' + f.name); await wait(60); } });
      v.select(['Plan.docx', 'Budget.xlsx', 'Notes.md']); v.focus(); 0""")
    page.keyboard.press("Enter")
    page.wait_for_timeout(20)
    page.evaluate("v.update({ title: 'B', files: B }); 0")
    page.wait_for_timeout(300)
    check("opening several, then another place shown: none of its files is opened", all(x.startswith("A/") for x in page.evaluate("log")), page.evaluate("log"))
    check("and the new place has nothing selected (a file of the same id there was not chosen)", page.evaluate("v.selection().length") == 0)
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    reused = page.evaluate("""() => { const first = document.querySelector('.tf .tf-file'); v.update({ title: 'A', files: A.slice() });
      return document.querySelector('.tf .tf-file') === first; }""")
    check("update({ files }) with the same files keeps the rows drawn (the React pattern)", reused)
    page.evaluate("v.update({ onRename: async () => {} }); v.search('n'); v.rename('Plan.docx'); 0")
    page.wait_for_timeout(50)
    before = page.inner_text(".tf .tf-sub")
    page.evaluate("v.update({ confirmDelete: false, onDelete: async () => {} }); v.remove('Notes.md'); 0")
    page.wait_for_timeout(100)
    after = page.inner_text(".tf .tf-sub")
    check("a delete while another file is renamed during a search: the count follows",
          before.startswith("2 of 3 files") and after.startswith("1 of 2 files"), (before, after))
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("""v.update({ multiple: true, onDelete: async f => { if (f.id === 'Budget.xlsx') return; } }); v.select(['Plan.docx', 'Budget.xlsx']); v.focus(); 0""")
    page.keyboard.press("Delete")
    page.wait_for_selector(".tf .tf-veil:not([hidden])")
    page.evaluate("v.setFiles(A.filter(f => f.id !== 'Budget.xlsx')); 0")
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    said = page.evaluate("document.querySelector('.tf .tf-status').textContent")
    check("several to delete, the list losing one meanwhile: the one that went is named (not \"1 files\")", "Deleted Plan.docx." in said, said)
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("v.setFiles([]); v.update({ onAdd: async p => p.map(x => ({ id: x, name: x.split('/').pop() })) }); 0")
    page.focus(".tf .tf-empty .tf-btn")
    page.evaluate("v.addPaths(['/x/one.pdf']); 0")
    page.wait_for_timeout(200)
    check("files added while the focus is on the empty place's button: the focus goes to the list", page.evaluate("document.activeElement.classList.contains('tf-list')"),
          page.evaluate("document.activeElement.className"))
    page.evaluate("v.setFiles([{ id: 's', name: 'Scan', type: 'application/pdf' }, { id: 'p', name: 'Plan.docx' }, { id: 'q', name: 'Plan 2.docx' }, { id: 'l', name: 'Lease.pdf' }]); 0")
    names = page.evaluate("[...document.querySelectorAll('.tf .tf-file')].map(r => r.getAttribute('aria-label'))")
    check("a row whose name does not say its kind is named with it", any(n.startswith("Scan, PDF") for n in names) and not any(n.startswith("Plan.docx, ") and "DOC" in n for n in names), names)
    page.evaluate("v.search('plan'); 0")
    page.wait_for_timeout(700)
    check("a search: how many files show is spoken once the typing stops", "2 of 4 files" in page.evaluate("document.querySelector('.tf .tf-live').textContent"),
          page.evaluate("document.querySelector('.tf .tf-live').textContent"))
    page.evaluate("v.search(''); v.update({ typeAheadMs: 1000 }); v.focus(); 0")
    typed = page.evaluate("""() => { const g = document.querySelector('.tf .tf-list'); const k = key => g.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
      k('x'); const said = document.querySelector('.tf .tf-status').textContent;
      return new Promise(r => setTimeout(() => { k('p'); setTimeout(() => { k('l'); r([said, v.selected()?.name]); }, 850); }, 1100)); }""")
    check("type-ahead: a miss says so; typeAheadMs sets how long a name keeps being typed (\"pl\" from the top, not Lease)",
          typed[0] == "Nothing starts with “x”." and typed[1] == "Plan.docx", typed)
    page.close()

    page = fresh(browser)
    took = page.evaluate("""() => { const all = Array.from({ length: 20000 }, (_, i) => ({ id: i, name: 'File ' + i + '.pdf' }));
      // Hidden, so only the component's own work is timed (not the browser drawing 18,000 rows).
      const host = document.createElement('div'); host.style.display = 'none'; document.body.append(host);
      const w = TaurisFiles.mount(host, { multiple: true, confirmDelete: false, files: all, onDelete: async () => {} });
      w.select(all.slice(0, 2000).map(f => f.id)); const t = performance.now();
      host.querySelector('.tf-list').dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete', bubbles: true }));
      return new Promise(r => { const wait = () => w.files().length === 18000 ? r(performance.now() - t) : setTimeout(wait, 20); wait(); }); }""")
    check("deleting 2,000 of 20,000 files takes one pass, not one per file", took < 3000, took)
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("""v.update({ dropArea: 'element', onAdd: async p => { log.push('A'); return []; } });
      const d = document.createElement('div'); d.style.cssText = 'position:fixed;left:0;top:0;width:400px;height:200px;background:#fff;z-index:5'; document.body.append(d); 0""")
    page.evaluate("__emit('tauri://drag-drop', { paths: ['/x/a.pdf'], position: { x: 100 * devicePixelRatio, y: 100 * devicePixelRatio } }); 0")
    page.wait_for_timeout(100)
    check("dropArea element: a drop over something drawn on top of it is not its", page.evaluate("log") == [], page.evaluate("log"))
    page.close()

    page = fresh(browser, "dark", reduced_motion="reduce")
    page.click(".tf-file:nth-child(2) .tf-c-name")
    bar = page.evaluate("getComputedStyle(document.querySelector('.tf-file[aria-selected=true] .tf-cell')).backgroundSize")
    check("dark: a selected row has a bar at its start (its tint alone is under 3:1 on the list)", bar.startswith("3px"), bar)
    page.close()
    page = fresh(browser)
    page.emulate_media(forced_colors="active")
    page.evaluate("demo.files.busy('Adding…'); 0")
    look = page.evaluate("(() => { const c = getComputedStyle(document.querySelector('.tf-add')); return [c.opacity, c.color]; })()")
    check("Windows high contrast: the Add button while adding is drawn in the system's disabled colour", look[0] == "1", look)
    page.close()

    # ---------- a tenth review ----------
    page = fresh(browser)
    took = page.evaluate("""() => { let all = Array.from({ length: 2000 }, (_, i) => ({ id: i, name: 'File ' + i + '.pdf' }));
      const host = document.createElement('div'); host.style.display = 'none'; document.body.append(host);
      const w = TaurisFiles.mount(host, { multiple: true, confirmDelete: false, files: all,
        onDelete: async f => { all = all.filter(x => x.id !== f.id); w.update({ files: all }); } });
      w.selectAll(); const t = performance.now();
      host.querySelector('.tf-list').dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete', bubbles: true }));
      return new Promise(r => { const wait = () => w.files().length === 0 ? r(performance.now() - t) : setTimeout(wait, 20); wait(); }); }""")
    check("deleting 2,000 files, the app sending its list back after each: one pass a frame, not one a file", took < 3000, took)
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("""v.update({ multiple: true, confirmDelete: false, onDelete: async f => { await wait(30); window.A = A.filter(x => x.id !== f.id); } });
      v.selectAll(); v.focus(); 0""")
    page.keyboard.press("Delete")
    page.wait_for_timeout(45)
    page.evaluate("v.update({ title: 'B', files: B.concat([{ id: 'Extra.pdf', name: 'Extra.pdf', where: 'B' }]) }); 0")
    page.wait_for_timeout(300)
    check("several files being deleted, another place shown between two frames: none of its files vanish",
          sorted(page.evaluate("v.files().map(f => f.where + '/' + f.name)")) == ["B/Budget.xlsx", "B/Extra.pdf", "B/Notes.md", "B/Plan.docx"],
          page.evaluate("v.files().map(f => f.where + '/' + f.name)"))
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("v.update({ onRename: async (f, n) => { await wait(150); log.push(f.where + '/' + n); } }); v.rename('Notes.md'); 0")
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type("Notes old.md")
    page.keyboard.press("Enter")
    page.wait_for_timeout(20)
    page.evaluate("v.update({ title: 'B', files: B }); 0")
    page.wait_for_timeout(300)
    check("a rename waiting for the app when another place is shown: that place's file of the same id keeps its name",
          "Notes.md" in page.evaluate("v.files().map(f => f.name)") and page.evaluate("v.files().every(f => f.where === 'B')"),
          page.evaluate("v.files().map(f => f.where + '/' + f.name)"))
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("window.batches = []; v.update({ confirmDelete: false, onDelete: async (f, b) => { batches.push([f.name, b.index, b.files.length]); } }); v.selectAll(); v.focus(); 0")
    page.keyboard.press("Delete")
    page.wait_for_timeout(200)
    check("onDelete hears which of the batch it is (to ask once, for all, at the first)", page.evaluate("batches.map(b => [b[1], b[2]])") == [[0, 3], [1, 3], [2, 3]],
          page.evaluate("batches"))
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.focus(".tf .tf-q")
    page.evaluate("v.setFiles([]); 0")
    check("the search field with the focus, the list emptied: the focus stays in the component", page.evaluate("document.activeElement.closest('.tf') !== null"),
          page.evaluate("document.activeElement.tagName"))
    page.evaluate("v.setFiles(A); v.search('zzz'); 0")
    page.focus(".tf .tf-nomatch .tf-clear")
    page.evaluate("v.search(''); 0")
    check("Clear search with the focus, the search cleared: the focus goes to the list", page.evaluate("document.activeElement.classList.contains('tf-list')"),
          page.evaluate("document.activeElement.className"))
    ids = page.evaluate("[...document.querySelectorAll('.tf .tf-file')].map(r => r.id)")
    page.evaluate("v.setFiles([{ id: 'First.pdf', name: 'Aaa first.pdf', where: 'A' }, ...A]); 0")
    again = page.evaluate("[...document.querySelectorAll('.tf .tf-file')].slice(1).map(r => r.id)")
    check("a row keeps its id when a file arrives above it (the screen reader is not told of it again)", ids == again, (ids, again))
    page.evaluate("document.querySelector('.tf .tf-file:nth-child(2) .tf-c-name').click(); 0")
    check("a click no pointer made (a screen reader's) selects the row", page.evaluate("v.selected()?.name") == "Budget.xlsx", page.evaluate("v.selected()?.name"))
    page.evaluate("v.setFiles([]); 0")
    described = page.evaluate("(() => { const b = document.querySelector('.tf .tf-empty .tf-btn'); return (b.getAttribute('aria-describedby') || '').split(' ').map(i => document.getElementById(i)?.textContent); })()")
    check("the empty place's button is described by what the place says", len(described) == 2 and all(described), described)
    page.close()

    # An input method composing, through Chromium's debugging protocol (WebKit has none here).
    if not WEBKIT:
        page = fresh(browser)
        cdp = page.context.new_cdp_session(page)
        page.focus(".tf-q")
        cdp.send("Input.imeSetComposition", {"selectionStart": 1, "selectionEnd": 1, "text": "こ"})
        page.wait_for_timeout(100)
        shown_while = page.locator(".tf-file").count()
        cdp.send("Input.insertText", {"text": "こん"})
        page.wait_for_timeout(100)
        check("the search waits for an input method's text (the list is not filtered by half a word)", shown_while == 8, shown_while)
        page.close()

    for accent, dark, var in (("#039250", False, "--tauris-accent"), ("#ffd400", False, "--tauris-accent"), ("#000080", True, "--tauris-accent"),
                              ("#ffd400", False, "--tf-accent"), ("#000080", True, "--tf-accent"), ("#0d6efd", False, "--tf-accent")):
        page = fresh(browser, "dark" if dark else "light", reduced_motion="reduce")
        page.add_style_tag(content=f":root {{ {var}: {accent}; }}")
        page.evaluate("__emit('tauri://drag-enter', { paths: ['/a.pdf'] }); 0")
        lines = [css(page, ".tf-drop-title", "color"), css(page, ".tf-panel", "background-color")]
        page.evaluate("__emit('tauri://drag-leave', null); demo.files.setFiles([]); 0")
        page.wait_for_timeout(50)
        pair = [css(page, ".tf-empty .tf-primary", "color"), css(page, ".tf-empty .tf-primary", "background-color")] + lines
        page.hover(".tf-empty .tf-primary")
        page.wait_for_timeout(50)
        hover = [css(page, ".tf-empty .tf-primary", "color"), css(page, ".tf-empty .tf-primary", "background-color")]
        page.close()
        ratios = contrasts(browser, [pair[:2], pair[2:], hover])
        check(f"{var} {accent} alone ({'dark' if dark else 'light'}): text on it, on it hovered, and the accent as text all read",
              ratios[0] >= 4.0 and ratios[1] >= 4.5 and ratios[2] >= 4.5 and hover[1] != pair[1]
              and lines[0] not in ("rgb(38, 117, 191)", "rgb(106, 166, 224)"), (pair, hover, ratios))

    # ---------- a twelfth review: lists that come and go, and the focus with them ----------
    page = fresh(browser)
    page.evaluate(MOUNT, None)
    # The app sends the old place's list, then shows another place, in one go: the old list is never taken.
    page.evaluate("""v.update({ confirmDelete: false, onDelete: async f => { await wait(20); v.setFiles(A.filter(x => x !== f)); v.update({ title: 'B', files: B }); } });
      v.selectAll(); v.focus(); 0""")
    page.keyboard.press("Delete")
    page.wait_for_timeout(300)
    got = page.evaluate("v.files().map(f => f.where + '/' + f.name)")
    check("several deleting, the app's list for the old place sent and then another place: the new place's files stay",
          got == ["B/Plan.docx", "B/Budget.xlsx", "B/Notes.md"], got)
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("""v.update({ confirmDelete: false, onDelete: async f => { await wait(20); if (f.name === 'Plan.docx') v.update({ files: A.filter(x => x !== f), sort: { key: 'size', up: false }, multiple: false }); } });
      v.selectAll(); v.focus(); 0""")
    page.keyboard.press("Delete")
    page.wait_for_timeout(300)
    look = (page.get_attribute(".tf-th.tf-c-size", "aria-sort"), page.get_attribute(".tf-list", "aria-multiselectable"))
    check("update({ files, sort, multiple }) while several are deleted: the files wait for the frame, the rest applies at once",
          look == ("descending", "false"), look)
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("v.update({ confirmDelete: false, onDelete: async () => log.push('deleted') }); v.update({ onDelete: undefined }); v.select('Plan.docx'); v.focus(); 0")
    page.keyboard.press("Delete")
    page.wait_for_timeout(100)
    check("update({ onDelete: undefined }) takes the handler away (as leaving it out of mount does)",
          page.evaluate("log") == [] and len(page.evaluate("v.files()")) == 3 and page.evaluate("document.body.firstElementChild.querySelectorAll('.tf-ib[data-act=delete]').length") == 0, page.evaluate("log"))
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    # An add on its way for A; the app shows an empty list, then another place's (other files, same title).
    page.evaluate("""v.update({ onAdd: async p => { await wait(150); return p.map(x => ({ id: x, name: x.split('/').pop() })); } });
      v.addPaths(['/u/Late.pdf']); setTimeout(() => { v.setFiles([]); v.setFiles([{ id: 'c1', name: 'Other.pdf' }]); }, 30); 0""")
    page.wait_for_timeout(400)
    got = page.evaluate("v.files().map(f => f.name)")
    check("an add for one place, the app going through an empty list to another place's: the file is not added there", got == ["Other.pdf"], got)
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    # The person deletes the last file, then adds one: the same place, so the new file is selected.
    page.evaluate("""v.setFiles([A[0]]); v.update({ confirmDelete: false, onDelete: async () => v.setFiles([]),
      onAdd: async p => { const out = p.map(x => ({ id: x, name: x.split('/').pop() })); v.setFiles(out); await wait(20); return out; } });
      v.select('Plan.docx'); v.focus(); 0""")
    page.keyboard.press("Delete")
    page.wait_for_timeout(100)
    page.evaluate("v.addPaths(['/u/First.pdf']); 0")
    page.wait_for_timeout(200)
    got = page.evaluate("[v.files().map(f => f.name), v.selected()?.name ?? null]")
    check("the last file deleted, then one added: it is added and selected (the same place)", got == [["First.pdf"], "First.pdf"], got)
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("""window.seen = []; v.update({ confirmDelete: false, onDelete: async (f, { index }) => { if (index === 1) seen.push(v.selection().map(x => x.name)); await wait(30); } });
      v.selectAll(); v.focus(); 0""")
    page.keyboard.press("Delete")
    page.wait_for_timeout(300)
    got = page.evaluate("seen")
    check("while several are deleted, one already gone is not in selection() any more", got and "Budget.xlsx" not in got[0], got)
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("""v.setFiles(Array.from({ length: 10 }, (_, i) => ({ id: 'f' + i, name: 'File ' + i + '.txt', size: i })));
      window.removed = 0; new MutationObserver(ms => { for (const m of ms) removed += m.removedNodes.length; })
        .observe(document.querySelector('.tf-tbody'), { childList: true }); 0""")
    page.wait_for_timeout(50)
    page.evaluate("v.setFiles(v.files().filter(f => f.id !== 'f4')); 0")
    page.wait_for_timeout(50)
    got = page.evaluate("[removed, document.querySelector('.tf-tbody').children.length]")
    check("one file of ten gone: one row is taken out, the nine others stay where they are", got == [1, 9], got)
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("v.update({ onDelete: async () => {} }); v.select('Plan.docx'); v.focus(); 0")
    page.keyboard.press("Delete")
    page.wait_for_selector(".tf-veil:not([hidden])")
    page.evaluate("v.setFiles([]); 0")
    page.wait_for_timeout(50)
    got = page.evaluate("[document.querySelector('.tf-veil').hidden, document.activeElement.closest('.tf') !== null]")
    check("the delete question, the app's list emptied: it closes, and the focus stays in the component", got == [True, True], got)
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("v.update({ onDelete: async () => {} }); v.select('Plan.docx'); v.focus(); 0")
    page.keyboard.press("Shift+F10")
    page.wait_for_selector(".tmn-menu")
    page.evaluate("v.setFiles([]); 0")
    page.keyboard.press("Escape")
    page.wait_for_timeout(50)
    check("the row menu open, the list emptied, then Escape: the focus stays in the component",
          page.evaluate("document.activeElement.closest('.tf') !== null"), page.evaluate("document.activeElement.outerHTML.slice(0, 80)"))
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("document.querySelector('.tf-th.tf-c-by .tf-sort').focus(); 0")
    page.evaluate("v.update({ columns: ['kind', 'name', 'size'] }); 0")
    got = page.evaluate("document.activeElement.closest('.tf-th')?.dataset.col ?? document.activeElement.className")
    check("the focus on a column header the app takes away: the header nearest it", got == "size", got)
    page.close()

    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("v.update({ onAdd: async () => [] }); v.setFiles([]); 0")
    with_add = (page.get_attribute(".tf-empty", "aria-describedby"), page.is_visible(".tf-empty .tf-primary"))
    page.evaluate("v.update({ onAdd: undefined }); 0")
    without = page.get_attribute(".tf-empty", "aria-describedby")
    check("the empty place's text is read once: by its button, or by the place when there is no button",
          with_add[0] is None and with_add[1] and without and without.endswith("-empty-text"), (with_add, without))
    page.close()

    # 20,000 files shown: only the rows in view are drawn, so nothing waits on all of them.
    page = fresh(browser)
    big = page.evaluate("""() => { const all = Array.from({ length: 20000 }, (_, i) => ({ id: i, name: 'File ' + String(i).padStart(5, '0') + '.pdf', size: i }));
      const host = document.createElement('div'); host.id = 'big'; host.style.cssText = 'height:400px;width:700px'; document.body.prepend(host);
      let t = performance.now(); window.w = TaurisFiles.mount(host, { multiple: true, files: all }); host.getBoundingClientRect(); const mount = performance.now() - t;
      window.all = all; return { mount, drawn: host.querySelectorAll('.tf-file').length, count: host.querySelector('.tf-list').getAttribute('aria-rowcount') }; }""")
    page.evaluate("w.select(0); w.focus(); 0")
    t0 = page.evaluate("performance.now()")
    for _ in range(10):
        page.keyboard.press("ArrowDown")
    down = (page.evaluate("performance.now()") - t0) / 10
    page.keyboard.press("End")
    page.wait_for_timeout(50)
    end = page.evaluate("""(() => { const g = document.querySelector('#big .tf-list'); const a = document.getElementById(g.getAttribute('aria-activedescendant'));
      const r = a.getBoundingClientRect(), v = g.getBoundingClientRect(); return [a.querySelector('.tf-c-name').textContent, a.getAttribute('aria-rowindex'), r.top >= v.top && r.bottom <= v.bottom + 0.5]; })()""")
    timed = page.evaluate("""() => { let t = performance.now(); w.search('File 1'); const search = performance.now() - t;
      w.search(''); const next = all.slice(); next[5] = { ...next[5], name: 'Renamed.pdf' };
      t = performance.now(); w.setFiles(next); document.getElementById('big').getBoundingClientRect(); const set = performance.now() - t;
      return { search, set, drawn: document.querySelectorAll('#big .tf-file').length }; }""")
    page.evaluate("document.querySelector('#big .tf-list').scrollTop = 250000; 0")
    page.wait_for_timeout(100)
    middle = page.evaluate("""(() => { const g = document.querySelector('#big .tf-list').getBoundingClientRect();
      return document.elementFromPoint(g.left + 200, g.top + 100)?.closest('.tf-file')?.querySelector('.tf-c-name').textContent; })()""")
    check("20,000 files: mounted, stepped through, searched and given a new list quickly, drawing only the rows in view",
          big["mount"] < 600 and big["drawn"] < 80 and big["count"] == "20001" and down < 40 and timed["search"] < 200 and timed["set"] < 300
          and timed["drawn"] < 80, (big, down, timed))
    check("and End shows the last file (row 20,001 of 20,001), scrolling shows the files there",
          end == ["File 19999.pdf", "20001", True] and middle is not None and 9990 <= int(middle[5:10]) <= 10010, (end, middle))
    page.close()

    # Options no other test reached.
    page = fresh(browser)
    page.evaluate(MOUNT, None)
    page.evaluate("v.setFiles([{ id: 'd', name: 'Dated.pdf', added: '2026-03-04T10:00:00Z' }]); v.update({ formatDate: (d, f) => 'Y' + d.getUTCFullYear() + ' ' + f.name }); 0")
    added = page.inner_text(".tf-file .tf-c-added")
    page.evaluate("v.focusSearch(); 0")
    check("formatDate writes the Added column; focusSearch() puts the focus in the search field",
          added == "Y2026 Dated.pdf" and page.evaluate("document.activeElement.classList.contains('tf-q')"), added)
    page.close()
    page = browser.new_page()
    page.add_init_script(library_script())
    page.goto((HERE / "page.html").as_uri())
    page.evaluate("""(() => { const h = document.createElement('div'); h.style.height = '200px'; document.body.append(h);
      TaurisFiles.mount(h, { styles: false, files: [{ id: 1, name: 'a.txt' }] }); return 0; })()""")
    check("styles: false adds no stylesheet (the app brings its own)",
          page.evaluate("document.adoptedStyleSheets.length") == 0 and page.locator(".tf-file").count() == 1)
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
