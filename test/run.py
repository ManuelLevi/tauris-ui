"""Tests the page side of tauris-ui in a headless browser (nothing touches the screen).

Run:  python test/run.py [screenshot-folder]
Needs Python playwright and Google Chrome. Exits non-zero when a check fails.
"""
import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
WEB = HERE.parent / "web"
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def library_script(can_drag_out=True):
    css = (WEB / "tabs.css").read_text()
    return (WEB / "tabs.js").read_text().replace('"__TAURIS_TABS_CSS__"', json.dumps(css)) \
        .replace("__TAURIS_TABS_VERSION__", "test") \
        .replace('"__TAURIS_TABS_CAN_DRAG_OUT__"', "true" if can_drag_out else "false")


def shot(page, name):
    if SHOTS:
        page.screenshot(path=str(SHOTS / f"tabs_{name}.png"), clip={"x": 0, "y": 0, "width": 760, "height": 220})


def titles(page):
    return page.evaluate("[...document.querySelectorAll('.tt-tabs .tt-tab:not(.tt-ghost) .tt-title')].map(e => e.textContent)")


def fresh(browser, options="{}", before="", width=760, color_scheme="dark", can_drag_out=True):
    page = browser.new_page(viewport={"width": width, "height": 300}, device_scale_factor=2, color_scheme=color_scheme)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.errors = []
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    if before:
        page.add_init_script(before)
    page.add_init_script((HERE / "mock_tauri.js").read_text())
    page.add_init_script(library_script(can_drag_out))
    page.goto((HERE / "page.html").as_uri())
    page.evaluate(f"window.tabs = TaurisTabs.mount(document.getElementById('strip'), {options})")
    if "__deny" not in before:
        page.wait_for_selector(".tt-tab")
    return page


def tab_box(page, n):
    return page.locator(".tt-tabs .tt-tab:not(.tt-ghost)").nth(n).bounding_box()


# ---------- the README's colours: every pair of text and what it sits on reads ----------
def _lum(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _ratio(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


_block = (HERE.parent / "README.md").read_text().split("```css", 1)[1].split("```", 1)[0]
_light = dict(re.findall(r"--tauris-([\w-]+): (#[0-9a-f]{6})", _block.split("@media")[0]))
_dark = dict(re.findall(r"--tauris-([\w-]+): (#[0-9a-f]{6})", _block.split(":root[data-tauris-theme=\"dark\"]")[1]))
_system_dark = dict(re.findall(r"--tauris-([\w-]+): (#[0-9a-f]{6})", _block.split("@media")[1].split(":root[data-tauris-theme=\"dark\"]")[0]))
check("the README's two dark blocks (the system's, the app's choice) say the same", _system_dark == _dark and len(_dark) >= 13, (_system_dark, _dark))
_pairs = [("fg", "bg"), ("fg", "chrome"), ("fg", "hover"), ("fg", "sel-inactive"), ("dim", "bg"), ("dim", "chrome"), ("dim", "hover"),
          ("accent-ink", "bg"), ("accent-ink", "chrome"), ("on-accent", "accent"), ("sel-fg", "sel-bg")]
for _name, _set in (("light", _light), ("dark", _dark)):
    _low = [(a, b, round(_ratio(_set[a], _set[b]), 2)) for a, b in _pairs if _ratio(_set[a], _set[b]) < 4.5]
    check(f"the README's {_name} colours: text reads on what it sits on (4.5:1)", len(_set) >= 13 and not _low, (_low, len(_set)))

with sync_playwright() as p:
    # CI runs the Chromium of the pinned Playwright (the same browser every day); here, Chrome.
    browser = p.chromium.launch(channel=None if os.environ.get("TAURIS_TEST_CHROMIUM") else "chrome")

    # --- rendering ---
    page = fresh(browser)
    check("renders the three tabs", titles(page) == ["Tab 1", "Tab 2", "Tab 3"], titles(page))
    check("first tab is active", page.locator(".tt-tab.tt-active .tt-title").text_content() == "Tab 1")
    check("window title follows the active tab", page.title() == "Tab 1", page.title())
    check("strip is 40px high", page.locator("#strip").bounding_box()["height"] == 40)
    shot(page, "1_default")

    # --- click, new, close ---
    page.locator(".tt-tab").nth(2).click()
    check("click activates a tab", page.locator(".tt-tab.tt-active .tt-title").text_content() == "Tab 3")
    page.locator(".tt-new").click()
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 4")
    page.wait_for_timeout(300)  # the new tab pops in
    check("+ adds a tab and activates it", titles(page)[-1] == "Tab 4" and page.title() == "Tab 4")
    page.locator(".tt-tab").nth(3).hover()
    page.locator(".tt-tab").nth(3).locator(".tt-close").click()
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 3")
    check("× closes the tab", titles(page) == ["Tab 1", "Tab 2", "Tab 3"], titles(page))
    page.locator(".tt-tab").nth(1).click(button="middle")
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 2")
    check("middle click closes the tab", titles(page) == ["Tab 1", "Tab 3"], titles(page))

    # --- right-click menu ---
    page.locator(".tt-tab").nth(0).click(button="right")
    page.wait_for_selector(".tt-menu")
    labels = page.evaluate("[...document.querySelectorAll('.tt-menu-item .tt-menu-label')].map(e => e.textContent)")
    check("right click opens the menu", labels == ["New tab", "Close tab", "Close other tabs", "Close tabs to the right", "Move to new window"], labels)
    shot(page, "2_menu")
    page.keyboard.press("Escape")
    check("Escape closes the menu", page.locator(".tt-menu").count() == 0)
    page.locator(".tt-tab").nth(1).click(button="right")
    page.get_by_text("Close tab", exact=True).click()
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 1")
    check("Close tab in the menu closes that tab", titles(page) == ["Tab 1"], titles(page))
    page.locator(".tt-new").click()
    page.locator(".tt-new").click()
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 3")
    page.locator(".tt-tab").nth(0).click(button="right")
    page.get_by_text("Close other tabs", exact=True).click()
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 1")
    check("Close other tabs keeps only that tab", titles(page) == ["Tab 1"], titles(page))
    page.locator(".tt-tab").nth(0).click(button="right")
    disabled = page.evaluate("[...document.querySelectorAll('.tt-menu-item')].filter(b => b.getAttribute('aria-disabled') === 'true').map(b => b.textContent)")
    check("items that do nothing are disabled", len(disabled) == 3, disabled)
    page.keyboard.press("Escape")
    page.close()

    # --- drag reorder ---
    page = fresh(browser)
    a, c = tab_box(page, 0), tab_box(page, 2)
    page.mouse.move(a["x"] + 40, a["y"] + 16)
    page.mouse.down()
    page.mouse.move(a["x"] + 120, a["y"] + 16, steps=4)
    page.mouse.move(c["x"] + 80, c["y"] + 16, steps=8)
    shot(page, "3_drag_tab")
    page.mouse.up()
    page.wait_for_timeout(400)
    check("dragging a tab past the others reorders them", page.evaluate("window.__titles()") == ["Tab 2", "Tab 3", "Tab 1"], page.evaluate("window.__titles()"))
    page.close()

    # --- drag out ---
    page = fresh(browser)
    a = tab_box(page, 1)
    page.mouse.move(a["x"] + 40, a["y"] + 16)
    page.mouse.down()
    page.mouse.move(a["x"] + 40, a["y"] + 120, steps=6)
    calls = page.evaluate("window.__calls.map(c => c[0])")
    check("dragging below the strip hands the tab to Rust", "drag_out" in calls, calls)
    page.mouse.up()
    page.close()

    # --- drag previews ---
    for mode in ["ghost", "title", "none"]:
        page = fresh(browser, f"{{ dragPreview: '{mode}' }}")
        a = tab_box(page, 0)
        page.mouse.move(a["x"] + 40, a["y"] + 16)
        page.mouse.down()
        page.mouse.move(a["x"] + 100, a["y"] + 30, steps=4)
        page.mouse.move(a["x"] + 260, a["y"] + 30, steps=6)
        floating = page.locator(".tt-preview").count()
        check(f"dragPreview '{mode}' " + ("floats nothing" if mode == "none" else "floats a preview"),
              floating == (0 if mode == "none" else 1), floating)
        check(f"dragPreview '{mode}' leaves the tab's slot dimmed", page.locator(".tt-tab.tt-slot").count() == 1)
        shot(page, f"4_preview_{mode}")
        page.mouse.up()
        page.wait_for_timeout(300)
        check(f"dragPreview '{mode}' clears the preview on release", page.locator(".tt-preview").count() == 0)
        page.close()

    # --- customising ---
    page = fresh(browser, """{
      renderTab: (tab, { active }) => { const s = document.createElement('span'); s.className = 'tt-title'; s.textContent = '#' + tab.title;
        const x = document.createElement('b'); x.setAttribute('data-tt-close', ''); x.textContent = 'x'; return [s, x]; },
      contextMenu: (tab, items) => [...items, '-', { label: 'Rename', action: () => window.__renamed = tab && tab.title }],
      tabClass: tab => 'mine'
    }""")
    page.add_style_tag(content=":root { --tt-accent: #ff00aa; --tt-tab-radius: 0px; }")
    check("renderTab replaces the tab contents", titles(page)[0] == "#Tab 1", titles(page))
    check("tabClass adds a class", page.locator(".tt-tab.mine").count() == 3)
    check("an app's own variables win over the defaults",
          page.evaluate("getComputedStyle(document.querySelector('.tt-tab.tt-active')).borderTopLeftRadius") == "0px")
    page.locator(".tt-tab").nth(0).hover()
    page.locator(".tt-tab").nth(0).locator("b").click()
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 2")
    check("data-tt-close closes the tab", titles(page)[0] == "#Tab 2", titles(page))
    page.locator(".tt-tab").nth(0).click(button="right")
    page.get_by_text("Rename", exact=True).click()
    check("contextMenu can add items", page.evaluate("window.__renamed") == "Tab 2")
    shot(page, "5_custom")
    page.close()

    # --- one look for every component ---
    page = fresh(browser)
    page.add_style_tag(content=":root { --tauris-accent: rgb(1, 2, 3); --tauris-bg: rgb(4, 5, 6); --tauris-fg: rgb(7, 8, 9); --tauris-chrome: rgb(10, 11, 12); --tauris-sel-bg: rgb(13, 14, 15); --tauris-font: Georgia, serif; }")
    look = page.evaluate("""() => { const r = getComputedStyle(document.documentElement), v = n => r.getPropertyValue(n).trim();
      return [v('--tt-accent'), v('--tt-active-bg'), v('--tt-strip-bg'), v('--tt-fg-active'), getComputedStyle(document.querySelector('.tt-tab')).fontFamily]; }""")
    # The accent alone: its bar is the accent made light enough to read on the (dark) strip.
    check("the tabs follow the shared --tauris-* colours and font",
          look == ["oklch(from rgb(1, 2, 3) clamp(0.75, l * 1, 1) c h)", "rgb(4, 5, 6)", "rgb(10, 11, 12)", "rgb(7, 8, 9)", "Georgia, serif"], look)
    page.add_style_tag(content=":root { --tauris-accent-ink: rgb(16, 17, 18); }")
    check("with --tauris-accent-ink, the bar is that", page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--tt-accent').trim()") == "rgb(16, 17, 18)")
    page.close()

    # --- the app chooses light or dark ---
    page = fresh(browser, color_scheme="dark")
    page.evaluate("document.documentElement.dataset.taurisTheme = 'light'")
    strip = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--tt-strip-bg').trim()")
    check("system dark, app light (data-tauris-theme): the strip follows the app", strip == "#ececef", strip)
    page.close()

    # --- right click on the empty strip ---
    page = fresh(browser)
    page.mouse.click(745, 20, button="right")
    page.wait_for_selector(".tt-menu")
    labels = page.evaluate("[...document.querySelectorAll('.tt-menu-item .tt-menu-label')].map(e => e.textContent)")
    check("right click on the empty strip offers a new tab", labels == ["New tab"], labels)
    page.close()


    # --- many tabs: the row scrolls, + stays reachable ---
    page = fresh(browser, before="window.__tabCount = 50", width=960)
    page.wait_for_timeout(200)
    check("50 tabs: the row scrolls", page.locator(".tt-tabs.tt-scrolling").count() == 1)
    plus = page.locator(".tt-new").bounding_box()
    check("50 tabs: + stays inside the window", plus["x"] + plus["width"] <= 960, plus)
    page.locator(".tt-tab").nth(49).scroll_into_view_if_needed()
    page.locator(".tt-tab").nth(49).click()
    page.wait_for_timeout(100)
    box = page.locator(".tt-tab.tt-active").bounding_box()
    check("50 tabs: the active tab is in view", box["x"] >= 0 and box["x"] + box["width"] <= 960, box)
    shot(page, "6_fifty")
    page.close()

    # --- keyboard ---
    page = fresh(browser)
    page.locator(".tt-tab").nth(0).focus()
    check("only the active tab is in the Tab order", page.evaluate("[...document.querySelectorAll('.tt-tab')].map(t => t.tabIndex)") == [0, -1, -1])
    page.keyboard.press("ArrowRight")
    check("ArrowRight shows the next tab", page.locator(".tt-tab.tt-active .tt-title").text_content() == "Tab 2")
    check("focus follows the active tab", page.evaluate("document.activeElement.classList.contains('tt-active')"))
    page.keyboard.press("End")
    check("End shows the last tab", page.locator(".tt-tab.tt-active .tt-title").text_content() == "Tab 3")
    page.keyboard.press("Delete")
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 2")
    check("Delete closes the focused tab", titles(page) == ["Tab 1", "Tab 2"], titles(page))
    page.locator(".tt-tab.tt-active").focus()
    page.keyboard.press("Shift+F10")
    page.wait_for_selector(".tt-menu")
    check("Shift+F10 opens the menu with the first item focused", page.evaluate("document.activeElement.textContent.startsWith('New tab')"))
    page.keyboard.press("ArrowDown")
    check("arrows move through the menu", page.evaluate("document.activeElement.textContent.startsWith('Close tab')"))
    page.keyboard.press("Escape")
    check("Escape returns focus to the tab", page.evaluate("document.activeElement.classList.contains('tt-tab')"))
    check("the tab list is labelled", page.get_attribute(".tt-tabs", "aria-label") == "Tabs")
    page.close()

    # The README's look: a yellow bar for a dark strip. The menu follows the system (light here): its focus line is the menu's own.
    page = fresh(browser, color_scheme="light")
    page.add_style_tag(content=":root { --tt-accent: #FFB800; --tt-strip-bg: #0a0c11; }")
    page.locator(".tt-tab.tt-active").focus()
    page.keyboard.press("Shift+F10")
    page.wait_for_selector(".tt-menu")
    line = page.evaluate("getComputedStyle(document.activeElement).outlineColor")
    menu = page.evaluate("getComputedStyle(document.querySelector('.tt-menu')).backgroundColor")
    rgb = lambda c: "#%02x%02x%02x" % tuple(int(v) for v in re.findall(r"[\d.]+", c)[:3])
    check("--tt-accent set for the strip: a menu item's focus line still reads on the menu (3:1)",
          _ratio(rgb(line), rgb(menu)) >= 3, (line, menu))
    page.close()

    # --- closing asks first ---
    page = fresh(browser, "{ onBeforeClose: tab => tab.title !== 'Tab 2' }")
    page.locator(".tt-tab").nth(1).click(button="middle")
    page.wait_for_timeout(200)
    check("onBeforeClose can keep a tab open", len(titles(page)) == 3, titles(page))
    page.locator(".tt-tab").nth(2).click(button="middle")
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 2")
    check("onBeforeClose lets other tabs close", titles(page) == ["Tab 1", "Tab 2"], titles(page))
    page.evaluate("window.__emit('tauris-ui:close-request', { label: 'tabs-1', tab: 1 })")
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 1")
    check("a close request from Rust (⌘W) goes through the page", titles(page) == ["Tab 2"], titles(page))
    page.close()

    # --- buttons inside a custom tab get their clicks ---
    page = fresh(browser, """{ renderTab: tab => { const s = document.createElement('span'); s.className = 'tt-title'; s.textContent = tab.title;
        const b = document.createElement('button'); b.className = 'pin'; b.textContent = 'P'; b.onclick = () => window.__pinned = (window.__pinned || 0) + 1;
        return [s, b]; } }""")
    page.locator(".tt-tab").nth(1).locator(".pin").click()
    page.locator(".tt-tab").nth(0).locator(".pin").click()
    check("buttons in a custom tab receive clicks", page.evaluate("window.__pinned") == 2, page.evaluate("window.__pinned"))
    page.close()

    # --- API ---
    page = fresh(browser)
    new_id = page.evaluate("tabs.open({ title: 'Report', view: 'report' })")
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 4")
    check("open() resolves to the new tab's id", isinstance(new_id, int) and page.evaluate(f"tabs.activeTab().id === {new_id}"))
    check("open() puts the tab after the active one", titles(page)[1] == "Report", titles(page))
    check("TaurisTabs.version is set", page.evaluate("TaurisTabs.version") == "test")
    try:
        page.evaluate("TaurisTabs.mount(document.getElementById('strip'))")
        check("a second mount on the same strip is refused", False)
    except Exception:
        check("a second mount on the same strip is refused", True)
    page.evaluate("tabs.destroy(); window.tabs = TaurisTabs.mount(document.getElementById('strip'))")
    page.wait_for_selector(".tt-tab")
    page.locator(".tt-tab").nth(0).click(button="right")
    page.wait_for_timeout(100)
    check("after destroy and mount, one menu opens", page.locator(".tt-menu").count() == 1, page.locator(".tt-menu").count())
    check("after destroy and mount, one strip is drawn", page.locator(".tt-tabs").count() == 1)
    page.close()

    page = fresh(browser, "{ labels: { closeTab: 'Fechar separador', newTab: 'Novo separador' } }")
    page.locator(".tt-tab").nth(0).click(button="right")
    page.wait_for_selector(".tt-menu")
    labels = page.evaluate("[...document.querySelectorAll('.tt-menu-label')].map(e => e.textContent)")
    check("labels change the words", labels[:2] == ["Novo separador", "Fechar separador"], labels)
    page.close()

    # --- a missing permission says how to fix it ---
    page = fresh(browser, before="window.__deny = true")
    page.wait_for_timeout(300)
    check("a refused call explains the capability fix",
          any("tauris-ui:default" in e and "tabs-*" in e for e in page.errors), page.errors)
    page.close()

    # --- light mode ---
    page = fresh(browser, color_scheme="light")
    bg = page.evaluate("getComputedStyle(document.querySelector('.tt-strip')).backgroundColor")
    check("the default look follows light mode", bg == "rgb(236, 236, 239)", bg)
    shot(page, "7_light")
    page.close()

    # --- where Rust cannot follow a dragged-out tab, it stays in the strip ---
    page = fresh(browser, can_drag_out=False)
    a = tab_box(page, 1)
    page.mouse.move(a["x"] + 40, a["y"] + 16)
    page.mouse.down()
    page.mouse.move(a["x"] + 40, a["y"] + 120, steps=6)
    page.mouse.up()
    calls = page.evaluate("window.__calls.map(c => c[0])")
    check("without macOS a tab is never handed out of its window", "drag_out" not in calls, calls)
    page.close()

    # --- an older answer from Rust never overwrites a newer one ---
    page = fresh(browser)
    page.evaluate("window.__slow = { window_state: 400 }; tabs.reload()")  # slow, older answer
    page.evaluate("window.__slow = {}; window.__emit('tauris-ui:state-changed', 'tabs-1')")
    page.locator(".tt-new").click()
    page.wait_for_timeout(700)
    check("stale answers are dropped", len(titles(page)) == 4 and titles(page) == page.evaluate("window.__titles()"),
          [titles(page), page.evaluate("window.__titles()")])
    page.close()

    # --- dragging toward an end of a crowded row scrolls it ---
    page = fresh(browser, before="window.__tabCount = 50", width=960)
    page.wait_for_timeout(200)
    a = tab_box(page, 0)
    page.mouse.move(a["x"] + 30, a["y"] + 16)
    page.mouse.down()
    page.mouse.move(a["x"] + 80, a["y"] + 16, steps=4)
    page.mouse.move(870, a["y"] + 16, steps=8)
    page.wait_for_timeout(1500)
    page.mouse.up()
    page.wait_for_timeout(300)
    where = page.evaluate("window.__titles().indexOf('Tab 1')")
    check("holding a dragged tab at the edge scrolls the row, so it can go far", where > 16, where)
    page.close()

    # --- updating a tab does not resend the strip's layout ---
    page = fresh(browser)
    page.evaluate("window.__calls.length = 0; for (let i = 0; i < 10; i++) tabs.update(tabs.activeTab(), { query: 'q' + i })")
    page.wait_for_timeout(200)
    counts = page.evaluate("({ u: __calls.filter(c => c[0] === 'update_tab').length, r: __calls.filter(c => c[0] === 'report_strip').length })")
    check("ten updates send ten updates and no layout", counts == {"u": 10, "r": 0}, counts)
    page.evaluate("tabs.reload(); 0")
    page.wait_for_timeout(100)
    sent = page.evaluate("__calls.filter(c => c[0] === 'update_tab').at(-1)[1].fields.query")
    check("update sends the app's fields to Rust, and they come back from it", sent == "q9" and page.evaluate("tabs.activeTab().query") == "q9",
          (sent, page.evaluate("tabs.activeTab().query")))
    page.close()

    page = fresh(browser, "{ panelId: 'page' }")
    check("panelId links the tabs to the page", page.get_attribute(".tt-tab", "aria-controls") == "page")
    page.close()

    # --- the close guard: the window's close button asks every tab ---
    page = fresh(browser, "{ onBeforeClose: tab => window.__allow || tab.title !== 'Tab 2' }")
    page.wait_for_timeout(100)
    check("a page with onBeforeClose turns on the close guard", page.evaluate("window.__guard") is True)
    page.evaluate("window.__emit('tauris-ui:close-window-request', 'tabs-1')")
    page.wait_for_timeout(200)
    check("one tab refusing keeps the window open", page.evaluate("window.__windowClosed") is None)
    page.evaluate("window.__allow = true; window.__emit('tauris-ui:close-window-request', 'tabs-1')")
    page.wait_for_timeout(200)
    check("all tabs agreeing closes the window", page.evaluate("window.__windowClosed") == 1)
    check("the page answers every close request at once", page.evaluate("window.__closeAsked") == 2)
    page.evaluate("tabs.destroy()")
    page.wait_for_timeout(100)
    check("destroy turns the guard off", page.evaluate("window.__guard") is False)
    page.close()

    page = fresh(browser)
    page.wait_for_timeout(100)
    check("without onBeforeClose there is no guard", page.evaluate("window.__guard") is None)
    page.locator(".tt-tab").nth(1).click(button="right")
    page.get_by_text("Move to new window", exact=True).click()
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 2")
    check("Move to new window takes the tab out", page.evaluate("window.__movedOut") == "Tab 2" and titles(page) == ["Tab 1", "Tab 3"], titles(page))
    page.close()

    # --- a click while an older answer is on its way ---
    page = fresh(browser)
    page.evaluate("window.__slow = { window_state: 400 }; tabs.reload()")
    page.locator(".tt-tab").nth(2).click()
    page.evaluate("window.__slow = {}")
    page.wait_for_timeout(800)
    check("a click is not undone by an older answer", page.locator(".tt-tab.tt-active .tt-title").text_content() == "Tab 3")
    page.close()

    page = fresh(browser)
    page.evaluate("tabs.update(tabs.activeTab(), { id: 99, query: 'x' })")
    check("update() never changes a tab's id", page.evaluate("tabs.tabs.map(t => t.id)") == [1, 2, 3])
    page.close()

    page = fresh(browser, before="Object.defineProperty(navigator, 'platform', { get: () => 'Linux x86_64' }); Object.defineProperty(navigator, 'userAgentData', { get: () => ({ platform: 'Linux' }) })")
    page.locator(".tt-tab").nth(0).click(button="right")
    page.wait_for_selector(".tt-menu")
    shortcut = page.evaluate("document.querySelector('.tt-menu-shortcut').textContent")
    check("shortcuts read Ctrl+ off a Mac", shortcut == "Ctrl+T", shortcut)
    page.close()

    # --- repeated close requests while onBeforeClose is still answering ---
    page = fresh(browser, "{ onBeforeClose: (tab, info) => { (window.__asked ||= []).push([tab.title, info.reason]); return new Promise(r => setTimeout(() => r(true), 150)); } }")
    page.evaluate("for (let i = 0; i < 2; i++) window.__emit('tauris-ui:close-window-request', 'tabs-1')")
    page.wait_for_timeout(800)
    asked = page.evaluate("window.__asked")
    check("two close-button clicks ask each tab once", len(asked) == 3 and all(r == "window" for _, r in asked), asked)
    check("and close the window once", page.evaluate("window.__windowClosed") == 1)
    page.evaluate("window.__asked = []; tabs.close(1); tabs.close(1)")
    page.wait_for_timeout(400)
    check("two closes of one tab ask once, with reason 'tab'", page.evaluate("window.__asked") == [["Tab 1", "tab"]], page.evaluate("window.__asked"))
    page.close()

    # --- StrictMode: mount, destroy, mount; the newest mount's guard wins ---
    page = fresh(browser, "{ onBeforeClose: () => true }")
    page.evaluate("tabs.destroy(); window.tabs = TaurisTabs.mount(document.getElementById('strip'), { onBeforeClose: () => true })")
    page.wait_for_timeout(200)
    calls = page.evaluate("window.__guardCalls")
    check("each guard message carries a growing number", [c[1] for c in calls] == [1, 2, 3], calls)
    check("the guard stays on after a remount", page.evaluate("window.__guard") is True)
    page.close()

    # --- an app whose CSS uses layers (Tailwind 4 style) ---
    page = fresh(browser)
    page.add_style_tag(content="""
      @layer theme, base, components, utilities;
      @layer base { *, ::before, ::after { padding: 0; margin: 0; border: 0 solid; } }
      @layer base { :root { --tt-strip-bg: rgb(9, 9, 9); } }
      :root { --tt-accent: rgb(1, 2, 3); }
    """)
    page.wait_for_timeout(100)
    style = page.evaluate("""(() => { const t = getComputedStyle(document.querySelector('.tt-tab'));
      const s = getComputedStyle(document.querySelector('.tt-strip'));
      return { pad: t.paddingLeft, inset: s.paddingLeft, accent: s.getPropertyValue('--tt-accent').trim(),
               strip: s.backgroundColor, radius: t.borderTopLeftRadius }; })()""")
    check("a reset in the app's own layers does not strip the tabs", style["pad"] != "0px" and style["inset"] != "0px", style)
    check("variables outside any layer win", style["accent"] == "rgb(1, 2, 3)", style)
    check("variables inside the app's own layers do not", style["strip"] != "rgb(9, 9, 9)", style)
    page.close()

    # --- update() in a framework that compares objects (React) ---
    page = fresh(browser)
    page.evaluate("""window.__seen = []; window.__before = tabs.activeTab();
      tabs.on('change', ({ tabs: list }) => window.__seen.push(list.find(t => t.id === 1)));
      tabs.update(tabs.activeTab(), { view: 'users' })""")
    check("update() gives a new tab object and fires change",
          page.evaluate("window.__seen.length === 1 && window.__seen[0] !== window.__before && window.__seen[0].view === 'users' && tabs.activeTab().view === 'users'"))
    page.evaluate("const t = tabs.activeTab(); t.query = 'kept'; tabs.update(t)")
    check("changes made on the tab object itself are kept", page.evaluate("tabs.activeTab().query") == "kept")
    page.close()

    page = fresh(browser, before="window.__tabCount = 50", width=960)
    page.wait_for_timeout(200)
    page.evaluate("document.querySelector('.tt-tabs').scrollLeft = 900")
    page.evaluate("for (let i = 0; i < 5; i++) tabs.update(tabs.activeTab(), { query: 'q' + i })")
    left = page.evaluate("document.querySelector('.tt-tabs').scrollLeft")
    check("typing (update) leaves a scrolled row where it is", left == 900, left)
    page.close()

    # --- keys typed into a field inside a tab stay in the field ---
    page = fresh(browser, """{ renderTab: tab => { const s = document.createElement('span'); s.className = 'tt-title'; s.textContent = tab.title;
        const i = document.createElement('input'); i.className = 'rename'; i.value = tab.title; return [s, i]; } }""")
    page.locator(".tt-tab").nth(0).locator(".rename").focus()
    page.keyboard.press("End")
    page.keyboard.press("Backspace")
    page.keyboard.press("Delete")
    page.wait_for_timeout(200)
    check("End, Backspace and Delete in a rename box leave the tabs alone",
          len(titles(page)) == 3 and page.locator(".tt-tab.tt-active .tt-title").text_content() == "Tab 1", titles(page))
    page.locator(".tt-tab").nth(1).click()
    page.locator(".tt-tab.tt-active").focus()
    page.keyboard.press("Backspace")
    page.wait_for_timeout(200)
    check("Backspace on a tab does not close it", len(titles(page)) == 3, titles(page))
    page.close()

    # --- Windows high contrast ---
    page = fresh(browser)
    page.emulate_media(forced_colors="active")
    page.locator(".tt-tab").nth(1).focus()
    page.keyboard.press("ArrowRight")
    outline = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
    check("high-contrast mode shows a focus outline", outline == "solid", outline)
    page.close()

    # --- the tree view as the plugin delivers it: script with its stylesheet inside ---
    tree_js = (WEB / "tree.js").read_text().replace('"__TAURIS_TREE_CSS__"', json.dumps((WEB / "tree.css").read_text()))
    page = browser.new_page(viewport={"width": 600, "height": 300})
    page.on("pageerror", lambda e: failures.append(f"page error: {e}"))
    page.add_init_script(tree_js)
    page.goto((HERE / "page.html").as_uri())
    page.evaluate("const d = document.createElement('div'); d.id = 't'; d.style.height = '200px'; document.body.append(d)")
    check("no tree stylesheet is added until a tree is mounted", page.evaluate("document.adoptedStyleSheets.length") == 0)
    page.evaluate("TaurisTree.mount(document.getElementById('t'), { data: [{ id: 1, label: 'Root', expanded: true, children: [{ id: 2, label: 'Child' }] }] })")
    height = page.evaluate("document.querySelector('[role=treeitem]').getBoundingClientRect().height")
    check("mounting a tree adds its stylesheet (18px rows)", page.evaluate("document.adoptedStyleSheets.length") == 1 and height == 18, height)
    page.close()

    # --- a starter template's plain button/input rules leave the components alone ---
    TEMPLATE_CSS = """
      input, button { border-radius: 8px; border: 1px solid transparent; padding: 0.6em 1.2em; font-size: 1em;
        font-weight: 500; color: #0f0f0f; background-color: #ffffff; box-shadow: 0 2px 2px rgba(0, 0, 0, 0.2); }
      button:hover { border-color: #396cd8; }
      button:active { border-color: #396cd8; background-color: #e8e8e8; }
    """
    page = fresh(browser)
    page.add_style_tag(content=TEMPLATE_CSS)
    page.wait_for_timeout(100)
    look = page.evaluate("""(() => { const s = e => getComputedStyle(document.querySelector(e));
      return { close: [s('.tt-tab.tt-active .tt-close').paddingLeft, s('.tt-tab.tt-active .tt-close').boxShadow, s('.tt-tab.tt-active .tt-close').backgroundColor],
               plus: [s('.tt-new').paddingLeft, s('.tt-new').boxShadow, s('.tt-new').borderRadius] }; })()""")
    check("an app's button rules leave the close and + buttons alone",
          look["close"] == ["0px", "none", "rgba(0, 0, 0, 0)"] and look["plus"][0] == "0px" and look["plus"][1] == "none", look)
    page.locator(".tt-tab").nth(0).click(button="right")
    page.wait_for_selector(".tt-menu")
    item = page.evaluate("getComputedStyle(document.querySelector('.tt-menu-item')).boxShadow")
    check("an app's button rules leave the menu items alone", item == "none", item)
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 2")
    check("Enter on a menu item runs it (Close tab)", titles(page) == ["Tab 2", "Tab 3"], titles(page))
    page.locator(".tt-new").focus()
    page.keyboard.press("Enter")
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 3")
    check("Enter on the + opens a tab", len(titles(page)) == 3)
    page.close()

    tree_js_for = lambda: (WEB / "tree.js").read_text().replace('"__TAURIS_TREE_CSS__"', json.dumps((WEB / "tree.css").read_text()))
    page = browser.new_page(viewport={"width": 600, "height": 300}, device_scale_factor=2)
    page.add_init_script(tree_js_for())
    page.goto((HERE / "page.html").as_uri())
    page.add_style_tag(content=TEMPLATE_CSS)
    page.evaluate("""const d = document.createElement('div'); d.id = 't'; d.style.height = '200px'; document.body.append(d);
      window.tree = TaurisTree.mount(d, { columns: [{ label: 'Setting', width: 200 }, { label: 'Value', key: 'v', editable: true }],
        data: [{ id: 1, label: 'Name', values: { v: 'Atlas' } }] }); tree.edit(1)""")
    ed = page.evaluate("(() => { const e = getComputedStyle(document.querySelector('.tv-editor')); return [e.paddingTop, e.borderRadius, e.boxShadow, e.height]; })()")
    check("an app's input rules leave the tree's editor alone", ed == ["0px", "0px", "none", "18px"], ed)
    page.close()

    # --- the tree under a strict content policy (no data: images, no inline styles) ---
    csp = HERE / "csp.html"
    page = browser.new_page(viewport={"width": 400, "height": 240}, device_scale_factor=2)
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.add_init_script(tree_js_for())
    page.goto(csp.as_uri())
    page.evaluate("""window.tree = TaurisTree.mount(document.getElementById('t'), { data: [{ id: 'a', label: 'Root', expanded: true,
      children: [{ id: 'b', label: 'One' }, { id: 'c', label: 'Two', expanded: true, children: [{ id: 'd', label: 'Three' }] }] }] })""")
    page.wait_for_timeout(100)
    box = page.locator("#t").bounding_box()
    shot_bytes = page.screenshot(clip={"x": box["x"], "y": box["y"], "width": 40, "height": 80})
    from io import BytesIO
    from PIL import Image
    pixels = set(Image.open(BytesIO(shot_bytes)).convert("RGB").getdata())
    check("under a strict content policy the tree still draws its lines and boxes", len(pixels) > 3 and not errors, (len(pixels), errors))
    page.close()

    # --- the tree: keyboard between cells, row names, warnings, hidden mounts, high contrast ---
    def tree_page(width=600, height=300):
        page = browser.new_page(viewport={"width": width, "height": height})
        page.warnings = []
        page.on("console", lambda m: page.warnings.append(m.text) if m.type == "warning" else None)
        page.on("pageerror", lambda e: failures.append(f"page error: {e}"))
        page.add_init_script(tree_js_for())
        page.goto((HERE / "page.html").as_uri())
        return page

    page = tree_page()
    page.evaluate("""const d = document.createElement('div'); d.style.height = '200px'; document.body.append(d);
      window.tree = TaurisTree.mount(d, { columns: [{ label: 'Setting', width: 160 }, { label: 'Value', key: 'v', editable: true },
        { label: 'Note', key: 'n', editable: true, align: 'center' }],
        data: [{ id: 1, label: 'Port', values: { v: 3128, n: 'proxy' } }, { id: 2, label: 'Proxy', values: { v: true, n: '' } }] });
      tree.edit(1)""")
    page.keyboard.press("Tab")
    on_note = page.evaluate("document.activeElement.classList.contains('tv-editor') && document.activeElement.closest('.tv-cell').dataset.col")
    page.keyboard.press("Shift+Tab")
    back = page.evaluate("document.activeElement.closest('.tv-cell') && document.activeElement.closest('.tv-cell').dataset.col")
    check("Tab and Shift+Tab move between a row's editable values", on_note == "2" and back == "1", (on_note, back))
    page.keyboard.press("Escape")
    label = page.evaluate("document.querySelector('[role=treeitem]').getAttribute('aria-label')")
    check("screen readers hear the column names", label == "Port, Value: 3128, Note: proxy", label)
    said = page.evaluate("document.querySelectorAll('[role=treeitem]')[1].getAttribute('aria-label')")
    check("a true/false value is read as on or off", said == "Proxy, Value: on, Note: ", said)
    check("align: 'center' centres a column", page.locator(".tv-cell.tv-center").count() >= 1 and page.locator(".tv-hcell.tv-center").count() == 1)
    page.close()

    page = tree_page()
    page.evaluate("""const d = document.createElement('div'); document.body.append(d);
      const many = Array.from({ length: 300 }, (_, i) => ({ id: i % 299, label: 'Row ' + i }));
      TaurisTree.mount(d, { data: many })""")
    page.wait_for_timeout(200)
    check("repeated ids are reported", any("repeated or missing" in w for w in page.warnings), page.warnings)
    check("a tree with no height says so", any("has no height" in w for w in page.warnings), page.warnings)
    page.close()

    page = tree_page()
    page.evaluate("""const d = document.createElement('div'); d.style.cssText = 'height: 200px; display: none'; d.id = 'hidden'; document.body.append(d);
      window.tree = TaurisTree.mount(d, { columns: [{ label: 'Name', width: 200 }, { label: 'Size', key: 's' }],
        data: Array.from({ length: 300 }, (_, i) => ({ id: i, label: 'File ' + i, values: { s: i } })) })""")
    page.evaluate("document.getElementById('hidden').style.display = 'block'")
    page.wait_for_timeout(100)
    page.evaluate("tree.select(299)")
    page.wait_for_timeout(100)
    fits = page.evaluate("""(() => { const box = document.querySelector('.tv-scroll').getBoundingClientRect();
      const row = document.querySelector('[role=treeitem][aria-selected=true]').getBoundingClientRect();
      return row.bottom <= box.bottom + 0.5 && row.top >= box.top; })()""")
    check("a tree mounted while hidden still scrolls the selected row fully into view", fits)
    page.close()

    page = tree_page()
    page.emulate_media(forced_colors="active")
    page.evaluate("""const d = document.createElement('div'); d.style.height = '200px'; document.body.append(d);
      window.tree = TaurisTree.mount(d, { data: [{ id: 'a', label: 'Root', children: [{ id: 'b', label: 'Child' }] }] }); tree.select('a')""")
    adjust = page.evaluate("[getComputedStyle(document.querySelector('.tv-box')).forcedColorAdjust, getComputedStyle(document.querySelector('[aria-selected=true]')).forcedColorAdjust]")
    check("high-contrast mode keeps the boxes and the selection drawn", adjust == ["none", "none"], adjust)
    page.close()

    # --- a fifth review ---
    page = fresh(browser, """{ renderTab: tab => { const t = document.createElement('span'); t.className = 'tt-title'; t.textContent = tab.title;
      const b = document.createElement('button'); b.className = 'mine'; b.textContent = 'pin';
      b.addEventListener('click', () => { window.pinned = (window.pinned || 0) + 1; }); return [t, b]; },
      onBeforeClose: () => { throw new Error('boom'); } }""")
    check("a tab the app draws is named by what it shows", page.get_attribute(".tt-tab", "aria-label") is None)
    page.evaluate("document.querySelector('.tt-tab .mine').focus()")
    page.keyboard.press("Enter")
    check("Enter on a button inside a tab presses that button", page.evaluate("window.pinned") == 1, page.evaluate("window.pinned"))
    page.locator(".tt-tab").nth(1).click()
    page.locator(".tt-tab").nth(1).focus()
    page.keyboard.press("Delete")
    page.wait_for_timeout(100)
    check("onBeforeClose that throws keeps the tab, and says why in the console",
          len(titles(page)) == 3 and any("onBeforeClose failed" in m for m in page.errors), page.errors)
    page.keyboard.press("Shift+F10")
    second = page.evaluate("document.querySelectorAll('.tt-tab')[1].dataset.id")
    page.evaluate("id => { tabs.update(Number(id), { title: 'Renamed' }); }", second)
    page.wait_for_function("[...document.querySelectorAll('.tt-title')].some(t => t.textContent === 'Renamed')")
    page.keyboard.press("Escape")
    check("the strip drawn again while its menu was open: Escape still puts the focus on the tab",
          page.evaluate("document.activeElement.dataset?.id") == second, page.evaluate("document.activeElement.outerHTML.slice(0, 80)"))
    page.close()
    page = fresh(browser, """{ onBeforeClose: () => { window.calls = (window.calls || 0) + 1; return new Promise(r => { window.answer = r; }); } }""")
    check("a default tab's name for screen readers is its title (not its close button too)", page.get_attribute(".tt-tab", "aria-label") == "Tab 1")
    page.locator(".tt-tab").first.focus()
    page.evaluate("tabs.update(tabs.tabs[0], { title: 'Renamed' })")
    check("update() on the focused tab keeps the focus on it", page.evaluate("document.activeElement.dataset?.id") == page.evaluate("String(tabs.tabs[0].id)"))
    page.keyboard.press("Delete")
    page.evaluate("__emit('tauris-ui:close-window-request', 'tabs-1')")
    page.wait_for_timeout(100)
    check("Delete (as ⌘W) and the window's close button together ask the tab once",
          page.evaluate("window.calls") == 1 and page.evaluate("window.__closeAsked") == 1, page.evaluate("[window.calls, window.__closeAsked]"))
    page.close()
    page = fresh(browser, before="window.__noActive = true")
    reachable = page.evaluate("[...document.querySelectorAll('.tt-tab')].map(t => t.getAttribute('tabindex'))")
    check("no tab active: the first tab is still reachable with Tab", reachable == ["0", "-1", "-1"], reachable)
    page.evaluate("tabs.update(tabs.tabs[0], { title: 'R' })")
    reachable = page.evaluate("[...document.querySelectorAll('.tt-tab')].map(t => t.getAttribute('tabindex'))")
    check("and still after update()", reachable == ["0", "-1", "-1"], reachable)
    page.close()

    # --- a seventh review ---
    page = fresh(browser, """{ renderTab: tab => { const t = document.createElement('span'); t.className = 'my-title'; t.textContent = tab.title;
      t.addEventListener('dblclick', () => { window.renames = (window.renames || 0) + 1; }); return [t]; } }""")
    page.locator(".tt-tab").nth(1).click()
    check("a click on a tab gives it the focus (the keys work on the strip right after)",
          page.evaluate("document.activeElement.classList.contains('tt-tab')"), page.evaluate("document.activeElement.tagName"))
    page.keyboard.press("ArrowRight")
    check("and → goes on to the next tab", page.locator(".tt-tab.tt-active .my-title").text_content() == "Tab 3")
    box = page.locator(".tt-tab").nth(0).locator(".my-title").bounding_box()
    page.mouse.dblclick(box["x"] + 4, box["y"] + box["height"] / 2)
    check("a double-click reaches what the app drew in the tab (to rename it)", page.evaluate("window.renames") >= 1, page.evaluate("window.renames"))
    page.evaluate("window.held = tabs.tabs[0]; tabs.update(held, { title: 'A' }); held.note = 'x'; tabs.update(held)")
    check("a tab object the app keeps: a later update(tab) does not undo the earlier one",
          page.evaluate("tabs.tabs[0].title") == "A" and page.evaluate("tabs.tabs[0].note") == "x")
    gap = page.evaluate("(() => { const r = document.querySelector('.tt-tabs').getBoundingClientRect(); const t = document.querySelectorAll('.tt-tab')[1].getBoundingClientRect(); return { x: t.left - 1, y: r.top + r.height / 2 }; })()")
    page.mouse.click(gap["x"], gap["y"], button="right")
    check("a right click between two tabs opens the strip's menu, not the browser's", page.locator(".tt-menu").count() == 1)
    page.keyboard.press("Escape")
    page.close()

    page = fresh(browser)
    page.locator(".tt-tab").first.focus()
    page.keyboard.press("Shift+F10")
    page.keyboard.press("ArrowDown")
    ring = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
    check("the item the keys chose in a tab's menu has a ring", ring == "solid", ring)
    page.keyboard.press("Escape")
    page.close()

    page = fresh(browser)
    box = page.locator(".tt-tab").nth(0).bounding_box()
    page.mouse.move(box["x"] + 20, box["y"] + 10)
    page.mouse.down()
    page.mouse.move(box["x"] + 32, box["y"] + 10, steps=3)
    page.mouse.move(box["x"] + 20, box["y"] + 10, steps=3)
    page.mouse.up()
    page.wait_for_timeout(400)
    left = page.evaluate("document.querySelector('.tt-tab').className")
    check("a drag released where it began leaves the tab with no drag look", left.split() == ["tt-tab", "tt-active"], left)
    page.locator(".tt-tab").first.focus()
    page.keyboard.press("Shift+F10")
    page.click(".tt-menu-sep") if page.locator(".tt-menu-sep").count() else page.click(".tt-menu", position={"x": 2, "y": 2})
    page.keyboard.press("Escape")
    check("a click on the menu's padding or a line keeps its keys (Escape still closes it)", page.locator(".tt-menu").count() == 0)
    page.close()

    # --- an eighth review ---
    page = fresh(browser, before="window.__tabCount = 6")
    page.locator(".tt-tab").first.focus()
    page.keyboard.press("Delete")
    page.evaluate("""for (let i = 0; i < 4; i++) document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete', repeat: true, bubbles: true }))""")
    page.wait_for_timeout(200)
    check("Delete held down closes one tab, not one per repeat", len(titles(page)) == 5, titles(page))
    page.close()

    page = fresh(browser, "{ dragPreview: 'ghost' }", before="window.__tabCount = 1")
    box = tab_box(page, 0)
    page.mouse.move(box["x"] + 30, box["y"] + 16)
    page.mouse.down()
    page.mouse.move(box["x"] + 90, box["y"] + 30, steps=6)
    page.evaluate("__emit('tauris-ui:state-changed', 'tabs-1')")
    page.wait_for_timeout(200)
    page.mouse.up()
    left = page.evaluate("document.querySelector('.tt-tab').className")
    check("a lone tab that carried its window keeps no drag look", left.split() == ["tt-tab", "tt-active"], left)
    page.close()

    page = fresh(browser)
    page.evaluate("window.got = []; for (const e of ['activate', 'close', 'update', 'drop']) tabs.on(e, v => got.push([e, v && (v.tab ? v.tab.title : v.title)]))")
    page.locator(".tt-tab").nth(1).click(button="right")
    page.evaluate("__TAURI__.core.invoke('plugin:tauris-ui|open_tab', { title: 'Inserted', fields: {} })")
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 4")
    page.get_by_text("Close tabs to the right", exact=True).click()
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 3")
    check("Close tabs to the right closes those right of the tab as it is now (tabs came since the menu opened)",
          titles(page) == ["Tab 1", "Inserted", "Tab 2"], titles(page))
    got = page.evaluate("got")
    check("a tab made active by Rust (one opened) says activate", ["activate", "Inserted"] in got, got)
    check("a tab the page closes says close", ["close", "Tab 3"] in got, got)
    page.evaluate("tabs.update(tabs.tabs[0], { title: 'Renamed' })")
    check("update() says update", ["update", "Renamed"] in page.evaluate("got"), page.evaluate("got"))
    page.evaluate("got.length = 0")
    page.locator(".tt-new").click()
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 4")
    check("the + says activate for the new tab", page.evaluate("got").count(["activate", "Tab 5"]) == 1, page.evaluate("got"))
    page.close()

    page = fresh(browser, before="window.__tabCount = 4")
    page.evaluate("window.drops = []; tabs.on('drop', d => drops.push(d.index)); 0")
    c, d = tab_box(page, 2), tab_box(page, 3)
    page.mouse.move(d["x"] + d["width"] / 2, d["y"] + 16)
    page.mouse.down()
    page.mouse.move(d["x"] + d["width"] / 2 - 20, d["y"] + 16, steps=4)
    page.mouse.move(c["x"] + c["width"] / 2 - 10, c["y"] + 16, steps=8)
    page.evaluate("__TAURI__.core.invoke('plugin:tauris-ui|close_tab', { tab: 1 })")
    page.wait_for_timeout(100)
    page.mouse.up()
    page.wait_for_timeout(400)
    check("a drop lands by the tab it was dropped by, though Rust closed a tab meanwhile",
          titles(page) == ["Tab 2", "Tab 4", "Tab 3"], titles(page))
    check("and says where it landed", page.evaluate("drops") == [1], page.evaluate("drops"))
    page.close()

    page = fresh(browser, """{ renderTab: tab => { const t = document.createElement('span'); t.className = 'my-title'; t.textContent = tab.title;
      t.addEventListener('click', () => { window.clicks = (window.clicks || 0) + 1; }); return [t]; } }""")
    page.locator(".tt-tab").nth(2).locator(".my-title").click()
    check("the first click on a tab the app draws reaches what it drew", page.evaluate("window.clicks") == 1, page.evaluate("window.clicks"))
    page.wait_for_timeout(50)
    check("and the tab is drawn as active after", page.locator(".tt-tab.tt-active .my-title").text_content() == "Tab 3")
    page.close()

    page = fresh(browser)
    steps = []
    for keys in ["Control+Tab", "Control+Tab", "Control+Shift+Tab", "Meta+Shift+BracketLeft", "Meta+Shift+BracketRight"]:
        page.keyboard.press(keys)
        steps.append(page.evaluate("tabs.activeTab().title"))
    check("^Tab, ^⇧Tab, ⌘⇧[ and ⌘⇧] step through the tabs", steps == ["Tab 2", "Tab 3", "Tab 2", "Tab 1", "Tab 2"], steps)
    page.close()
    page = fresh(browser, "{ shortcuts: false, middleClickClose: false, appear: false, documentTitle: t => 'App: ' + t?.title }")
    page.keyboard.press("Control+Tab")
    check("shortcuts: false leaves ^Tab alone", page.evaluate("tabs.activeTab().title") == "Tab 1")
    page.locator(".tt-tab").nth(1).click(button="middle")
    page.wait_for_timeout(100)
    check("middleClickClose: false keeps the tab", len(titles(page)) == 3, titles(page))
    check("documentTitle names the window", page.title() == "App: Tab 1", page.title())
    page.locator(".tt-new").click()
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 4")
    check("appear: false: a new tab does not pop in", page.locator(".tt-appear").count() == 0)
    page.close()
    page = fresh(browser)
    page.locator(".tt-new").click()
    page.wait_for_function("document.querySelectorAll('.tt-tab').length === 4")
    check("a new tab pops in", page.evaluate("document.querySelectorAll('.tt-tab')[3].classList.contains('tt-appear')"))
    page.close()

    page = fresh(browser, color_scheme="light")
    page.emulate_media(forced_colors="active")
    page.wait_for_timeout(50)
    look = page.evaluate("""(() => { const [a, b] = document.querySelectorAll('.tt-tab'); const ca = getComputedStyle(a), cb = getComputedStyle(b);
      return [ca.boxShadow, ca.borderTopColor, cb.borderTopColor, cb.backgroundColor]; })()""")
    check("Windows high contrast: the active tab is framed, with its bar on top; idle tabs draw no frame",
          "inset" in look[0] and look[1] != look[2], look)
    page.close()

    # --- a ninth review ---
    page = fresh(browser, before="window.__tabCount = 30")
    page.evaluate("const t = document.querySelector('.tt-tabs'); t.scrollLeft = t.scrollWidth; 0")
    page.wait_for_timeout(100)
    mids = page.evaluate("__calls.filter(c => c[0] === 'report_strip').at(-1)[1].mids")
    check("a scrolled row tells Rust where its tabs are now (drops from other windows land right)", mids[0] < 0, mids[:3])
    last = tab_box(page, 27)
    page.evaluate("__calls.length = 0")
    page.mouse.move(last["x"] + 30, last["y"] + 16)
    page.mouse.down()
    page.mouse.move(last["x"] + 30, last["y"] + 140, steps=8)
    page.mouse.up()
    grab = page.evaluate("(__calls.find(c => c[0] === 'drag_out') || [0, {}])[1].grabX")
    check("a tab dragged out of a scrolled row is held where it was grabbed (its new window under the mouse)", grab is not None and 0 <= grab < 300, grab)
    page.close()

    page = fresh(browser, before="window.__tabCount = 30")
    page.evaluate("window.drops = []; tabs.on('drop', d => drops.push(d.index)); 0")
    lefts = page.evaluate("[...document.querySelectorAll('.tt-tab')].map(t => t.getBoundingClientRect().left)")
    first = tab_box(page, 0)
    page.mouse.move(first["x"] + 20, first["y"] + 16)
    page.mouse.down()
    page.mouse.move(first["x"] + 40, first["y"] + 16, steps=3)
    # Place 5: well inside the row, where holding the tab does not scroll it.
    page.mouse.move(lefts[5] + 20, first["y"] + 16, steps=12)
    page.mouse.up()
    page.wait_for_timeout(400)
    check("a tab dropped exactly on a place lands there (the tabs sit a gap apart)", page.evaluate("drops") == [5], (page.evaluate("drops"), titles(page)[:10]))
    page.close()

    page = fresh(browser, """{ renderTab: tab => { const s = document.createElement('span'); s.className = 'my-title'; s.textContent = tab.title;
      if (tab.id === 1) { const i = document.createElement('input'); i.id = 'rename'; i.value = tab.title; s.append(i); } return [s]; } }""")
    page.focus("#rename")
    page.keyboard.type("ab")
    page.evaluate("__TAURI__.core.invoke('plugin:tauris-ui|update_tab', { tab: 2, title: 'Tab 2', fields: { status: 'synced' } }); __emit('tauris-ui:state-changed', 'tabs-1'); 0")
    page.wait_for_timeout(100)
    check("Rust changing another tab keeps a field the app drew in a tab, its text and the focus",
          page.evaluate("document.activeElement.id") == "rename" and page.input_value("#rename").endswith("ab"), page.evaluate("document.activeElement.tagName"))
    page.close()

    page = fresh(browser, "{ onBeforeClose: () => true }", before="window.__slow = { window_state: 150 }")
    page.wait_for_timeout(300)
    page.evaluate("__TAURI__.core.invoke('plugin:tauris-ui|new_tab'); 0")
    page.evaluate("__emit('tauris-ui:close-request', { label: 'tabs-1', tab: 4 }); 0")
    page.wait_for_timeout(600)
    check("⌘W for a tab the page had not loaded yet still closes it", page.evaluate("__titles()") == ["Tab 1", "Tab 2", "Tab 3"], page.evaluate("__titles()"))
    page.close()

    page = fresh(browser, "{ contextMenu: (tab, items) => [...items, '-', { label: 'Remove all', danger: true }] }")
    page.evaluate("const a = document.createElement('textarea'); a.id = 'notes'; a.style.cssText = 'position:fixed;top:120px;left:20px'; document.body.append(a); 0")
    page.focus("#notes")
    gap = page.evaluate("(() => { const r = document.querySelector('.tt-strip, #strip').getBoundingClientRect(); return { x: r.right - 120, y: r.top + r.height / 2 }; })()")
    page.mouse.click(gap["x"], gap["y"], button="right")
    page.keyboard.press("Escape")
    check("a menu opened with the mouse gives the focus back where it was (the page's field)", page.evaluate("document.activeElement.id") == "notes",
          page.evaluate("document.activeElement.className"))
    page.locator(".tt-tab").first.click(button="right")
    page.hover(".tt-menu-item.tt-danger")
    look = page.evaluate("[getComputedStyle(document.querySelector('.tt-menu-item.tt-danger')).color, getComputedStyle(document.documentElement).getPropertyValue('--tt-menu-fg').trim()]")
    check("a danger item hovered takes the menu's text colour (readable on the hover)", look[0] == page.evaluate(f"(() => {{ const d = document.createElement('div'); d.style.color = '{look[1]}'; document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c; }})()"), look)
    page.keyboard.press("Escape")
    page.close()

    # --- a tenth review ---
    FIELD = """{ renderTab: tab => { const s = document.createElement('span'); s.className = 'my-title'; s.textContent = tab.title;
      if (tab.id === 3) { const i = document.createElement('input'); i.id = 'rename'; i.value = tab.title;
        i.addEventListener('input', () => tabs.update(tab, { title: i.value })); s.append(i); } return [s]; } }"""
    page = fresh(browser, FIELD)
    page.focus("#rename")
    page.keyboard.type("ab")
    typed = page.evaluate("[document.activeElement.id, document.activeElement.value]")
    page.evaluate("__TAURI__.core.invoke('plugin:tauris-ui|close_tab', { tab: 1 }); 0")
    page.wait_for_timeout(150)
    check("typing in a field the app drew in a tab (its title updated as it goes) keeps the focus and the text",
          typed == ["rename", "Tab 3ab"], typed)
    check("and Rust closing a tab before it keeps them too", page.evaluate("[document.activeElement.id, document.activeElement.value]") == ["rename", "Tab 3ab"],
          page.evaluate("[document.activeElement.id, document.activeElement.value]"))
    page.close()

    page = fresh(browser, "{ onBeforeClose: () => false }", before="window.__slow = { window_state: 80 }")
    page.wait_for_timeout(300)
    page.evaluate("__TAURI__.core.invoke('plugin:tauris-ui|new_tab'); __emit('tauris-ui:close-request', { label: 'tabs-1', tab: 4 }); setTimeout(() => __emit('tauris-ui:state-changed', 'tabs-1'), 20); 0")
    page.wait_for_timeout(600)
    check("⌘W for a tab not loaded yet, while more changes arrive: it is asked, not closed past its question", page.evaluate("__titles()").count("Tab 4") == 1,
          page.evaluate("__titles()"))
    page.close()

    page = fresh(browser, "{ onBeforeClose: tab => tab.id !== 4 }", before="window.__slow = { window_state: 80 }")
    page.wait_for_timeout(300)
    page.evaluate("__TAURI__.core.invoke('plugin:tauris-ui|new_tab'); __emit('tauris-ui:close-window-request', 'tabs-1'); 0")
    page.wait_for_timeout(600)
    check("the window's close button asks a tab Rust added a moment ago too", page.evaluate("window.__windowClosed") is None, page.evaluate("window.__windowClosed"))
    page.close()

    page = fresh(browser, "{ newIcon: '<b class=\\'my-plus\\'>+</b>', closeIcon: '<i class=\\'my-x\\'>x</i>', moveThreshold: 30, detachDistance: 120 }")
    check("newIcon and closeIcon draw the app's own markup", page.locator(".tt-new .my-plus").count() == 1 and page.locator(".tt-tab .my-x").count() == 3)
    box = tab_box(page, 0)
    page.mouse.move(box["x"] + 30, box["y"] + 16)
    page.mouse.down()
    page.mouse.move(box["x"] + 50, box["y"] + 16, steps=4)
    small = page.evaluate("document.querySelector('.tt-tab').classList.contains('tt-dragging')")
    page.mouse.move(box["x"] + 70, box["y"] + 16, steps=4)
    big = page.evaluate("document.querySelector('.tt-tab').classList.contains('tt-dragging')")
    page.evaluate("__calls.length = 0")
    page.mouse.move(box["x"] + 70, box["y"] + 110, steps=6)
    near = page.evaluate("__calls.some(c => c[0] === 'drag_out')")
    page.mouse.move(box["x"] + 70, box["y"] + 200, steps=6)
    far = page.evaluate("__calls.some(c => c[0] === 'drag_out')")
    page.mouse.up()
    check("moveThreshold and detachDistance set when a drag begins and when the tab leaves the strip",
          (small, big, near, far) == (False, True, False, True), (small, big, near, far))
    page.close()

    page = fresh(browser)
    page.locator(".tt-new").click()
    page.wait_for_timeout(600)
    check("a new tab's pop-in is done once it has played (it does not play again when the strip is put in order)",
          page.locator(".tt-appear").count() == 0)
    page.close()

    # --- an eleventh review ---
    page = fresh(browser)
    page.evaluate("window.held = tabs.tabs[0]; tabs.update(held.id, { title: 'New' }); tabs.update(held, { note: 'x' }); 0")
    check("update(tab, patch) with an older object of the tab: only what it changes is taken (the newer title stays)",
          page.evaluate("[tabs.tabs[0].title, tabs.tabs[0].note]") == ["New", "x"], page.evaluate("[tabs.tabs[0].title, tabs.tabs[0].note]"))
    box = page.locator(".tt-tab.tt-active .tt-close").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.evaluate("tabs.update(tabs.activeTab(), { title: 'Changed while pressed' }); 0")
    page.mouse.up()
    page.wait_for_timeout(200)
    check("the close button pressed, the tab updated meanwhile, then released: the tab closes", len(titles(page)) == 2, titles(page))
    check("reload() resolves true when its answer is the one shown", page.evaluate("tabs.reload()") is True)
    page.close()

    page = fresh(browser, """{ renderTab: tab => { const s = document.createElement('span'); s.className = 'my-title'; s.textContent = tab.title;
      const i = document.createElement('input'); i.className = 'my-field'; s.append(i); return [s]; } }""")
    page.click(".tt-tab .my-field", button="right")
    page.wait_for_timeout(50)
    check("a right click in a field the app drew in a tab leaves the field its own menu (no tab menu)", page.locator(".tt-menu").count() == 0)
    page.close()

    page = fresh(browser, "{ contextMenu: false }")
    page.click(".tt-tab", button="right")
    page.locator(".tt-tab").first.focus()
    page.keyboard.press("Shift+F10")
    page.wait_for_timeout(50)
    check("contextMenu: false: no tab menu, from the mouse or the keys", page.locator(".tt-menu").count() == 0)
    page.locator(".tt-tab").nth(2).focus()
    page.keyboard.press("Home")
    check("Home shows the first tab", page.locator(".tt-tab.tt-active .tt-title").text_content() == "Tab 1")
    page.close()

    # WebKit has no moveBefore: the tab with the focus is never taken out and put back as the others move.
    page = fresh(browser, before="delete Element.prototype.moveBefore;")
    page.locator(".tt-tab").first.focus()
    page.keyboard.press("End")
    page.evaluate("""window.blurred = 0; window.node = document.activeElement; node.addEventListener('blur', () => blurred++);
      __TAURI__.core.invoke('plugin:tauris-ui|move_tab', { tab: 1, index: 2 }); 0""")
    page.wait_for_timeout(200)
    check("tabs moving around the one with the focus (no moveBefore): it keeps the focus all along",
          titles(page) == ["Tab 2", "Tab 3", "Tab 1"] and page.evaluate("[document.activeElement === node, blurred]") == [True, 0],
          (titles(page), page.evaluate("[document.activeElement === node, blurred]")))
    page.close()

    # --- the example app's page (examples/basic/ui), as a new app starts from it ---
    page = browser.new_page(viewport={"width": 760, "height": 400})
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.add_init_script((HERE / "mock_tauri.js").read_text())
    page.add_init_script(library_script())
    page.goto((HERE.parent / "examples" / "basic" / "ui" / "index.html").as_uri())
    page.wait_for_selector(".tt-tab")
    page.fill("#note", "milk")
    page.locator(".tt-tab").nth(1).click()
    page.fill("#note", "eggs")
    page.wait_for_timeout(50)
    page.evaluate("window.__emit('tauris-ui:close-window-request', 'tabs-1')")
    page.wait_for_timeout(100)
    first = page.evaluate("window.__windowClosed")
    page.evaluate("window.__emit('tauris-ui:close-window-request', 'tabs-1')")
    page.wait_for_timeout(100)
    check("example: a window with two noted tabs closes on the second try", first is None and page.evaluate("window.__windowClosed") == 1,
          (first, page.evaluate("window.__windowClosed")))
    page.click("#title")
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.press("Backspace")
    page.keyboard.type("Groceries")
    page.wait_for_timeout(50)
    check("example: emptying the title and typing a new one gives that title", page.input_value("#title") == "Groceries"
          and page.locator(".tt-tab.tt-active .tt-title").text_content() == "Groceries", page.input_value("#title"))
    page.close()

    # --- the terminal as the plugin delivers it: no stylesheet until it is used ---
    term_js = (WEB / "terminal.js").read_text().replace('"__TAURIS_TERMINAL_CSS__"', json.dumps((WEB / "terminal.css").read_text()))
    page = browser.new_page(viewport={"width": 600, "height": 300})
    page.on("pageerror", lambda e: failures.append(f"page error: {e}"))
    page.add_init_script(term_js)
    page.goto((HERE / "page.html").as_uri())
    check("no terminal stylesheet is added until the terminal is used", page.evaluate("document.adoptedStyleSheets.length") == 0)
    page.evaluate("const d = document.createElement('div'); d.innerHTML = '<div class=\"tm-band\">SIGN ON</div>'; document.body.append(d); TaurisTerminal.mount(d)")
    band = page.evaluate("getComputedStyle(document.querySelector('.tm-band')).fontFamily")
    check("using the terminal adds its stylesheet", page.evaluate("document.adoptedStyleSheets.length") == 1 and "Mono" in band, band)
    page.close()

    browser.close()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
