// A stand-in for the Rust side, so the page script can be tested in a plain
// browser. Set window.__tabCount before it loads for more tabs, and
// window.__deny to make every command fail as a missing permission would.
(() => {
  let nextId = 0;
  const make = title => ({ id: ++nextId, title, view: null, query: "" });
  const count = window.__tabCount || 3;
  let tabs = Array.from({ length: count }, (_, i) => make(`Tab ${i + 1}`));
  let active = tabs[0].id;
  const listeners = {};
  window.__calls = [];
  const emit = (event, payload) => (listeners[event] || []).forEach(fn => fn({ payload }));
  const changed = () => emit("tauris-ui:state-changed", "tabs-1");
  const commands = {
    window_state: () => ({ label: "tabs-1", tabs: JSON.parse(JSON.stringify(tabs)), active }),
    new_tab: () => { const t = make(`Tab ${nextId + 1}`); tabs.push(t); active = t.id; changed(); return t.id; },
    open_tab: ({ title, fields }) => {
      const t = { ...make(title), ...fields };
      const at = tabs.findIndex(x => x.id === active) + 1;
      tabs.splice(at, 0, t); active = t.id; changed();
      return t.id;
    },
    close_tab: ({ tab }) => {
      const i = tabs.findIndex(t => t.id === tab);
      if (i < 0) return;
      tabs.splice(i, 1);
      if (active === tab && tabs.length) active = tabs[Math.min(i, tabs.length - 1)].id;
      changed();
    },
    activate_tab: ({ tab }) => { active = tab; },
    move_tab: ({ tab, index }) => {
      const i = tabs.findIndex(t => t.id === tab);
      const [t] = tabs.splice(i, 1);
      tabs.splice(index, 0, t);
      changed();
    },
    // Like Rust: the fields are replaced, not merged; id and title stay the tab's own.
    update_tab: ({ tab, title, fields }) => {
      const i = tabs.findIndex(x => x.id === tab);
      if (i < 0) return;
      const { id: _id, title: _title, ...rest } = fields;
      tabs[i] = { id: tab, title, ...rest };
    },
    report_strip: () => {},
    drag_out: () => {},
    set_close_guard: ({ on, seq }) => {
      if (seq >= (window.__guardSeq || 0)) { window.__guardSeq = seq; window.__guard = on; }
      (window.__guardCalls ||= []).push([on, seq]);
    },
    close_asked: () => { window.__closeAsked = (window.__closeAsked || 0) + 1; },
    close_window: () => { window.__windowClosed = (window.__windowClosed || 0) + 1; },
    move_to_new_window: ({ tab }) => {
      const i = tabs.findIndex(t => t.id === tab);
      if (i < 0 || tabs.length < 2) return;
      window.__movedOut = tabs.splice(i, 1)[0].title;
      if (active === tab) active = tabs[Math.min(i, tabs.length - 1)].id;
      changed();
    },
  };
  window.__TAURI__ = {
    core: {
      invoke: async (name, args) => {
        const command = name.replace("plugin:tauris-ui|", "");
        window.__calls.push([command, args]);
        if (window.__deny) throw `${name} not allowed. Plugin not found or not allowed by ACL`;
        const result = commands[command]?.(args);
        // window.__slow[command] = ms delays that command's answer (to test answers arriving out of order).
        const wait = window.__slow?.[command];
        if (wait) await new Promise(r => setTimeout(r, wait));
        return result;
      },
    },
    event: {
      listen: async (event, fn) => {
        (listeners[event] ||= []).push(fn);
        return () => { listeners[event] = listeners[event].filter(f => f !== fn); };
      },
    },
    webviewWindow: { getCurrentWebviewWindow: () => ({ label: "tabs-1" }) },
  };
  window.__titles = () => tabs.map(t => t.title);
  window.__emit = emit;
})();
