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
    editor?: TaurisTreeEditor;
    readOnly?: boolean;
    expanded?: boolean;
  }

  interface TaurisTreeColumn<V extends object = Record<string, unknown>> {
    label: string;
    width?: number;
    /** Which entry of `node.values` the column shows; the first column holds the tree. */
    key?: keyof V & string;
    minWidth?: number;
    editable?: boolean;
    align?: "left" | "right" | "center";
    className?: string;
  }

  interface TaurisTreeOptions<V extends object = Record<string, unknown>> {
    data?: TaurisTreeNode<V>[];
    /** null for a plain tree; the first column holds the tree, the last one stretches. */
    columns?: TaurisTreeColumn<V>[] | null;
    /** The tree's accessible name. */
    label?: string;
    /** Dotted connector lines (false: +/- boxes only). */
    lines?: boolean;
    /** More icons by name, as svg markup. */
    icons?: Record<string, string>;
    /** Rows drawn above and below the visible ones. */
    overscan?: number;
    /** Add the stylesheet (false: bring your own). */
    styles?: boolean;
  }

  interface TaurisTreeEvents<V extends object = Record<string, unknown>> {
    select: { node: TaurisTreeNode<V> | null };
    toggle: { node: TaurisTreeNode<V>; expanded: boolean };
    /** An edited value, already written into node.values. */
    change: { node: TaurisTreeNode<V>; column: keyof V & string; value: unknown };
    /** Enter or double-click on a row. */
    activate: { node: TaurisTreeNode<V> };
  }

  interface TaurisTreeView<V extends object = Record<string, unknown>> {
    /** Replaces every node; open rows and the selection are kept where their ids still exist. */
    setData(nodes: TaurisTreeNode<V>[]): void;
    expand(id: string | number): void;
    collapse(id: string | number): void;
    toggle(id: string | number): void;
    expandAll(): void;
    collapseAll(): void;
    /** Selects a row, opening its parents; null clears the selection. */
    select(id: string | number | null): void;
    selected(): TaurisTreeNode<V> | null;
    get(id: string | number): TaurisTreeNode<V> | null;
    isExpanded(id: string | number): boolean;
    /** Opens a cell's editor (the first editable column by default); false if it cannot. */
    edit(id: string | number, column?: keyof V & string): boolean;
    focus(): void;
    /** Returns a function that stops listening. */
    on<K extends keyof TaurisTreeEvents<V>>(event: K, fn: (payload: TaurisTreeEvents<V>[K]) => void): () => void;
    /** Removes the tree and every listener; mount can then be called again. */
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
