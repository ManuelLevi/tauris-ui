"""Tests the example that uses every component (examples/all/ui) in a headless browser.

Run:  python test/all_run.py [screenshot-folder]
Needs Python playwright and Google Chrome. Nothing touches the screen.
Exits non-zero when a check fails. With a folder, it saves screenshots at 2x, light and dark.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from engine import launch

HERE = Path(__file__).parent
WEB = HERE.parent / "web"
PAGE = HERE.parent / "examples" / "all" / "ui" / "index.html"
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if SHOTS:
    SHOTS.mkdir(parents=True, exist_ok=True)
failures = []


def component(name, tag):
    """A component's script as the plugin delivers it: with its stylesheet inside."""
    return (WEB / f"{name}.js").read_text().replace(f'"__TAURIS_{tag}_CSS__"', json.dumps((WEB / f"{name}.css").read_text()))


def scripts():
    tabs = component("tabs", "TABS").replace("__TAURIS_TABS_VERSION__", "test").replace('"__TAURIS_TABS_CAN_DRAG_OUT__"', "true")
    return [(HERE / "mock_tauri.js").read_text(), tabs, component("menus", "MENUS"), component("tree", "TREE"),
            component("files", "FILES"), component("terminal", "TERMINAL"), component("sidebar", "SIDEBAR"),
            component("finder", "FINDER"),
            component("dialog", "DIALOG")]


# What Rust does for the example: a new tab is a project, the picker gives one file, `inspect` sizes it.
RUST = """
(() => {
  const real = window.__TAURI__.core.invoke;
  window.__TAURI__.core.invoke = async (name, args) => {
    if (name === "inspect") return args.paths.map(path => ({ path, name: path.split("/").pop(), size: 3000, mime: "text/plain" }));
    if (name === "plugin:tauris-ui|pick_files") return ["/Users/m/Docs/Minutes.txt"];
    const result = await real(name, args);
    if (name === "plugin:tauris-ui|window_state") result.tabs = result.tabs.map(t => (t.ref ? t : { ...t, title: "Project A", kind: "project", ref: "project-a" }));
    return result;
  };
})();
"""


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail != "" and not ok else ""))
    if not ok:
        failures.append(name)


def fresh(browser, scheme="light"):
    page = browser.new_page(viewport={"width": 1100, "height": 720}, device_scale_factor=2, color_scheme=scheme, locale="en-GB")
    page.on("pageerror", lambda e: failures.append(f"page error: {e}") or print("PAGEERROR", e))
    page.add_init_script("window.__tabCount = 1")
    for script in scripts():
        page.add_init_script(script)
    page.add_init_script(RUST)
    page.goto(PAGE.as_uri())
    page.wait_for_selector(".tt-tab")
    page.wait_for_selector(".tv-row")
    page.wait_for_selector(".tf-file")
    return page


def shot(page, name):
    if SHOTS:
        page.screenshot(path=str(SHOTS / f"all_{name}.png"))


def texts(page, selector):
    return page.evaluate("s => [...document.querySelectorAll(s)].map(e => e.textContent.trim())", selector)


def menu(page):
    return page.evaluate("""[...document.querySelectorAll('.tmn-menu > *')].map(i => i.classList.contains('tmn-sep') ? '-' : i.querySelector('.tmn-label').textContent)""")


def active_title(page):
    return page.locator(".tt-tab.tt-active .tt-title").text_content()


def tree_names(page):
    return page.evaluate("[...document.querySelectorAll('.tv-row')].map(r => r.textContent.replace(/\\d+kb$/, '').trim())")


with sync_playwright() as p:
    browser = launch(p)

    # ---------- the first look ----------
    page = fresh(browser)
    check("the sidebar holds the tree: teams, projects and files, with their sizes",
          tree_names(page) == ["Team A", "Project A", "Hello.md", "Sup.txt", "Team B", "Megalomania", "readme.md", "Team C", "Vacation Mexico", "places to visit.md"]
          and page.evaluate("document.querySelector('#side').contains(document.querySelector('.tv-row'))")
          and page.locator(".tv-row:has-text('Hello.md')").text_content().endswith("45kb"), tree_names(page))
    page.wait_for_function("document.querySelector('#side .tsb-image img')?.naturalWidth > 0")
    check("the sidebar's head is the product: its logo and its name",
          page.get_attribute("#side .tsb-image img", "src") == "logo.svg" and page.inner_text("#side .tsb-title") == "All Components")
    check("the tab shows Project A: its files in the table, its project selected in the tree",
          active_title(page) == "Project A" and texts(page, ".tf-file .tf-name") == ["Hello.md", "Sup.txt"]
          and page.locator(".tv-row[aria-selected='true']").text_content().startswith("Project A"),
          (active_title(page), texts(page, ".tf-file")))
    check("the toolbar names the team of the shown project (pressed), the menu bar has File, View and Help",
          page.get_attribute("#toolbar .tmn-tool:has-text('Team A')", "aria-pressed") == "true"
          and page.get_attribute("#toolbar .tmn-tool:has-text('Team B')", "aria-pressed") == "false"
          and texts(page, ".tmn-title") == ["File", "View", "Help"], texts(page, ".tmn-title"))
    shot(page, "light")

    # ---------- the right click on a file ----------
    page.click(".tv-row:has-text('Hello.md')", button="right")
    page.wait_for_selector(".tmn-menu")
    check("a right click on a file: Open, Open in new tab, Edit…, Delete…", menu(page) == ["Open", "Open in new tab", "-", "Edit…", "Delete…"], menu(page))
    page.click(".tmn-item:has-text('Open in new tab')")
    page.wait_for_timeout(100)
    check("Open in new tab: a tab named after the file, showing it",
          page.locator(".tt-tab").count() == 2 and active_title(page) == "Hello.md" and page.is_visible("#doc")
          and not page.is_visible("#files") and "The first note" in page.text_content("#doc-text"), active_title(page))
    page.click(".tv-row:has-text('Sup.txt')", button="right")
    page.click(".tmn-item:has-text('Open')", position={"x": 20, "y": 8})
    page.wait_for_timeout(100)
    check("Open: the file replaces what this tab shows", page.locator(".tt-tab").count() == 2 and active_title(page) == "Sup.txt", active_title(page))
    page.click(".tv-row:has-text('Sup.txt')", button="right")
    page.click(".tmn-item:has-text('Edit')")
    page.wait_for_selector(".tdl")
    form = page.evaluate("[document.querySelector('.tdl-title').textContent, document.activeElement.value]")
    page.keyboard.type("Sup 2.txt")
    page.keyboard.press("Enter")
    review = page.evaluate("[...document.querySelectorAll('.tdl-review-rows tr')].map(r => r.textContent)")
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    check("Edit…: a form (the name selected), the change reviewed, then it does nothing but say so",
          form == ["Edit File", "Sup.txt"] and review == ["Name:Sup.txt → Sup 2.txt"] and page.text_content("#status") == "Edit does nothing in this example."
          and active_title(page) == "Sup.txt", (form, review, page.text_content("#status")))
    page.click(".tv-row:has-text('Sup.txt')", button="right")
    page.click(".tmn-item:has-text('Delete')")
    page.wait_for_selector(".tdl")
    asked = page.evaluate("[document.querySelector('.tdl-title').textContent, document.activeElement.textContent]")
    page.click(".tdl-danger")
    page.wait_for_timeout(50)
    check("Delete…: a question (on Cancel at first), then it does nothing but say so",
          asked == ["Delete “Sup.txt”?", "Cancel"] and page.text_content("#status") == "Delete does nothing in this example." and "Sup.txt" in tree_names(page), asked)
    page.click(".tv-row:has-text('Team B')", button="right")
    check("a team has no menu", page.locator(".tmn-menu").count() == 0)

    # ---------- the projects ----------
    shown = active_title(page)
    page.click(".tv-row:has-text('Vacation Mexico') .tv-label")
    page.wait_for_timeout(100)
    only_selected = (active_title(page) == shown, page.evaluate("document.querySelector('.tv-row[aria-selected=true]').textContent.startsWith('Vacation Mexico')"),
                     page.get_attribute(".tv-row:has-text('Vacation Mexico')", "aria-expanded"))
    check("a click on a project's name only selects it (as in a desktop outline): nothing opens, it stays as it was",
          only_selected == (True, True, "true"), only_selected)
    page.dblclick(".tv-row:has-text('Vacation Mexico') .tv-label")
    page.wait_for_timeout(100)
    check("a double click shows its files in this tab",
          active_title(page) == "Vacation Mexico" and texts(page, ".tf-file .tf-name") == ["places to visit.md"] and page.is_visible("#files"),
          (active_title(page), texts(page, ".tf-file .tf-name")))
    page.click("#toolbar .tmn-tool:has-text('Team B')")
    check("a team's toolbar button lists its projects", menu(page) == ["Megalomania"], menu(page))
    page.click(".tmn-item:has-text('Megalomania')")
    page.wait_for_timeout(100)
    check("choosing one shows it, and its team's button is the pressed one",
          active_title(page) == "Megalomania" and page.get_attribute("#toolbar .tmn-tool:has-text('Team B')", "aria-pressed") == "true"
          and page.get_attribute("#toolbar .tmn-tool:has-text('Team A')", "aria-pressed") == "false")
    page.click("#toolbar .tmn-tool:has-text('Home')")
    page.wait_for_timeout(100)
    check("Home shows the first project", active_title(page) == "Project A")

    # ---------- the table's own menu and actions ----------
    page.click(".tf-file:has-text('Hello.md')", button="right")
    page.wait_for_selector(".tmn-menu")
    check("the table's row menu: Open, Rename, Delete", menu(page) == ["Open", "Rename", "-", "Delete"] or menu(page) == ["Open", "Rename", "Delete"], menu(page))
    page.click(".tmn-item:has-text('Delete')")
    page.wait_for_timeout(100)
    page.get_by_role("button", name="Delete").last.click()
    page.wait_for_timeout(200)
    check("Delete in the table does nothing: the file stays, and it says so",
          texts(page, ".tf-file .tf-name") == ["Hello.md", "Sup.txt"] and "does nothing" in page.text_content("#status"),
          (texts(page, ".tf-file .tf-name"), page.text_content("#status")))

    # ---------- File > Add files… ----------
    page.click(".tmn-title:has-text('File')")
    check("File has Add files…", menu(page) == ["Add files…"], menu(page))
    page.click(".tmn-item:has-text('Add files')")
    page.wait_for_timeout(300)
    check("Add files… puts the picked file in the table and the tree",
          "Minutes.txt" in texts(page, ".tf-file .tf-name") and "Minutes.txt" in tree_names(page),
          (texts(page, ".tf-file .tf-name"), tree_names(page)))

    # ---------- View > Hide Sidebar ----------
    page.click(".tmn-title:has-text('View')")
    check("View: Hide Sidebar, Find…, Search Line", menu(page) == ["Hide Sidebar", "Find…", "Search Line"], menu(page))
    page.click(".tmn-item:has-text('Hide Sidebar')")
    page.wait_for_timeout(300)
    state = page.get_attribute("#side", "data-tsb-state")
    check("Hide Sidebar collapses it", state in ("rail", "hidden"), state)
    page.click(".tmn-title:has-text('View')")
    check("and the menu then says Show Sidebar", menu(page)[0] == "Show Sidebar", menu(page))
    page.click(".tmn-item:has-text('Show Sidebar')")
    page.wait_for_timeout(300)
    check("Show Sidebar opens it again", page.get_attribute("#side", "data-tsb-state") == "open", page.get_attribute("#side", "data-tsb-state"))
    page.close()

    # ---------- the search line ----------
    page = fresh(browser)
    page.click(".tm-cmd-input")
    page.keyboard.type("mexico")
    names = texts(page, "#hits tr td:nth-child(2)")
    check("typing “mexico” lists 1) Vacation Mexico and 2) places to visit.md",
          names == ["Vacation Mexico", "places to visit.md"] and texts(page, "#hits tr td:nth-child(1)") == ["1", "2"]
          and page.get_attribute("#matches", "data-tm-state") == "ok", (names, page.get_attribute("#matches", "data-tm-state")))
    shot(page, "search")
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    check("Enter opens the first, and the line and the list are empty again",
          active_title(page) == "Vacation Mexico" and page.locator("#hits tr").count() == 0 and page.input_value(".tm-cmd-input") == "",
          (active_title(page), page.locator("#hits tr").count()))
    page.keyboard.type("mexico")
    first = page.evaluate("[...document.querySelectorAll('#hits tr')].map(r => r.getAttribute('aria-selected'))")
    page.keyboard.press("ArrowDown")
    down = page.evaluate("[...document.querySelectorAll('#hits tr')].map(r => r.getAttribute('aria-selected'))")
    page.keyboard.press("ArrowDown")
    wrapped = page.evaluate("[...document.querySelectorAll('#hits tr')].map(r => r.getAttribute('aria-selected'))")
    page.keyboard.press("ArrowUp")
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    check("↑ and ↓ choose a match (the first is chosen at first, and they go round), Enter opens the one chosen",
          first == ["true", "false"] and down == ["false", "true"] and wrapped == ["true", "false"] and active_title(page) == "places to visit.md",
          (first, down, wrapped, active_title(page)))
    page.keyboard.type("mexico")
    page.click("#hits tr:nth-child(1)")
    page.wait_for_timeout(100)
    check("a click on a match opens it", active_title(page) == "Vacation Mexico", active_title(page))
    page.click(".tm-cmd-input")
    page.keyboard.type("mexico 2")
    check("a number after the name keeps the same list", texts(page, "#hits tr td:nth-child(2)") == ["Vacation Mexico", "places to visit.md"])
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    check("and Enter opens that one (in this tab)",
          active_title(page) == "places to visit.md" and page.locator(".tt-tab").count() == 1 and page.is_visible("#doc"), active_title(page))
    page.click(".tm-cmd-input")
    page.keyboard.type("mexico")
    page.evaluate("document.querySelector('.tm-cmd-input').select()")
    page.keyboard.type("1")
    check("a number alone does not search again", texts(page, "#hits tr td:nth-child(2)") == ["Vacation Mexico", "places to visit.md"])
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    check("and Enter opens that one", active_title(page) == "Vacation Mexico", active_title(page))
    page.click(".tm-cmd-input")
    shown = active_title(page)
    page.keyboard.type("zzz")
    check("nothing matching turns the band red and lists nothing",
          page.get_attribute("#matches", "data-tm-state") == "error" and page.locator("#hits tr").count() == 0, page.get_attribute("#matches", "data-tm-state"))
    page.keyboard.press("Enter")
    check("Enter on it says so and opens nothing", "Nothing to open" in page.text_content("#status") and active_title(page) == shown)
    page.keyboard.press("Escape")
    page.wait_for_timeout(50)
    check("Escape clears the line and the list", page.input_value(".tm-cmd-input") == "" and page.get_attribute("#matches", "data-tm-state") in (None, ""),
          page.get_attribute("#matches", "data-tm-state"))
    page.close()

    # ---------- the sheets ----------
    page = fresh(browser)
    page.click("body", position={"x": 600, "y": 300})
    page.keyboard.press("ControlOrMeta+/")
    page.wait_for_selector(".tdl-sheet")
    groups = page.evaluate("[...document.querySelectorAll('.tdl-shortcut-group h3')].map(h => h.textContent)")
    page.keyboard.press("Escape")
    page.click(".tmn-title:text-is('Help')")
    page.click(".tmn-item:has-text('About this example')")
    page.wait_for_selector(".tdl-about")
    name = page.inner_text(".tdl-about-name")
    page.keyboard.press("Enter")
    check("⌘/ shows the Keyboard Shortcuts; Help › About this example the About sheet",
          groups == ["Everywhere", "Tabs", "Lists"] and name == "All Components" and page.locator(".tdl").count() == 0, (groups, name))
    page.close()

    # ---------- find anything: ⌘K ----------
    page = fresh(browser)
    page.click("body", position={"x": 600, "y": 300})
    page.keyboard.press("ControlOrMeta+k")
    page.wait_for_selector(".tfd-input")
    page.keyboard.type("mexico")
    found = page.evaluate("[...document.querySelectorAll('.tfd-row .tfd-label')].map(r => r.textContent)")
    check("⌘K (Ctrl+K) opens the finder; “mexico” finds the project, and the file whose text says Mexico City",
          found[:1] == ["Vacation Mexico"] and "places to visit.md" in found, found)
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    check("Enter opens what was found, in this tab", active_title(page) == "Vacation Mexico" and page.locator(".tfd").count() == 0, active_title(page))
    page.keyboard.press("ControlOrMeta+k")
    page.keyboard.type("team b")
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    check("a team found shows in the tree", page.evaluate("document.querySelector('#tree [aria-selected=true]')?.dataset.key") == "team-b",
          page.evaluate("document.querySelector('#tree [aria-selected=true]')?.dataset.key"))
    page.close()

    # ---------- dark ----------
    page = fresh(browser, "dark")
    shot(page, "dark")
    page.wait_for_timeout(300)
    check("dark: the page and the toolbar follow the system",
          page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(47, 50, 52)"
          and page.evaluate("getComputedStyle(document.querySelector('#toolbar .tmn-tool[aria-pressed=true]')).backgroundColor") == "rgb(90, 94, 97)")
    page.close()

    browser.close()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
