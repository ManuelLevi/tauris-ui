"""Headless tests for the finder (web/finder.js), on test/finder_demo.html.

    python test/finder_run.py

Nothing touches the screen. TAURIS_TEST_CHROMIUM=1 or TAURIS_TEST_WEBKIT=1
runs it in CI's browsers (see engine.py).
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from engine import launch

HERE = Path(__file__).parent
WEB = HERE.parent / "web"
DEMO = HERE / "finder_demo.html"
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        failures.append(name)


def fresh(browser, scheme="light"):
    page = browser.new_page(viewport={"width": 1000, "height": 640}, device_scale_factor=2, color_scheme=scheme)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.goto(DEMO.as_uri())
    page.evaluate("localStorage.clear(); 0")
    return page


def finder_key(page):
    return "Meta+KeyK" if page.evaluate("/mac/i.test(navigator.userAgentData?.platform || navigator.platform)") else "Control+KeyK"


def rows(page):
    return page.evaluate("[...document.querySelectorAll('.tfd-row')].map(r => r.querySelector('.tfd-label').textContent)")


def groups(page):
    return page.evaluate("[...document.querySelectorAll('.tfd-group')].map(g => g.getAttribute('aria-label'))")


def chosen(page):
    return page.evaluate("document.querySelector('.tfd-row[aria-selected=true] .tfd-label')?.textContent ?? null")


def said(page):
    return page.evaluate("said.splice(0)")


def search(page, text):
    page.fill(".tfd-input", text)
    page.wait_for_timeout(20)


with sync_playwright() as p:
    browser = launch(p)

    # ---------- opening ----------
    page = fresh(browser)
    page.focus("#field")
    page.keyboard.press(finder_key(page))
    opened = (page.is_visible(".tfd"), page.evaluate("document.activeElement.classList.contains('tfd-input')"), said(page))
    check("⌘K (Ctrl+K) opens it, the keys in its field", opened == (True, True, [["open"]]), opened)
    a11y = page.evaluate("""(() => { const i = document.querySelector('.tfd-input'); return [document.querySelector('.tfd').getAttribute('role'), i.getAttribute('role'),
      i.getAttribute('aria-controls') === document.querySelector('.tfd-list').id, document.querySelector('.tfd-list').getAttribute('role')]; })()""")
    check("a dialog with a combobox over a listbox", a11y == ["dialog", "combobox", True, "listbox"], a11y)
    check("nothing typed: the latest items (no recent ones yet)", groups(page) == ["Latest"] and rows(page)[0] == "Sign the lease", (groups(page), rows(page)))
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)  # its fade
    check("Esc closes it (with a short fade) and the focus goes back", not page.is_visible(".tfd") and page.evaluate("document.activeElement.id") == "field"
          and said(page) == [["close", False]])
    page.close()

    # ---------- finding ----------
    page = fresh(browser)
    page.evaluate("finder.open(); 0")
    said(page)
    search(page, "north")
    check("a word at a label's start: found first, the match marked, the count said (Stripe too, by its e-mail address)",
          rows(page) == ["Northwind Launch", "Stripe"] and page.inner_text(".tfd-row mark") == "North" and page.inner_text(".tfd-count") == "2", (rows(page), page.inner_text(".tfd-count")))
    search(page, "rp")
    check("initials find it: “rp” is Revenue Pipeline", rows(page)[:1] == ["Revenue Pipeline"], rows(page))
    search(page, "cafe")
    check("accents fold: “cafe” finds Café opening", rows(page) == ["Café opening"], rows(page))
    search(page, "parking")
    check("a `more` text is searched (letters together) and shown in the detail", rows(page) == ["Sign the lease"]
          and "parking" in page.inner_text(".tfd-row .tfd-snip"), (rows(page), page.inner_text(".tfd-list")))
    search(page, "hunter2")
    check("what the app leaves out of `more` (a secret) is never found", rows(page) == [] and "Nothing matches" in page.inner_text(".tfd-empty"), rows(page))
    search(page, "l")
    check("results by group, each group cut at its limit (2 of 3 projects), saying so",
          "Projects" in groups(page) and page.evaluate("document.querySelectorAll('[aria-label=Projects] .tfd-row').length") == 2
          and "2 of" in page.inner_text("[aria-label=Projects] .tfd-group-head"), (groups(page), page.inner_text(".tfd-list")))
    search(page, "deck")
    check("the group with the best match comes first; a done task is dimmed", groups(page) == ["Documents", "Tasks"]
          and page.evaluate("document.querySelector('.tfd-dim .tfd-label').textContent") == "Send the board deck", groups(page))
    page.close()

    # ---------- the keys and the mouse ----------
    page = fresh(browser)
    page.focus("#field")
    page.evaluate("finder.open(); 0")
    said(page)
    search(page, "e")
    first = chosen(page)
    page.keyboard.press("ArrowDown")
    second = chosen(page)
    page.keyboard.press("Control+KeyP")
    back_up = chosen(page)
    page.keyboard.press("Tab")
    next_group = page.evaluate("document.querySelector('.tfd-row[aria-selected=true]').closest('.tfd-group').getAttribute('aria-label')")
    check("↓ and ⌃P move, Tab goes to the next group, the field keeps the keys",
          first == rows(page)[0] and second == rows(page)[1] and back_up == first and next_group != groups(page)[0]
          and page.evaluate("document.activeElement.classList.contains('tfd-input')"), (first, second, back_up, next_group))
    active = page.evaluate("document.querySelector('.tfd-input').getAttribute('aria-activedescendant') === document.querySelector('.tfd-row[aria-selected=true]').id")
    check("the field names the chosen row (aria-activedescendant)", active)
    page.keyboard.press("Shift+F10")
    menu = said(page)
    check("the menu key on a result: onContextMenu, the panel stays", len(menu) == 1 and menu[0][0] == "menu" and menu[0][2] == "keyboard"
          and page.evaluate("finder.isOpen"), menu)
    page.keyboard.press("Enter")
    picked = said(page)
    check("Enter picks the chosen one: closed, then onPick", page.evaluate("finder.isOpen") is False and picked[-1][0] == "pick" and picked[-1][2] == "keyboard"
          and ["close", True] in picked, picked)
    page.evaluate("finder.open(); 0")
    check("what was picked comes back as Recent", groups(page)[0] == "Recent" and rows(page)[0] == page.inner_text("#shown"), (groups(page), rows(page)))
    search(page, "atlas")
    page.click(".tfd-row")
    check("a click picks too", said(page)[-1] == ["pick", "p3", "mouse"] and page.inner_text("#shown") == "Atlas")
    page.evaluate("finder.open(); 0")
    search(page, "stripe")
    page.click(".tfd-row", button="right")
    check("a right click on a result: onContextMenu, the panel stays", said(page)[-1] == ["menu", "w1", "mouse"] and page.evaluate("finder.isOpen"))
    page.mouse.click(10, 600)
    check("a press beside the panel closes it", page.evaluate("finder.isOpen") is False)
    page.close()

    # ---------- MLPC's: ⌘↩ for a new tab, long text, ⌘K again ----------
    page = fresh(browser)
    page.evaluate("finder.open(); 0")
    said(page)
    cmd_enter = "Meta+Enter" if page.evaluate("/mac/i.test(navigator.userAgentData?.platform || navigator.platform)") else "Control+Enter"
    search(page, "north")
    page.keyboard.press("Shift+Enter")
    page.keyboard.press("Alt+Enter")
    still = page.evaluate("finder.isOpen")
    strip = page.inner_text(".tfd-keys")
    page.keyboard.press(cmd_enter)
    check("⌘↩ picks with cmd (a new tab); ⇧↩ and ⌥↩ do nothing; the key strip says what ⌘↩ does (labels.openAlt)",
          still and "New Tab" in strip and said(page)[-1] == ["pick", "p1", "keyboard", "cmd"], (still, strip))
    page.evaluate("finder.open(); 0")
    search(page, "atlas")
    page.click(".tfd-row", modifiers=["ControlOrMeta"])
    check("a ⌘-click picks with cmd too", said(page)[-1] == ["pick", "p3", "mouse", "cmd"], page.evaluate("said"))
    page.evaluate("finder.open(); 0")
    search(page, "rp")
    check("strict items match only with their letters together: “rp” finds Revenue Pipeline, not “Rang the plumber”", rows(page) == ["Revenue Pipeline"], rows(page))
    search(page, "plumber")
    check("and they match with them together", rows(page) == ["Rang the plumber about the pipes"], rows(page))
    search(page, "meeting")
    check("a label cut short is whole in its tooltip", page.evaluate("document.querySelector('.tfd-row').title").startswith("A very long log entry"))
    page.keyboard.press(finder_key(page))
    sel = page.evaluate("(() => { const i = document.querySelector('.tfd-input'); return [i.selectionStart, i.selectionEnd, i.value.length, document.activeElement === i]; })()")
    check("⌘K with it open selects the field's text, to type a new search at once", sel[0] == 0 and sel[1] == sel[2] == 7 and sel[3], sel)
    page.close()

    # ---------- the look ----------
    for scheme in ("light", "dark"):
        page = fresh(browser, scheme)
        page.evaluate("finder.open(); 0")
        search(page, "north")
        c = page.evaluate("""(() => { const s = q => getComputedStyle(document.querySelector(q)); return [s('.tfd-row[aria-selected=true]').color, s('.tfd-row[aria-selected=true]').backgroundColor,
          s('.tfd-group-head').color, s('.tfd').backgroundColor]; })()""")
        ratios = page.evaluate("""(cs) => { const rgb = c => { const cv = document.createElement('canvas').getContext('2d'); cv.fillStyle = c; cv.fillRect(0, 0, 1, 1); return [...cv.getImageData(0, 0, 1, 1).data].slice(0, 3); };
          const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
          const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return Math.round((x + 0.05) / (y + 0.05) * 100) / 100; };
          return [ratio(cs[0], cs[1]), ratio(cs[2], cs[3])]; }""", c)
        check(f"{scheme}: the chosen row and the group headings read (4.5:1)", min(ratios) >= 4.5, (c, ratios))
        page.close()

    # ---------- as the plugin delivers it ----------
    page = browser.new_page(viewport={"width": 800, "height": 500})
    page.add_init_script((WEB / "finder.js").read_text().replace('"__TAURIS_FINDER_CSS__"', json.dumps((WEB / "finder.css").read_text())))
    page.goto((HERE / "csp.html").as_uri())
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    before = page.evaluate("document.adoptedStyleSheets.length")
    page.evaluate("window.f = TaurisFinder.mount({ items: [{ id: 1, label: 'One' }] }); f.open('o'); 0")
    check("under a strict content policy: its stylesheet once it is used, and no error",
          before == 0 and page.evaluate("document.adoptedStyleSheets.length") == 1 and not errors and page.locator(".tfd-row").count() == 1, errors)
    page.evaluate("f.destroy(); 0")
    check("destroy() closes it", page.locator(".tfd").count() == 0)
    page.close()

    browser.close()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
