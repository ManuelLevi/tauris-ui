// Types for the collapsible sidebar (window.TaurisSidebar). In a TypeScript
// app, copy this file into the app (for example src/sidebar.d.ts).

declare global {
  interface TaurisSidebarItem {
    /** Unique among the items. */
    id: string | number;
    label: string;
    /** Text (an emoji, a letter) or markup starting with "<" (an svg). None: its first letter stands for it in the rail. */
    icon?: string | null;
    /** A number or short text on its right (a dot in the rail); 0, null or "" shows none. */
    count?: number | string | null;
    /** A group: its items, shown below it when it is open. */
    children?: TaurisSidebarEntry[];
    /** A group that starts open. */
    expanded?: boolean;
    /** Shown, but not chosen and not reached by the keys. */
    disabled?: boolean;
    /** A tooltip when it is open (in the rail the label is the tooltip). */
    title?: string;
  }

  /** A heading between sections (a line in the rail). */
  interface TaurisSidebarHeading {
    heading: string;
  }

  type TaurisSidebarEntry = TaurisSidebarItem | TaurisSidebarHeading;

  interface TaurisSidebarLabels {
    /** The list's name for screen readers, when there is no title. */
    label: string;
    hide: string;
    show: string;
    /** The edge's name for screen readers. */
    resize: string;
  }

  interface TaurisSidebarOptions {
    items?: TaurisSidebarEntry[];
    /** The id of the selected item, or null. */
    selected?: string | number | null;
    /** Collapsed at first (storageKey, when it has one, says instead). */
    collapsed?: boolean;
    /** "rail" (default): a column of icons. "hide": nothing (the app shows it again with toggle() or the shortcut). */
    collapse?: "rail" | "hide";
    /** The side of the window it is on (default "left"). */
    side?: "left" | "right";
    /** Its width open, and the narrowest and widest its edge drags it to (default 220, 160, 420). */
    width?: number;
    minWidth?: number;
    maxWidth?: number;
    /** A heading at its top, beside the button; also the list's name. */
    title?: string;
    /** An element of the app's shown below the items (a tree view): it fills the rest of the height and scrolls, while the sidebar is open. */
    content?: HTMLElement | null;
    /** ⌃⌘S on a Mac, Ctrl+Shift+B elsewhere, collapses and opens it (default true). */
    shortcut?: boolean;
    /** How long after a key the next one still adds to the label being typed (default 700). */
    typeAheadMs?: number;
    /** Keeps its width and whether it is collapsed in the browser's storage under this key. */
    storageKey?: string | null;
    /** false: the page brings its own stylesheet. */
    styles?: boolean;
    labels?: Partial<TaurisSidebarLabels>;
    /** Choosing a group opens it too (otherwise its arrow, a double-click or Right does). */
    openOnSelect?: boolean;
    /** The person chose an item (not called by select()). */
    onSelect?: (item: TaurisSidebarItem, info: { how: "mouse" | "keyboard" }) => void;
    /** A right click on an item, or the menu key on it: where to open the app's own menu. Given, the browser's menu does not open. */
    onContextMenu?: (item: TaurisSidebarItem, at: { x: number; y: number; how: "mouse" | "keyboard" }) => void;
    onToggle?: (info: { collapsed: boolean; how: "button" | "shortcut" | "edge" | "api" }) => void;
    /** The person changed its width (by its edge, from the mouse or the keys). */
    onResize?: (info: { width: number }) => void;
  }

  interface TaurisSidebar {
    /** Replaces the items (the focus stays on the item of the same id; open groups stay open). */
    setItems(items: TaurisSidebarEntry[]): void;
    /** Selects an item (null: none); the groups around it open. onSelect is not called. */
    select(id: string | number | null): void;
    /** The selected item, or null. */
    selected(): TaurisSidebarItem | null;
    /** The element below the items that holds `content`, for the app's own part. */
    readonly body: HTMLElement;
    /** Shows the body after the app filled it (or emptied it). */
    refresh(): void;
    /** Collapses it (true), opens it (false), or switches (no argument). */
    toggle(collapsed?: boolean): void;
    readonly collapsed: boolean;
    /** Its width when open, in pixels. */
    readonly width: number;
    setWidth(width: number): void;
    /** Changes options: items, selected, title, labels, the on… functions, collapse, side, widths. */
    update(changes: Partial<TaurisSidebarOptions>): void;
    /** Puts the keyboard focus on the item Tab reaches. */
    focus(): void;
    /** Removes it and its listeners; mount can then be called again on the element. */
    destroy(): void;
  }

  interface Window {
    TaurisSidebar: {
      mount(element: HTMLElement, options?: TaurisSidebarOptions): TaurisSidebar;
    };
  }

  const TaurisSidebar: Window["TaurisSidebar"];
}

export {};
