// All twelve components in one window: the tab strip (TaurisTabs), the menu
// bar and the toolbar with Back, Forward and Find (TaurisMenu), a sidebar
// (TaurisSidebar) holding a tree (TaurisTree), the table of a project's files
// (TaurisFiles), a search line (TaurisTerminal), find-anything with ⌘K
// (TaurisFinder), the dialogs (TaurisDialog: Edit in a window of its own,
// Delete, Keyboard Shortcuts, About), Home: the projects in a table
// (TaurisTable) in an order dragged into place (TaurisReorder), with their
// activity, status and the files' capacity bar (TaurisGlance), and the status
// bar (TaurisStatus). The data is data.js; nothing is saved but the tabs.

"use strict";

// One of the app's dialog windows (Edit… opens in one): the dialog draws itself there,
// and this example has no field types of its own to define. Everywhere else, the app.
if (!TaurisDialog.inWindow) main();

function main() {

  const $ = id => document.getElementById(id);
  const invoke = (command, args) => window.__TAURI__.core.invoke(command, args);
  const kb = bytes => `${Math.max(1, Math.round(bytes / KB))}kb`;
  const count = n => `${n} file${n === 1 ? "" : "s"}`;

  // The status bar: the last message (an Undo after a move), the files against the plan, the sidebar.
  const statusBar = TaurisStatus.mount($("status"), { timeout: 6000 });
  function say(text, options) {
    statusBar.say(text, typeof options === "string" ? { kind: options } : options ?? {});
  }
  function paintStatus() {
    const n = TEAMS.flatMap(t => t.projects).reduce((a, p) => a + p.files.length, 0);
    statusBar.update({ segments: [
      { id: "files", text: `${n} / ${MAX_FILES} files`, strong: n >= MAX_FILES, title: `${n} files, of the plan's ${MAX_FILES}` },
      { id: "sidebar", text: `Sidebar: ${side.collapsed ? "Hidden" : "Shown"}`, pressed: !side.collapsed, title: "Show or hide the sidebar (⌃⌘S)", onClick: () => side.toggle() },
    ] });
  }

  // ---------- the data, by id ----------

  // Every team, project and file: { kind, id, name, team, project?, file?, path }.
  const nodes = new Map();
  function addFile(team, project, file) {
    nodes.set(file.id, { kind: "file", id: file.id, name: file.name, team, project, file, path: `${team.name} / ${project.name} / ${file.name}` });
  }
  for (const team of TEAMS) {
    nodes.set(team.id, { kind: "team", id: team.id, name: team.name, team, path: team.name });
    for (const project of team.projects) {
      nodes.set(project.id, { kind: "project", id: project.id, name: project.name, team, project, path: `${team.name} / ${project.name}` });
      for (const file of project.files) addFile(team, project, file);
    }
  }

  // ---------- the tabs: each one shows a project or a file ----------

  const tabs = TaurisTabs.mount($("strip"), { panelId: "work" });

  // Shows `node` in this tab, or in a new one (Home: { kind: "home" }).
  function open(node, { newTab = false } = {}) {
    if (node.kind === "team") return;
    const spec = node.kind === "home" ? { title: "Home", kind: "home", ref: "home" } : { title: node.name, kind: node.kind, ref: node.id };
    const tab = tabs.activeTab();
    if (newTab || !tab) tabs.open(spec);
    else tabs.update(tab, spec);
  }

  // ---------- the sidebar, with the tree in it ----------

  // The sidebar's head is the product: its logo and name. Its content is the
  // tree's element: it fills what is left under the head.
  const treeHost = document.createElement("div");
  treeHost.id = "tree";
  const side = TaurisSidebar.mount($("side"), {
    title: "All Components", image: "logo.svg", width: 280, storageKey: "all-components-sidebar", content: treeHost,
    onToggle: () => paintStatus(),
  });
  paintStatus();

  function treeData() {
    const open = id => (tree ? tree.isExpanded(id) : true);
    return TEAMS.map(team => ({
      id: team.id, label: team.name, expanded: open(team.id),
      children: team.projects.map(project => ({
        id: project.id, label: project.name, expanded: open(project.id),
        children: project.files.map(file => ({ id: file.id, label: file.name, values: { size: kb(file.size) } })),
      })),
    }));
  }

  let tree = null;
  tree = TaurisTree.mount(treeHost, {
    label: "Projects",
    columns: [{ label: "Name", width: 170 }, { label: "Size", key: "size", width: 60, align: "right" }],
    data: treeData(),
  });

  // As in a desktop outline: a click selects; Enter or a double click opens a project (its files) or a file.
  tree.on("activate", ({ node }) => {
    const picked = nodes.get(String(node.id));
    if (picked) open(picked);
  });

  // The tree leaves the right click to the app.
  treeHost.addEventListener("contextmenu", e => {
    const row = e.target instanceof Element ? e.target.closest(".tv-row") : null;
    if (!row) return;
    e.preventDefault();
    const node = nodes.get(row.dataset.key);
    if (!node || node.kind === "team") return;
    const box = row.getBoundingClientRect();
    const at = e.clientX || e.clientY ? { x: e.clientX, y: e.clientY } : { x: box.left + 24, y: box.bottom };
    TaurisMenu.open(menuFor(node), at, { label: node.name, returnTo: row });
  });

  // What can be done to a project or a file, wherever it is shown (the tree, the finder).
  function menuFor(node) {
    const items = [
      { label: "Open", action: () => open(node) },
      { label: "Open in new tab", action: () => open(node, { newTab: true }) },
    ];
    if (node.kind === "file") {
      items.push("-",
        { label: "Edit…", action: () => editFile(node) },
        { label: "Delete…", danger: true, action: () => deleteFile(node) });
    }
    return items;
  }

  // Edit and Delete ask, as an app would, then do nothing (the data is read-only).
  async function editFile(node) {
    const values = await TaurisDialog.form({
      // In a window of its own, attached to this one (in the page where there is no plugin).
      window: true,
      title: "Edit File", ok: "Save",
      fields: [{ name: "name", label: "Name", value: node.name, required: true }, { name: "by", label: "Added by", value: node.file.by }],
      review: v => [["Name", node.name, v.name], ["Added by", node.file.by, v.by]].filter(([, a, b]) => a !== b).map(([field, before, after]) => ({ field, before, after })),
    });
    if (values) say("Edit does nothing in this example.");
  }
  // The delete runs inside the question: refused, the question stays with the reason on its line.
  async function deleteFile(node) {
    await TaurisDialog.confirm({
      title: `Delete “${node.name}”?`, message: "This cannot be undone.", ok: "Delete", danger: true,
      run: () => { throw new Error("Deleting does nothing in this example."); },
    });
  }

  // ---------- the files table ----------

  const rows = project => project.files.map(f => ({ id: f.id, name: f.name, size: f.size, added: f.added, by: f.by }));

  const filesView = TaurisFiles.mount($("files"), {
    dropArea: "element",
    onOpen: file => open(nodes.get(file.id)),
    onRename: () => Promise.reject("Renaming does nothing in this example."),
    onDelete: () => Promise.reject("Deleting does nothing in this example."),
    onMessage: say,
  });

  // The table shows one project: its own list, and where "Add files…" puts a new file.
  function showProject(project, team) {
    filesView.update({
      title: project.name,
      place: project.name,
      subtitle: team.name,
      color: project.color,
      files: rows(project),
      onAdd: async paths => {
        const infos = await invoke("inspect", { paths });
        const taken = infos.find(info => project.files.some(f => f.name === info.name));
        if (taken) throw `${taken.name} is already in ${project.name}.`;
        const added = infos.map(info => ({ id: `${project.id}/${info.name}`, name: info.name, size: info.size, added: new Date(), by: "You", text: "" }));
        for (const file of added) {
          project.files.push(file);
          addFile(team, project, file);
        }
        tree.setData(treeData());
        return rows({ files: added });
      },
    });
  }

  // ---------- what the active tab shows ----------

  const teamButtons = new Map();

  function render() {
    const tab = tabs.activeTab();
    const atHome = tab?.kind === "home";
    $("home").hidden = !atHome;
    if (atHome) {
      $("files").hidden = true;
      $("doc").hidden = true;
      drawHome();
      for (const button of teamButtons.values()) button.setAttribute("aria-pressed", "false");
      home.setAttribute("aria-pressed", "true");
      visited("home");
      return;
    }
    home.setAttribute("aria-pressed", "false");
    const node = tab && nodes.get(String(tab.ref));
    if (!node || node.kind === "team") return;
    const isFile = node.kind === "file";
    $("files").hidden = isFile;
    $("doc").hidden = !isFile;
    if (isFile) {
      $("doc-title").textContent = node.name;
      $("doc-meta").textContent = `${node.path} · ${kb(node.file.size)} · added ${node.file.added} by ${node.file.by}`;
      $("doc-text").textContent = node.file.text || "(No preview: the file was added from this computer.)";
    } else {
      showProject(node.project, node.team);
    }
    tree.select(node.id);
    for (const [team, button] of teamButtons) button.setAttribute("aria-pressed", String(team === node.team));
    visited(node.id);
  }
  tabs.on("change", render);

  // ---------- the toolbar and the menu bar ----------

  const ICONS = {
    home: "<svg viewBox='0 0 16 16' aria-hidden='true'><path d='M1.8 7.6 8 2l6.2 5.6M3.4 6.6v7h9.2v-7'/></svg>",
    team: "<svg viewBox='0 0 16 16' aria-hidden='true'><circle cx='6' cy='5' r='2.4'/><path d='M1.6 13.4c0-2.6 2-4 4.4-4s4.4 1.4 4.4 4M10.6 7.4a2.2 2.2 0 1 0 0-4.4M12 9.6c1.6.4 2.6 1.6 2.6 3.8'/></svg>",
  };

  function tool(label, icon) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tmn-tool";
    button.insertAdjacentHTML("afterbegin", icon);
    button.append(label);
    $("toolbar").append(button);
    return button;
  }

  const home = tool("Home", ICONS.home);
  home.addEventListener("click", () => open({ kind: "home" }));
  const separator = document.createElement("span");
  separator.className = "tmn-tool-sep";
  $("toolbar").append(separator);
  for (const team of TEAMS) {
    const button = tool(team.name, ICONS.team);
    teamButtons.set(team, button);
    TaurisMenu.button(button, {
      items: () => team.projects.map(project => ({ label: project.name, color: project.color, shortcut: String(project.files.length), action: () => open(nodes.get(project.id)) })),
    });
  }

  // The toolbar: one stop for Tab, ← → between its buttons; Back and Forward through the
  // views this tab has shown (⌘[ ⌘]); Find anything (⌘K) at its end.
  const views = { list: [], at: -1, stepping: false };
  const toolbar = TaurisMenu.toolbar($("toolbar"), {
    back: () => step(-1),
    forward: () => step(1),
    find: { label: "Find anything", shortcut: "⌘K", onClick: () => finder.open() },
  });
  function visited(key) {
    if (views.stepping) views.stepping = false;
    else if (views.list[views.at] !== key) {
      views.list = views.list.slice(0, views.at + 1).concat(key);
      views.at = views.list.length - 1;
    }
    toolbar.setHistory({ back: views.at > 0, forward: views.at < views.list.length - 1 });
  }
  function step(dir) {
    const at = views.at + dir;
    if (at < 0 || at >= views.list.length) return;
    views.at = at;
    views.stepping = true;
    const key = views.list[at];
    open(key === "home" ? { kind: "home" } : nodes.get(key));
  }

  TaurisMenu.bar($("menubar"), {
    menus: [
      { label: "File", items: () => [
        { label: "Add files…", action: () => filesView.add(), disabled: $("files").hidden },
      ] },
      { label: "View", items: () => [
        { label: "Back", shortcut: toolbar.keys.back, disabled: views.at <= 0, action: () => step(-1) },
        { label: "Forward", shortcut: toolbar.keys.forward, disabled: views.at >= views.list.length - 1, action: () => step(1) },
        "-",
        { label: side.collapsed ? "Show Sidebar" : "Hide Sidebar", shortcut: "⌃⌘S", action: () => side.toggle() },
        { label: "Find…", shortcut: "⌘K", action: () => finder.open() },
        { label: "Search Line", action: () => cmd.focus() },
      ] },
      { label: "Help", items: [
        { label: "Keyboard Shortcuts", shortcut: "⌘/", action: showShortcuts },
        "-",
        { label: "About this example", action: () => TaurisDialog.about({ name: "All Components", mark: "🧩",
          description: "Every tauris-ui component in one app. The projects and files are sample data.",
          rows: [["tauris-ui", window.TaurisTabs?.version ?? "?"], ["Teams", String(TEAMS.length)]] }) },
      ] },
    ],
  });

  // ---------- Home: the projects, in the person's order ----------

  // Home's rows: a project and its team, in the order the person puts them in (by dragging, or ⌥⌘↑ ⌥⌘↓).
  const PROJECTS = TEAMS.flatMap(team => team.projects.map(project => ({ id: project.id, project, team })));
  let homeOrder = PROJECTS.map(p => p.id);
  let held = null; // the order held still while a row is dragged

  // Growing or slowing, by the last three weeks against the three before.
  function trendOf(activity) {
    const sum = list => list.reduce((a, b) => a + b, 0);
    return sum(activity.slice(-3)) >= sum(activity.slice(-6, -3)) ? { kind: "ok", word: "Growing" } : { kind: "warn", word: "Slowing" };
  }

  const OPEN_ICON = "<svg viewBox='0 0 16 16'><path d='M6.5 3H3v10h10V9.5M9.5 3H13v3.5M13 3 7.5 8.5'/></svg>";
  const homeTable = TaurisTable.mount($("home-table"), {
    label: "Projects",
    columns: [
      { key: "name", label: "Project", text: p => p.project.name, value: p => p.project.name,
        render: p => {
          const name = document.createElement("span");
          const dot = document.createElement("span");
          dot.className = "dot";
          dot.style.background = p.project.color;
          name.append(dot, p.project.name);
          return name;
        } },
      { key: "team", label: "Team", width: 90, text: p => p.team.name, value: p => p.team.name },
      { key: "files", label: "Files", width: 64, align: "right", text: p => String(p.project.files.length), value: p => p.project.files.length },
      { key: "activity", label: "Activity", width: 92, sortable: false,
        render: p => TaurisGlance.sparkline(p.project.activity, { label: `${p.project.name}: edits a week, the last six weeks`, color: p.project.color }) },
      { key: "status", label: "Status", width: 100, value: p => trendOf(p.project.activity).word,
        render: p => { const t = trendOf(p.project.activity); return TaurisGlance.status(t.kind, t.word); } },
      { label: "Actions", actions: [
        { id: "open", icon: OPEN_ICON, title: "Open", onClick: p => open(nodes.get(p.id)) },
        { id: "copy", icon: "⧉", title: "Copy Name", copy: p => p.project.name },
      ] },
    ],
    onOpen: (p, { cmd }) => open(nodes.get(p.id), { newTab: cmd }),
    onContextMenu: (p, at) => { if (p) TaurisMenu.open(homeMenu(p.id), at, { label: p.project.name }); },
    // Sorted by a column, the rows are not in the person's order: moving them waits for Manual Order.
    onSort: sort => {
      homeReorder.update({ enabled: !sort });
      if (sort) say("Sorted. A project's menu has Manual Order, to move rows again.");
    },
    onMessage: (text, kind) => say(text, { kind }),
  });

  function drawHome() {
    const files = PROJECTS.flatMap(({ project }) => project.files.map(file => ({ title: `${file.name} · ${project.name}`, color: project.color })));
    $("home-head").replaceChildren($("home-title"), TaurisGlance.capacity({ label: "Files", max: MAX_FILES, items: files }));
    homeTable.setRows(TaurisReorder.arrange(PROJECTS, held ?? homeOrder));
  }

  function homeMenu(id) {
    const at = homeOrder.indexOf(id);
    const manual = !homeTable.sort;
    const why = manual ? undefined : "sorted";
    return [
      ...menuFor(nodes.get(id)),
      "-",
      { label: "Move Up", shortcut: TaurisReorder.keys.up, disabled: !manual || at === 0, reason: why, action: () => { if (homeReorder.move(id, -1)) homeTable.flash(id); } },
      { label: "Move Down", shortcut: TaurisReorder.keys.down, disabled: !manual || at === homeOrder.length - 1, reason: why, action: () => { if (homeReorder.move(id, 1)) homeTable.flash(id); } },
      { label: "Manual Order", disabled: manual, action: () => { homeTable.update({ sort: null }); homeReorder.update({ enabled: true }); } },
    ];
  }

  const homeReorder = TaurisReorder.attach(homeTable.scroller, {
    rows: ".ttb-row",
    onStart: (id, ids) => { held = ids; },
    onMove: (ids, { id, to }) => {
      const was = homeOrder;
      homeOrder = ids;
      held = null;
      drawHome();
      homeTable.select(id);
      say(`${nodes.get(id).name} is now ${to + 1} of ${ids.length}.`, { undo: () => { homeOrder = was; drawHome(); homeTable.select(id); } });
    },
    onCancel: () => { held = null; drawHome(); },
    onRefuse: text => say(text),
  });

  // ---------- the search line ----------

  TaurisTerminal.mount($("term"));
  const pane = TaurisTerminal.pane($("matches"));
  let hits = [];
  let chosen = -1; // the match ↑ and ↓ are on (Enter opens it)
  const SHOWN = 8;

  // ↑ and ↓ go through the matches while there are some (the line's history otherwise).
  function arrow(e) {
    const n = Math.min(hits.length, SHOWN);
    if (!n || e.altKey || e.ctrlKey || e.metaKey || (e.key !== "ArrowDown" && e.key !== "ArrowUp")) return false;
    chosen = (chosen + (e.key === "ArrowDown" ? 1 : -1) + n) % n;
    showHits();
    return true;
  }
  const cmd = TaurisTerminal.commandLine($("cmd"), { prompt: "SEARCH>", label: "Search", onSubmit: submit, onKey: arrow });

  function cell(tr, text, className) {
    const td = document.createElement("td");
    td.textContent = text;
    if (className) td.className = className;
    tr.append(td);
  }

  function showHits() {
    $("hits").replaceChildren(...hits.slice(0, SHOWN).map((node, i) => {
      const tr = document.createElement("tr");
      tr.setAttribute("aria-selected", String(i === chosen));
      // A click opens it too.
      tr.addEventListener("click", () => { chosen = i; submit(cmd.value || node.name); });
      cell(tr, String(i + 1), "tm-num");
      cell(tr, node.name, "tm-value");
      cell(tr, node.kind === "project" ? node.team.name : `${node.team.name} / ${node.project.name}`, "tm-dim");
      cell(tr, node.kind === "project" ? count(node.project.files.length) : kb(node.file.size), "tm-num");
      return tr;
    }));
  }

  // A line is a name, a name and a number ("mexico 2": the second match), or a number alone (from the list shown).
  function parse(typed) {
    const line = typed.trim().toLowerCase();
    const alone = /^\d+$/.test(line);
    const ended = /^(.*\S)\s+(\d+)$/.exec(line);
    return { query: alone ? null : ended ? ended[1] : line, pick: alone ? Number(line) : ended ? Number(ended[2]) : null };
  }

  // What is typed matches a project or a file by its place and name: "mexico" finds the project and its file.
  function search(typed) {
    const { query } = parse(typed);
    if (query === null) return;
    hits = query ? [...nodes.values()].filter(n => n.kind !== "team" && n.path.toLowerCase().includes(query)) : [];
    chosen = hits.length ? 0 : -1; // Enter opens the first, until ↑ or ↓ choose another
    showHits();
    if (!query) pane.reset();
    else if (hits.length) pane.ok();
    else pane.error();
  }

  function submit(line) {
    // A number typed picks that match; otherwise the one ↑ and ↓ are on.
    const { pick } = parse(line);
    const picked = hits[pick != null ? pick - 1 : chosen];
    if (!picked) {
      pane.error();
      say(`Nothing to open for “${line.trim()}”.`);
      return;
    }
    open(picked);
    cmd.clear();
    search("");
  }

  // The library gives Enter (onSubmit); the app listens to the typing itself.
  $("cmd").addEventListener("input", () => search(cmd.value));
  $("cmd").addEventListener("keydown", e => { if (e.key === "Escape") setTimeout(() => search(cmd.value), 0); });

  function showShortcuts() {
    TaurisDialog.shortcuts({ groups: [
      { title: "Everywhere", items: [{ label: "Find anything", keys: ["⌘K"] }, { label: "Show or hide the sidebar", keys: ["⌃⌘S"] }, { label: "Keyboard Shortcuts", keys: ["⌘/"] }] },
      { title: "Tabs", items: [{ label: "New tab", keys: ["⌘T"] }, { label: "Close tab", keys: ["⌘W"] }, { label: "Next or previous tab", keys: ["⌃Tab", "⌃⇧Tab"], either: true }] },
      { title: "Lists", items: [{ label: "Open", keys: ["↩"] }, { label: "Rename", keys: ["F2"] }, { label: "Its menu", keys: ["⇧F10"] },
        { label: "Move a project up or down (Home)", keys: [TaurisReorder.keys.up, TaurisReorder.keys.down], either: true }] },
    ] });
  }
  document.addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key === "/" && !TaurisDialog.isOpen) {
      e.preventDefault();
      showShortcuts();
    }
  });

  // ---------- find anything: ⌘K (the finder's own shortcut) ----------

  const finder = TaurisFinder.mount({
    // Every team, project and file; a file's text is searched too.
    items: () => [...nodes.values()].map(n => ({
      id: n.id,
      kind: n.kind,
      label: n.name,
      detail: n.kind === "file" ? `${n.team.name} / ${n.project.name} · ${kb(n.file.size)}`
        : n.kind === "project" ? `${n.team.name} · ${count(n.project.files.length)}` : `${n.team.projects.length} projects`,
      more: n.kind === "file" ? [n.file.text] : [],
      color: n.project?.color,
      when: n.file?.added,
    })),
    kinds: [{ id: "project", label: "Projects", bias: 40 }, { id: "file", label: "Files" }, { id: "team", label: "Teams" }],
    storageKey: "all-components-finder",
    onPick: item => {
      const node = nodes.get(item.id);
      // A team shows in the tree; a project or a file opens.
      if (node.kind === "team") {
        side.toggle(false);
        tree.select(node.id);
      } else {
        open(node);
      }
    },
    onContextMenu: (item, at) => {
      const node = nodes.get(item.id);
      if (node.kind !== "team") TaurisMenu.open(menuFor(node), at, { label: node.name });
    },
  });
}
