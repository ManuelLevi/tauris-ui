"""Headless tests for the status bar (web/status.js), on test/frame_demo.html.

    python test/status_run.py [shots-dir]

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
DEMO = HERE / "frame_demo.html"
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
SIZE = {"width": 760, "height": 420}
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
    page.wait_for_selector(".tst-seg")
    return page


def css(page, selector, prop):
    return page.evaluate("([s, p]) => getComputedStyle(document.querySelector(s)).getPropertyValue(p)", [selector, prop])


def segs(page):
    return page.evaluate("[...document.querySelectorAll('.tst-seg')].map(s => s.textContent)")


def library_script():
    """status.js as the plugin delivers it: with its stylesheet inside."""
    return (WEB / "status.js").read_text().replace('"__TAURIS_STATUS_CSS__"', json.dumps((WEB / "status.css").read_text()))


with sync_playwright() as p:
    browser = launch(p)

    page = fresh(browser)
    check("a 22px bar along the foot: the message on the left, the segments on the right",
          page.evaluate("Math.round(document.getElementById('status').getBoundingClientRect().height)") == 22
          and page.evaluate("Math.round(document.getElementById('status').getBoundingClientRect().bottom)") == SIZE["height"]
          and segs(page) == ["Online", "7 / 20 tasks", "Sound: On"])
    check("a dot in its state's colour, a tooltip", css(page, ".tst-dot", "background-color") == "rgb(31, 138, 76)"
          and page.get_attribute(".tst-seg[data-id=online]", "title") == "Connected to the server")
    check("a segment that does something is a button; a toggle says it is on",
          page.evaluate("document.querySelector('.tst-seg[data-id=sound]').tagName") == "BUTTON"
          and page.get_attribute(".tst-seg[data-id=sound]", "aria-pressed") == "true"
          and page.evaluate("document.querySelector('.tst-seg[data-id=tasks]').tagName") == "SPAN")
    page.click(".tst-seg[data-id=sound]")
    check("a click runs it", page.evaluate("said") == [["sound"]])
    page.evaluate("bar.set('online', { dot: 'bad', text: 'Offline' }); bar.set('tasks', { strong: true, text: '20 / 20 tasks' })")
    check("set(): one segment changes", segs(page)[:2] == ["Offline", "20 / 20 tasks"] and css(page, ".tst-dot", "background-color") == "rgb(196, 55, 45)"
          and css(page, ".tst-seg[data-id=tasks]", "font-weight") == "600")
    page.evaluate("bar.set('online', { dot: 'wait', text: 'Connecting…' })")
    check("wait: a pulse", css(page, ".tst-dot", "animation-name") == "tst-wait")

    # ---------- messages and Undo ----------
    page.focus("#list")
    page.evaluate("window.undone = 0; bar.say('Deleted “Atlas”.', { undo: () => { undone++; } })")
    check("a message, read out, with an Undo", page.evaluate("bar.message") == "Deleted “Atlas”." and page.get_attribute(".tst-msg", "aria-live") == "polite"
          and page.is_visible(".tst-act") and page.inner_text(".tst-act") == "Undo")
    page.click(".tst-act")
    check("Undo runs it, the message goes, and the focus is back on the list",
          lambda: page.evaluate("undone") == 1 and page.evaluate("bar.message") == "" and page.evaluate("document.activeElement.id") == "list",
          lambda: (page.evaluate("undone"), page.evaluate("document.activeElement.id")))
    page.evaluate("bar.say('Could not save.', { kind: 'error', action: { label: 'Retry', run: () => { window.retried = true; } } })")
    check("an error in its colour, with another action", css(page, ".tst-msg", "color") == "rgb(179, 38, 30)" and page.inner_text(".tst-act") == "Retry")
    page.focus("#list")
    page.keyboard.press("Tab")
    page.evaluate("document.querySelector('.tst-act').focus()")
    page.keyboard.press("Enter")
    check("pressed from the keyboard: it runs, the focus back where it came from", lambda: page.evaluate("window.retried") is True)
    page.evaluate("bar.say('Saved.', { undo: () => {}, actionFor: 200 })")
    check("the action goes after a moment; the message stays", lambda: not page.is_visible(".tst-act") and page.evaluate("bar.message") == "Saved.")
    page.evaluate("bar.say('Copied.', { timeout: 200 })")
    check("a message with a timeout goes", lambda: page.evaluate("bar.message") == "")
    long = "A very long message " * 12
    page.evaluate("t => bar.say(t)", long)
    check("a long message ends in …, whole in its tooltip", css(page, ".tst-msg", "text-overflow") == "ellipsis" and page.get_attribute(".tst-msg", "title") == long)
    page.click("#status", button="right")
    check("a right click: the app's menu", page.evaluate("said").count(["menu", True]) == 1)
    check("a second mount on the same element is refused",
          page.evaluate("(() => { try { TaurisStatus.mount(document.getElementById('status')); return false; } catch (e) { return true; } })()"))
    check("destroy() empties it", page.evaluate("bar.destroy(); document.getElementById('status').children.length") == 0)
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / "status.png"))
    page.close()

    page = fresh(browser, scheme="dark")
    check("dark: the dark colours", css(page, "#status", "background-color") == "rgb(52, 55, 58)" and css(page, ".tst-dot", "background-color") == "rgb(69, 194, 122)")
    page.close()
    page = fresh(browser, reduced_motion="reduce")
    page.evaluate("bar.set('online', { dot: 'wait', text: 'Connecting…' })")
    check("reduced motion: no pulse", css(page, ".tst-dot", "animation-name") == "none")
    page.close()

    # ---------- as the plugin delivers it ----------
    page = browser.new_page(viewport=SIZE)
    page.add_init_script(library_script())
    page.goto((HERE / "csp.html").as_uri())
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    before = page.evaluate("document.adoptedStyleSheets.length")
    page.evaluate("TaurisStatus.mount(document.getElementById('t'), { segments: [{ id: 'a', text: 'A' }] }).say('Hi'); 0")
    check("under a strict content policy: no stylesheet until it is used, then one, and no error",
          before == 0 and page.evaluate("document.adoptedStyleSheets.length") == 1 and not errors
          and page.evaluate("getComputedStyle(document.querySelector('.tst')).display") == "flex", errors)
    page.close()

    browser.close()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
