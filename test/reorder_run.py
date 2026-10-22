"""Headless tests for drag to reorder (web/reorder.js), on test/reorder_demo.html.

    python test/reorder_run.py [shots-dir]

Nothing touches the screen. TAURIS_TEST_CHROMIUM=1 or TAURIS_TEST_WEBKIT=1
runs it in CI's browsers (see engine.py).
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from engine import launch, settled

HERE = Path(__file__).parent
WEB = HERE.parent / "web"
DEMO = HERE / "reorder_demo.html"
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
SIZE = {"width": 980, "height": 620}
MAC = sys.platform == "darwin"
failures = []


def check(name, ok, detail=""):
    ok, detail = settled(ok, detail)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        failures.append(name)


def fresh(browser, scheme="light", reduced_motion="no-preference"):
    page = browser.new_page(viewport=SIZE, device_scale_factor=2, color_scheme=scheme, reduced_motion=reduced_motion)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.goto(DEMO.as_uri())
    page.wait_for_selector("#tasks tbody tr")
    return page


def said(page):
    return page.evaluate("said.splice(0)")


def heard(page):
    """What the page has said so far, left in its log (a check may ask again)."""
    return page.evaluate("said.slice()")


def order(page, selector="#tasks tbody tr"):
    return page.evaluate("s => [...document.querySelectorAll(s)].map(r => r.dataset.id)", selector)


def box(page, selector):
    return page.evaluate("s => { const r = document.querySelector(s).getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }", selector)


def row(i, table="tasks"):
    return f"#{table} tbody tr:nth-child({i})"


def grab(page, selector, dy=0):
    """Presses on a row's first cell, then moves the pointer by dy, in steps."""
    b = box(page, selector + " td:first-child")
    x, y = b["x"] + 30, b["y"] + b["h"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    if dy:
        page.mouse.move(x, y + dy, steps=8)
    return x, y


def library_script():
    """reorder.js as the plugin delivers it: with its stylesheet inside."""
    return (WEB / "reorder.js").read_text().replace('"__TAURIS_REORDER_CSS__"', json.dumps((WEB / "reorder.css").read_text()))


MOVE_DOWN = "ControlOrMeta+Alt+ArrowDown"
MOVE_UP = "ControlOrMeta+Alt+ArrowUp"

with sync_playwright() as p:
    browser = launch(p)

    # ---------- a drag ----------
    page = fresh(browser)
    first = order(page)
    check("the demo's tasks, open then done", first[:3] == ["t1", "t2", "t3"] and first[-2:] == ["d1", "d2"], first)
    h = box(page, row(1))["h"]
    x, y = grab(page, row(1), dy=2.5 * h)
    check("a drag lifts a copy of the row; the row stays, faint, and a line shows where it lands",
          page.locator(".trd-ghost").count() == 1 and page.locator(".trd-line").count() == 1
          and page.evaluate("document.querySelector('#tasks tbody tr:nth-child(1)').classList.contains('trd-src')")
          and page.evaluate("getComputedStyle(document.querySelector('#tasks tbody tr:nth-child(1) td')).opacity") == "0.35")
    check("onStart gets its group's order, to hold still", heard(page)[:1] == [["start", "t1", ",".join(first[:10])]], heard(page))
    said(page)
    g = box(page, ".trd-ghost")
    check("the copy follows the pointer, as wide as the row (lifted a little)", abs(g["y"] - (y + 2.5 * h - h / 2)) <= 2 and abs(g["w"] - box(page, row(1))["w"] * 1.006) <= 1, g)
    check("the line is between the third and fourth rows", lambda: abs(box(page, ".trd-line")["y"] + 1 - box(page, row(4))["y"]) <= 2,
          lambda: (box(page, ".trd-line"), box(page, row(4))))
    check("the copy is not a row: no id, no data-*, no aria-*, nothing a count of the rows finds",
          page.evaluate("document.querySelectorAll('[data-id]').length") == page.evaluate("TASKS.length + 9 + ITEMS.length")
          and page.evaluate("[...document.querySelectorAll('.trd-ghost *')].every(e => ![...e.attributes].some(a => a.name === 'id' || a.name.startsWith('data-') || a.name.startsWith('aria-')))"))
    check("nothing is selected as text while it is dragged", page.evaluate("getComputedStyle(document.body).userSelect || getComputedStyle(document.body).webkitUserSelect") == "none")
    page.mouse.up()
    check("dropped: onMove gets the group's new order, by the mouse", said(page) == [["move", "t1", 0, 2, "mouse", "t2,t3,t1,t4,t5,t6,t7,t8,t9,t10"]], heard(page))
    check("the app draws it: the row is in its new place", order(page)[:4] == ["t2", "t3", "t1", "t4"], order(page))
    check("the copy and the line are gone, and nothing is faint", page.locator(".trd-ghost, .trd-line, .trd-src").count() == 0)
    check("the release's click does not land on the row under it", page.evaluate("clicks") == [], page.evaluate("clicks"))
    check("the rows slide into place", lambda: page.locator("#tasks tr.trd-settle").count() >= 1)
    check("a screen reader hears where it went", lambda: page.evaluate("document.querySelector('.trd-live')?.textContent") == "Moved to 3 of 10.",
          lambda: page.evaluate("document.querySelector('.trd-live')?.textContent"))
    page.click(row(2) + " td:first-child")
    check("a click that does not move is a click", page.evaluate("clicks") == ["t3"], page.evaluate("clicks"))
    page.close()

    page = fresh(browser)
    grab(page, row(1), dy=3)
    page.mouse.up()
    check("under 4px it is no drag: no copy, no onStart, and the click goes through",
          page.locator(".trd-ghost:not(.trd-back)").count() == 0 and said(page) == [] and page.evaluate("clicks") == ["t1"])
    grab(page, row(2), dy=40)
    page.keyboard.press("Escape")
    check("Esc puts it back: onCancel, and the order is as it was",
          [s[0] for s in heard(page)] == ["start", "cancel"] and order(page)[:3] == ["t1", "t2", "t3"], heard(page))
    said(page)
    page.mouse.up()
    check("and the release after Esc is no click", page.evaluate("clicks") == ["t1"], page.evaluate("clicks"))
    check("the copy slides back and goes", lambda: page.locator(".trd-ghost").count() == 0)
    h = box(page, row(1))["h"]
    grab(page, row(3), dy=h * 0.3)
    page.mouse.move(box(page, row(3))["x"] + 30, box(page, row(3))["y"] + h / 2 + 6, steps=2)
    page.mouse.up()
    check("dropped where it was: onCancel, not onMove", [s[0] for s in said(page)] == ["start", "cancel"])
    page.close()

    # ---------- what it cannot do ----------
    page = fresh(browser)
    page.evaluate("document.querySelector('#tasks-wrap').scrollTop = 1000")
    b = box(page, row(11))
    page.mouse.move(b["x"] + 30, b["y"] + b["h"] / 2)
    page.mouse.down()
    page.mouse.move(b["x"] + 30, b["y"] - 40, steps=6)
    check("a row that may not move says why, and does not lift",
          page.locator(".trd-ghost:not(.trd-back)").count() == 0 and said(page) == [["refuse", "Done tasks sort by the day they were done."]])
    page.mouse.up()
    last_open = box(page, row(10))
    page.mouse.move(last_open["x"] + 30, last_open["y"] + last_open["h"] / 2)
    page.mouse.down()
    page.mouse.move(last_open["x"] + 30, box(page, row(12))["y"] + 6, steps=6)
    check("over another group's rows: refused, no line, the not-allowed pointer, said once",
          page.evaluate("document.documentElement.classList.contains('trd-no')") and page.evaluate("getComputedStyle(document.querySelector('.trd-line')).visibility") == "hidden"
          and [s for s in heard(page) if s[0] == "refuse"] == [["refuse", "It can only move among its own group."]], heard(page))
    page.mouse.up()
    check("dropped there: it goes back", [s[0] for s in said(page)][-1] == "cancel" and order(page)[9] == "t10", heard(page))
    b = box(page, row(1))
    page.evaluate("document.querySelector('#tasks-wrap').scrollTop = 0")
    btn = box(page, row(1) + " button")
    page.mouse.move(btn["x"] + 5, btn["y"] + 5)
    page.mouse.down()
    page.mouse.move(btn["x"] + 5, btn["y"] + 60, steps=6)
    check("a press on the row's own button is no drag", page.locator(".trd-ghost:not(.trd-back)").count() == 0)
    page.mouse.up()
    b = box(page, row(1) + " td:first-child")
    page.mouse.move(b["x"] + 30, b["y"] + 8)
    page.mouse.down(button="right")
    page.mouse.move(b["x"] + 30, b["y"] + 60, steps=6)
    page.mouse.up(button="right")
    check("nor is a right-button press", page.locator(".trd-ghost:not(.trd-back)").count() == 0)
    page.close()

    # ---------- off and on ----------
    page = fresh(browser)
    page.evaluate("tasks.update({ enabled: false })")
    grab(page, row(1), dy=60)
    check("enabled: false: no drag", page.locator(".trd-ghost:not(.trd-back)").count() == 0)
    page.mouse.up()
    page.evaluate("getSelection().removeAllRanges()")  # that press selected text, as any press on text does
    page.evaluate("tasks.update({ enabled: true })")
    grab(page, row(1), dy=60)
    check("enabled again: it drags", page.locator(".trd-ghost").count() == 1 and page.evaluate("tasks.dragging") == "t1")
    page.evaluate("tasks.update({ enabled: false })")
    check("turned off mid-drag: the row goes back", page.evaluate("tasks.dragging") is None and [s[0] for s in said(page)][-1] == "cancel")
    page.mouse.up()
    # Last: off, the keys are the page's own again (WebKit scrolls the page with ⌥⌘↓).
    page.focus(row(1))
    page.keyboard.press(MOVE_DOWN)
    check("off, the keys move nothing", order(page)[:2] == ["t1", "t2"])
    page.close()

    # ---------- the keys ----------
    page = fresh(browser)
    page.focus(row(2))
    page.keyboard.press(MOVE_DOWN)
    check(f"{'⌥⌘↓' if MAC else 'Ctrl+Alt+↓'} moves the row with the focus one place down",
          said(page) == [["move", "t2", 1, 2, "keyboard", "t1,t3,t2,t4,t5,t6,t7,t8,t9,t10"]] and order(page)[:3] == ["t1", "t3", "t2"], heard(page))
    check("the focus stays on it, drawn anew", lambda: page.evaluate("document.activeElement.dataset.id") == "t2", lambda: page.evaluate("document.activeElement.dataset.id"))
    page.keyboard.press(MOVE_UP)
    page.keyboard.press(MOVE_UP)
    page.keyboard.press(MOVE_UP)
    check("up, and at the top it says so", order(page)[:2] == ["t2", "t1"] and said(page)[-1] == ["refuse", "It is first already."], heard(page))
    page.evaluate("picked = 't4'; drawTasks(); document.querySelector('#tasks-wrap').tabIndex = 0; document.querySelector('#tasks-wrap').focus()")
    page.keyboard.press(MOVE_DOWN)
    check("with the focus on the container, the selected row moves", order(page)[4] == "t4" and order(page)[3] == "t5", order(page))
    said(page)
    check("move() from a menu: the same, told as by the menu", page.evaluate("tasks.move('t5', -1)") is True
          and said(page)[0][4] == "menu" and order(page)[2] == "t5", order(page))
    check("move() at the end: false, and said", page.evaluate("tasks.move('t10', 1)") is False and said(page) == [["refuse", "It is last already."]])
    check("the keys a menu shows", page.evaluate("TaurisReorder.keys") == ({"up": "⌥⌘↑", "down": "⌥⌘↓"} if MAC else {"up": "Ctrl+Alt+↑", "down": "Ctrl+Alt+↓"}))
    page.close()

    # ---------- items of several rows ----------
    page = fresh(browser)
    projects = "#projects tbody tr"
    first = order(page, projects)
    b = box(page, "#projects tbody tr[data-id=p1]")
    page.mouse.move(b["x"] + 30, b["y"] + b["h"] / 2)
    page.mouse.down()
    page.mouse.move(b["x"] + 30, box(page, "#projects tbody tr[data-id=k5]")["y"] + 12, steps=10)
    check("a heading drags with its rows: all of them faint", page.locator("#projects .trd-src").count() == 3)
    page.mouse.up()
    check("and they land together, after the next project's rows", said(page)[-1][:5] == ["move", "p1", 0, 1, "mouse"]
          and order(page, projects) == ["p2", "k3", "k4", "k5", "p1", "k1", "k2", "p3", "k6"], order(page, projects))
    page.wait_for_timeout(250)  # the rows' slide into place
    k3 = box(page, "#projects tbody tr[data-id=k3]")
    page.mouse.move(k3["x"] + 40, k3["y"] + k3["h"] / 2)
    page.mouse.down()
    page.mouse.move(k3["x"] + 40, box(page, "#projects tbody tr[data-id=k1]")["y"] + 12, steps=10)
    check("a row under a heading cannot land among another heading's rows", page.evaluate("document.documentElement.classList.contains('trd-no')"))
    page.mouse.move(k3["x"] + 40, box(page, "#projects tbody tr[data-id=k5]")["y"] + 18, steps=10)
    check("among its own it can, its line indented", not page.evaluate("document.documentElement.classList.contains('trd-no')")
          and box(page, ".trd-line")["x"] >= box(page, "#projects tbody tr[data-id=k5]")["x"] + 15, box(page, ".trd-line"))
    page.mouse.up()
    check("it moves among them", order(page, projects)[:4] == ["p2", "k4", "k5", "k3"], order(page, projects))
    page.close()

    # ---------- not a table, scrolling, the look ----------
    page = fresh(browser)
    b = box(page, "#list li:nth-child(1)")
    page.mouse.move(b["x"] + 30, b["y"] + b["h"] / 2)
    page.mouse.down()
    page.mouse.move(b["x"] + 30, box(page, "#list li:nth-child(3)")["y"] + 20, steps=8)
    check("list items: the copy is an item", page.evaluate("document.querySelector('.trd-ghost').firstElementChild.tagName") == "LI")
    page.mouse.up()
    check("and it moves", page.evaluate("ITEMS") == ["Green", "Blue", "Red", "Yellow"], page.evaluate("ITEMS"))
    wrap = box(page, "#tasks-wrap")
    grab(page, row(1))
    page.mouse.move(wrap["x"] + 40, wrap["y"] + 20, steps=2)
    page.mouse.move(wrap["x"] + 40, wrap["y"] + wrap["h"] - 6, steps=8)
    check("near the bottom edge the rows scroll", lambda: page.evaluate("document.querySelector('#tasks-wrap').scrollTop") > 20,
          lambda: page.evaluate("document.querySelector('#tasks-wrap').scrollTop"))
    check("the line is the accent colour, the copy has a shadow",
          page.evaluate("getComputedStyle(document.querySelector('.trd-line')).backgroundColor") == "rgb(38, 117, 191)"
          and page.evaluate("getComputedStyle(document.querySelector('.trd-ghost')).boxShadow") != "none")
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / "reorder.png"))
    page.keyboard.press("Escape")
    page.mouse.up()
    check("arrange(): a list in an order, the others after in theirs",
          page.evaluate("TaurisReorder.arrange([{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }], ['c', 'a']).map(x => x.id)") == ["c", "a", "b", "d"])
    check("destroy(): no drags, and attach works again", page.evaluate("list.destroy(); window.list2 = TaurisReorder.attach(document.getElementById('list-wrap'), { rows: 'li' }); true"))
    check("a second attach on the same element is refused", page.evaluate("(() => { try { TaurisReorder.attach(document.getElementById('list-wrap')); return false; } catch (e) { return true; } })()"))
    page.close()

    page = fresh(browser, scheme="dark")
    grab(page, row(1), dy=60)
    check("dark: the line in the dark accent", page.evaluate("getComputedStyle(document.querySelector('.trd-line')).backgroundColor") == "rgb(106, 166, 224)")
    page.keyboard.press("Escape")
    page.mouse.up()
    page.close()

    page = fresh(browser, reduced_motion="reduce")
    page.focus(row(1))
    page.keyboard.press(MOVE_DOWN)
    check("reduced motion: the rows do not slide", order(page)[:2] == ["t2", "t1"] and page.locator(".trd-settle").count() == 0)
    page.close()

    # ---------- as the plugin delivers it ----------
    page = browser.new_page(viewport=SIZE)
    page.add_init_script(library_script())
    page.goto((HERE / "csp.html").as_uri())
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    before = page.evaluate("document.adoptedStyleSheets.length")
    page.evaluate("""(() => { const s = document.createElement('div'); s.innerHTML = '<p data-id="a">A</p><p data-id="b">B</p>'; document.body.append(s);
      TaurisReorder.attach(s); return 0; })()""")
    check("under a strict content policy: no stylesheet until it is used, then one, and no error",
          before == 0 and page.evaluate("document.adoptedStyleSheets.length") == 1 and not errors, errors)
    page.close()

    browser.close()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
