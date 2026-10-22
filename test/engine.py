"""The browser a page suite runs in: Chrome here; the Chromium of the pinned
Playwright with TAURIS_TEST_CHROMIUM=1 (as CI); WebKit with TAURIS_TEST_WEBKIT=1,
Tauri's engine on macOS and Linux (CI runs it too)."""
import os

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
