"""Tests the page side of tauris-ui in a headless browser (nothing touches the screen).

Run:  python test/run.py [screenshot-folder]
Needs Python playwright and Google Chrome. Exits non-zero when a check fails.
"""
import json
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


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")

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
    check("the tabs follow the shared --tauris-* colours and font", look == ["rgb(1, 2, 3)", "rgb(4, 5, 6)", "rgb(10, 11, 12)", "rgb(7, 8, 9)", "Georgia, serif"], look)
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
    check("update keeps the app's fields", page.evaluate("window.__titles().length") == 3)
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
