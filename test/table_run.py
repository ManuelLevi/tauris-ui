"""Headless tests for the data table (web/table.js), on test/table_demo.html.

    python test/table_run.py [shots-dir]

Nothing touches the screen. TAURIS_TEST_CHROMIUM=1 or TAURIS_TEST_WEBKIT=1
runs it in CI's browsers (see engine.py).
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from engine import WEBKIT, launch, settled

HERE = Path(__file__).parent
WEB = HERE.parent / "web"
DEMO = HERE / "table_demo.html"
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
SIZE = {"width": 760, "height": 560}
failures = []


def check(name, ok, detail=""):
    ok, detail = settled(ok, detail)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        failures.append(name)


def fresh(browser, scheme="light"):
    extra = {} if WEBKIT else {"permissions": ["clipboard-read", "clipboard-write"]}
    page = browser.new_page(viewport=SIZE, device_scale_factor=2, color_scheme=scheme, **extra)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.goto(DEMO.as_uri())
    page.wait_for_selector("#tasks .ttb-row")
    return page


def said(page):
    return page.evaluate("said.splice(0)")


def heard(page):
    """What the page has said so far, left in its log (a check may ask again)."""
    return page.evaluate("said.slice()")


def lines(page):
    """Each body row as the table shows it: a group's row as "# label detail", a row by its id."""
    return page.evaluate("""[...document.querySelectorAll('#tasks tbody tr')].map(tr => tr.classList.contains('ttb-group')
      ? '# ' + tr.querySelector('.ttb-group-label').textContent + ' ' + tr.querySelector('.ttb-group-detail').textContent
      : tr.classList.contains('ttb-none') ? '- ' + tr.textContent : tr.dataset.id)""")


def css(page, selector, prop):
    return page.evaluate("([s, p]) => getComputedStyle(document.querySelector(s)).getPropertyValue(p)", [selector, prop])


def row(i):
    return f'#tasks tr.ttb-row[data-id="t{i}"]'


def library_script():
    """table.js as the plugin delivers it: with its stylesheet inside."""
    return (WEB / "table.js").read_text().replace('"__TAURIS_TABLE_CSS__"', json.dumps((WEB / "table.css").read_text()))


with sync_playwright() as p:
    browser = launch(p)

    # ---------- what it shows ----------
    page = fresh(browser)
    check("rows under their groups' rows, a group's count (or its own detail), rows of no group listed last",
          lines(page) == ["# Atlas 3", "t1", "t2", "t3", "# Orion 2 open · 1 done", "t4", "t5", "t6", "# Vega 0", "- Nothing here.", "t7"], lines(page))
    check("a group's colour square", css(page, '#tasks tr.ttb-group[data-group="orion"] .ttb-chip', "background-color") == "rgb(184, 58, 49)")
    check("25px rows under a 23px header",
          page.evaluate("Math.round(document.querySelector('#tasks tr.ttb-row').getBoundingClientRect().height)") == 25
          and page.evaluate("Math.round(document.querySelector('#tasks .ttb-th').getBoundingClientRect().height)") == 23)
    check("cells: text, or what render gave; numbers on the right",
          page.evaluate(f"[...document.querySelectorAll('{row(2)} td')].slice(0, 3).map(c => c.textContent)") == ["Call the printer", "24 Oct", "12"]
          and css(page, f"{row(2)} td:nth-child(3)", "text-align") == "right")
    check("a dim row", css(page, f"{row(6)} td", "color") == "rgb(95, 99, 112)")
    check("a grid for a screen reader, its name and header cells",
          page.get_attribute("#tasks .ttb-list", "role") == "grid" and page.get_attribute("#tasks .ttb-list", "aria-label") == "Tasks"
          and page.evaluate("[...document.querySelectorAll('#tasks th')].map(t => t.getAttribute('aria-sort'))") == ["none", "none", "none", None])
    check("the tooltip has the whole text when asked", page.get_attribute(f"{row(1)} td:first-child", "title") == "Write the brief")
    check("an empty table says so", page.evaluate("document.querySelector('#plain .ttb-empty').textContent") == "No people yet."
          and page.is_visible("#plain .ttb-empty"))
    check("a column that does not sort has no sort button", page.locator("#plain th:nth-child(2) .ttb-sort").count() == 0)
    page.evaluate("document.querySelector('#tasks .ttb-list').scrollTop = 120")
    check("the header stays at the top", lambda: abs(page.evaluate("document.querySelector('#tasks .ttb-th').getBoundingClientRect().top - document.querySelector('#tasks .ttb-list').getBoundingClientRect().top")) <= 1.5)
    page.evaluate("document.querySelector('#tasks .ttb-list').scrollTop = 0")

    # ---------- sorting ----------
    page.click("#tasks th:nth-child(3) .ttb-sort")
    check("a header sorts: ▲, within each group, onSort told",
          lines(page)[1:4] == ["t1", "t3", "t2"] and lines(page)[5:8] == ["t4", "t6", "t5"]
          and page.evaluate("document.querySelector('#tasks th:nth-child(3) .ttb-arrow').textContent") == "▲"
          and page.get_attribute("#tasks th:nth-child(3)", "aria-sort") == "ascending" and said(page) == [["sort", "size", True]], lines(page))
    page.click("#tasks th:nth-child(3) .ttb-sort")
    check("again: the other way, ▼", lines(page)[1:4] == ["t2", "t3", "t1"] and page.get_attribute("#tasks th:nth-child(3)", "aria-sort") == "descending", lines(page))
    page.click("#tasks th:nth-child(2) .ttb-sort")
    check("by what value() gives (a date shown as \"24 Oct\"), no date last", lines(page)[5:8] == ["t6", "t4", "t5"], lines(page))
    said(page)
    page.evaluate("tasks.update({ sort: null })")
    check("sort: null: the rows in the app's order again", lines(page)[1:4] == ["t1", "t2", "t3"] and page.locator("#tasks .ttb-arrow").count() == 0)

    # ---------- selection, mouse and keys ----------
    page.click(f"{row(2)} td:first-child")
    check("a click selects the row, in the accent colour while the table has the keys",
          page.get_attribute(row(2), "aria-selected") == "true" and css(page, f"{row(2)} td", "background-color") == "rgb(38, 117, 191)"
          and css(page, f"{row(2)} td", "color") == "rgb(255, 255, 255)" and said(page) == [["select", "t2", "mouse"]])
    check("the grid names the selected row", page.get_attribute("#tasks .ttb-list", "aria-activedescendant") == page.get_attribute(row(2), "id"))
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    check("↓ moves, past a group's row", page.evaluate("tasks.selected().id") == "t4", heard(page))
    page.keyboard.press("End")
    check("End: the last row", page.evaluate("tasks.selected().id") == "t7")
    page.keyboard.press("ControlOrMeta+ArrowUp")
    check("⌘↑: the first", page.evaluate("tasks.selected().id") == "t1")
    page.keyboard.press("PageDown")
    check("Page Down: a page on", page.evaluate("tasks.selected().id") not in ("t1", "t2"), page.evaluate("tasks.selected().id"))
    page.keyboard.press("Home")
    said(page)
    page.keyboard.press("Enter")
    check("Enter opens it", said(page) == [["open", "t1", "keyboard", False]])
    page.keyboard.press("Space")
    check("onKey takes a key first (Space here)", said(page) == [["space", "t1"]])
    page.keyboard.press("Shift+F10")
    check("⇧F10: its menu, from the keyboard", said(page) == [["menu", "t1", "keyboard"]])
    page.keyboard.type("pi")
    check("a name typed selects it", page.evaluate("tasks.selected().id") == "t5")
    page.wait_for_timeout(800)
    said(page)
    page.keyboard.type("zz")
    check("nothing starts with it: said", [x for x in said(page) if x[0] == "message"][-1] == ["message", "Nothing starts with “zz”.", "error"])
    page.focus("#field")
    check("the keys elsewhere: the selection grey", css(page, f"{row(5)} td", "background-color") == "rgb(220, 222, 227)")
    page.dblclick(f"{row(3)} td:first-child")
    check("a double click opens it", heard(page)[-1] == ["open", "t3", "mouse", False], heard(page))
    page.dblclick('#tasks tr.ttb-group[data-group="atlas"] td')
    check("a double click on a group's row: onGroupOpen", heard(page)[-1] == ["group-open", "atlas"])
    page.click('#tasks tr.ttb-group[data-group="orion"] td', button="right")
    check("a right click on a group's row: onGroupContextMenu", heard(page)[-1] == ["group-menu", "orion"])
    page.click(f"{row(4)} td:first-child", button="right")
    check("a right click on a row selects it and asks for its menu", heard(page)[-2:] == [["select", "t4", "mouse"], ["menu", "t4", "mouse"]], heard(page))
    said(page)
    page.evaluate("document.getElementById('tasks').style.height = '420px'")
    page.click("#tasks .ttb-list", position={"x": 50, "y": 400})
    check("a click on the empty space: nothing selected", page.evaluate("tasks.selected()") is None and said(page) == [["select", None, "mouse"]])
    page.evaluate("document.getElementById('tasks').style.height = ''")

    # ---------- a row's buttons ----------
    check("a row's buttons hide until it is pointed at", css(page, f"{row(1)} .ttb-ib[data-act=edit]", "opacity") == "0")
    page.hover(f"{row(1)} td:first-child")
    check("pointed at, they show", lambda: css(page, f"{row(1)} .ttb-ib[data-act=edit]", "opacity") == "1")
    check("a toggle that is on is shown pressed, always",
          page.get_attribute(f"{row(2)} .ttb-ib[data-act=flag]", "aria-pressed") == "true" and css(page, f"{row(2)} .ttb-ib[data-act=flag]", "opacity") == "1")
    check("each button is named with its row", page.get_attribute(f"{row(1)} .ttb-ib[data-act=edit]", "aria-label") == "Edit: Write the brief")
    page.click(f"{row(1)} .ttb-ib[data-act=flag]")
    check("a toggle clicked: the app's action, and it shows pressed",
          heard(page)[-1] == ["flag", "t1", True] and page.get_attribute(f"{row(1)} .ttb-ib[data-act=flag]", "aria-pressed") == "true", heard(page))
    said(page)
    page.click(f"{row(1)} .ttb-ib[data-act=edit]")
    got = said(page)
    check("a button's click is its own: no open, the keys stay on the table",
          got == [["edit", "t1", "mouse"]] and page.evaluate("document.activeElement.classList.contains('ttb-list')"), got)
    page.dblclick(f"{row(1)} .ttb-ib[data-act=edit]")
    check("nor does a double click on one open the row", not any(x[0] == "open" for x in said(page)))
    page.click(f"{row(3)} .ttb-ib[data-act=copy]")
    if WEBKIT:
        check("copy: copied, or said that it could not", lambda: any(x[0] == "message" and x[1] in ("Copied", "Could not copy.") for x in heard(page)), lambda: heard(page))
    else:
        check("copy: its text on the clipboard, a tick for a moment, said",
              lambda: page.evaluate("navigator.clipboard.readText()") == "Book the venue" and page.locator(f"{row(3)} .ttb-ib.ttb-copied").count() == 1
              and ["message", "Copied", "ok"] in heard(page), lambda: heard(page))
        check("then the icon again", lambda: page.locator(f"{row(3)} .ttb-ib.ttb-copied").count() == 0)

    # ---------- the app's changes ----------
    page.evaluate("tasks.select('t5')")
    page.evaluate("document.querySelector('#tasks .ttb-list').scrollTop = 40")
    page.evaluate("ROWS.push({ id: 't8', group: 'vega', name: 'Hire a photographer', due: null, size: 2 }); tasks.setRows(ROWS)")
    check("new rows: the selection and the scroll stay, a group's count follows",
          page.evaluate("tasks.selected().id") == "t5" and page.evaluate("document.querySelector('#tasks .ttb-list').scrollTop") == 40
          and "# Vega 1" in lines(page), lines(page))
    page.evaluate("tasks.flash('t8')")
    check("flash(): selected, in view, flashed", page.evaluate("tasks.selected().id") == "t8"
          and page.evaluate("document.querySelector('#tasks tr[data-id=t8]').classList.contains('ttb-flash')"))
    check("the flash fades and goes", lambda: not page.evaluate("document.querySelector('#tasks tr[data-id=t8]').classList.contains('ttb-flash')"))
    page.evaluate("ROWS.splice(ROWS.findIndex(r => r.id === 't8'), 1); tasks.setRows(ROWS)")
    check("the selected row gone: nothing selected", page.evaluate("tasks.selected()") is None)
    check("a second mount on the same element is refused",
          page.evaluate("(() => { try { TaurisTable.mount(document.getElementById('tasks'), { columns: [] }); return false; } catch (e) { return true; } })()"))
    check("destroy() empties it, and mount works again",
          page.evaluate("plain.destroy(); const t = TaurisTable.mount(document.getElementById('plain'), { columns: [{ key: 'a' }], rows: [{ id: 1, a: 'x' }] }); document.querySelectorAll('#plain .ttb-row').length === 1"))
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / "table.png"))
    page.close()

    page = fresh(browser, scheme="dark")
    page.click(f"{row(2)} td:first-child")
    check("dark: the dark colours", css(page, f"{row(2)} td", "background-color") == "rgb(47, 101, 202)"
          and css(page, "#tasks .ttb-th", "background-color") == "rgb(52, 55, 58)")
    if SHOTS:
        page.screenshot(path=str(SHOTS / "table_dark.png"))
    page.close()

    # ---------- as the plugin delivers it ----------
    page = browser.new_page(viewport=SIZE)
    page.add_init_script(library_script())
    page.goto((HERE / "csp.html").as_uri())
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    before = page.evaluate("document.adoptedStyleSheets.length")
    page.evaluate("TaurisTable.mount(document.getElementById('t'), { columns: [{ key: 'a', label: 'A' }], rows: [{ id: 1, a: 'x' }] }); 0")
    check("under a strict content policy: no stylesheet until it is used, then one, and no error",
          before == 0 and page.evaluate("document.adoptedStyleSheets.length") == 1 and not errors
          and page.evaluate("getComputedStyle(document.querySelector('.ttb-list')).overflowY") == "auto", errors)
    page.close()

    browser.close()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
