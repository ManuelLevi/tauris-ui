"""Headless tests for the dialogs (web/dialog.js), on test/dialog_demo.html.

    python test/dialog_run.py

Nothing touches the screen. TAURIS_TEST_CHROMIUM=1 or TAURIS_TEST_WEBKIT=1
runs it in CI's browsers (see engine.py).
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from engine import WEBKIT, launch

HERE = Path(__file__).parent
WEB = HERE.parent / "web"
DEMO = HERE / "dialog_demo.html"
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        failures.append(name)


def fresh(browser, scheme="light"):
    page = browser.new_page(viewport={"width": 1000, "height": 700}, device_scale_factor=2, color_scheme=scheme)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.goto(DEMO.as_uri())
    return page


def focused(page):
    return page.evaluate("document.activeElement.id || document.activeElement.textContent.trim().slice(0, 30)")


def ask(page, script):
    """Starts a dialog; its answer lands in window.answer."""
    page.evaluate("window.answer = undefined; (" + script + ").then(a => { window.answer = a === undefined ? '(none)' : a; }); 0")
    page.wait_for_selector(".tdl")


def answer(page):
    page.wait_for_function("window.answer !== undefined", timeout=3000)
    return page.evaluate("window.answer")


with sync_playwright() as p:
    browser = launch(p)

    # ---------- a question ----------
    page = fresh(browser)
    page.focus("#list")
    ask(page, "TaurisDialog.confirm({ title: 'Delete “Atlas”?', message: 'Its files go too.\\n\\nThis cannot be undone.', ok: 'Delete', danger: true })")
    a11y = page.evaluate("""(() => { const d = document.querySelector('.tdl'); return [d.getAttribute('role'), d.getAttribute('aria-modal'),
      document.getElementById(d.getAttribute('aria-labelledby')).textContent, document.getElementById(d.getAttribute('aria-describedby')).textContent.includes('cannot be undone')]; })()""")
    check("a question: an alert dialog, named by its title and described by its message", a11y == ["alertdialog", "true", "Delete “Atlas”?", True], a11y)
    check("it starts on Cancel (Enter never deletes by accident); the page under it is out of reach",
          focused(page) == "Cancel" and page.evaluate("document.querySelector('main').inert"), focused(page))
    page.keyboard.press("Tab")
    on_delete = focused(page)
    page.keyboard.press("Tab")
    check("Tab goes round inside it", on_delete == "Delete" and focused(page) == "Cancel", (on_delete, focused(page)))
    page.keyboard.press("Enter")
    check("Enter on Cancel says no; the focus goes back to the list, the page in reach again",
          answer(page) is False and focused(page) == "list" and not page.evaluate("document.querySelector('main').inert"), focused(page))
    ask(page, "TaurisDialog.confirm({ title: 'Delete?', ok: 'Delete', danger: true })")
    page.click(".tdl-danger")
    check("its red button says yes", answer(page) is True)
    ask(page, "TaurisDialog.confirm({ title: 'Delete?' })")
    page.keyboard.press("Escape")
    no_esc = answer(page)
    ask(page, "TaurisDialog.confirm({ title: 'Delete?' })")
    page.mouse.click(5, 690)
    check("Esc, and a press beside it, say no", no_esc is False and answer(page) is False)
    # native: the system's alert through the plugin; without it, the page asks
    page.evaluate("""window.asked = []; window.__TAURI__ = { core: { invoke: async (c, a) => { asked.push([c, a.ok, a.warning]); return true; } } }; 0""")
    page.evaluate("window.answer = undefined; TaurisDialog.confirm({ title: 'Quit?', ok: 'Quit', native: true, danger: true }).then(a => { window.answer = a; }); 0")
    check("native: asked with the system's alert (the plugin's ask), nothing drawn in the page",
          answer(page) is True and page.evaluate("asked") == [["plugin:tauris-ui|ask", "Quit", True]] and page.locator(".tdl").count() == 0)
    page.evaluate("window.__TAURI__.core.invoke = async () => { throw 'The file dialogs need tauris-ui\\'s files feature'; }; 0")
    ask(page, "TaurisDialog.confirm({ title: 'Quit?', native: true })")
    check("native without the system's alert: asked in the page", page.locator(".tdl").count() == 1)
    page.keyboard.press("Escape")
    page.close()

    # ---------- a form ----------
    page = fresh(browser)
    page.focus("#field")
    ask(page, "newProject()")
    labels = page.evaluate("[...document.querySelectorAll('.tdl-label')].map(l => l.textContent)")
    layout = page.evaluate("""(() => { const l = document.querySelector('.tdl-label').getBoundingClientRect(), f = document.querySelector('.tdl-input').getBoundingClientRect();
      return [getComputedStyle(document.querySelector('.tdl-label')).textAlign, l.right <= f.left, Math.round(f.height)]; })()""")
    check("a form in the Swing layout: right-aligned “Label:” beside each field, 26px fields",
          labels[:4] == ["Name:", "Team:", "Budget:", "Notes:"] and layout == ["right", True, 26], (labels, layout))
    ph = page.evaluate("""(() => { const i = document.querySelector('.tdl-input'); i.value = 'x'; const typed = getComputedStyle(i).color; i.value = '';
      return [getComputedStyle(i, '::placeholder').color, typed]; })()""")
    # (WebKit gives a placeholder's colour as its field's to a script.)
    check("an example placeholder, dimmer than typed text", WEBKIT or ph[0] != ph[1], ph)
    check("it starts in its first field; its hint on the kept line", focused(page).endswith("-name") and page.inner_text(".tdl-line-hint") == "Names are unique.",
          focused(page))
    page.wait_for_timeout(250)  # its opening (a slight scale) done
    line_h = page.evaluate("document.querySelector('.tdl').getBoundingClientRect().height")
    page.keyboard.press("Enter")
    tip = (page.inner_text(".tdl-cell:has(#" + page.evaluate("document.activeElement.id") + ") .tdl-tip"), page.evaluate("document.activeElement.getAttribute('aria-invalid')"))
    check("a needed field left empty: a balloon under it, the field marked and given the keys", tip == ("Name is needed.", "true"), tip)
    page.keyboard.type("Atlas")
    cleared = page.evaluate("document.querySelector('.tdl-tip:not([hidden])') === null")
    page.keyboard.press("Enter")
    taken = page.evaluate("document.querySelector('.tdl-tip:not([hidden])')?.textContent")
    check("typing clears it; the app's check (validate) refuses a taken name the same way", cleared and taken == "That name is taken.", (cleared, taken))
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type("Orion")
    page.fill("[id$='-budget']", "5000000")
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    refused = page.inner_text(".tdl-line-error")
    same_h = page.evaluate("document.querySelector('.tdl').getBoundingClientRect().height") == line_h
    check("a throw from submit: its message on the kept line, the hint gone, the dialog the same height, still open",
          refused == "The server refused a budget that large." and same_h and page.locator(".tdl").count() == 1, (refused, same_h))
    page.fill("[id$='-budget']", "5000")
    page.check("[id$='-public']")
    page.keyboard.press("Enter")
    got = answer(page)
    check("then it saves and closes with the values; the focus goes back", got == {"name": "Orion", "team": "Team A", "budget": 5000, "notes": "", "public": True}
          and page.evaluate("said") == [["saved", "Orion"]] and focused(page) == "field", (got, focused(page)))
    ask(page, "newProject()")
    page.focus("[id$='-notes']")
    page.keyboard.type("line one")
    page.keyboard.press("Enter")
    page.keyboard.type("line two")
    in_area = page.locator(".tdl").count() == 1 and page.input_value("[id$='-notes']") == "line one\nline two"
    page.keyboard.press("Escape")
    check("Enter in a text area is a new line; Esc cancels (null)", in_area and answer(page) is None)
    page.close()

    # ---------- a review before saving ----------
    page = fresh(browser)
    ask(page, "editProject()")
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type("Atlas Prime")
    page.keyboard.press("Enter")
    rows = page.evaluate("[...document.querySelectorAll('.tdl-review-rows tr')].map(r => r.textContent)")
    check("review: the changes, “Field: old → new”, before saving (only those changed)", rows == ["Name:Atlas → Atlas Prime"]
          and page.is_hidden(".tdl-page") and focused(page) == "Save", (rows, focused(page)))
    page.keyboard.press("Escape")
    back = page.is_visible(".tdl-page") and page.evaluate("document.activeElement.value") == "Atlas Prime"
    page.keyboard.press("Enter")
    page.keyboard.press("Enter")
    check("Esc during the review goes back to the fields; Save saves", back and answer(page) == {"name": "Atlas Prime", "owner": "Ana"}, back)
    ask(page, "TaurisDialog.review({ title: 'Save Changes', rows: [{ field: 'Password', after: 'changed' }, { field: 'Name', before: 'A', after: 'B' }] })")
    rows = page.evaluate("[...document.querySelectorAll('.tdl-review-rows tr')].map(r => r.textContent)")
    page.keyboard.press("Enter")
    check("a review on its own: a secret says only that it changed", rows == ["Password:changed", "Name:A → B"] and answer(page) is True, rows)
    page.close()

    # ---------- the sheets ----------
    page = fresh(browser)
    ask(page, """TaurisDialog.shortcuts({ groups: [
      { title: 'Everywhere', items: [{ label: 'Find anything', keys: ['⌘K'] }, { label: 'Back or forward', keys: ['⌘[', '⌘]'], either: true }] },
      { title: 'Tasks', items: [{ label: 'New task', keys: ['⌘N'] }, { label: 'Done', keys: ['⌘↩'] }, { label: 'Delete', keys: ['⌫'] }] },
      { title: 'People', items: [{ label: 'New person', keys: ['⌘⇧N'] }] },
      { title: 'Passwords', items: [{ label: 'Copy', keys: ['⌘C'] }] } ] })""")
    sheet = page.evaluate("""(() => [document.querySelectorAll('.tdl-column').length, [...document.querySelectorAll('.tdl-column')].map(c => c.querySelectorAll('dt').length),
      document.querySelectorAll('.tdl-key').length, [...document.querySelectorAll('.tdl-keys')][1].textContent])()""")
    check("Keyboard Shortcuts: groups in three columns of about the same height, keys as keycaps, “either” rows",
          sheet[0] == 3 and max(sheet[1]) - min(sheet[1]) <= 2 and sheet[2] == 8 and sheet[3] == "⌘[ or ⌘]", sheet)
    page.keyboard.press("Enter")
    check("Done closes it", answer(page) == "(none)")
    ask(page, "TaurisDialog.about({ name: 'MLPC', mark: '🗂', description: 'Projects, KPIs and people.', rows: [['Version', '2.4.0'], ['Signed in as', 'Ana']] })")
    about = page.evaluate("[document.querySelector('.tdl-title').textContent, document.querySelector('.tdl-about-name').textContent, [...document.querySelectorAll('.tdl-about-rows dt')].map(d => d.textContent)]")
    page.keyboard.press("Escape")
    check("About: its mark, name, description and key/value rows; Esc closes it", about == ["About MLPC", "MLPC", ["Version", "Signed in as"]] and answer(page) == "(none)", about)
    page.close()

    # ---------- a titled panel ----------
    page = fresh(browser)
    head = page.evaluate("""(() => { const p = document.getElementById('kpis'), h = p.querySelector('.tdl-panel-head'), r = p.getBoundingClientRect(), hr = h.getBoundingClientRect();
      return [h.textContent, Math.round(hr.top + hr.height / 2 - r.top), p.getAttribute('aria-label'), p.querySelectorAll('p').length]; })()""")
    check("a titled panel: its title, count and buttons on its top line; its content stays", head[0] == "KPIs· 2+ New KPI…Open" and abs(head[1]) <= 1 and head[2] == "KPIs" and head[3] == 2, head)
    page.click(".tdl-panel-action")
    page.click(".tdl-panel-action[aria-disabled=true]", force=True)
    page.evaluate("panel.update({ count: 3 }); 0")
    check("its buttons act (a disabled one does not); update() changes the count", page.evaluate("said") == ["new kpi"] and "· 3" in page.inner_text(".tdl-panel-head"))
    page.close()

    # ---------- the look ----------
    for scheme in ("light", "dark"):
        page = fresh(browser, scheme)
        ask(page, "newProject()")
        page.keyboard.press("Enter")
        c = page.evaluate("""(() => { const s = q => getComputedStyle(document.querySelector(q)); return [s('.tdl-label').color, s('.tdl').backgroundColor,
          s('.tdl-primary').color, s('.tdl-primary').backgroundColor, s('.tdl-tip').color, s('.tdl-tip').backgroundColor, s('.tdl-line-hint').color]; })()""")
        ratios = page.evaluate("""(cs) => { const rgb = c => { const cv = document.createElement('canvas').getContext('2d'); cv.fillStyle = c; cv.fillRect(0, 0, 1, 1); return [...cv.getImageData(0, 0, 1, 1).data].slice(0, 3); };
          const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
          const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return Math.round((x + 0.05) / (y + 0.05) * 100) / 100; };
          return [ratio(cs[0], cs[1]), ratio(cs[2], cs[3]), ratio(cs[4], cs[5]), ratio(cs[6], cs[1])]; }""", c)
        check(f"{scheme}: labels, the default button, a field's refusal and the hint read (4.5:1)", min(ratios) >= 4.5, (c, ratios))
        page.close()

    # ---------- as the plugin delivers it ----------
    page = browser.new_page(viewport={"width": 800, "height": 500})
    page.add_init_script((WEB / "dialog.js").read_text().replace('"__TAURIS_DIALOG_CSS__"', json.dumps((WEB / "dialog.css").read_text())))
    page.goto((HERE / "csp.html").as_uri())
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    before = page.evaluate("document.adoptedStyleSheets.length")
    page.evaluate("TaurisDialog.confirm({ title: 'Go?' }); 0")
    check("under a strict content policy: its stylesheet once it is used, and no error",
          before == 0 and page.evaluate("document.adoptedStyleSheets.length") == 1 and not errors and page.evaluate("TaurisDialog.isOpen"), errors)
    page.close()

    browser.close()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
