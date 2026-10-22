"""Tests the terminal look (web/terminal.js, web/terminal.css) in a headless browser.

Run:  python test/terminal_run.py [screenshot-folder] [reference.html]
Needs Python playwright, Pillow and Google Chrome. Nothing touches the screen.
Exits non-zero when a check fails. With a folder, it saves screenshots at 2x:
the demo, the band states and a close-up of the table. With a reference page
(a design the look was drawn from), it also saves that page rendered the same
way, and both side by side.
"""
import io
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
WEB = HERE.parent / "web"
DEMO = HERE / "terminal_demo.html"
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
REFERENCE = Path(sys.argv[2]) if len(sys.argv) > 2 else None
if SHOTS:
    SHOTS.mkdir(parents=True, exist_ok=True)
SIZE = {"width": 1100, "height": 560}
# Waits until the page has drawn twice: the cursor moves on the next frame.
TWO_FRAMES = "new Promise(done => requestAnimationFrame(() => requestAnimationFrame(() => done(0))))"
SCALE = 2
failures = []

# The colours of terminal.css, as computed styles report them.
BLACK, AMBER, AMBER_DIM, WHITE, GREY = "rgb(0, 0, 0)", "rgb(255, 164, 36)", "rgb(162, 106, 28)", "rgb(242, 242, 242)", "rgb(140, 140, 140)"
GREEN, RED, YELLOW, KEY_GREY = "rgb(62, 214, 107)", "rgb(255, 68, 56)", "rgb(255, 225, 77)", "rgb(90, 90, 90)"
FIELD, FIELD_2, LINE, LINE_2, ROW, CHROME = "rgb(10, 31, 79)", "rgb(20, 50, 124)", "rgb(38, 38, 38)", "rgb(58, 58, 58)", "rgb(14, 14, 14)", "rgb(16, 16, 16)"
TIME = re.compile(r"^\d\d:\d\d:\d\d$")
DATE = re.compile(r"^\d{4}-\d\d-\d\d$")

# A starter template's plain rules (create-tauri-app and Vite have these).
TEMPLATE_CSS = """
  input, button { border-radius: 8px; border: 1px solid transparent; padding: 0.6em 1.2em; font-size: 1em;
    font-weight: 500; font-family: inherit; color: #0f0f0f; background-color: #ffffff; box-shadow: 0 2px 2px rgba(0, 0, 0, 0.2);
    transition: border-color 0.25s; outline: none; }
  button { cursor: pointer; }
  button:hover { border-color: #396cd8; }
  button:active { border-color: #396cd8; background-color: #e8e8e8; }
  input:focus { border-color: #396cd8; }
"""

# A small terminal with every part, built with DOM calls only (no inline styles),
# for the pages that load the library as the plugin delivers it.
BUILD = """host => {
  host.innerHTML = `
  <div id="root" class="tm tm-screen">
    <div id="cmd"></div>
    <div class="tm-panes">
      <section id="pane" class="tm-pane">
        <h2 class="tm-band"><span>SIGN ON</span><span data-tm-clock></span></h2>
        <div class="tm-pane-body">
          <form class="tm-form">
            <label class="tm-form-line"><span class="tm-label">USERNAME</span><input id="user" class="tm-field" value="j.okafor"></label>
            <label class="tm-form-line"><span class="tm-label">PASSWORD</span><input id="pass" class="tm-field" type="password" value="harbour-lights"></label>
            <label class="tm-form-line"><span class="tm-label">REMEMBER</span><input id="check" class="tm-check" type="checkbox" checked><span class="tm-note">KEEP ME SIGNED IN</span></label>
            <div class="tm-form-line"><span class="tm-label"></span><span id="go" class="tm-key tm-go" role="button" tabindex="0">GO</span><span id="print" class="tm-key" role="button" tabindex="0" aria-keyshortcuts="F8">PRINT</span></div>
          </form>
        </div>
      </section>
      <section class="tm-pane">
        <table class="tm-table"><thead><tr><th>SUBSYSTEM</th><th class="tm-num">LOAD MS</th><th>PROFILE</th></tr></thead>
          <tbody><tr><td>STORAGE</td><td class="tm-num">13.5</td><td><meter id="bar" class="tm-bar" min="0" max="100" value="100"></meter></td></tr></tbody></table>
        <ol id="log"></ol>
      </section>
    </div>
    <footer class="tm-legend"><span class="tm-key tm-cancel">CANCEL</span><span>= ESC</span></footer>
  </div>`;
  host.style.height = "320px";
  window.prints = 0;
  document.getElementById("print").addEventListener("click", () => prints++);
  window.term = TaurisTerminal.mount(document.getElementById("root"));
  window.cmd = TaurisTerminal.commandLine(document.getElementById("cmd"), { prompt: "ATLAS>" });
  cmd.value = "SIGNON";
  window.messages = TaurisTerminal.log(document.getElementById("log"));
  messages.add("READY FOR SIGN ON");
  window.band = TaurisTerminal.pane(document.getElementById("pane"));
  return 0;
}"""

# The look of the parts an app's starter rules could reach.
SIGNATURE = """() => {
  const props = ["padding-top", "padding-left", "border-top-width", "border-bottom-width", "border-left-width", "border-radius",
    "box-shadow", "background-color", "color", "font-size", "font-weight", "height", "width", "outline-style", "transition-duration"];
  const sig = s => { const c = getComputedStyle(document.querySelector(s)); return Object.fromEntries(props.map(p => [p, c.getPropertyValue(p)])); };
  return Object.fromEntries(["#user", "#pass", "#check", ".tm-cmd-input", "#go", ".tm-band", ".tm-table td"].map(s => [s, sig(s)]));
}"""


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail != "" and not ok else ""))
    if not ok:
        failures.append(name)


def library_script():
    """terminal.js as the plugin delivers it: with its stylesheet inside."""
    return (WEB / "terminal.js").read_text().replace('"__TAURIS_TERMINAL_CSS__"', json.dumps((WEB / "terminal.css").read_text()))


def fresh(browser, reduced_motion="no-preference", feed=False):
    page = browser.new_page(viewport=SIZE, device_scale_factor=SCALE, color_scheme="dark", reduced_motion=reduced_motion)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.goto(DEMO.as_uri())
    page.wait_for_selector(".tm-log li")
    page.evaluate("document.fonts.ready.then(() => 0)")
    if not feed:
        page.evaluate("demo.live(false)")
    # Every click on a key, by id.
    page.evaluate("""() => { window.__clicks = [];
      for (const k of document.querySelectorAll('.tm-key[id]')) k.addEventListener('click', () => __clicks.push(k.id)); }""")
    return page


def clicks(page):
    return page.evaluate("window.__clicks.splice(0)")


def css(page, selector, prop, pseudo=None):
    return page.evaluate("([s, p, ps]) => getComputedStyle(document.querySelector(s), ps).getPropertyValue(p)", [selector, prop, pseudo])


def rect(page, selector):
    return page.evaluate("""s => { const r = document.querySelector(s).getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height }; }""", selector)


def picture(page):
    return Image.open(io.BytesIO(page.screenshot(animations="disabled"))).convert("RGB")


def hex_rgb(text):
    return tuple(int(n) for n in re.findall(r"\d+", text)[:3])


def near(a, b, tolerance=24):
    return max(abs(x - y) for x, y in zip(a, b)) <= tolerance


def shot(page, name, clip=None):
    if SHOTS:
        page.screenshot(path=str(SHOTS / f"terminal_{name}.png"), clip=clip, animations="disabled")


def strict_page(browser, url, before=""):
    page = browser.new_page(viewport={"width": 760, "height": 340}, device_scale_factor=SCALE)
    page.errors = []
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.add_init_script("window.__csp = []; document.addEventListener('securitypolicyviolation', e => __csp.push(e.violatedDirective + ' ' + e.blockedURI));")
    if before:
        page.add_init_script(before)
    page.add_init_script(library_script())
    page.goto(url)
    return page


with sync_playwright() as p:
    # CI runs the Chromium of the pinned Playwright (the same browser every day); here, Chrome.
    browser = p.chromium.launch(channel=None if os.environ.get("TAURIS_TEST_CHROMIUM") else "chrome")

    # ---------- screenshots: the demo, and the reference rendered the same way ----------
    page = fresh(browser, feed=True)
    page.evaluate("document.fonts.load('12px \"IBM Plex Mono\"').then(() => 0)")
    shot(page, "demo")
    demo_png = page.screenshot(animations="disabled")
    page.close()
    if REFERENCE:
        page = browser.new_page(viewport=SIZE, device_scale_factor=SCALE, color_scheme="dark")
        page.goto(REFERENCE.resolve().as_uri())
        page.evaluate("document.fonts.ready.then(() => 0)")
        page.wait_for_timeout(800)
        shot(page, "reference")
        ref_png = page.screenshot(animations="disabled")
        page.close()
        if SHOTS:
            left, right = Image.open(io.BytesIO(ref_png)), Image.open(io.BytesIO(demo_png))
            gap = 32
            both = Image.new("RGB", (left.width + gap + right.width, max(left.height, right.height)), (48, 48, 48))
            both.paste(left, (0, 0))
            both.paste(right, (left.width + gap, 0))
            both.save(SHOTS / "terminal_side_by_side.png")

    # ---------- the look ----------
    page = fresh(browser)
    root = "#term"
    check("the screen is 12px / 18px", (css(page, root, "font-size"), css(page, root, "line-height")) == ("12px", "18px"))
    family = css(page, root, "font-family")
    check("IBM Plex Mono first, then monospace fallbacks", family == '"IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace', family)
    check("amber on black", (css(page, root, "color"), css(page, root, "background-color")) == (AMBER, BLACK))

    check("command line: 22px high, with a rule below",
          rect(page, ".tm-cmd")["h"] == 22 and css(page, ".tm-cmd", "border-bottom-color") == LINE and css(page, ".tm-cmd", "border-bottom-width") == "1px")
    check("command line: a bold prompt and yellow typed text",
          page.inner_text(".tm-prompt") == "ATLAS>" and css(page, ".tm-prompt", "font-weight") == "600"
          and css(page, ".tm-cmd-input", "color") == YELLOW and page.evaluate("demo.cmd.value") == "SIGNON")
    cur = rect(page, ".tm-cmd .tm-cursor")
    check("command line: a 7 x 13 yellow block that blinks",
          cur["w"] == 7 and cur["h"] == 13 and css(page, ".tm-cmd .tm-cursor", "background-color") == YELLOW
          and css(page, ".tm-cmd .tm-cursor", "animation-name") == "tm-blink"
          and css(page, ".tm-cmd .tm-cursor", "animation-iteration-count") == "infinite", cur)
    date, clock = page.inner_text(".tm-cmd [data-tm-date]"), page.inner_text(".tm-cmd [data-tm-clock]")
    check("command line: the date and time on the right, in white",
          DATE.match(date) and TIME.match(clock) and css(page, ".tm-cmd [data-tm-clock]", "color") == WHITE
          and rect(page, ".tm-cmd [data-tm-clock]")["x"] + rect(page, ".tm-cmd [data-tm-clock]")["w"] > SIZE["width"] - 12, (date, clock))
    both = page.evaluate("[...document.querySelectorAll('#monitor .tm-band [data-tm-clock], .tm-cmd [data-tm-clock]')].map(c => c.textContent)")
    check("a clock in a band shows the same time (both read at once)", len(both) == 2 and both[0] == both[1], both)
    page.wait_for_function("t => document.querySelector('.tm-cmd [data-tm-clock]').textContent !== t", arg=clock, timeout=1500)
    check("the clock ticks every second", page.inner_text(".tm-cmd [data-tm-clock]") != clock)

    band = "#signon .tm-band"
    check("band: 18px of amber with black bold text",
          rect(page, band)["h"] == 18 and css(page, band, "background-color") == AMBER and css(page, band, "color") == BLACK
          and css(page, band, "font-weight") == "600")
    check("band: the right side is lighter (500)", css(page, band + " > :last-child", "font-weight") == "500")
    left, right = rect(page, "#signon"), rect(page, "#monitor")
    check("panes: 1px apart, the gap in #262626",
          right["x"] - (left["x"] + left["w"]) == 1 and css(page, ".tm-panes", "background-color") == LINE, (left, right))
    img = picture(page)
    gap_px = img.getpixel((int((left["x"] + left["w"]) * SCALE), int(300 * SCALE)))
    check("panes: the gap's pixels are #262626", gap_px == (38, 38, 38), gap_px)

    user, pw = rect(page, "#user"), rect(page, "#pass")
    label = rect(page, "#login .tm-label")
    check("fields: 22px high, 13px text, white on dark blue",
          user["h"] == 22 and css(page, "#user", "font-size") == "13px" and css(page, "#user", "color") == WHITE
          and css(page, "#user", "background-color") == FIELD and css(page, "#user", "border-bottom-color") == FIELD_2)
    check("fields: a 92px label column, then the field, then a 40px column (as the reference: 284px)",
          user["x"] - label["x"] == 100 and user["w"] == 284, (label, user))
    check("fields: a focused field is lighter blue with a yellow bar on its left",
          page.evaluate("document.activeElement.id") == "pass" and css(page, "#pass", "background-color") == FIELD_2
          and css(page, "#pass", "box-shadow") == f"{YELLOW} 2px 0px 0px 0px inset", css(page, "#pass", "box-shadow"))
    check("fields: an unfocused one has no bar", css(page, "#user", "box-shadow") == "none")
    check("checkbox: [X] when checked", css(page, "#remember", "content", "::before") == '"[X]"')
    page.evaluate("document.getElementById('remember').click()")
    check("checkbox: [ ] when not", css(page, "#remember", "content", "::before") == '"[ ]"')
    check("checkbox: white, three characters wide",
          css(page, "#remember", "color") == WHITE and 20 <= rect(page, "#remember")["w"] <= 23, rect(page, "#remember"))
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    page.keyboard.press("Space")
    check("checkbox: Space flips it, as any checkbox", page.evaluate("document.getElementById('remember').checked") is True)

    keys = page.evaluate("""[...document.querySelectorAll('#go, #cancel, .tm-legend .tm-key:not(.tm-go):not(.tm-cancel):not([id]), #help')].map(k => {
      const c = getComputedStyle(k), r = k.getBoundingClientRect(); return [k.textContent, c.backgroundColor, c.color, r.height, c.fontSize, c.borderRadius]; })""")
    check("keys: GO green, CANCEL red, grey, yellow; 20px, 11px text",
          keys == [["GO", GREEN, BLACK, 20, "11px", "2px"], ["CANCEL", RED, "rgb(255, 255, 255)", 20, "11px", "2px"],
                   ["TAB", KEY_GREY, "rgb(255, 255, 255)", 20, "11px", "2px"], ["HELP", YELLOW, BLACK, 20, "11px", "2px"]], keys)
    check("keys: the form's keys are 56px wide at least", rect(page, "#go")["w"] == 56)
    page.evaluate("demo.live(false)")
    check("keys: a toggle that is off is grey", css(page, "#live", "background-color") == KEY_GREY and css(page, "#live", "color") == WHITE)

    heads = page.evaluate("[...document.querySelectorAll('.tm-table th')].map(e => e.getBoundingClientRect().height)")
    rows = page.evaluate("[...document.querySelectorAll('.tm-table tbody tr, .tm-table tfoot tr')].map(e => e.getBoundingClientRect().height)")
    check("table: a 20px header and 21px rows", set(heads) == {20} and set(rows) == {21}, (heads, rows))
    check("table: dim amber headers over a rule", css(page, ".tm-table th", "color") == AMBER_DIM and css(page, ".tm-table th", "border-bottom-color") == LINE_2)
    states = page.evaluate("[...document.querySelectorAll('.tm-table tbody tr')].map(r => [r.cells[0].textContent, getComputedStyle(r.cells[0]).color, r.cells[1].textContent, getComputedStyle(r.cells[1]).color, getComputedStyle(r.cells[2]).color])")
    check("table: names in amber, details in white", all(s[1] == AMBER and s[4] == WHITE for s in states), states)
    colour_of = {s[2]: s[3] for s in states}
    check("table: UP green, SEALED yellow, NONE grey", (colour_of["UP"], colour_of["SEALED"], colour_of["NONE"]) == (GREEN, YELLOW, GREY), colour_of)
    check("table: numbers are right-aligned", css(page, ".tm-table tbody .tm-num", "text-align") == "right")
    check("table: the totals row is bold amber over a rule",
          css(page, ".tm-table tfoot td", "font-weight") == "600" and css(page, ".tm-table tfoot td:nth-child(3)", "color") == AMBER
          and css(page, ".tm-table tfoot td", "border-top-color") == LINE_2)
    page.hover(".tm-table tbody tr:nth-child(2) td:nth-child(3)")
    check("table: the row under the mouse lights up", css(page, ".tm-table tbody tr:nth-child(2) td", "background-color") == ROW
          and css(page, ".tm-table tbody tr:nth-child(3) td", "background-color") == "rgba(0, 0, 0, 0)")
    page.mouse.move(5, 540)

    img = picture(page)
    amber = hex_rgb(AMBER)

    def bar_pixels(row):
        r = rect(page, f".tm-table tbody tr:nth-child({row}) .tm-bar")
        y = int((r["y"] + r["h"] / 2) * SCALE)
        return r, [near(img.getpixel((int((r["x"] + x + 0.5) * SCALE), y)), amber) for x in range(int(r["w"]))]

    r, full = bar_pixels(4)
    check("bar: 8px high", r["h"] == 8, r)
    check("bar: segments of 5px with 2px spaces", full[:35] == ([True] * 5 + [False] * 2) * 5, full[:35])
    lit = sum(full[: (int(r["w"]) // 7) * 7]) / ((int(r["w"]) // 7) * 7)
    check("bar: a full meter fills the cell", abs(lit - 5 / 7) < 0.02, lit)
    _, half = bar_pixels(2)
    end = max(i for i, on in enumerate(half) if on) + 1
    check("bar: the value sets the length (6.4 of 13.5)", abs(end / len(half) - 6.4 / 13.5) < 0.04, (end, len(half)))
    check("bar: it grows in, in steps", css(page, ".tm-bar", "animation-name") == "tm-grow" and "steps(14" in css(page, ".tm-bar", "animation-timing-function"))

    check("log: a role=log that speaks politely", page.get_attribute("#log", "role") == "log" and page.get_attribute("#log", "aria-live") == "polite")
    first = page.evaluate("(() => { const li = document.querySelector('#log li'); return [li.children[0].textContent, li.children[0].getAttribute('datetime'), getComputedStyle(li.children[0]).color, li.getBoundingClientRect().height, li.children[1].getBoundingClientRect().x - li.children[0].getBoundingClientRect().x]; })()")
    check("log: each row starts with its time in dim amber, 68px wide",
          TIME.match(first[0]) and first[1] and first[2] == AMBER_DIM and first[3] == 18 and first[4] == 76, first)
    legend = rect(page, ".tm-legend")
    check("legend: a 26px strip in #101010 with a rule above",
          legend["h"] == 26 and legend["y"] + legend["h"] == SIZE["height"] and css(page, ".tm-legend", "background-color") == CHROME
          and css(page, ".tm-legend", "border-top-color") == LINE and css(page, ".tm-legend", "color") == GREY, legend)

    radii = page.evaluate("""[...new Set(['#term', '.tm-cmd', '.tm-cmd-input', '.tm-panes', '.tm-pane', '.tm-band', '.tm-field', '.tm-check',
      '.tm-table', '.tm-table th', '.tm-table td', '.tm-bar', '.tm-log', '.tm-log li', '.tm-legend', '.tm-status']
      .flatMap(s => [...document.querySelectorAll(s)]).map(e => getComputedStyle(e).borderRadius))]""")
    check("no rounding anywhere (keys keep the reference's 2px)", radii == ["0px"], radii)
    page.close()

    # ---------- band states ----------
    page = fresh(browser)
    bg = lambda s: css(page, s, "background-color")
    page.evaluate("demo.signon.ok()")
    page.wait_for_timeout(300)
    check("ok(): the band turns green, text stays black", bg("#signon .tm-band") == GREEN and css(page, "#signon .tm-band", "color") == BLACK)
    check("ok(): other panes keep amber", bg("#monitor .tm-band") == AMBER)
    if SHOTS:
        shot(page, "band_ok", {"x": 0, "y": 0, "width": 470, "height": 300})
    page.evaluate("demo.signon.error()")
    page.wait_for_timeout(300)
    check("error(): the band turns red with white text", bg("#signon .tm-band") == RED and css(page, "#signon .tm-band", "color") == "rgb(255, 255, 255)")
    page.evaluate("demo.signon.reset()")
    page.wait_for_timeout(300)
    check("reset(): back to amber", bg("#signon .tm-band") == AMBER and page.get_attribute("#signon", "data-tm-state") is None)
    page.evaluate("window.msgBand = TaurisTerminal.pane(document.querySelectorAll('#monitor .tm-band')[1]); msgBand.ok()")
    page.wait_for_timeout(300)
    check("pane() on one band colours only that band",
          page.evaluate("[...document.querySelectorAll('#monitor .tm-band')].map(b => getComputedStyle(b).backgroundColor)") == [AMBER, GREEN])
    check("the band changes colour with a short fade", css(page, ".tm-band", "transition-duration") == "0.2s")
    page.evaluate("msgBand.reset(); document.getElementById('user').value = ''")
    page.click("#go")
    page.wait_for_timeout(300)
    check("the demo: GO with no username turns the band red and says why",
          bg("#signon .tm-band") == RED and page.inner_text("#status").startswith("ERR 01") and css(page, "#status", "color") == RED
          and page.evaluate("document.activeElement.id") == "user")
    shot(page, "band_error", {"x": 0, "y": 0, "width": 470, "height": 300})
    page.fill("#user", "j.okafor")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    check("the demo: Enter in a field signs on, and the band turns green",
          bg("#signon .tm-band") == GREEN and page.inner_text("#status") == "AUTHENTICATED" and page.inner_text("#session-state") == "OPEN")
    page.close()

    # ---------- message log ----------
    page = fresh(browser)
    page.evaluate("demo.messages.clear()")
    check("clear() empties the log", page.locator("#log li").count() == 0)
    page.evaluate("window.row = demo.messages.add('ORDER 4471 FILLED  200 @ 41.18', 'ok')")
    flash = page.evaluate("[row.className, getComputedStyle(row).animationName, getComputedStyle(row).backgroundColor]")
    check("add(): the new row flashes amber", flash[0] == "tm-new tm-ok" and flash[1] == "tm-flash" and flash[2] not in ("rgba(0, 0, 0, 0)", BLACK), flash)
    page.wait_for_timeout(1400)
    check("add(): the flash ends and leaves no trace",
          page.evaluate("[row.className, getComputedStyle(row).backgroundColor]") == ["tm-ok", "rgba(0, 0, 0, 0)"])
    page.evaluate("""demo.messages.add('FEED LATENCY 380 MS', 'warn'); demo.messages.add('ERR 07  LINK TO LDN-2 LOST', 'error');
      demo.messages.add('RECONNECTING'); demo.messages.add('<b>14 ORDERS</b> QUEUED')""")
    colours = page.evaluate("[...document.querySelectorAll('#log li')].map(li => getComputedStyle(li).color)")
    check("kinds: ok green, warn yellow, error red, plain white", colours == [GREEN, YELLOW, RED, WHITE, WHITE], colours)
    check("text is shown as text, never as markup",
          page.evaluate("document.querySelector('#log li:last-child span').textContent") == "<b>14 ORDERS</b> QUEUED"
          and page.locator("#log b").count() == 0)
    page.evaluate("for (let i = 1; i <= 40; i++) demo.messages.add(`TICK ${i}  EURUSD 1.0842`)")
    at_bottom = "(() => { const l = document.getElementById('log'); return l.scrollHeight > l.clientHeight && Math.abs(l.scrollHeight - l.clientHeight - l.scrollTop) <= 1; })()"
    check("the log follows the newest row", page.evaluate(at_bottom))
    page.evaluate("document.getElementById('log').scrollTop = 0; demo.messages.add('TICK 41  EURUSD 1.0843')")
    check("scrolled up to read, a new row does not pull the log down", page.evaluate("document.getElementById('log').scrollTop") == 0)
    page.evaluate("const l = document.getElementById('log'); l.scrollTop = l.scrollHeight; demo.messages.add('TICK 42  EURUSD 1.0841')")
    check("back at the bottom, it follows again", page.evaluate(at_bottom))
    capped = page.evaluate("""() => { const ol = document.createElement('ol'); document.body.append(ol);
      const small = TaurisTerminal.log(ol, { max: 5 }); for (let i = 1; i <= 8; i++) small.add(`LINE ${i}`);
      return [ol.children.length, ol.firstElementChild.lastChild.textContent, ol.getAttribute('role'), ol.className]; }""")
    check("max keeps the newest rows", capped == [5, "LINE 4", "log", "tm-log"], capped)
    page.evaluate("demo.messages.add('MARKET OPEN', 'ok', new Date(2026, 9, 21, 8, 0, 0))")
    check("a message can carry its own time", page.evaluate("document.querySelector('#log li:last-child time').textContent") == "08:00:00")
    page.close()

    # ---------- keyboard ----------
    page = fresh(browser)
    page.evaluate("window.addEventListener('keydown', e => window.__prevented = e.defaultPrevented)")
    page.focus("#remember")
    page.keyboard.press("Tab")
    check("Tab reaches the keys", page.evaluate("document.activeElement.id") == "go")
    page.keyboard.press("Tab")
    check("one key after the other", page.evaluate("document.activeElement.id") == "cancel")
    check("a key shows its focus", css(page, "#cancel", "outline-style") == "solid")
    clicks(page)
    page.keyboard.press("Space")
    check("Space presses a key", clicks(page) == ["cancel"] and page.input_value("#pass") == "")
    page.focus("#go")
    page.evaluate("document.getElementById('go').dispatchEvent(new KeyboardEvent('keyup', { key: ' ', bubbles: true }))")
    check("a Space that went down elsewhere does not press a key", clicks(page) == [])
    page.focus("#go")
    page.evaluate("document.getElementById('go').dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }))")
    page.focus("#user")
    page.focus("#go")
    page.evaluate("document.getElementById('go').dispatchEvent(new KeyboardEvent('keyup', { key: ' ', bubbles: true }))")
    check("a Space whose release was lost (the focus left) presses nothing later", clicks(page) == [])
    page.focus("#go")
    page.fill("#pass", "harbour-lights")
    page.focus("#go")
    page.keyboard.press("Enter")
    check("Enter presses a key", clicks(page) == ["go"] and page.inner_text("#status") == "VERIFYING")
    page.wait_for_timeout(3400)
    page.focus("#user")
    page.keyboard.press("F9")
    check("F9 presses the key that lists it, while typing in a field",
          clicks(page) == ["clear"] and page.locator("#log li").count() == 0 and page.evaluate("document.activeElement.id") == "user")
    page.keyboard.press("F1")
    check("F1 presses HELP", clicks(page) == ["help"] and "HELP" in page.inner_text("#log li:last-child"))
    page.keyboard.press("Shift+F1")
    check("Shift+F1 does not", clicks(page) == [])
    page.keyboard.press("F5")
    check("an F-key no key lists is left alone", clicks(page) == [] and page.evaluate("window.__prevented") is False)
    page.evaluate("document.getElementById('help').setAttribute('aria-disabled', 'true')")
    page.keyboard.press("F1")
    page.click("#help", force=True)  # Playwright itself will not click a disabled control
    page.focus("#help")
    page.keyboard.press("Enter")
    check("a disabled key ignores F-keys, clicks and Enter", clicks(page) == [] and css(page, "#help", "opacity") == "0.45")
    page.evaluate("document.getElementById('help').removeAttribute('aria-disabled'); document.getElementById('help').hidden = true")
    page.keyboard.press("F1")
    check("a hidden key ignores its F-key", clicks(page) == [])
    page.close()

    # ---------- command line ----------
    page = fresh(browser)
    page.evaluate("demo.cmd.clear(); demo.cmd.focus()")
    check("the line has a name for screen readers", page.get_attribute(".tm-cmd-input", "aria-label") == "Command")
    x0 = rect(page, ".tm-cmd .tm-cursor")["x"] - rect(page, ".tm-cmd-input")["x"]
    page.keyboard.type("status")
    page.evaluate(TWO_FRAMES)
    x6 = rect(page, ".tm-cmd .tm-cursor")["x"] - rect(page, ".tm-cmd-input")["x"]
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("ArrowLeft")
    page.evaluate(TWO_FRAMES)
    x4 = rect(page, ".tm-cmd .tm-cursor")["x"] - rect(page, ".tm-cmd-input")["x"]
    ch = x6 / 6
    check("the block cursor sits on the caret, one character per step",
          x0 == 0 and 6.5 <= ch <= 8 and abs(x4 - 4 * ch) < 0.5, (x0, x6, x4))
    check("the system caret is hidden", css(page, ".tm-cmd-input", "caret-color") == "rgba(0, 0, 0, 0)")
    page.keyboard.press("End")
    page.keyboard.press("Enter")
    check("Enter runs the command and empties the line",
          page.evaluate("demo.cmd.value") == "" and page.inner_text("#log li:last-child span") == "3 PEERS · 48,213 DOCUMENTS · VAULT SEALED")
    page.keyboard.type("xyz")
    page.keyboard.press("Enter")
    check("an unknown command is an error row", page.evaluate("document.querySelector('#log li:last-child').classList.contains('tm-error')"))
    page.keyboard.press("ArrowUp")
    check("Up brings back the last command", page.evaluate("demo.cmd.value") == "xyz")
    page.keyboard.press("ArrowUp")
    check("and the one before", page.evaluate("demo.cmd.value") == "status")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    check("Down goes back to an empty line", page.evaluate("demo.cmd.value") == "")
    page.keyboard.type("signon")
    page.keyboard.press("Escape")
    check("Escape empties the line (and the page's own Escape is not called)",
          page.evaluate("demo.cmd.value") == "" and page.inner_text("#log li:last-child span") != "PASSWORD CLEARED")
    page.keyboard.press("Enter")
    check("an empty line sends nothing", page.inner_text("#log li:last-child span") != "")
    page.evaluate("demo.cmd.destroy()")
    check("destroy() empties its element", page.evaluate("document.getElementById('cmd').children.length") == 0
          and page.evaluate("document.getElementById('cmd').className") == "")
    page.evaluate("window.again = TaurisTerminal.commandLine(document.getElementById('cmd'), { prompt: 'DESK>' })")
    check("commandLine works again after destroy", page.inner_text(".tm-prompt") == "DESK>")
    page.close()

    page = fresh(browser)
    page.evaluate("demo.cmd.clear(); demo.cmd.focus()")
    page.keyboard.type("status")
    page.keyboard.press("Enter")
    page.keyboard.type("buy 100 AAP")
    page.keyboard.press("ArrowUp")
    up = page.input_value(".tm-cmd-input")
    page.keyboard.press("ArrowDown")
    check("Up shows the last command; Down gives back what was being typed", up == "status" and page.input_value(".tm-cmd-input") == "buy 100 AAP",
          (up, page.input_value(".tm-cmd-input")))
    page.close()

    page = fresh(browser)
    page.evaluate("demo.cmd.clear(); demo.cmd.focus()")
    page.keyboard.insert_text("日本語")
    page.evaluate(TWO_FRAMES)
    wide = page.evaluate("""(() => { const i = document.querySelector('.tm-cmd-input'); const c = document.querySelector('.tm-cmd .tm-cursor');
      const r = document.createRange(); const m = document.createElement('span'); m.style.font = getComputedStyle(i).font; m.style.letterSpacing = getComputedStyle(i).letterSpacing;
      m.style.position = 'absolute'; m.style.whiteSpace = 'pre'; m.textContent = i.value; document.body.append(m); const w = m.getBoundingClientRect().width; m.remove();
      return [c.getBoundingClientRect().left - i.getBoundingClientRect().left, w]; })()""")
    check("the block cursor sits after wide characters (CJK), not in their middle", abs(wide[0] - wide[1]) < 2, wide)
    page.evaluate("document.querySelector('.tm-cmd-input').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true }))")
    check("Enter that confirms an input method's text sends nothing", page.input_value(".tm-cmd-input") == "日本語")
    page.close()

    page = fresh(browser)
    page.evaluate("demo.cmd.clear(); demo.cmd.focus()")
    page.keyboard.insert_text("x" * 160)
    page.evaluate(TWO_FRAMES)
    inside = "(() => { const i = document.querySelector('.tm-cmd-input').getBoundingClientRect(); const c = document.querySelector('.tm-cmd .tm-cursor').getBoundingClientRect(); return [c.left >= i.left - 0.5, c.right <= i.right + 0.5, Math.round(c.left), Math.round(i.right)]; })()"
    at_end = page.evaluate(inside)
    page.set_viewport_size({"width": 500, "height": SIZE["height"]})
    page.wait_for_timeout(100)
    page.evaluate(TWO_FRAMES)
    narrower = page.evaluate(inside)
    check("at the end of a line that scrolls, the block stays inside the field, also once the window narrows",
          at_end[:2] == [True, True] and narrower[:2] == [True, True], (at_end, narrower))
    page.close()

    page = fresh(browser)
    page.evaluate("demo.cmd.clear(); demo.cmd.focus()")
    page.keyboard.insert_text("abc שלום")
    page.evaluate(TWO_FRAMES)
    caret = page.evaluate("""(() => { const i = document.querySelector('.tm-cmd-input'); const c = document.querySelector('.tm-cmd .tm-cursor');
      const m = document.createElement('span'); m.style.font = getComputedStyle(i).font; m.style.position = 'absolute'; m.style.whiteSpace = 'pre';
      m.textContent = 'abc '; document.body.append(m); const w = m.getBoundingClientRect().width; m.remove();
      return [c.getBoundingClientRect().left - i.getBoundingClientRect().left, w]; })()""")
    check("after right-to-left text the block sits where the caret is (at the Hebrew's left edge), not past it",
          abs(caret[0] - caret[1]) < 2, caret)
    page.close()

    page = fresh(browser)
    page.evaluate("document.getElementById('cmd').setAttribute('dir', 'rtl'); demo.cmd.clear(); demo.cmd.focus()")
    page.keyboard.insert_text("שלום עולם")
    page.evaluate(TWO_FRAMES)
    rtl = page.evaluate("""(() => { const i = document.querySelector('.tm-cmd-input').getBoundingClientRect(); const c = document.querySelector('.tm-cmd .tm-cursor').getBoundingClientRect();
      return [Math.round(c.left - i.left), Math.round(i.width)]; })()""")
    check("a right-to-left command line: the block cursor sits where the caret is (at the line's left end), not at the field's start",
          rtl[0] < rtl[1] - 20 and rtl[0] > 0, rtl)
    page.close()

    page = fresh(browser)
    rows = page.evaluate("""(() => { const ol = document.createElement('ol'); ol.style.cssText = 'height:120px;overflow:auto;overflow-anchor:none'; /* as WebKit: no scroll anchoring */ document.body.prepend(ol);
      const log = TaurisTerminal.log(ol, { max: 20 }); for (let i = 1; i <= 20; i++) log.add(`ROW ${i}`);
      const r9 = [...ol.children][8]; ol.scrollTop = r9.offsetTop - ol.firstElementChild.offsetTop;
      const top = () => [...ol.children].find(li => li.getBoundingClientRect().bottom > ol.getBoundingClientRect().top + 1).textContent;
      const before = top(); for (let i = 21; i <= 23; i++) log.add(`ROW ${i}`); return [before, top()]; })()""")
    check("a full log trimming old rows keeps the place of someone reading further up", rows[0] == rows[1], rows)
    page.close()

    # ---------- a page that brings its own stylesheet ----------
    term_js = (WEB / "terminal.js").read_text().replace('"__TAURIS_TERMINAL_CSS__"', json.dumps((WEB / "terminal.css").read_text()))
    page = browser.new_page(viewport={"width": 600, "height": 300})
    page.add_init_script(term_js)
    page.goto("about:blank")
    sheets = page.evaluate("""() => { const d = document.createElement('div'); document.body.append(d);
      const c = document.createElement('div'); d.append(c); TaurisTerminal.commandLine(c, { styles: false });
      const t = TaurisTerminal.mount(d, { styles: false }); TaurisTerminal.log(document.createElement('ul')); TaurisTerminal.pane(document.createElement('div'));
      const before = document.adoptedStyleSheets.length; t.destroy(); TaurisTerminal.mount(document.createElement('div'));
      return [before, document.adoptedStyleSheets.length]; }""")
    check("styles: false keeps every part from adding the stylesheet; a later mount without it adds it", sheets == [0, 1], sheets)
    page.close()

    # ---------- mount and destroy ----------
    page = fresh(browser)
    try:
        page.evaluate("TaurisTerminal.mount(document.getElementById('term'))")
        check("a second mount on one element is refused", False)
    except Exception:
        check("a second mount on one element is refused", True)
    page.evaluate("demo.term.destroy()")
    page.focus("#user")
    page.keyboard.press("F9")
    check("after destroy() the F-keys are free and class tm stays (the page wrote it)",
          clicks(page) == [] and page.evaluate("document.getElementById('term').classList.contains('tm')"))
    page.evaluate("window.t2 = TaurisTerminal.mount(document.getElementById('term'))")
    page.keyboard.press("F9")
    check("mount after destroy works", clicks(page) == ["clear"])
    marked = page.evaluate("""() => { const d = document.createElement('div'); document.body.append(d);
      const t = TaurisTerminal.mount(d); const had = d.className; t.destroy(); return [had, d.className]; }""")
    check("mount marks a plain element .tm, destroy unmarks it", marked == ["tm", ""], marked)
    page.close()

    # ---------- reduced motion ----------
    page = fresh(browser, reduced_motion="reduce")
    page.evaluate("window.row = demo.messages.add('ORDER 4472 FILLED', 'ok')")
    motion = page.evaluate("""[getComputedStyle(document.querySelector('.tm-cmd .tm-cursor')).animationName, getComputedStyle(row).animationName,
      getComputedStyle(document.querySelector('.tm-bar')).animationName, getComputedStyle(document.querySelector('.tm-band')).transitionDuration]""")
    check("reduced motion: no blink, no flash, no growing bars, no fade", motion == ["none", "none", "none", "0s"], motion)
    page.close()

    # ---------- as the plugin delivers it ----------
    page = strict_page(browser, (HERE / "page.html").as_uri())
    check("no terminal stylesheet is added before it is used", page.evaluate("document.adoptedStyleSheets.length") == 0)
    page.evaluate("(" + BUILD + ")(document.body.appendChild(document.createElement('div')))")
    check("using it adds its stylesheet once", page.evaluate("document.adoptedStyleSheets.length") == 1
          and css(page, ".tm-band", "background-color") == AMBER and rect(page, ".tm-band")["h"] == 18)
    before = page.evaluate(SIGNATURE)
    cursor_before = rect(page, ".tm-cmd .tm-cursor")
    page.add_style_tag(content=TEMPLATE_CSS)
    page.wait_for_timeout(100)
    after = page.evaluate(SIGNATURE)
    changed = {s: {k: (before[s][k], after[s][k]) for k in before[s] if before[s][k] != after[s][k]} for s in before}
    changed = {s: d for s, d in changed.items() if d}
    check("a starter template's input and button rules change nothing", not changed, changed)
    check("nor the command line's cursor", rect(page, ".tm-cmd .tm-cursor") == cursor_before)
    page.focus("#user")
    check("a focused field keeps its look under the template",
          css(page, "#user", "box-shadow") == f"{YELLOW} 2px 0px 0px 0px inset" and css(page, "#user", "border-top-width") == "0px")
    page.close()

    # ---------- under a strict content policy ----------
    page = strict_page(browser, (HERE / "csp.html").as_uri())
    page.evaluate("(" + BUILD + ")(document.getElementById('t'))")
    page.evaluate("messages.add('LINK UP', 'ok'); band.error()")
    page.focus("#user")
    page.keyboard.press("F8")
    page.wait_for_timeout(400)
    img = picture(page)
    bar = rect(page, "#bar")
    lit = [near(img.getpixel((int((bar["x"] + x + 0.5) * SCALE), int((bar["y"] + 4) * SCALE))), hex_rgb(AMBER)) for x in range(14)]
    check("strict policy: the look is all there (band, field, bar)",
          css(page, ".tm-band", "background-color") == RED and css(page, "#pass", "background-color") == FIELD
          and lit == [True] * 5 + [False] * 2 + [True] * 5 + [False] * 2,
          (css(page, ".tm-band", "background-color"), css(page, "#pass", "background-color"), lit))
    check("strict policy: the clocks, the log and the F-keys work",
          TIME.match(page.inner_text(".tm-band [data-tm-clock]")) and page.locator("#log li").count() == 2 and page.evaluate("prints") == 1)
    check("strict policy: no console errors and nothing refused", not page.errors and page.evaluate("__csp") == [], (page.errors, page.evaluate("__csp")))
    shot(page, "strict_policy")
    page.close()

    # ---------- a close-up of the table ----------
    if SHOTS:
        page = fresh(browser)
        page.hover(".tm-table tbody tr:nth-child(5) td:nth-child(3)")
        m = rect(page, "#monitor")
        shot(page, "table", {"x": m["x"], "y": m["y"], "width": m["w"], "height": 200})
        page.close()

    browser.close()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
