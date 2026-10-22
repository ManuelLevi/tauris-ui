// Types for drag to reorder (window.TaurisReorder). In a TypeScript app, copy
// this file into the app (for example src/reorder.d.ts).

declare global {
  interface TaurisReorderLabels {
    /** A key move at the top: text, or (id) => text. */
    first: string | ((id: string) => string);
    last: string | ((id: string) => string);
    /** The pointer over rows it cannot land among (another group's). */
    notHere: string;
    /** Said to a screen reader after a move: (place, count) => text. */
    moved: string | ((place: number, count: number) => string);
  }

  /** What a row's item moves among: its id (its first row's id) and its rows (a heading and the rows under it). */
  interface TaurisReorderItem {
    id: string | number;
    els: Element[];
  }

  interface TaurisReorderMove {
    id: string;
    /** Its place before and after, in its group. */
    from: number;
    to: number;
    how: "mouse" | "keyboard" | "menu";
  }

  interface TaurisReorderOptions {
    /** The rows that can be dragged (default "[data-id]"). */
    rows?: string;
    /** A row's id (default its data-id). */
    id?: (row: Element) => string | number | null | undefined;
    /** A row moves among the rows of its own group only (the open tasks, one project's KPIs). */
    group?: ((row: Element) => unknown) | null;
    /** What the row's item moves among, in the order shown, itself included (items of several rows). */
    items?: ((row: Element) => TaurisReorderItem[]) | null;
    /** A drag starts only here (a grip); default anywhere on the row but its controls (a control marked .tauris-drag starts one too: a name that opens on a click). */
    handle?: string | null;
    /** false: no drags and no keys (default true). */
    enabled?: boolean;
    /** ⌥⌘↑ and ⌥⌘↓ (Ctrl+Alt elsewhere) move the current row (default true). */
    keys?: boolean;
    /** The id the keys move (default: the row with the focus, else the one with aria-selected="true"). */
    current?: (() => string | number | null | undefined) | null;
    /** Whether a row may move: true, false, or why not ("Done tasks sort by the day they were done."). */
    movable?: ((id: string, row: Element) => boolean | string) | null;
    /** How far in the line starts, in px (rows under a heading). */
    indent?: number | ((row: Element) => number);
    labels?: Partial<TaurisReorderLabels>;
    /** false: the page brings its own stylesheet. */
    styles?: boolean;
    /** A drag began: hold `ids`, the order now, still until it ends (live changes must not move rows under the pointer). */
    onStart?: (id: string, ids: string[]) => void;
    /** The new order of the moved row's group: keep it, and draw the rows in it. */
    onMove?: (ids: string[], move: TaurisReorderMove) => void;
    /** Esc, a drop back where it was, or the window lost the focus. */
    onCancel?: (id: string) => void;
    /** A move refused: show the text (a status bar). */
    onRefuse?: (text: string) => void;
  }

  interface TaurisReorder {
    /** Changes options: enabled, keys, rows, id, group, items, handle, current, movable, indent, labels, the on… functions. */
    update(changes: Partial<TaurisReorderOptions>): void;
    /** Moves a row one place up (-1) or down (1), as the keys do (a menu's Move Up): true if it moved. */
    move(id: string | number, dir: -1 | 1): boolean;
    /** The id of the row being dragged, or null. */
    readonly dragging: string | null;
    /** Removes it; a drag under way ends where it began. */
    destroy(): void;
  }

  interface Window {
    TaurisReorder: {
      /** Drag to reorder the rows in `container`, the element that holds (and scrolls) them. */
      attach(container: HTMLElement, options?: TaurisReorderOptions): TaurisReorder;
      /** `list` in the order of `order` (ids); the ones not in it keep their order, after. */
      arrange<T>(list: T[], order: (string | number)[] | null | undefined, key?: (item: T) => string | number): T[];
      /** The keys that move a row, as a menu shows them ("⌥⌘↑", or "Ctrl+Alt+↑"). */
      readonly keys: { up: string; down: string };
    };
  }

  const TaurisReorder: Window["TaurisReorder"];
}

export {};
