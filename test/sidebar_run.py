"""Headless tests for the sidebar (web/sidebar.js), on test/sidebar_demo.html.

    python test/sidebar_run.py [shots-dir]

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
DEMO = HERE / "sidebar_demo.html"
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
SIZE = {"width": 900, "height": 560}
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        failures.append(name)


def fresh(browser, scheme="light", reduced_motion="no-preference"):
    page = browser.new_page(viewport=SIZE, device_scale_factor=2, color_scheme=scheme, reduced_motion=reduced_motion)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.goto(DEMO.as_uri())
    page.wait_for_selector(".tsb-item")
    return page


def css(page, selector, prop):
    return page.evaluate("([s, p]) => getComputedStyle(document.querySelector(s)).getPropertyValue(p)", [selector, prop])


def width(page):
    return round(page.evaluate("document.getElementById('side').getBoundingClientRect().width"))


def labels(page):
    return page.evaluate("[...document.querySelectorAll('#side .tsb-item')].map(i => i.querySelector('.tsb-label').textContent)")


def focused(page):
    return page.evaluate("document.activeElement.closest?.('.tsb-item')?.dataset.key ?? document.activeElement.className")


def said(page):
    return page.evaluate("said.splice(0)")


def shortcut(page):
    """⌃⌘S on a Mac, Ctrl+Shift+B elsewhere (as the page sees the system)."""
    return "Control+Meta+KeyS" if page.evaluate("/Mac/.test(navigator.platform)") else "Control+Shift+KeyB"


CONTRAST = """(pairs) => { const rgb = c => { const cv = document.createElement('canvas').getContext('2d'); cv.fillStyle = c; cv.fillRect(0, 0, 1, 1);
    return [...cv.getImageData(0, 0, 1, 1).data].slice(0, 3); };
  const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  return pairs.map(([a, b]) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return Math.round((x + 0.05) / (y + 0.05) * 100) / 100; }); }"""


def library_script():
    """sidebar.js as the plugin delivers it: with its stylesheet inside."""
    return (WEB / "sidebar.js").read_text().replace('"__TAURIS_SIDEBAR_CSS__"', json.dumps((WEB / "sidebar.css").read_text()))


with sync_playwright() as p:
    browser = launch(p)

    # ---------- what it shows ----------
    page = fresh(browser)
    check("its items, a group's open below it, in order", labels(page) == ["Inbox", "Flagged", "Sent", "Atlas", "Documents", "Board minutes", "Northwind", "Archive"],
          labels(page))
    check("a title, a heading between sections, 220px wide",
          page.inner_text("#side .tsb-title") == "Mail" and page.locator("#side .tsb-heading").count() == 1 and width(page) == 220, width(page))
    check("the selected item is the page shown; the list is one Tab stop, on it",
          page.get_attribute("[data-key=inbox]", "aria-current") == "page"
          and page.evaluate("[...document.querySelectorAll('#side .tsb-item')].filter(i => i.tabIndex === 0).map(i => i.dataset.key)") == ["inbox"])
    check("named for screen readers: the list by the title, an item with its count",
          page.get_attribute("#side .tsb-nav", "aria-label") == "Mail" and page.get_attribute("[data-key=inbox]", "aria-label") == "Inbox, 12"
          and page.get_attribute("[data-key=atlas]", "aria-expanded") == "true" and page.get_attribute("[data-key=archive]", "aria-disabled") == "true")
    rows = page.evaluate("[...document.querySelectorAll('#side .tsb-item')].map(i => Math.round(i.getBoundingClientRect().height))")
    check("rows 28px high", set(rows) == {28}, rows)
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / "sidebar_light.png"))

    # ---------- the mouse ----------
    page.click("[data-key=sent]")
    check("a click selects an item, and the app hears it",
          said(page) == [["select", "sent", "mouse"]] and page.get_attribute("[data-key=sent]", "aria-current") == "page"
          and page.get_attribute("[data-key=inbox]", "aria-current") is None and page.inner_text("#heading") == "Sent")
    page.click("[data-key=atlas] .tsb-chevron")
    check("a group's arrow closes it, selecting nothing", page.locator("[data-key=atlas-docs]").count() == 0 and said(page) == []
          and page.get_attribute("[data-key=atlas]", "aria-expanded") == "false")
    page.dblclick("[data-key=atlas] .tsb-label")
    check("a double-click on a group opens it (and its click selects it)", page.locator("[data-key=atlas-docs]").count() == 1
          and said(page) == [["select", "atlas", "mouse"]])
    page.click("[data-key=archive]", force=True)
    check("a disabled item is not chosen", said(page) == [])
    page.close()

    # ---------- the keys ----------
    page = fresh(browser)
    page.focus("#field")
    page.keyboard.press("Shift+Tab")
    on_edge = page.evaluate("document.activeElement.className")
    page.keyboard.press("Shift+Tab")
    check("going back from the page with Tab: the edge, then the selected item", on_edge == "tsb-grip" and focused(page) == "inbox", (on_edge, focused(page)))
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    at_sent = focused(page)
    page.keyboard.press("End")
    at_end = focused(page)
    page.keyboard.press("Home")
    check("Up, Down, Home, End move (past the disabled one)", (at_sent, at_end, focused(page)) == ("sent", "northwind", "inbox"), (at_sent, at_end, focused(page)))
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    check("Enter selects the item with the focus", said(page) == [["select", "flagged", "keyboard"]])
    page.keyboard.press("a")
    on_atlas = focused(page)
    page.keyboard.press("ArrowLeft")
    closed = page.locator("[data-key=atlas-docs]").count() == 0
    page.keyboard.press("ArrowRight")
    opened = page.locator("[data-key=atlas-docs]").count() == 1
    page.keyboard.press("ArrowRight")
    in_group = focused(page)
    page.keyboard.press("ArrowLeft")
    check("a letter jumps to an item; Left closes a group, Right opens it, then goes into it; Left goes back up",
          (on_atlas, closed, opened, in_group, focused(page)) == ("atlas", True, True, "atlas-docs", "atlas"), (on_atlas, closed, opened, in_group, focused(page)))
    page.keyboard.press("Space")
    check("Space selects too", said(page) == [["select", "atlas", "keyboard"]])
    ring = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
    check("the item the keys are on has a ring", ring == "solid", ring)
    page.close()

    # ---------- collapsing ----------
    page = fresh(browser)
    page.click("#side .tsb-toggle")
    page.wait_for_timeout(300)  # the width eases
    rail = (page.get_attribute("#side", "data-tsb-state"), width(page), page.is_hidden("[data-key=inbox] .tsb-label"),
            page.get_attribute("[data-key=inbox]", "title"), page.get_attribute("#side .tsb-toggle", "aria-expanded"),
            page.get_attribute("#side .tsb-toggle", "aria-label"), said(page))
    check("its button collapses it to a 44px rail of icons, each named by a tooltip; the app hears it",
          rail == ("rail", 44, True, "Inbox (12)", "false", "Show sidebar", [["toggle", True, "button"]]), rail)
    check("the rail shows the first level only, a count as a dot, an item with no icon by its letter",
          labels(page) == ["Inbox", "Flagged", "Sent", "Atlas", "Northwind", "Archive"] and page.is_visible("[data-key=inbox] .tsb-count")
          and page.inner_text("[data-key=northwind] .tsb-icon") == "N", labels(page))
    if SHOTS:
        page.screenshot(path=str(SHOTS / "sidebar_rail.png"))
    page.focus("[data-key=inbox]")
    page.keyboard.press("End")
    check("in the rail the keys go through the first level", focused(page) == "northwind", focused(page))
    page.click("[data-key=atlas]")
    page.wait_for_timeout(300)
    check("a group chosen in the rail opens the sidebar, the group open", page.get_attribute("#side", "data-tsb-state") == "open"
          and page.locator("[data-key=atlas-docs]").count() == 1 and said(page) == [["toggle", False, "button"], ["select", "atlas", "mouse"]], said(page))
    page.focus("#field")
    page.keyboard.press(shortcut(page))
    page.wait_for_timeout(50)
    collapsed = page.get_attribute("#side", "data-tsb-state")
    page.keyboard.press(shortcut(page))
    check("⌃⌘S (Ctrl+Shift+B) collapses and opens it from anywhere; opened, the keys go on in it",
          collapsed == "rail" and page.get_attribute("#side", "data-tsb-state") == "open" and focused(page) == "atlas"
          and said(page) == [["toggle", True, "shortcut"], ["toggle", False, "shortcut"]], (collapsed, focused(page)))
    page.evaluate("side.toggle(true); 0")
    check("toggle() collapses it; collapsed says so", page.evaluate("side.collapsed") is True and said(page) == [["toggle", True, "api"]])
    page.close()

    page = fresh(browser)
    page.evaluate("side.destroy(); window.side = TaurisSidebar.mount(document.getElementById('side'), { items: ITEMS, collapse: 'hide', onToggle: i => said.push(['toggle', i.collapsed, i.how]) }); 0")
    page.focus("[data-key=inbox]")
    page.keyboard.press(shortcut(page))
    page.wait_for_timeout(300)
    gone = (width(page), page.evaluate("document.querySelector('#side .tsb-nav').inert"), page.is_hidden("#side .tsb-grip"),
            page.evaluate("document.getElementById('side').contains(document.activeElement)"))
    check("collapse: 'hide': nothing shows, nothing in it can be reached, and the focus leaves it",
          gone == (0, True, True, False), gone)
    page.keyboard.press(shortcut(page))
    page.wait_for_timeout(300)
    check("and the shortcut brings it back", width(page) == 220 and focused(page) == "inbox", (width(page), focused(page)))
    page.close()

    # ---------- the edge ----------
    page = fresh(browser)
    box = page.locator("#side .tsb-grip").bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + 200
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 80, y, steps=4)
    page.mouse.up()
    check("its edge drags it wider; the app hears the new width", width(page) == 300 and said(page) == [["resize", 300]], width(page))
    page.mouse.move(x + 80, y)
    page.mouse.down()
    page.mouse.move(x + 600, y, steps=4)
    page.mouse.up()
    check("no wider than maxWidth", width(page) == 420, width(page))
    said(page)
    box = page.locator("#side .tsb-grip").bounding_box()
    x = box["x"] + box["width"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(40, y, steps=6)
    page.mouse.up()
    page.wait_for_timeout(300)
    check("dragged narrow, it collapses (and keeps its width for later)", page.get_attribute("#side", "data-tsb-state") == "rail"
          and page.evaluate("side.width") == 420 and said(page) == [["toggle", True, "edge"]], (page.get_attribute("#side", "data-tsb-state"), said(page)))
    box = page.locator("#side .tsb-grip").bounding_box()
    x = box["x"] + box["width"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 200, y, steps=6)
    page.mouse.up()
    page.wait_for_timeout(300)
    check("from the rail, dragged out, it opens at the width dragged to", page.get_attribute("#side", "data-tsb-state") == "open"
          and 230 <= width(page) <= 250 and said(page)[0] == ["toggle", False, "edge"], width(page))
    page.dblclick("#side .tsb-grip")
    page.wait_for_timeout(300)  # the width eases
    check("a double-click on the edge puts its width back", width(page) == 220, width(page))
    page.focus("#side .tsb-grip")
    now = lambda: page.evaluate("side.width")
    page.keyboard.press("ArrowRight")
    w1 = now()
    page.keyboard.press("Shift+ArrowRight")
    w2 = now()
    page.keyboard.press("Home")
    w3 = now()
    page.keyboard.press("End")
    w4 = now()
    page.wait_for_timeout(300)
    check("the edge from the keys: Right and Shift+Right widen, Home and End go to the narrowest and widest",
          (w1, w2, w3, w4) == (230, 280, 160, 420) and page.get_attribute("#side .tsb-grip", "aria-valuenow") == "420" and width(page) == 420, (w1, w2, w3, w4, width(page)))
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    check("Enter on the edge collapses it", page.get_attribute("#side", "data-tsb-state") == "rail")
    page.close()

    page = fresh(browser)
    page.evaluate("side.destroy(); window.side = TaurisSidebar.mount(document.getElementById('side'), { items: ITEMS, side: 'right' }); document.body.append(document.getElementById('side')); 0")
    box = page.locator("#side .tsb-grip").bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + 200
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x - 60, y, steps=4)
    page.mouse.up()
    look = (width(page), css(page, "#side", "border-left-width"), round(box["x"]), round(page.evaluate("document.getElementById('side').getBoundingClientRect().left")))
    check("on the right, its edge is on its left, and dragging left widens it",
          look[0] == 280 and look[1] == "1px" and abs(look[2] - (SIZE["width"] - 220)) <= 1, look)
    page.close()

    # ---------- the app's own menu on an item; a group opened by choosing it ----------
    page = fresh(browser)
    page.evaluate("side.update({ onContextMenu: (item, at) => said.push(['menu', item.id, at.how, at.x > 0 && at.y > 0]), openOnSelect: true }); 0")
    page.click("[data-key=northwind] .tsb-label", button="right")
    page.focus("[data-key=sent]")
    page.keyboard.press("Shift+F10")
    page.click("[data-key=northwind] .tsb-label")
    check("onContextMenu hears a right click and the menu key on an item, where to open the app's menu",
          said(page) == [["menu", "northwind", "mouse", True], ["menu", "sent", "keyboard", True], ["select", "northwind", "mouse"]], page.evaluate("said"))
    check("openOnSelect: choosing a group opens it", page.locator("[data-key=nw-plan]").count() == 1)
    page.click("[data-key=northwind] .tsb-label")
    check("and choosing it again leaves it open", page.locator("[data-key=nw-plan]").count() == 1)
    page.close()

    # ---------- the app's own part: a tree view, say ----------
    page = fresh(browser)
    page.evaluate("""(() => { side.destroy(); const c = document.createElement('div'); c.id = 'mine';
      for (let i = 0; i < 60; i++) { const r = document.createElement('div'); r.textContent = 'Row ' + i; r.style.height = '20px'; c.append(r); }
      window.side = TaurisSidebar.mount(document.getElementById('side'), { content: c, title: 'Files' }); return 0; })()""")
    part = page.evaluate("""(() => { const s = document.getElementById('side').getBoundingClientRect(), h = document.querySelector('#side .tsb-head').getBoundingClientRect(),
      b = document.querySelector('#side .tsb-body'), r = b.getBoundingClientRect();
      return [b.contains(document.getElementById('mine')), Math.round(r.top - h.bottom), Math.round(s.bottom - r.bottom), b.scrollHeight > b.clientHeight,
              document.querySelector('#side .tsb-nav').hidden, side.body === b]; })()""")
    check("content: the app's element below the head (no items, no room for them), filling the rest of the height and scrolling",
          part == [True, 0, 0, True, True, True], part)
    page.evaluate("side.toggle(true); 0")
    page.wait_for_timeout(300)
    in_rail = page.is_visible("#mine")
    slim = width(page)
    page.evaluate("side.toggle(false); 0")
    page.wait_for_timeout(300)
    check("it shows only while the sidebar is open (not in the rail), and collapsed with no items it is a slim 32px strip, its button alone",
          not in_rail and page.is_visible("#mine") and slim == 32, slim)
    page.evaluate("""(() => { side.destroy(); window.side = TaurisSidebar.mount(document.getElementById('side'), { items: ITEMS.slice(0, 3) });
      const p = document.createElement('p'); p.id = 'later'; p.textContent = 'Later'; side.body.append(p); side.refresh(); return 0; })()""")
    order = page.evaluate("""(() => { const n = document.querySelector('#side [data-key=sent]').getBoundingClientRect(), l = document.getElementById('later').getBoundingClientRect();
      return l.top >= n.bottom; })()""")
    check("filled later through side.body (then refresh()), below the items", page.is_visible("#later") and order)
    page.close()

    # ---------- kept between runs, changed by the app ----------
    page = fresh(browser)
    page.evaluate("localStorage.clear(); side.destroy(); window.side = TaurisSidebar.mount(document.getElementById('side'), { items: ITEMS, storageKey: 'demo-side' }); side.setWidth(310); side.toggle(true); 0")
    page.reload()
    page.wait_for_selector(".tsb-item")
    page.evaluate("side.destroy(); window.side = TaurisSidebar.mount(document.getElementById('side'), { items: ITEMS, storageKey: 'demo-side' }); 0")
    check("storageKey keeps its width and whether it is collapsed", page.evaluate("[side.width, side.collapsed]") == [310, True], page.evaluate("[side.width, side.collapsed]"))
    page.evaluate("localStorage.clear(); 0")
    page.close()

    page = fresh(browser)
    page.focus("[data-key=flagged]")
    page.evaluate("side.setItems([{ id: 'new', label: 'New' }, ...ITEMS]); 0")
    kept = focused(page)
    page.evaluate("side.select('nw-plan'); 0")
    check("new items keep the focus on the same item; select() opens the groups around an item (and says nothing)",
          kept == "flagged" and page.get_attribute("[data-key=nw-plan]", "aria-current") == "page" and said(page) == []
          and page.evaluate("side.selected().id") == "nw-plan", kept)
    page.evaluate("side.update({ title: 'Post', labels: { hide: 'Fold' } }); 0")
    check("update() changes the title and the words", page.inner_text("#side .tsb-title") == "Post"
          and page.get_attribute("#side .tsb-toggle", "aria-label") == "Fold" and page.get_attribute("#side .tsb-nav", "aria-label") == "Post")
    page.evaluate("side.destroy(); 0")
    page.focus("#field")
    page.keyboard.press(shortcut(page))
    check("destroy() empties the element and the shortcut does nothing more",
          page.evaluate("document.getElementById('side').children.length") == 0 and not page.evaluate("document.getElementById('side').classList.contains('tsb')"))
    page.evaluate("window.side = TaurisSidebar.mount(document.getElementById('side'), { items: ITEMS }); 0")
    check("and mount works again on it", page.locator("#side .tsb-item").count() == 8)
    page.close()

    # ---------- the look: light and dark, contrast, motion ----------
    for scheme in ("light", "dark"):
        page = fresh(browser, scheme)
        page.focus("[data-key=inbox]")
        c = page.evaluate("""(() => { const s = q => getComputedStyle(document.querySelector(q)); return {
          fg: s('[data-key=flagged]').color, bg: s('#side').backgroundColor, dim: s('#side .tsb-heading').color,
          selFg: s('[data-key=inbox]').color, selBg: s('[data-key=inbox]').backgroundColor, ring: s('[data-key=inbox]').outlineColor }; })()""")
        page.focus("#field")
        c2 = page.evaluate("""(() => { const s = getComputedStyle(document.querySelector('[data-key=inbox]')); return { fg: s.color, bg: s.backgroundColor }; })()""")
        # The keys' ring on the selected item sits on its fill.
        ratios = page.evaluate(CONTRAST, [[c["fg"], c["bg"]], [c["dim"], c["bg"]], [c["selFg"], c["selBg"]], [c2["fg"], c2["bg"]], [c["ring"], c["selBg"]]])
        check(f"{scheme}: text, headings, the selection with and without the focus read (4.5:1), and the keys' ring shows (3:1)",
              min(ratios[:4]) >= 4.5 and ratios[4] >= 3, (c, c2, ratios))
        if SHOTS and scheme == "dark":
            page.screenshot(path=str(SHOTS / "sidebar_dark.png"))
        page.close()
    page = fresh(browser, reduced_motion="reduce")
    check("reduced motion: it collapses at once", css(page, "#side", "transition-duration") in ("0s", ""), css(page, "#side", "transition-duration"))
    page.close()

    # ---------- as the plugin delivers it ----------
    page = browser.new_page(viewport=SIZE)
    page.add_init_script(library_script())
    page.goto((HERE / "csp.html").as_uri())
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    before = page.evaluate("document.adoptedStyleSheets.length")
    page.evaluate("""(() => { const s = document.createElement('div'); s.style.height = '300px'; document.body.append(s);
      TaurisSidebar.mount(s, { items: [{ id: 'a', label: 'A' }] }); return 0; })()""")
    check("under a strict content policy: no stylesheet until it is used, then one, and no error",
          before == 0 and page.evaluate("document.adoptedStyleSheets.length") == 1 and not errors
          and page.evaluate("getComputedStyle(document.querySelector('.tsb')).display") == "flex", errors)
    page.close()

    browser.close()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
