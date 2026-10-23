"""Headless tests for the dialogs (web/dialog.js), on test/dialog_demo.html.

    python test/dialog_run.py

Nothing touches the screen. TAURIS_TEST_CHROMIUM=1 or TAURIS_TEST_WEBKIT=1
runs it in CI's browsers (see engine.py).
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from engine import WEBKIT, launch, settled

HERE = Path(__file__).parent
WEB = HERE.parent / "web"
DEMO = HERE / "dialog_demo.html"
failures = []


def check(name, ok, detail=""):
    ok, detail = settled(ok, detail)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        failures.append(name)


def fresh(browser, scheme="light"):
    page = browser.new_page(viewport={"width": 1000, "height": 700}, device_scale_factor=2, color_scheme=scheme)
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.goto(DEMO.as_uri())
    return page


def focused(page):
    return page.evaluate("document.activeElement.id || document.activeElement.textContent.trim().slice(0, 30)")


def ask(page, script):
    """Starts a dialog; its answer lands in window.answer."""
    page.evaluate("window.answer = undefined; (" + script + ").then(a => { window.answer = a === undefined ? '(none)' : a; }); 0")
    page.wait_for_selector(".tdl")


# A dialog's own window, stood in for: what the plugin would do, the page's calls kept in __sent.
MOCK = """window.__sent = []; window.__TAURI__ = { core: { invoke: async (name, args) => {
  __sent.push([name, args]);
  if (name === 'plugin:tauris-ui|dialog_window_open') return 'tauris-dialog-1';
  if (name === 'plugin:tauris-ui|dialog_window_spec') return window.__spec;
  if (name === 'plugin:tauris-ui|dialog_window_ready') return args.height;
  return null; } } };"""


def relay(owner, child):
    """Carries the plugin's messages: the dialog window's sends to the window that asked, and its replies back."""
    for name, args in child.evaluate("__sent.splice(0)"):
        if name == "plugin:tauris-ui|dialog_window_send":
            owner.evaluate("m => __taurisUiDeliver('tauris-ui:dialog-window', { label: 'tauris-dialog-1', message: m })", args["message"])
        elif name == "plugin:tauris-ui|dialog_window_ready":
            child.evaluate("s => { window.__size = s; }", args)
        elif name == "plugin:tauris-ui|dialog_window_close":
            child.evaluate("window.__closed = true")
            owner.evaluate("__taurisUiDeliver('tauris-ui:dialog-window', { label: 'tauris-dialog-1', message: { type: 'closed' } })")
    for name, args in owner.evaluate("__sent.splice(0)"):
        if name == "plugin:tauris-ui|dialog_window_reply" and args["message"].get("type") != "focus":
            child.evaluate("m => __taurisUiDeliver('tauris-ui:dialog-window', { label: 'tauris-dialog-1', message: m })", args["message"])
        elif name == "plugin:tauris-ui|dialog_window_open":
            owner.evaluate("s => { window.__opened = s; }", args)


def pump(owner, child, until, seconds=3):
    """Relays until `until` (a script on the dialog window or the owner) holds."""
    import time
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        relay(owner, child)
        if until():
            return True
        time.sleep(0.03)
    return False


def answer(page):
    page.wait_for_function("window.answer !== undefined", timeout=3000)
    return page.evaluate("window.answer")


with sync_playwright() as p:
    browser = launch(p)

    # ---------- a question ----------
    page = fresh(browser)
    page.focus("#list")
    ask(page, "TaurisDialog.confirm({ title: 'Delete “Atlas”?', message: 'Its files go too.\\n\\nThis cannot be undone.', ok: 'Delete', danger: true })")
    a11y = page.evaluate("""(() => { const d = document.querySelector('.tdl'); return [d.getAttribute('role'), d.getAttribute('aria-modal'),
      document.getElementById(d.getAttribute('aria-labelledby')).textContent, document.getElementById(d.getAttribute('aria-describedby')).textContent.includes('cannot be undone')]; })()""")
    check("a question: an alert dialog, named by its title and described by its message", a11y == ["alertdialog", "true", "Delete “Atlas”?", True], a11y)
    check("it starts on Cancel (Enter never deletes by accident); the page under it is out of reach",
          focused(page) == "Cancel" and page.evaluate("document.querySelector('main').inert"), focused(page))
    page.keyboard.press("Tab")
    on_delete = focused(page)
    page.keyboard.press("Tab")
    check("Tab goes round inside it", on_delete == "Delete" and focused(page) == "Cancel", (on_delete, focused(page)))
    page.keyboard.press("Enter")
    check("Enter on Cancel says no; the focus goes back to the list, the page in reach again",
          answer(page) is False and focused(page) == "list" and not page.evaluate("document.querySelector('main').inert"), focused(page))
    ask(page, "TaurisDialog.confirm({ title: 'Delete?', ok: 'Delete', danger: true })")
    page.click(".tdl-danger")
    check("its red button says yes", answer(page) is True)
    ask(page, "TaurisDialog.confirm({ title: 'Delete?' })")
    page.keyboard.press("Escape")
    no_esc = answer(page)
    ask(page, "TaurisDialog.confirm({ title: 'Delete?' })")
    page.mouse.click(5, 690)
    check("Esc, and a press beside it, say no", no_esc is False and answer(page) is False)
    # native: the system's alert through the plugin; without it, the page asks
    page.evaluate("""window.asked = []; window.__TAURI__ = { core: { invoke: async (c, a) => { asked.push([c, a.ok, a.warning]); return true; } } }; 0""")
    page.evaluate("window.answer = undefined; TaurisDialog.confirm({ title: 'Quit?', ok: 'Quit', native: true, danger: true }).then(a => { window.answer = a; }); 0")
    check("native: asked with the system's alert (the plugin's ask), nothing drawn in the page",
          answer(page) is True and page.evaluate("asked") == [["plugin:tauris-ui|ask", "Quit", True]] and page.locator(".tdl").count() == 0)
    page.evaluate("window.__TAURI__.core.invoke = async () => { throw 'The file dialogs need tauris-ui\\'s files feature'; }; 0")
    ask(page, "TaurisDialog.confirm({ title: 'Quit?', native: true })")
    check("native without the system's alert: asked in the page", page.locator(".tdl").count() == 1)
    page.keyboard.press("Escape")
    page.close()

    # ---------- a form ----------
    page = fresh(browser)
    page.focus("#field")
    ask(page, "newProject()")
    labels = page.evaluate("[...document.querySelectorAll('.tdl-label')].map(l => l.textContent)")
    layout = page.evaluate("""(() => { const l = document.querySelector('.tdl-label').getBoundingClientRect(), f = document.querySelector('.tdl-input').getBoundingClientRect();
      return [getComputedStyle(document.querySelector('.tdl-label')).textAlign, l.right <= f.left, Math.round(f.height)]; })()""")
    check("a form in the Swing layout: right-aligned “Label:” beside each field, 26px fields",
          labels[:4] == ["Name:", "Team:", "Budget:", "Notes:"] and layout == ["right", True, 26], (labels, layout))
    ph = page.evaluate("""(() => { const i = document.querySelector('.tdl-input'); i.value = 'x'; const typed = getComputedStyle(i).color; i.value = '';
      return [getComputedStyle(i, '::placeholder').color, typed]; })()""")
    # (WebKit gives a placeholder's colour as its field's to a script.)
    check("an example placeholder, dimmer than typed text", WEBKIT or ph[0] != ph[1], ph)
    check("it starts in its first field; its hint on the kept line", focused(page).endswith("-name") and page.inner_text(".tdl-line-hint") == "Names are unique.",
          focused(page))
    page.wait_for_timeout(250)  # its opening (a slight scale) done
    line_h = page.evaluate("document.querySelector('.tdl').getBoundingClientRect().height")
    page.keyboard.press("Enter")
    tip = (page.inner_text(".tdl-cell:has(#" + page.evaluate("document.activeElement.id") + ") .tdl-tip"), page.evaluate("document.activeElement.getAttribute('aria-invalid')"))
    check("a needed field left empty: a balloon under it, the field marked and given the keys", tip == ("Name is needed.", "true"), tip)
    page.keyboard.type("Atlas")
    cleared = page.evaluate("document.querySelector('.tdl-tip:not([hidden])') === null")
    page.keyboard.press("Enter")
    taken = page.evaluate("document.querySelector('.tdl-tip:not([hidden])')?.textContent")
    check("typing clears it; the app's check (validate) refuses a taken name the same way", cleared and taken == "That name is taken.", (cleared, taken))
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type("Orion")
    page.fill("[id$='-budget']", "5000000")
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    refused = page.inner_text(".tdl-line-error")
    same_h = page.evaluate("document.querySelector('.tdl').getBoundingClientRect().height") == line_h
    check("a throw from submit: its message on the kept line, the hint gone, the dialog the same height, still open",
          refused == "The server refused a budget that large." and same_h and page.locator(".tdl").count() == 1, (refused, same_h))
    page.fill("[id$='-budget']", "5000")
    page.check("[id$='-public']")
    page.keyboard.press("Enter")
    got = answer(page)
    check("then it saves and closes with the values; the focus goes back", got == {"name": "Orion", "team": "Team A", "budget": 5000, "notes": "", "public": True}
          and page.evaluate("said") == [["saved", "Orion"]] and focused(page) == "field", (got, focused(page)))
    ask(page, "newProject()")
    page.focus("[id$='-notes']")
    page.keyboard.type("line one")
    page.keyboard.press("Enter")
    page.keyboard.type("line two")
    in_area = page.locator(".tdl").count() == 1 and page.input_value("[id$='-notes']") == "line one\nline two"
    page.keyboard.press("Escape")
    check("Enter in a text area is a new line; Esc cancels (null)", in_area and answer(page) is None)
    page.close()

    # ---------- a review before saving ----------
    page = fresh(browser)
    ask(page, "editProject()")
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type("Atlas Prime")
    page.keyboard.press("Enter")
    rows = page.evaluate("[...document.querySelectorAll('.tdl-review-rows tr')].map(r => r.textContent)")
    check("review: the changes, “Field: old → new”, before saving (only those changed)", rows == ["Name:Atlas → Atlas Prime"]
          and page.is_hidden(".tdl-page") and focused(page) == "Save", (rows, focused(page)))
    page.keyboard.press("Escape")
    back = page.is_visible(".tdl-page") and page.evaluate("document.activeElement.value") == "Atlas Prime"
    page.keyboard.press("Enter")
    page.keyboard.press("Enter")
    check("Esc during the review goes back to the fields; Save saves", back and answer(page) == {"name": "Atlas Prime", "owner": "Ana"}, back)
    ask(page, "TaurisDialog.review({ title: 'Save Changes', rows: [{ field: 'Password', after: 'changed' }, { field: 'Name', before: 'A', after: 'B' }] })")
    rows = page.evaluate("[...document.querySelectorAll('.tdl-review-rows tr')].map(r => r.textContent)")
    page.keyboard.press("Enter")
    check("a review on its own: a secret says only that it changed", rows == ["Password:changed", "Name:A → B"] and answer(page) is True, rows)
    page.close()

    # ---------- a check that asks first, a review's own note, a field's limit ----------
    page = fresh(browser)
    ask(page, """TaurisDialog.form({ title: 'Edit Value', fields: [{ name: 'when', label: 'Date' }, { name: 'value', label: 'Value', value: '10', maxLength: 4 }],
      validate: v => TaurisDialog.confirm({ title: 'Future Date', message: 'Save it?', ok: 'Save', cancel: 'No' }).then(yes => (yes ? null : false)),
      review: v => ({ rows: [{ field: 'Value', before: '10', after: v.value }], note: Number(v.value) > 100 ? 'That’s a large change.' : null }) })""")
    page.focus("[id$='-value']")
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type("12345")
    limit = (page.input_value("[id$='-value']"), page.evaluate("document.querySelector('.tdl-tip:not([hidden])')?.textContent"))
    check("maxLength: typing stops there, and it says so under the field", limit == ("1234", "At most 4 characters."), limit)
    page.keyboard.press("Enter")
    page.wait_for_function("document.querySelectorAll('.tdl').length === 2", timeout=3000)
    page.keyboard.press("Escape")
    page.wait_for_function("document.querySelectorAll('.tdl').length === 1", timeout=3000)
    stayed = (page.is_visible(".tdl-page"), page.inner_text(".tdl-line-error"), focused(page).endswith("-value"), page.evaluate("window.answer"))
    check("validate giving false (No to its question): the form stays as it is, nothing said, the keys back in their field",
          stayed == (True, "", True, None), stayed)
    page.keyboard.press("Enter")
    page.wait_for_function("document.querySelectorAll('.tdl').length === 2", timeout=3000)
    page.keyboard.press("Enter")
    page.wait_for_selector(".tdl-review:not([hidden])")
    note = page.evaluate("document.querySelector('.tdl-review-note')?.textContent")
    page.keyboard.press("Enter")
    check("review giving { rows, note }: its note under the changes; then it saves", note == "That’s a large change." and answer(page) == {"when": "", "value": "1234"}, note)
    page.close()

    # ---------- where a form starts, a press beside it ----------
    page = fresh(browser)
    kpi = "[{ name: 'project', label: 'Project', type: 'select', options: ['Atlas', 'Orion'] }, { name: 'name', label: 'Name', value: 'Reach' }, { name: 'unit', label: 'Unit'%s }]"
    ask(page, "TaurisDialog.form({ title: 'New KPI', fields: " + kpi % "" + " })")
    check("a form starts in its first text field, not a select above it", focused(page).endswith("-name"), focused(page))
    page.evaluate("""window.__nudged = false; new MutationObserver(() => { window.__nudged ||= document.querySelector('.tdl').classList.contains('tdl-nudge'); })
      .observe(document.querySelector('.tdl'), { attributes: true })""")
    page.mouse.click(5, 690)
    page.wait_for_timeout(50)
    nudged = (page.locator(".tdl").count(), page.evaluate("window.__nudged"), focused(page).endswith("-name"), page.evaluate("window.answer"))
    check("a press beside it: a short shake, still open, the keys where they were", nudged == (1, True, True, None), nudged)
    page.keyboard.press("Escape")
    answer(page)
    ask(page, "TaurisDialog.form({ title: 'New KPI', fields: " + kpi % ", autofocus: true" + " })")
    check("autofocus: it starts in that field", focused(page).endswith("-unit"), focused(page))
    page.keyboard.press("Escape")
    answer(page)
    page.close()

    # ---------- the sheets ----------
    page = fresh(browser)
    ask(page, """TaurisDialog.shortcuts({ groups: [
      { title: 'Everywhere', items: [{ label: 'Find anything', keys: ['⌘K'] }, { label: 'Back or forward', keys: ['⌘[', '⌘]'], either: true }] },
      { title: 'Tasks', items: [{ label: 'New task', keys: ['⌘N'] }, { label: 'Done', keys: ['⌘↩'] }, { label: 'Delete', keys: ['⌫'] }] },
      { title: 'People', items: [{ label: 'New person', keys: ['⌘⇧N'] }] },
      { title: 'Passwords', items: [{ label: 'Copy', keys: ['⌘C'] }] } ] })""")
    sheet = page.evaluate("""(() => [document.querySelectorAll('.tdl-column').length, [...document.querySelectorAll('.tdl-column')].map(c => c.querySelectorAll('dt').length),
      document.querySelectorAll('.tdl-key').length, [...document.querySelectorAll('.tdl-keys')][1].textContent])()""")
    check("Keyboard Shortcuts: groups in three columns of about the same height, keys as keycaps, “either” rows",
          sheet[0] == 3 and max(sheet[1]) - min(sheet[1]) <= 2 and sheet[2] == 8 and sheet[3] == "⌘[ or ⌘]", sheet)
    page.keyboard.press("Enter")
    check("Done closes it", answer(page) == "(none)")
    ask(page, "TaurisDialog.about({ name: 'MLPC', mark: '🗂', description: 'Projects, KPIs and people.', rows: [['Version', '2.4.0'], ['Signed in as', 'Ana']] })")
    about = page.evaluate("[document.querySelector('.tdl-title').textContent, document.querySelector('.tdl-about-name').textContent, [...document.querySelectorAll('.tdl-about-rows dt')].map(d => d.textContent)]")
    page.keyboard.press("Escape")
    check("About: its mark, name, description and key/value rows; Esc closes it", about == ["About MLPC", "MLPC", ["Version", "Signed in as"]] and answer(page) == "(none)", about)
    page.close()

    # ---------- a titled panel ----------
    page = fresh(browser)
    head = page.evaluate("""(() => { const p = document.getElementById('kpis'), h = p.querySelector('.tdl-panel-head'), r = p.getBoundingClientRect(), hr = h.getBoundingClientRect();
      return [h.textContent, Math.round(hr.top + hr.height / 2 - r.top), p.getAttribute('aria-label'), p.querySelectorAll('p').length]; })()""")
    check("a titled panel: its title, count and buttons on its top line; its content stays", head[0] == "KPIs· 2+ New KPI…Open" and abs(head[1]) <= 1 and head[2] == "KPIs" and head[3] == 2, head)
    page.click(".tdl-panel-action")
    page.click(".tdl-panel-action[aria-disabled=true]", force=True)
    page.evaluate("panel.update({ count: 3 }); 0")
    check("its buttons act (a disabled one does not); update() changes the count", page.evaluate("said") == ["new kpi"] and "· 3" in page.inner_text(".tdl-panel-head"))
    page.close()

    # ---------- the look ----------
    for scheme in ("light", "dark"):
        page = fresh(browser, scheme)
        ask(page, "newProject()")
        page.keyboard.press("Enter")
        c = page.evaluate("""(() => { const s = q => getComputedStyle(document.querySelector(q)); return [s('.tdl-label').color, s('.tdl').backgroundColor,
          s('.tdl-primary').color, s('.tdl-primary').backgroundColor, s('.tdl-tip').color, s('.tdl-tip').backgroundColor, s('.tdl-line-hint').color]; })()""")
        ratios = page.evaluate("""(cs) => { const rgb = c => { const cv = document.createElement('canvas').getContext('2d'); cv.fillStyle = c; cv.fillRect(0, 0, 1, 1); return [...cv.getImageData(0, 0, 1, 1).data].slice(0, 3); };
          const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
          const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return Math.round((x + 0.05) / (y + 0.05) * 100) / 100; };
          return [ratio(cs[0], cs[1]), ratio(cs[2], cs[3]), ratio(cs[4], cs[5]), ratio(cs[6], cs[1])]; }""", c)
        check(f"{scheme}: labels, the default button, a field's refusal and the hint read (4.5:1)", min(ratios) >= 4.5, (c, ratios))
        page.close()

    # ---------- a question whose action can fail ----------
    page = fresh(browser)
    page.focus("#list")
    ask(page, "TaurisDialog.confirm({ title: 'Delete “Atlas”?', ok: 'Delete', danger: true, run: async () => { window.tries = (window.tries || 0) + 1; if (window.tries === 1) throw new Error('The server refused: Atlas has open tasks.'); } })")
    page.click(".tdl-btn.tdl-danger")
    check("run: refused, the question stays, the reason on its line, the keys on Cancel",
          lambda: page.is_visible(".tdl") and page.inner_text(".tdl-question-line") == "The server refused: Atlas has open tasks." and focused(page) == "Cancel",
          lambda: (page.is_visible(".tdl"), focused(page)))
    page.click(".tdl-btn.tdl-danger")
    check("run again, done: the question closes, true", answer(page) is True and page.locator(".tdl").count() == 0)
    page.close()

    # ---------- the app's own fields ----------
    page = fresh(browser)
    page.evaluate("""TaurisDialog.defineField('people', (cell, field) => {
      const list = document.createElement('div'); list.className = 'people';
      let chosen = [...(field.value || [])];
      const draw = () => { list.replaceChildren(...field.options.map(n => { const b = document.createElement('label'); const c = document.createElement('input');
        c.type = 'checkbox'; c.checked = chosen.includes(n); c.addEventListener('change', () => { chosen = c.checked ? [...chosen, n] : chosen.filter(x => x !== n); }); b.append(c, n); return b; })); };
      draw(); cell.append(list); window.peopleDestroyed = false;
      return { value: () => chosen, focus: () => list.querySelector('input').focus(), destroy: () => { window.peopleDestroyed = true; } };
    }); 0""")
    ask(page, "TaurisDialog.form({ title: 'New Task', fields: [{ name: 'name', label: 'Name', value: 'Brief' }, { name: 'who', label: 'People', type: 'people', options: ['Ana', 'Ben'], required: true }], validate: async v => (v.who.includes('Ben') ? { field: 'who', text: 'Ben is away.' } : null) })")
    check("a field type the app defines: drawn in the form's layout, its label beside it", page.locator(".tdl-custom .people label").count() == 2
          and page.inner_text(".tdl-label.tdl-top:nth-of-type(2)") == "People:")
    page.keyboard.press("Enter")
    check("needed and empty: the balloon under it, its own focus", lambda: page.inner_text(".tdl-custom ~ .tdl-tip") == "People is needed." and page.evaluate("document.activeElement.closest('.people') !== null"))
    page.click(".people label:nth-child(2) input")
    page.click(".tdl-primary")
    check("an async check: its refusal on the app's field", lambda: page.inner_text(".tdl-custom ~ .tdl-tip") == "Ben is away.")
    page.click(".people label:nth-child(2) input")
    page.click(".people label:nth-child(1) input")
    page.click(".tdl-primary")
    check("its value with the others, and destroy() when the dialog closes", answer(page) == {"name": "Brief", "who": ["Ana"]} and page.evaluate("peopleDestroyed") is True,
          page.evaluate("window.answer"))
    ask(page, "TaurisDialog.form({ title: 'Photo', fields: [{ name: 'photo', label: 'Photo', render: cell => { const i = document.createElement('input'); i.id = 'ph'; i.value = 'me.png'; cell.append(i); return { value: () => i.value }; } }] })")
    page.keyboard.press("ControlOrMeta+Enter")
    check("a one-off field (render on the field), ⌘↩ from inside it", answer(page) == {"photo": "me.png"}, page.evaluate("window.answer"))
    page.close()

    # ---------- a password: Show, Generate ----------
    page = fresh(browser)
    ask(page, "TaurisDialog.form({ title: 'New Password', fields: [{ name: 'pw', label: 'Password', type: 'password', reveal: true, generate: true }] })")
    check("Show and Generate beside the field", page.locator(".tdl-pw .tdl-pw-btn").count() == 1 and page.inner_text(".tdl-pw-gen") == "Generate"
          and page.get_attribute(".tdl-pw input", "type") == "password")
    page.click(".tdl-pw-btn")
    check("Show: its text readable, the button pressed", page.get_attribute(".tdl-pw input", "type") == "text" and page.get_attribute(".tdl-pw-btn", "aria-pressed") == "true")
    page.click(".tdl-pw-btn")
    page.click(".tdl-pw-gen")
    made = page.evaluate("document.querySelector('.tdl-pw input').value")
    check("Generate: a strong one, shown and selected", len(made) == 20 and page.get_attribute(".tdl-pw input", "type") == "text"
          and page.evaluate("(() => { const i = document.querySelector('.tdl-pw input'); return i.selectionStart === 0 && i.selectionEnd === i.value.length; })()"), made)
    page.click(".tdl-pw-gen")
    check("and another each time", page.evaluate("document.querySelector('.tdl-pw input').value") != made)
    page.keyboard.press("Escape")
    page.close()

    # ---------- pictures in a review, About's values ----------
    page = fresh(browser)
    ask(page, "TaurisDialog.review({ rows: [{ field: 'Photo', beforeImage: 'data:image/gif;base64,R0lGODlhAQABAAAAACw=', afterImage: 'data:image/gif;base64,R0lGODlhAQABAAAAACw=' }, { field: 'Name', before: 'Ana', after: 'Ana Silva' }] })")
    check("a picture's change: its two pictures, named for a screen reader",
          page.evaluate("[...document.querySelectorAll('.tdl-review-rows tr[data-field=Photo] img')].map(i => i.alt)") == ["Photo, before", "Photo, after"]
          and page.locator(".tdl-review-rows .tdl-thumb").first.evaluate("e => Math.round(e.getBoundingClientRect().width)") == 34)
    page.keyboard.press("Escape")
    ask(page, "TaurisDialog.about({ name: 'MLPC', description: 'A shared plan.', rows: [['Server', 'https://plan.example.com']] })")
    check("About: its values and description can be selected (and copied)",
          page.evaluate("[...document.querySelectorAll('.tdl-about-rows dd, .tdl-about-text')].every(e => e.classList.contains('tauris-selectable') && getComputedStyle(e).userSelect === 'text')"))
    page.keyboard.press("Escape")
    page.close()

    # ---------- in a window of its own ----------
    owner = fresh(browser)
    owner.add_init_script(MOCK)
    owner.reload()
    owner.evaluate("TaurisDialog.defineField('people', (cell, f) => { const i = document.createElement('input'); i.className = 'pp'; i.value = (f.value || []).join(','); cell.append(i); return { value: () => i.value.split(',').filter(Boolean) }; }); 0")
    owner.focus("#list")
    owner.evaluate("""window.answer = undefined; window.saved = null; TaurisDialog.form({ window: true, title: 'Edit Task', wide: true, fields: [
      { name: 'name', label: 'Name', value: 'Brief' }, { name: 'who', label: 'People', type: 'people', value: ['Ana'] }],
      validate: v => (v.name === 'x' ? { field: 'name', text: 'Too short.' } : null),
      review: v => [{ field: 'Name', before: 'Brief', after: v.name }],
      submit: async v => { if (v.name === 'Nope') throw { field: 'name', text: 'Taken.' }; window.saved = v; } }).then(a => { window.answer = a; }); 0""")
    owner.wait_for_function("__sent.some(s => s[0] === 'plugin:tauris-ui|dialog_window_open')")
    opened = owner.evaluate("__sent.find(s => s[0] === 'plugin:tauris-ui|dialog_window_open')[1]")
    spec = json.loads(opened["spec"])
    check("window: true asks the plugin for a window of its own: its title and width, the dialog as data (its functions stay)",
          opened["title"] == "Edit Task" and opened["width"] == 560 and spec["kind"] == "form" and spec["has"] == {"validate": True, "review": True, "submit": True, "left": False}
          and "validate" not in spec["options"] and [f["name"] for f in spec["options"]["fields"]] == ["name", "who"], opened)
    check("meanwhile this page is out of reach, its clicks bring the dialog forward",
          owner.evaluate("document.querySelector('main').inert") and owner.locator(".tdl-shield").count() == 1 and owner.evaluate("TaurisDialog.isOpen"))
    owner.click(".tdl-shield")
    check("(a click on it: focus the dialog's window)", owner.evaluate("__sent.some(s => s[0] === 'plugin:tauris-ui|dialog_window_reply' && s[1].message.type === 'focus')"))
    child = browser.new_page(viewport={"width": 560, "height": 160}, device_scale_factor=2)
    child.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    # As in Tauri: window.__TAURI__ arrives after the plugin's scripts have run.
    child.add_init_script("window.addEventListener('DOMContentLoaded', () => { " + MOCK + " window.__spec = " + json.dumps(opened["spec"]) + "; });")
    child.add_init_script("window.addEventListener('DOMContentLoaded', () => TaurisDialog.defineField('people', (cell, f) => { const i = document.createElement('input'); i.className = 'pp'; i.value = (f.value || []).join(','); cell.append(i); return { value: () => i.value.split(',').filter(Boolean) }; }));")
    child.goto(DEMO.as_uri() + "#tauris-dialog")
    check("the dialog's window: the app's page, and only the dialog shows (no title bar of its own: the window's)",
          pump(owner, child, lambda: child.locator(".tdl-form").count() == 1)
          and child.evaluate("TaurisDialog.inWindow") is True and not child.is_visible("main") and not child.is_visible(".tdl-head")
          and child.evaluate("[...document.querySelectorAll('.tdl-label')].map(l => l.textContent)") == ["Name:", "People:"])
    check("it says its size, the window takes it", pump(owner, child, lambda: child.evaluate("window.__size?.width") == 560),
          child.evaluate("window.__size"))
    child.fill(".tdl-input", "x")
    child.keyboard.press("Enter")
    check("the app's check runs in the window that asked; its refusal shows here", pump(owner, child, lambda: child.inner_text(".tdl-tip:not([hidden])") == "Too short."))
    child.fill(".tdl-input", "Nope")
    child.keyboard.press("Enter")
    check("its review comes back to show", pump(owner, child, lambda: child.is_visible(".tdl-review") and "Brief → Nope" in child.inner_text(".tdl-review-rows")))
    child.keyboard.press("Enter")
    check("a save refused there: back to the fields, the balloon here", pump(owner, child, lambda: child.inner_text(".tdl-tip:not([hidden])") == "Taken."))
    child.fill(".tdl-input", "Brief 2")
    child.fill(".pp", "Ana,Ben")
    child.keyboard.press("ControlOrMeta+Enter")  # Enter in the app's own field is the field's
    pump(owner, child, lambda: child.is_visible(".tdl-review"))
    child.keyboard.press("Enter")
    check("saved: the values (the app's field's too) arrive, the window closes itself",
          pump(owner, child, lambda: owner.evaluate("window.answer") is not None and child.evaluate("window.__closed") is True)
          and owner.evaluate("window.saved") == {"name": "Brief 2", "who": ["Ana", "Ben"]} and owner.evaluate("window.answer") == {"name": "Brief 2", "who": ["Ana", "Ben"]})
    check("this page is in reach again, the keys back where they were",
          lambda: owner.locator(".tdl-shield").count() == 0 and not owner.evaluate("document.querySelector('main').inert") and focused(owner) == "list",
          lambda: focused(owner))
    child.close()
    owner.evaluate("window.answer = 'waiting'; TaurisDialog.about({ window: true, name: 'X' }).then(a => { window.answer = a ?? 'closed'; }); 0")
    owner.wait_for_function("__sent.some(s => s[0] === 'plugin:tauris-ui|dialog_window_open')")
    owner.evaluate("__sent.length = 0; __taurisUiDeliver('tauris-ui:dialog-window', { label: 'tauris-dialog-1', message: { type: 'closed' } })")
    check("its window closed from its title bar: the dialog ends", lambda: owner.evaluate("window.answer") == "closed" and owner.locator(".tdl-shield").count() == 0)
    errors = []
    owner.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    owner.evaluate("__sent.length = 0; window.answer = undefined; TaurisDialog.form({ window: true, title: 'Lost', fields: [{ name: 'a' }] }).then(a => { window.answer = a; }); 0")
    owner.wait_for_selector(".tdl-form", timeout=10000)
    check("a window that never shows its dialog: closed, the dialog in the page instead, and the console says why",
          owner.locator(".tdl-shield").count() == 0
          and owner.evaluate("__sent.some(s => s[0] === 'plugin:tauris-ui|dialog_window_reply' && s[1].message.type === 'close')")
          and any("did not show the dialog" in e for e in errors), errors)
    owner.keyboard.press("Escape")
    owner.evaluate("__taurisUiDeliver('tauris-ui:dialog-window', { label: 'tauris-dialog-1', message: { type: 'log', text: 'boom' } })")
    owner.evaluate("window.__TAURI__.core.invoke = async () => { throw new Error('no window'); }; window.answer = undefined; TaurisDialog.confirm({ title: 'x' }); 0")
    owner.evaluate("document.querySelector('.tdl .tdl-btn').click()")
    owner.evaluate("TaurisDialog.form({ window: true, title: 'Here', fields: [{ name: 'a' }] }).then(a => { window.answer = a; }); 0")
    check("no window to be had (no plugin, no permission): in the page instead", lambda: owner.locator(".tdl-form").count() == 1)
    owner.close()

    # ---------- as the plugin delivers it ----------
    page = browser.new_page(viewport={"width": 800, "height": 500})
    page.add_init_script((WEB / "dialog.js").read_text().replace('"__TAURIS_DIALOG_CSS__"', json.dumps((WEB / "dialog.css").read_text())))
    page.goto((HERE / "csp.html").as_uri())
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    before = page.evaluate("document.adoptedStyleSheets.length")
    page.evaluate("TaurisDialog.confirm({ title: 'Go?' }); 0")
    check("under a strict content policy: its stylesheet once it is used, and no error",
          before == 0 and page.evaluate("document.adoptedStyleSheets.length") == 1 and not errors and page.evaluate("TaurisDialog.isOpen"), errors)
    page.close()

    browser.close()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
