"""The browser a page suite runs in: Chrome here; the Chromium of the pinned
Playwright with TAURIS_TEST_CHROMIUM=1 (as CI); WebKit with TAURIS_TEST_WEBKIT=1,
Tauri's engine on macOS and Linux (CI runs it too)."""
import os
import time

WEBKIT = bool(os.environ.get("TAURIS_TEST_WEBKIT"))

# Headless WebKit's own right-click menu takes every event after it (Escape does
# not close it), so its pages never show it; an app's web view has its own.
NO_NATIVE_MENU = "document.addEventListener('contextmenu', e => e.preventDefault())"


def launch(p):
    if not WEBKIT:
        return p.chromium.launch(channel=None if os.environ.get("TAURIS_TEST_CHROMIUM") else "chrome")
    browser = p.webkit.launch()
    plain = browser.new_page

    def new_page(*args, **kwargs):
        page = plain(*args, **kwargs)
        page.add_init_script(NO_NATIVE_MENU)
        return page

    browser.new_page = new_page
    return browser


def settled(ok, detail):
    """A check's answer. Given as functions (a check after a pause), the answer is
    asked again for up to 3s while it is no: a slow machine (CI's Mac) finishes
    later than the pause. A yes is never waited for, so a check that something
    did not happen still answers at once."""
    if callable(ok):
        deadline = time.monotonic() + 3
        answer = ok()
        while not answer and time.monotonic() < deadline:
            time.sleep(0.05)
            answer = ok()
        ok = answer
    if callable(detail):
        detail = detail()
    return ok, detail
