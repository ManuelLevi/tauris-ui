// Types for the tree view (window.TaurisTree). In a TypeScript app, copy this
// file into the app (for example src/tree.d.ts); scripts/doctor.py says when
// the copy is out of date. Give your own values as a type parameter:
//   const tree = TaurisTree.mount<{ value: string | number | boolean }>(el, { data, columns });

declare global {
  /** How a value cell is edited in place. A plain string is the type alone. */
  type TaurisTreeEditor =
    | "text" | "number" | "checkbox" | "select" | "color"
    | { type: "text" }
    | { type: "number"; min?: number; max?: number; step?: number }
    | { type: "checkbox" }
    | { type: "select"; options: Array<string | number | { value: unknown; label?: string }> }
    | { type: "color" };

  /** A node of the tree. `values` fills the columns after the first, by key. */
  interface TaurisTreeNode<V extends object = Record<string, unknown>> {
    id: string | number;
    label: string;
    children?: TaurisTreeNode<V>[];
    /** folder, file, code, doc, data, image, package, lock, or a name from `icons`. */
    icon?: string;
    values?: Partial<V>;
    /** One editor for every value it fits, or one per column, by key. */
    editor?: TaurisTreeEditor | { [K in keyof V & string]?: TaurisTreeEditor };
    readOnly?: boolean;
    /** Open when the node first comes (in mount or setData); after that the person opens and closes it. */
    expanded?: boolean;
  }

  interface TaurisTreeColumn<V extends object = Record<string, unknown>> {
    label: string;
    width?: number;
    /** Which entry of `node.values` the column shows; the first column holds the tree. */
    key?: keyof V & string;
    minWidth?: number;
    editable?: boolean;
    /** How this column's values are edited (a node's own editor comes first). */
    editor?: TaurisTreeEditor;
    align?: "left" | "right" | "center";
    className?: string;
    /** false: a click on this header never sorts (when the tree sorts). */
    sortable?: boolean;
    /** What the column sorts by, instead of the value shown (e.g. an ISO date behind "21 Oct 2026").
     * A number, a string, a Date or a boolean; null, undefined and "" are empty and go last. */
    sortValue?: (node: TaurisTreeNode<V>) => unknown;
    /** A whole comparison instead (A to Z order; the tree turns it round for Z to A). */
    compare?: (a: TaurisTreeNode<V>, b: TaurisTreeNode<V>) => number;
  }

  /** An order: a column's key ("label" for the first column unless it has a key), up: true for A to Z. */
  interface TaurisTreeSort {
    key: string;
    up: boolean;
  }

  interface TaurisTreeOptions<V extends object = Record<string, unknown>> {
    data?: TaurisTreeNode<V>[];
    /** null for a plain tree; the first column holds the tree, the last one stretches. */
    columns?: TaurisTreeColumn<V>[] | null;
    /** The tree's accessible name. */
    label?: string;
    /** Dotted connector lines (false: +/- boxes only). */
    lines?: boolean;
    /** In a table (columns), rows that only group others in a band of their own, their names bold (default false: every row alike). */
    bandGroups?: boolean;
    /** More icons by name, as svg markup. */
    icons?: Record<string, string>;
    /** Rows drawn above and below the visible ones. */
    overscan?: number;
    /** A click on a column header sorts by it, a second click turns it round. Default: on when `sort` is given. */
    sortable?: boolean | null;
    /** The first order (and sortable headers). Default: the data's own order. */
    sort?: { key: string; up?: boolean } | null;
    /** ⌘-click (Ctrl-click) and Shift-click select several rows; ⌘A selects every row shown. Default false. */
    multiple?: boolean;
    /** Add the stylesheet (false: bring your own). */
    styles?: boolean;
  }

  interface TaurisTreeEvents<V extends object = Record<string, unknown>> {
    /** node: the selected row with the focus; nodes: every selected row, top to bottom. */
    select: { node: TaurisTreeNode<V> | null; nodes: TaurisTreeNode<V>[] };
    toggle: { node: TaurisTreeNode<V>; expanded: boolean };
    /** An edited value, already written into node.values. */
    change: { node: TaurisTreeNode<V>; column: keyof V & string; value: unknown };
    /** Enter or double-click on a row. */
    activate: { node: TaurisTreeNode<V> };
    /** The order changed (a header, or sort()); null is the data's own order. */
    sort: TaurisTreeSort | null;
    /** The person made a column wider or narrower (its edge dragged, or the keys). Keep `widths` to give them back. */
    resize: { column: string | null; index: number; width: number; widths: number[] };
  }

  interface TaurisTreeView<V extends object = Record<string, unknown>> {
    /** Replaces every node; open rows and the selection are kept where their ids still exist. */
    setData(nodes: TaurisTreeNode<V>[]): void;
    expand(id: string | number): void;
    collapse(id: string | number): void;
    toggle(id: string | number): void;
    expandAll(): void;
    collapseAll(): void;
    /** Selects a row, opening its parents; null clears the selection. An array selects several (with `multiple`). */
    select(id: string | number | Array<string | number> | null): void;
    /** The selected row with the focus, or null. */
    selected(): TaurisTreeNode<V> | null;
    /** Every selected row, top to bottom. */
    selection(): TaurisTreeNode<V>[];
    /** Selects every row shown (with `multiple`). */
    selectAll(): void;
    get(id: string | number): TaurisTreeNode<V> | null;
    isExpanded(id: string | number): boolean;
    /** Opens a cell's editor (the first editable column by default; a true/false value's box takes the focus); false if it cannot. */
    edit(id: string | number, column?: keyof V & string): boolean;
    focus(): void;
    /** Every column's width in pixels, as the person left them. */
    widths(): number[];
    /** Sets the columns' widths (pixels, in column order; null keeps one as it is). */
    setWidths(widths: (number | null)[]): void;
    /** Sorts by a column (up: true for A to Z); null goes back to the data's own order. In the order already in place it
     * sorts again (rows edited since move). False for a column that cannot sort. */
    sort(key: string | null, up?: boolean): boolean;
    /** The order now, or null for the data's own order. */
    sorting(): TaurisTreeSort | null;
    /** Returns a function that stops listening. */
    on<K extends keyof TaurisTreeEvents<V>>(event: K, fn: (payload: TaurisTreeEvents<V>[K]) => void): () => void;
    /** Removes the tree and every listener (a value being typed is kept first: a "change"); mount can then be called again. */
    destroy(): void;
  }

  const TaurisTree: {
    mount<V extends object = Record<string, unknown>>(element: HTMLElement, options?: TaurisTreeOptions<V>): TaurisTreeView<V>;
  };

  interface Window {
    TaurisTree: typeof TaurisTree;
  }
}

export {};
