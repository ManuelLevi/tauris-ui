// All seven components in one window: the tab strip (TaurisTabs), the menu bar
// and toolbar (TaurisMenu), a sidebar (TaurisSidebar) holding a tree
// (TaurisTree), the table of a project's files (TaurisFiles), a search line
// (TaurisTerminal) and find-anything with ⌘K (TaurisFinder). The data is
// data.js; nothing is saved but the tabs.

"use strict";

const $ = id => document.getElementById(id);
const invoke = (command, args) => window.__TAURI__.core.invoke(command, args);
const kb = bytes => `${Math.max(1, Math.round(bytes / KB))}kb`;
const count = n => `${n} file${n === 1 ? "" : "s"}`;

const status = $("status");
let sayTimer = 0;
function say(text) {
  status.textContent = text;
  clearTimeout(sayTimer);
  sayTimer = setTimeout(() => { status.textContent = ""; }, 4000);
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

// Shows `node` in this tab, or in a new one.
function open(node, { newTab = false } = {}) {
  if (node.kind === "team") return;
  const spec = { title: node.name, kind: node.kind, ref: node.id };
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
});

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

// A click on a project shows its files in this tab; Enter or a double click on a file opens it.
let syncing = false;
tree.on("select", ({ node }) => {
  const picked = node && nodes.get(String(node.id));
  if (!syncing && picked?.kind === "project") open(picked);
});
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
      { label: "Edit", action: () => say("Edit does nothing in this example.") },
      { label: "Delete", danger: true, action: () => say("Delete does nothing in this example.") });
  }
  return items;
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
  syncing = true;
  tree.select(node.id);
  syncing = false;
  for (const [team, button] of teamButtons) button.setAttribute("aria-pressed", String(team === node.team));
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
home.addEventListener("click", () => open(nodes.get(TEAMS[0].projects[0].id)));
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

TaurisMenu.bar($("menubar"), {
  menus: [
    { label: "File", items: () => [
      { label: "Add files…", action: () => filesView.add(), disabled: $("files").hidden },
    ] },
    { label: "View", items: () => [
      { label: side.collapsed ? "Show Sidebar" : "Hide Sidebar", shortcut: "⌃⌘S", action: () => side.toggle() },
      { label: "Find…", shortcut: "⌘K", action: () => finder.open() },
      { label: "Search Line", action: () => cmd.focus() },
    ] },
    { label: "Help", items: [
      { label: "About this example", action: () => say("Every tauris-ui component in one app. The projects and files are sample data.") },
    ] },
  ],
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
