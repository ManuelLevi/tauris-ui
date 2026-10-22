"""Headless tests for the small figures (web/glance.js), on test/glance_demo.html.

    python test/glance_run.py [shots-dir]

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
DEMO = HERE / "glance_demo.html"
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
SIZE = {"width": 700, "height": 400}
failures = []


def check(name, ok, detail=""):
    ok, detail = settled(ok, detail)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        failures.append(name)


def fresh(browser, scheme="light"):
    page = browser.new_page(viewport=SIZE, device_scale_factor=2, color_scheme=scheme)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.goto(DEMO.as_uri())
    page.wait_for_selector(".tgl-cap")
    return page


def css(page, selector, prop):
    return page.evaluate("([s, p]) => getComputedStyle(document.querySelector(s)).getPropertyValue(p)", [selector, prop])


def library_script():
    """glance.js as the plugin delivers it: with its stylesheet inside."""
    return (WEB / "glance.js").read_text().replace('"__TAURIS_GLANCE_CSS__"', json.dumps((WEB / "glance.css").read_text()))


with sync_playwright() as p:
    browser = launch(p)

    page = fresh(browser)
    # ---------- the sparkline ----------
    spark = "tr[data-id=b] .tgl-spark"
    check("a sparkline: 64 by 18, a line, the area under it, a dot on the last value",
          page.evaluate(f"(() => {{ const s = document.querySelector('{spark}'); const r = s.getBoundingClientRect();"
                        " return [Math.round(r.width), Math.round(r.height), s.querySelectorAll('.tgl-line, .tgl-area, .tgl-dot').length]; })()") == [64, 18, 3])
    check("dates as x: spaced by time (the last value a month after, not a step)",
          page.evaluate(f"document.querySelector('{spark} .tgl-line').getAttribute('d')") == "M2 15.5L16 2.5L62 9", page.evaluate(f"document.querySelector('{spark} .tgl-line').getAttribute('d')"))
    check("its label is what a screen reader hears, and the tooltip",
          page.get_attribute(spark, "role") == "img" and page.get_attribute(spark, "aria-label") == "Churn, last weeks"
          and page.evaluate(f"document.querySelector('{spark} title').textContent") == "Churn, last weeks")
    check("in the accent colour", css(page, f"{spark} .tgl-line", "stroke") == "rgb(38, 117, 191)")
    check("in a selected row, the row's text colour", css(page, "tr[data-id=a] .tgl-line", "stroke") == "rgb(255, 255, 255)")
    check("one value: a dot; none: nothing drawn",
          page.evaluate("document.querySelectorAll('tr[data-id=d] .tgl-spark > *:not(title)').length") == 1
          and page.evaluate("document.querySelectorAll('tr[data-id=e] .tgl-spark > *:not(title)').length") == 0)
    check("no label: hidden from a screen reader; a colour, a size, a range",
          page.evaluate("""(() => { const s = TaurisGlance.sparkline([1, 2, 3], { width: 30, height: 12, color: 'red', min: 0, max: 10 });
            return [s.getAttribute('aria-hidden'), s.getAttribute('viewBox'), s.style.getPropertyValue('--tgl-c'), s.querySelector('.tgl-line').getAttribute('d')]; })()""")
          == ["true", "0 0 30 12", "red", "M2 8.8L15 8.1L28 7.4"])
    check("values that are not numbers are left out",
          page.evaluate("TaurisGlance.sparkline([1, 'x', null, 4]).querySelector('.tgl-line').getAttribute('d')") == "M2 15.5L62 2.5")

    # ---------- the status ----------
    kinds = page.evaluate("[...document.querySelectorAll('.tgl-status')].map(s => [s.className, s.textContent, getComputedStyle(s.firstElementChild).backgroundColor])")
    check("a status: a dot and a word, a colour for each kind",
          kinds == [["tgl-status tgl-ok", "On track", "rgb(31, 138, 76)"], ["tgl-status tgl-warn", "Behind", "rgb(201, 138, 0)"],
                    ["tgl-status tgl-bad", "Off", "rgb(196, 55, 45)"], ["tgl-status tgl-done", "Reached", "rgb(38, 117, 191)"],
                    ["tgl-status tgl-new", "New", "rgba(0, 0, 0, 0)"], ["tgl-status tgl-none", "No values", "rgba(0, 0, 0, 0)"]], kinds)
    check("the dot is hidden from a screen reader; the word is read", page.get_attribute(".tgl-status > i", "aria-hidden") == "true")
    check("a word is text, never markup", page.evaluate("TaurisGlance.status('ok', '<b>x</b>').textContent") == "<b>x</b>")
    check("an unknown kind is none", page.evaluate("TaurisGlance.status('odd', 'x').className") == "tgl-status tgl-none")
    check("not something to press: the arrow pointer", css(page, ".tgl-status", "cursor") == "default")

    # ---------- the capacity bar ----------
    check("a capacity bar: the label, the count, a segment for each place",
          page.evaluate("document.querySelector('.tgl-cap-label').textContent") == "Open tasks"
          and page.evaluate("document.querySelector('.tgl-cap-count').textContent") == "3 / 20"
          and page.evaluate("document.querySelectorAll('.tgl-capbar > i').length") == 20
          and page.evaluate("document.querySelectorAll('.tgl-capbar > i.tgl-on').length") == 3)
    check("each held place in its holder's colour, its name as the tooltip; a free one says so",
          page.evaluate("[...document.querySelectorAll('.tgl-capbar > i')].slice(1, 4).map(i => [getComputedStyle(i).backgroundColor, i.title])")
          == [["rgb(184, 58, 49)", "Venue · Orion"], ["rgb(184, 58, 49)", "Cake · Orion"], ["rgb(225, 227, 231)", "Free"]])
    check("a meter for a screen reader", page.get_attribute(".tgl-capbar", "role") == "meter" and page.get_attribute(".tgl-capbar", "aria-valuenow") == "3"
          and page.get_attribute(".tgl-capbar", "aria-valuemax") == "20" and page.get_attribute(".tgl-capbar", "aria-label") == "Open tasks")
    check("140px wide, 7px tall", page.evaluate("(() => { const r = document.querySelector('.tgl-capbar').getBoundingClientRect(); return [r.width, r.height]; })()") == [140, 7])
    check("past the limit: the count and the bar in red",
          page.evaluate("""(() => { const c = TaurisGlance.capacity({ max: 2, used: 3 }); document.body.append(c);
            return [c.classList.contains('tgl-over'), getComputedStyle(c.querySelector('.tgl-cap-count')).color, getComputedStyle(c.querySelector('i.tgl-on')).backgroundColor]; })()""")
          == [True, "rgb(196, 55, 45)", "rgb(196, 55, 45)"])
    check("a large limit: one filled track, not a hundred segments",
          page.evaluate("""(() => { const c = TaurisGlance.capacity({ max: 100, used: 25 }); document.body.append(c);
            return [c.querySelectorAll('.tgl-capbar > i').length, c.querySelector('.tgl-on').getBoundingClientRect().width]; })()""") == [1, 35])
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / "glance.png"))
    page.close()

    page = fresh(browser, scheme="dark")
    check("dark: the colours for a dark page",
          css(page, ".tgl-ok > i", "background-color") == "rgb(69, 194, 122)" and css(page, "tr[data-id=b] .tgl-line", "stroke") == "rgb(106, 166, 224)"
          and css(page, ".tgl-capbar > i:last-child", "background-color") == "rgb(69, 72, 76)")
    if SHOTS:
        page.screenshot(path=str(SHOTS / "glance_dark.png"))
    page.close()

    # ---------- as the plugin delivers it ----------
    page = browser.new_page(viewport=SIZE)
    page.add_init_script(library_script())
    page.goto((HERE / "csp.html").as_uri())
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    before = page.evaluate("document.adoptedStyleSheets.length")
    page.evaluate("document.body.append(TaurisGlance.status('ok', 'Fine')); 0")
    check("under a strict content policy: no stylesheet until it is used, then one, and no error",
          before == 0 and page.evaluate("document.adoptedStyleSheets.length") == 1 and not errors
          and page.evaluate("getComputedStyle(document.querySelector('.tgl-status')).display") == "inline-flex", errors)
    page.evaluate("document.body.append(TaurisGlance.sparkline([1, 2]), TaurisGlance.capacity({ max: 3 })); 0")
    check("the others share it", page.evaluate("document.adoptedStyleSheets.length") == 1)
    page.close()

    browser.close()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
