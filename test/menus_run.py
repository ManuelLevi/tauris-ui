"""Tests the in-window menus (web/menus.js, web/menus.css) in a headless browser.

Run:  python test/menus_run.py [screenshot-folder]
Needs Python playwright and Google Chrome. Nothing touches the screen.
Exits non-zero when a check fails. With a folder, it saves screenshots at 2x:
a menu of the bar and a toolbar menu, in light and dark.
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

ACCENT, WHITE, FG, DISABLED, OPEN_BG = "rgb(38, 117, 191)", "rgb(255, 255, 255)", "rgb(30, 31, 34)", "rgb(163, 166, 173)", "rgb(219, 230, 244)"
DARK_MENU, DARK_ITEM = "rgb(47, 50, 52)", "rgb(53, 112, 176)"

TEMPLATE_CSS = """
  input, button { border-radius: 8px; border: 1px solid transparent; padding: 0.6em 1.2em; font-size: 1em;
    font-weight: 500; font-family: inherit; color: #0f0f0f; background-color: #ffffff; box-shadow: 0 2px 2px rgba(0, 0, 0, 0.2);
    transition: border-color 0.25s; outline: none; }
  button { cursor: pointer; }
  button:hover { border-color: #396cd8; }
  button:active { border-color: #396cd8; background-color: #e8e8e8; }
  :root { font-family: Inter, Avenir, Helvetica, Arial, sans-serif; font-size: 16px; line-height: 24px; font-weight: 400; }
"""

# A bar and a real <button> toolbar menu, built with DOM calls only.
BUILD = """host => {
  const nav = document.createElement("nav"); host.append(nav);
  const tools = document.createElement("div"); tools.className = "tmn-toolbar"; host.append(tools);
  const b = document.createElement("button"); b.className = "tmn-tool"; b.id = "tool"; b.textContent = "Projects"; tools.append(b);
  window.chosen = [];
  window.bar = TaurisMenu.bar(nav, { menus: [
    { label: "File", items: [{ label: "New", shortcut: "⌘N", action: () => chosen.push("new") }, "-", { label: "Quit", shortcut: "⌘Q" }] },
    { label: "Edit", items: [{ label: "Undo", disabled: true }, { label: "Copy", action: () => chosen.push("copy") }] },
  ] });
  window.tool = TaurisMenu.button(b, { items: [{ label: "Health", color: "#1baf7a", action: () => chosen.push("health") }] });
  return 0;
}"""

SIGNATURE = """() => {
  const props = ["padding-left", "border-top-width", "border-top-color", "border-radius", "box-shadow", "background-color",
    "color", "font-size", "font-weight", "height", "line-height"];
  const sig = s => { const c = getComputedStyle(document.querySelector(s)); return Object.fromEntries(props.map(p => [p, c.getPropertyValue(p)])); };
  return Object.fromEntries(["#tool", ".tmn-title"].map(s => [s, sig(s)]));
}"""


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail != "" and not ok else ""))
    if not ok:
        failures.append(name)


def library_script():
    """menus.js as the plugin delivers it: with its stylesheet inside."""
    return (WEB / "menus.js").read_text().replace('"__TAURIS_MENUS_CSS__"', json.dumps((WEB / "menus.css").read_text()))


def fresh(browser, scheme="light", reduced_motion="no-preference"):
    page = browser.new_page(viewport=SIZE, device_scale_factor=2, color_scheme=scheme, locale="en-GB", reduced_motion=reduced_motion)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.goto(DEMO.as_uri())
    page.wait_for_selector(".tmn-title")
    return page


def css(page, selector, prop):
    return page.locator(selector).first.evaluate("(e, p) => getComputedStyle(e).getPropertyValue(p)", prop)


def rect(page, selector):
    return page.locator(selector).first.evaluate("e => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }")


def items(page):
    return page.evaluate("""[...document.querySelectorAll('.tmn-menu > *')].map(i => i.classList.contains('tmn-sep') ? '-'
      : i.querySelector('.tmn-label').textContent + (i.querySelector('.tmn-shortcut') ? ' ' + i.querySelector('.tmn-shortcut').textContent : '')
        + (i.getAttribute('aria-disabled') === 'true' ? ' (off)' : ''))""")


def focused(page):
    return page.evaluate("""(() => { const a = document.activeElement; if (!a) return null;
      return a.querySelector?.('.tmn-label')?.textContent ?? a.textContent.trim() ?? a.className; })()""")


def title(name):
    return f".tmn-title:text-is('{name}')"


def shot(page, name):
    if SHOTS:
        page.screenshot(path=str(SHOTS / f"menus_{name}.png"), animations="disabled")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")

    # ---------- the bar, the look ----------
    page = fresh(browser)
    titles = page.evaluate("[...document.querySelectorAll('.tmn-title')].map(t => [t.textContent, t.getAttribute('role'), t.getAttribute('aria-haspopup'), t.getAttribute('tabindex')])")
    check("the bar: a menubar of menu titles, one of them in the Tab order",
          page.get_attribute("#menubar", "role") == "menubar" and [t[0] for t in titles] == ["File", "Edit", "View", "Window", "Help"]
          and all(t[1] == "menuitem" and t[2] == "menu" for t in titles) and [t[3] for t in titles].count("0") == 1, titles)
    check("the bar: 24px, a line under it", rect(page, "#menubar")["h"] == 24 and css(page, "#menubar", "border-bottom-width") == "1px")
    check("a menu that is off is grey", page.get_attribute(title("Window"), "aria-disabled") == "true" and css(page, title("Window"), "color") == DISABLED)
    page.click(title("File"))
    page.wait_for_timeout(150)  # the menu eases in by 2px
    check("a click opens the menu under its title", page.is_visible(".tmn-menu") and page.get_attribute(title("File"), "aria-expanded") == "true"
          and abs(rect(page, ".tmn-menu")["y"] - (rect(page, title("File"))["y"] + rect(page, title("File"))["h"])) < 1 and abs(rect(page, ".tmn-menu")["x"] - rect(page, title("File"))["x"]) < 1)
    check("its items: labels, shortcuts, lines, items that are off (made when it opens)",
          items(page) == ["Add files… ⌘O", "New folder… (off)", "-", "Open ↩ (off)", "Rename F2 (off)", "Delete ⌘⌫ (off)"], items(page))
    check("the menu: at least 220px, items 24px, a shadow, the open title tinted",
          rect(page, ".tmn-menu")["w"] >= 220 and rect(page, ".tmn-item")["h"] == 24 and css(page, ".tmn-menu", "box-shadow") != "none"
          and css(page, title("File"), "background-color") == OPEN_BG)
    check("the menu names itself and its title points to it",
          page.get_attribute(".tmn-menu", "role") == "menu" and page.get_attribute(".tmn-menu", "aria-label") == "File"
          and page.get_attribute(title("File"), "aria-controls") == page.get_attribute(".tmn-menu", "id"))
    page.hover(".tmn-item:has-text('Add files')")
    check("the item under the mouse: white on the accent",
          css(page, ".tmn-item:has-text('Add files')", "background-color") == ACCENT and css(page, ".tmn-item:has-text('Add files')", "color") == WHITE)
    page.hover(".tmn-item:has-text('New folder')")
    check("an item that is off does not light up", css(page, ".tmn-item:has-text('New folder')", "background-color") == "rgba(0, 0, 0, 0)")
    page.click(".tmn-item:has-text('New folder')", force=True)  # Playwright itself will not click an item that is off
    check("a click on an item that is off does nothing; the menu stays", page.is_visible(".tmn-menu"))
    page.hover(title("View"))
    check("with a menu open, pointing at another title opens that one",
          page.get_attribute(".tmn-menu", "aria-label") == "View" and page.locator(".tmn-menu").count() == 1
          and page.get_attribute(title("File"), "aria-expanded") == "false")
    check("checkable items: a ✓ column", page.evaluate("[...document.querySelectorAll('.tmn-item')].slice(0, 3).map(i => [i.getAttribute('role'), i.getAttribute('aria-checked'), i.querySelector('.tmn-check').textContent])")
          == [["menuitemcheckbox", "true", "✓"]] * 3)
    shot(page, "bar_light")
    page.click(".tmn-item:has-text('Added by')")
    check("choosing an item closes the menu and runs it", page.locator(".tmn-menu").count() == 0 and page.locator(".tf-th.tf-c-by").count() == 0)
    page.click(title("View"))
    check("the menu shows the state at the time it opens", page.get_attribute(".tmn-item:has-text('Added by')", "aria-checked") == "false")
    page.click(title("View"))
    check("a click on the open menu's title closes it", page.locator(".tmn-menu").count() == 0 and page.get_attribute(title("View"), "aria-expanded") == "false")
    page.click(title("Help"))
    page.click(".tf-title")
    check("a click elsewhere closes it", page.locator(".tmn-menu").count() == 0)
    page.click(title("Window"), force=True)
    check("a menu that is off does not open", page.locator(".tmn-menu").count() == 0)
    page.close()

    # ---------- keyboard ----------
    page = fresh(browser)
    page.evaluate("demo.bar.focus()")
    check("focus() puts the focus on the first title", focused(page) == "File")
    page.keyboard.press("ArrowRight")
    check("Right: the next title", focused(page) == "Edit")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    check("titles that are off are passed over", focused(page) == "Help")
    page.keyboard.press("ArrowRight")
    check("Right wraps round", focused(page) == "File")
    page.keyboard.press("End")
    page.keyboard.press("Home")
    check("End and Home", focused(page) == "File")
    page.keyboard.press("Enter")
    check("Enter opens with the first item that is on chosen", page.is_visible(".tmn-menu") and focused(page) == "Add files…")
    page.keyboard.press("ArrowDown")
    check("Down passes over items that are off and wraps", focused(page) == "Add files…")
    page.keyboard.press("ArrowRight")
    check("Right opens the next menu, its first item chosen", page.get_attribute(".tmn-menu", "aria-label") == "Edit" and focused(page) == "Find…"
          and page.locator(".tmn-menu").count() == 1)
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("ArrowLeft")
    check("Left goes back, and wraps past the menus that are off", page.get_attribute(".tmn-menu", "aria-label") == "Help")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    check("View, from the keyboard", page.get_attribute(".tmn-menu", "aria-label") == "View" and focused(page) == "Size")
    page.keyboard.press("End")
    check("End: the last item", focused(page) == "Sort by date added")
    page.keyboard.press("Home")
    page.keyboard.press("s")
    check("a letter: the next item starting with it", focused(page) == "Sort by name")
    page.wait_for_timeout(800)
    page.keyboard.type("sort by s")
    check("letters typed quickly spell a label, spaces too", focused(page) == "Sort by size" and page.is_visible(".tmn-menu"))
    page.keyboard.press("Escape")
    check("Escape closes it and puts the focus back on its title", page.locator(".tmn-menu").count() == 0 and focused(page) == "View")
    page.keyboard.press("ArrowUp")
    check("Up on a title opens the menu at its last item", focused(page) == "Sort by date added")
    page.keyboard.press("Tab")
    check("Tab closes it", page.locator(".tmn-menu").count() == 0)
    page.focus(".tf-q")
    page.keyboard.type("plan")
    page.click(title("Edit"))
    check("opened with the mouse: nothing chosen yet; Down chooses the first", focused(page) == "" or focused(page) is None or page.evaluate("document.activeElement.classList.contains('tmn-menu')"))
    page.keyboard.press("ArrowDown")
    check("Down from there", focused(page) == "Find…")
    page.keyboard.press("Escape")
    check("Escape after a mouse open: the focus goes back to where it was (the search field)", page.evaluate("document.activeElement.classList.contains('tf-q')"))
    page.click(".tf-file .tf-c-name")
    page.click(title("File"))
    page.click(".tmn-item:has-text('Rename')")
    check("an item runs after the focus is back: Rename puts it in the name field", page.evaluate("document.activeElement.classList.contains('tf-rename')"))
    page.keyboard.press("Escape")
    page.close()

    # ---------- menu buttons and menus at a point ----------
    page = fresh(browser)
    tb = "#tb-projects"
    check("a menu button: has a menu, says when it is open, and a ▾",
          page.get_attribute(tb, "aria-haspopup") == "menu" and page.get_attribute(tb, "aria-expanded") == "false"
          and page.get_attribute(tb, "role") == "button" and page.get_attribute(tb, "tabindex") == "0"
          and page.evaluate("(() => { const c = getComputedStyle(document.querySelector('#tb-projects'), '::after'); return [c.content, c.width, c.borderBottomStyle]; })()") == ['""', "4px", "solid"])
    check("the toolbar look: 26px buttons", rect(page, tb)["h"] == 26 and rect(page, "#tb-docs")["h"] == 26
          and css(page, "#tb-docs", "background-color") == OPEN_BG)
    page.click(tb)
    page.wait_for_timeout(150)
    menu, button = rect(page, ".tmn-menu"), rect(page, tb)
    check("a click opens it 3px under the button", abs(menu["y"] - (button["y"] + button["h"] + 3)) <= 1 and abs(menu["x"] - button["x"]) < 1
          and page.get_attribute(tb, "aria-expanded") == "true" and css(page, tb, "background-color") == OPEN_BG)
    chips = page.evaluate("[...document.querySelectorAll('.tmn-chip')].map(c => getComputedStyle(c).backgroundColor)")
    check("items with a colour show it as a chip", chips == ["rgb(42, 120, 214)", "rgb(235, 104, 52)", "rgb(27, 175, 122)", "rgb(237, 161, 0)"], chips)
    shot(page, "button_light")
    page.click(tb)
    check("the button again closes it", page.locator(".tmn-menu").count() == 0)
    page.click("#tb-docs")
    check("counts sit where shortcuts go", items(page) == ["Northwind Launch 8", "Seed Round 2026 0", "Health 0", "Open Loops 0"], items(page))
    page.click(".tmn-item:has-text('Health')")
    check("choosing runs the item", page.inner_text(".tf-title") == "Health")
    page.focus(tb)
    page.keyboard.press("Enter")
    check("Enter opens it with the first item chosen", focused(page) == "Edit Northwind Launch…")
    page.keyboard.press("Escape")
    check("Escape: the focus is back on the button", page.evaluate("document.activeElement.id") == "tb-projects")
    page.keyboard.press("ArrowUp")
    check("Up opens it at its last item", focused(page) == "Edit Open Loops…")
    page.keyboard.press("Enter")
    check("Enter chooses", page.inner_text("#msg") == "Edit Open Loops")
    page.click(title("File"))
    page.evaluate("TaurisMenu.open([{ label: 'Elsewhere' }], { x: 600, y: 300 })")
    check("one menu at a time", page.locator(".tmn-menu").count() == 1 and page.get_attribute(title("File"), "aria-expanded") == "false")
    page.keyboard.press("Escape")
    at_edge = page.evaluate("""() => { const h = TaurisMenu.open([{ label: 'One' }, { label: '<b>Two</b>' }, { label: 'Three' }], { x: 990, y: 550 });
      const r = document.querySelector('.tmn-menu').getBoundingClientRect(); const b = document.querySelectorAll('.tmn-menu b').length;
      const text = document.querySelectorAll('.tmn-label')[1].textContent; h.close(); return [r.right <= 1000 - 4, r.bottom <= 560 - 4, b, text]; }""")
    check("a menu at a point stays inside the window", at_edge[0] and at_edge[1], at_edge)
    check("labels are text, never markup", at_edge[2] == 0 and at_edge[3] == "<b>Two</b>", at_edge)
    page.close()

    # ---------- inside a modal dialog, and leaving the window ----------
    page = fresh(browser)
    in_dialog = page.evaluate("""() => { const d = document.createElement('dialog'); const b = document.createElement('button');
      b.textContent = 'Choose'; d.append(b); document.body.append(d); d.showModal(); window.picked = null;
      TaurisMenu.button(b, { items: [{ label: 'First', action: () => (picked = 'first') }] }); b.focus(); return 0; }""")
    page.keyboard.press("Enter")
    page.keyboard.press("Enter")
    check("a menu opened inside a modal dialog works (it hangs in the dialog)", page.evaluate("picked") == "first")
    page.evaluate("document.querySelector('dialog').close()")
    page.evaluate("demo.bar.focus()")
    page.keyboard.press("Enter")
    page.evaluate("window.dispatchEvent(new Event('blur'))")
    check("leaving the window closes the menu and puts the focus back on its title",
          page.locator(".tmn-menu").count() == 0 and focused(page) == "File")
    page.close()

    # ---------- sub-menus ----------
    page = fresh(browser)
    page.evaluate("""() => { demo.bar.destroy(); window.picked = []; window.ev2 = [];
      const pick = name => () => picked.push(name);
      window.bar3 = TaurisMenu.bar(document.getElementById('menubar'), {
        onClose: i => ev2.push(i.chosen),
        menus: [
          { label: 'File', items: [
            { label: 'New', action: pick('new') },
            { label: 'Open Recent', items: () => [
              { label: 'Budget.xlsx', action: pick('budget') },
              { label: 'More', items: [{ label: 'Deck.pdf', action: pick('deck') }] },
              { label: 'Gone.txt', disabled: true } ] },
            { label: 'Share', disabled: true, items: [{ label: 'Mail' }] },
            { label: 'Quit', action: pick('quit') } ] },
          { label: 'Edit', items: [{ label: 'Copy', action: pick('copy') }] } ] });
      return 0; }""")
    page.click(title("File"))
    parent = ".tmn-menu >> nth=0 >> .tmn-item:has-text('Open Recent')"
    check("an item with a sub-menu says so and shows an arrow",
          page.get_attribute(parent, "aria-haspopup") == "menu" and page.get_attribute(parent, "aria-expanded") == "false"
          and page.locator(parent + " .tmn-sub").count() == 1 and page.locator(parent + " .tmn-shortcut").count() == 0)
    page.hover(parent)
    page.wait_for_timeout(300)
    sub = page.locator(".tmn-menu").nth(1)
    pr, sr = page.locator(parent).bounding_box(), sub.bounding_box()
    check("resting the mouse on it opens the sub-menu to its right, the item stays lit",
          page.locator(".tmn-menu").count() == 2 and abs(sr["x"] - (pr["x"] + pr["width"] - 3)) <= 2
          and page.get_attribute(parent, "aria-expanded") == "true"
          and page.evaluate("getComputedStyle(document.querySelector('.tmn-item[aria-expanded=\"true\"]')).backgroundColor") == ACCENT, (pr, sr))
    page.hover(".tmn-menu >> nth=1 >> .tmn-item:has-text('Budget')")
    page.click(".tmn-menu >> nth=1 >> .tmn-item:has-text('Budget')")
    check("choosing in the sub-menu runs the item and closes every menu, as a choice",
          page.evaluate("picked") == ["budget"] and page.locator(".tmn-menu").count() == 0 and page.evaluate("ev2.splice(0)") == [True])
    page.click(title("File"))
    page.hover(parent)
    page.wait_for_timeout(300)
    page.hover(".tmn-menu >> nth=0 >> .tmn-item:has-text('Quit')")
    page.wait_for_timeout(100)
    still = page.locator(".tmn-menu").count()
    page.wait_for_timeout(300)
    check("moving on to another item closes the sub-menu a moment later (time to reach it)", still == 2 and page.locator(".tmn-menu").count() == 1)
    page.keyboard.press("Escape")
    page.evaluate("bar3.focus()")
    page.keyboard.press("Enter")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowRight")
    check("from the keyboard: Right opens the sub-menu at its first item", focused(page) == "Budget.xlsx" and page.locator(".tmn-menu").count() == 2)
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    check("Enter on a sub-menu item opens the next level", focused(page) == "Deck.pdf" and page.locator(".tmn-menu").count() == 3)
    page.keyboard.press("ArrowLeft")
    check("Left closes it and goes back to its item", focused(page) == "More" and page.locator(".tmn-menu").count() == 2)
    page.keyboard.press("ArrowDown")
    check("an item that is off is passed over in the sub-menu too", focused(page) == "Budget.xlsx")
    page.keyboard.press("Escape")
    check("Escape closes only the sub-menu", focused(page) == "Open Recent" and page.locator(".tmn-menu").count() == 1)
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowRight")
    check("a sub-menu item that is off does not open (Share is skipped; Right on Quit moves to Edit)",
          page.get_attribute(".tmn-menu", "aria-label") == "Edit" and page.locator(".tmn-menu").count() == 1, focused(page))
    page.keyboard.press("Escape")
    page.click(title("File"))
    page.hover(parent)
    page.wait_for_timeout(300)
    page.mouse.click(900, 500)
    check("a click outside closes every level, as no choice", page.locator(".tmn-menu").count() == 0 and page.evaluate("ev2.slice(-1)") == [False])
    edge = page.evaluate("""() => { TaurisMenu.open([{ label: 'Sub', items: [{ label: 'A long item name here' }] }], { x: 960, y: 100 }, { keyboard: true });
      return 0; }""")
    page.keyboard.press("ArrowRight")
    boxes = page.evaluate("[...document.querySelectorAll('.tmn-menu')].map(m => m.getBoundingClientRect().toJSON())")
    check("near the right edge the sub-menu opens to the left", boxes[1]["right"] <= boxes[0]["left"] + 4 and boxes[1]["left"] >= 0, boxes)
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    page.close()

    # ---------- sub-menus: the edges a review found ----------
    page = fresh(browser)
    page.evaluate("""() => { demo.bar.setMenus([{ label: 'File', items: [{ label: 'New' },
      { label: 'Open Recent', items: [{ label: 'Budget.xlsx' }] }, { label: 'Share', disabled: true, items: [{ label: 'Mail' }] },
      { label: 'Quit' }] }]); return 0; }""")
    page.click(title("File"))
    page.hover(".tmn-item:has-text('Open Recent')")
    page.wait_for_timeout(300)
    page.keyboard.press("ArrowDown")
    check("moving with the keys closes a sub-menu the mouse opened: one item lit",
          page.locator(".tmn-menu").count() == 1 and page.locator('.tmn-item[aria-expanded="true"]').count() == 0)
    page.keyboard.press("Escape")
    page.click(title("File"))
    item = page.locator(".tmn-item:has-text('Open Recent')").bounding_box()
    page.mouse.move(item["x"] + 20, item["y"] + item["height"] / 2)
    page.mouse.move(item["x"] + 20, item["y"] + 400, steps=2)
    page.wait_for_timeout(300)
    check("leaving the menu downwards drops a sub-menu that was about to open", page.locator(".tmn-menu").count() == 1)
    page.mouse.move(item["x"] + 20, item["y"] + item["height"] / 2)
    page.mouse.move(item["x"] + item["width"] + 30, item["y"] + item["height"] / 2, steps=2)
    page.wait_for_timeout(300)
    check("leaving it sideways, towards the sub-menu, still opens it", page.locator(".tmn-menu").count() == 2)
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    page.click(title("File"))
    page.locator(".tmn-item:has-text('Share')").focus()
    page.keyboard.press("Enter")
    enter_opens = page.locator(".tmn-menu").count()
    page.locator(".tmn-item:has-text('Share')").focus()
    page.keyboard.press("ArrowRight")
    check("Enter or Right on a sub-menu item that is off opens no sub-menu",
          enter_opens == 1 and page.locator(".tmn-menu[aria-label='Share']").count() == 0)
    page.close()

    # ---------- sub-menus: a second review ----------
    page = fresh(browser)
    page.evaluate("""() => { demo.bar.setMenus([{ label: 'File', items: [{ label: 'New' },
      { label: 'Open Recent', items: [{ label: 'Budget.xlsx' }] }, { label: 'Print' }] }]); return 0; }""")
    page.click(title("File"))
    page.hover(".tmn-item:has-text('Open Recent')")
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(300)
    check("a key pressed while a sub-menu is about to open stops it", page.locator(".tmn-menu").count() == 1 and focused(page) == "Print")
    page.hover(".tmn-item:has-text('Open Recent')")
    page.wait_for_timeout(300)
    page.hover(".tmn-item:has-text('New')")
    box = page.locator(".tmn-menu").first.bounding_box()
    page.mouse.move(box["x"] - 30, box["y"] + 10, steps=2)
    page.wait_for_timeout(400)
    check("a sub-menu about to close still closes when the mouse leaves the menu", page.locator(".tmn-menu").count() == 1)
    item = page.locator(".tmn-item:has-text('Open Recent')").bounding_box()
    page.mouse.move(item["x"] + 20, item["y"] + item["height"] / 2)
    page.mouse.move(box["x"] - 30, item["y"] + item["height"] / 2, steps=2)
    page.wait_for_timeout(300)
    check("leaving beside the item but away from the sub-menu's side does not open it", page.locator(".tmn-menu").count() == 1)
    page.close()

    # ---------- sub-menus: a third review ----------
    page = fresh(browser)
    page.evaluate("""() => { demo.bar.setMenus([{ label: 'File', items: [{ label: 'Open Recent', items: [{ label: 'A' }] },
      { label: 'Empty', items: [] }] }]); return 0; }""")
    page.click(title("File"))
    page.locator(".tmn-item:has-text('Open Recent')").focus()
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowLeft")
    check("a closed sub-menu leaves no pointer to it", page.get_attribute(".tmn-item:has-text('Open Recent')", "aria-controls") is None)
    page.locator(".tmn-item:has-text('Empty')").focus()
    page.keyboard.press("ArrowRight")
    check("an empty sub-menu does not open", page.locator(".tmn-menu").count() == 1)
    page.close()

    # ---------- onOpen and onClose (for a sound) ----------
    page = fresh(browser)
    page.evaluate("""() => { demo.bar.destroy(); window.ev = [];
      const hooks = { onOpen: i => ev.push(['open', i.label, i.how]), onClose: i => ev.push(['close', i.label, i.chosen]) };
      window.bar2 = TaurisMenu.bar(document.getElementById('menubar'), { ...hooks, menus: [
        { label: 'File', items: [{ label: 'New', action: () => {} }] }, { label: 'Edit', items: [{ label: 'Copy' }] }] });
      const b = document.createElement('span'); b.id = 'tools'; b.className = 'tmn-tool'; b.textContent = 'Tools';
      document.getElementById('toolbar').append(b);
      TaurisMenu.button(b, { ...hooks, items: [{ label: 'Sort' }] }); return 0; }""")
    events = lambda: page.evaluate("ev.splice(0)")
    page.click(title("File"))
    page.hover(title("Edit"))
    hop = events()
    page.click(".tf-title")
    check("onOpen on the first menu; moving to the next menu of the bar fires nothing; a click outside closes without a choice",
          hop == [["open", "File", "mouse"]] and events() == [["close", "Edit", False]], hop)
    page.click(title("File"))
    page.click(title("File"))
    check("its title again: open, then closed without a choice", events() == [["open", "File", "mouse"], ["close", "File", False]])
    page.evaluate("bar2.focus()")
    page.keyboard.press("Enter")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("Escape")
    check("from the keyboard: how is keyboard; Left and Right fire nothing; Escape closes without a choice",
          events() == [["open", "File", "keyboard"], ["close", "File", False]])
    page.click(title("File"))
    page.click(".tmn-item:has-text('New')")
    check("choosing an item: closed with chosen true", events() == [["open", "File", "mouse"], ["close", "File", True]])
    page.click("#tools")
    page.keyboard.press("Escape")
    page.focus("#tools")
    page.keyboard.press("Enter")
    page.keyboard.press("Enter")
    check("a menu button has the same hooks",
          events() == [["open", "Tools", "mouse"], ["close", "Tools", False], ["open", "Tools", "keyboard"], ["close", "Tools", True]])
    popup = page.evaluate("""() => { const seen = []; TaurisMenu.open([{ label: 'A' }], { x: 300, y: 300 }, { label: 'Row', onClose: i => seen.push(i) });
      document.querySelector('.tmn-item').click(); return seen; }""")
    check("a menu at a point tells its onClose whether an item was chosen", popup == [{"label": "Row", "chosen": True}], popup)
    page.close()

    # ---------- destroy ----------
    page = fresh(browser)
    left = page.evaluate("""() => { demo.bar.destroy(); const nav = document.getElementById('menubar');
      const b = TaurisMenu.button(document.getElementById('home'), { items: [{ label: 'x' }], caret: false });
      const caret = document.getElementById('home').classList.contains('tmn-caret'); b.destroy();
      const h = document.getElementById('home');
      return [nav.children.length, nav.getAttribute('role'), nav.className, caret, h.getAttribute('aria-haspopup'), h.getAttribute('aria-expanded'), h.className]; }""")
    check("destroy() leaves the elements as they were", left == [0, None, "", False, None, None, "tmn-tool"], left)
    again = page.evaluate("TaurisMenu.bar(document.getElementById('menubar'), { menus: [{ label: 'Only', items: [] }] }) && document.querySelectorAll('.tmn-title').length")
    check("a bar can be made again after destroy()", again == 1)
    try:
        page.evaluate("TaurisMenu.bar(document.getElementById('menubar'), { menus: [] })")
        check("a second bar on one element is refused", False)
    except Exception:
        check("a second bar on one element is refused", True)
    page.close()

    # ---------- dark, reduced motion ----------
    page = fresh(browser, "dark")
    page.click(title("View"))
    page.keyboard.press("ArrowDown")
    shot(page, "bar_dark")
    check("dark: the menu and the chosen item follow the system",
          css(page, ".tmn-menu", "background-color") == DARK_MENU and css(page, ".tmn-item:focus", "background-color") == DARK_ITEM)
    page.close()
    page = fresh(browser, reduced_motion="reduce")
    page.click(title("File"))
    check("reduced motion: the menu appears without moving", css(page, ".tmn-menu", "animation-name") == "none")
    page.close()

    # ---------- as the plugin delivers it ----------
    page = browser.new_page(viewport={"width": 700, "height": 300}, device_scale_factor=2)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.add_init_script(library_script())
    page.goto((HERE / "page.html").as_uri())
    check("no stylesheet is added before a menu is used", page.evaluate("document.adoptedStyleSheets.length") == 0)
    page.evaluate("(" + BUILD + ")(document.body)")
    check("using it adds its stylesheet once", page.evaluate("document.adoptedStyleSheets.length") == 1 and rect(page, ".tmn-bar")["h"] == 24)
    before = page.evaluate(SIGNATURE)
    page.add_style_tag(content=TEMPLATE_CSS)
    page.wait_for_timeout(100)
    after = page.evaluate(SIGNATURE)
    changed = {s: {k: (before[s][k], after[s][k]) for k in before[s] if before[s][k] != after[s][k]} for s in before}
    changed = {s: d for s, d in changed.items() if d}
    check("a starter template's button rules do not restyle a <button class=\"tmn-tool\">", not changed, changed)
    page.hover("#tool")
    page.wait_for_timeout(150)
    check("nor its hover", css(page, "#tool", "border-top-color") == "rgb(196, 198, 204)")
    page.click("#tool")
    check("a real <button> opens its menu", page.is_visible(".tmn-menu") and page.get_attribute("#tool", "aria-expanded") == "true")
    page.click(".tmn-item")
    check("and runs the item", page.evaluate("chosen") == ["health"])
    page.close()

    # ---------- under a strict content policy ----------
    page = browser.new_page(viewport={"width": 700, "height": 300}, device_scale_factor=2)
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.add_init_script("window.__csp = []; document.addEventListener('securitypolicyviolation', e => __csp.push(e.violatedDirective + ' ' + e.blockedURI));")
    page.add_init_script(library_script())
    page.goto((HERE / "csp.html").as_uri())
    page.evaluate("(" + BUILD + ")(document.getElementById('t'))")
    page.click(".tmn-title:text-is('File')")
    page.click(".tmn-item:has-text('New')")
    page.click("#tool")
    page.wait_for_timeout(150)
    check("strict policy: the menus open where they should, with their chips, and run their items",
          page.evaluate("chosen") == ["new"] and css(page, ".tmn-chip", "background-color") == "rgb(27, 175, 122)"
          and abs(rect(page, ".tmn-menu")["y"] - (rect(page, "#tool")["y"] + rect(page, "#tool")["h"] + 3)) <= 1)  # the pressed button sits 0.5px lower
    check("strict policy: no console errors and nothing refused", not errors and page.evaluate("__csp") == [], (errors, page.evaluate("__csp")))
    page.close()

    browser.close()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
