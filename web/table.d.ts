// Types for the data table (window.TaurisTable). In a TypeScript app, copy
// this file into the app (for example src/table.d.ts).

declare global {
  interface TaurisTableRow {
    /** Unique among the rows. */
    id: string | number;
    /** The group it goes under (see `groups`). */
    group?: string | number;
    /** Its text in the dim colour (a done task). */
    dim?: boolean;
    [field: string]: unknown;
  }

  /** A button on each row: shown when the row is pointed at or selected. */
  interface TaurisTableAction<R extends TaurisTableRow = TaurisTableRow> {
    id?: string;
    /** Text (an emoji), or markup starting with "<" (an svg, drawn in the text colour). */
    icon?: string;
    /** Its tooltip, and its name for a screen reader (with the row's name). */
    title: string;
    onClick?: (row: R, info: { how: "mouse" | "keyboard" }) => void;
    /** A toggle: whether it is on for this row (shown pressed, and always). */
    pressed?: (row: R) => boolean;
    /** Copies this text; the icon is a tick for a moment. */
    copy?: (row: R) => string;
    danger?: boolean;
  }

  interface TaurisTableColumn<R extends TaurisTableRow = TaurisTableRow> {
    /** The row's field it shows (and sorts by). */
    key?: string;
    label?: string;
    /** In px, or any CSS width; one column without a width takes the rest. */
    width?: number | string;
    align?: "left" | "right" | "center";
    /** What the cell shows: text, or an element (a TaurisGlance figure); or fill `cell` and return nothing. */
    render?: (row: R, cell: HTMLTableCellElement) => string | Node | null | undefined;
    /** The cell's text, when it is not the field (for typing a name, and the tooltip). */
    text?: (row: R) => string;
    /** What it sorts by, when not the field (a date for a "Fri" shown). */
    value?: (row: R) => unknown;
    compare?: (a: R, b: R) => number;
    /** false: its header does not sort. */
    sortable?: boolean;
    /** The cell's tooltip: true for its whole text, or (row) => text. */
    title?: boolean | ((row: R) => string);
    className?: string;
    /** A column of the row's buttons. */
    actions?: TaurisTableAction<R>[];
  }

  interface TaurisTableGroup {
    id: string | number;
    label: string;
    /** The colour square before its name (any CSS colour). */
    color?: string;
    /** After its name, dim (default how many rows it has): "4 open · 1 done". */
    detail?: string;
    /** Shown when it has no rows (default labels.emptyGroup). */
    empty?: string;
    [field: string]: unknown;
  }

  interface TaurisTableLabels {
    noneStarts: string | ((typed: string) => string);
    copied: string;
    copyFailed: string;
    emptyGroup: string;
    empty: string;
    count: string | ((rows: number) => string);
  }

  interface TaurisTableSort {
    key: string;
    up: boolean;
  }

  interface TaurisTableOptions<R extends TaurisTableRow = TaurisTableRow> {
    columns: TaurisTableColumn<R>[];
    rows?: R[];
    /** Rows under their group's row, in this order; rows of no group listed come last. */
    groups?: TaurisTableGroup[] | null;
    /** The column sorted (a click on a header changes it); null: the rows in the order given. */
    sort?: TaurisTableSort | null;
    /** false: no header sorts (default true). */
    sortable?: boolean;
    selected?: string | number | null;
    /** The column whose text typing matches (default the first). */
    typeKey?: string | null;
    /** How long after a key the next one still adds to the name being typed (default 700). */
    typeAheadMs?: number;
    /** The table's name, for a screen reader. */
    label?: string;
    labels?: Partial<TaurisTableLabels>;
    /** false: the page brings its own stylesheet. */
    styles?: boolean;
    onSelect?: (row: R | null, info: { how: "mouse" | "keyboard" }) => void;
    /** Enter or a double click; `cmd`: with ⌘ (Ctrl elsewhere), the app's other way to open (a new tab). */
    onOpen?: (row: R, info: { how: "mouse" | "keyboard"; cmd: boolean }) => void;
    /** A right click or the menu key (⇧F10); null on the empty space. */
    onContextMenu?: (row: R | null, at: { x: number; y: number; how: "mouse" | "keyboard" }) => void;
    /** A header was clicked: the table is sorted by it. */
    onSort?: (sort: TaurisTableSort | null) => void;
    /** Any key on the table, first: true when the app took it (Space, F2, Delete). */
    onKey?: (event: KeyboardEvent, row: R | null) => boolean | void;
    onGroupOpen?: (group: TaurisTableGroup, info: { how: "mouse"; cmd: boolean }) => void;
    onGroupContextMenu?: (group: TaurisTableGroup, at: { x: number; y: number; how: "mouse" }) => void;
    /** What the table has to say ("Nothing starts with “q”.", "Copied"): show it (a status bar). */
    onMessage?: (text: string, kind: "info" | "ok" | "error") => void;
  }

  interface TaurisTable<R extends TaurisTableRow = TaurisTableRow> {
    /** Replaces the rows; the selection and the scroll stay. */
    setRows(rows: R[]): void;
    /** The rows, in the app's order. */
    rows(): R[];
    /** The rows in the order they show (sorted, in groups). */
    shown(): R[];
    /** Changes options: columns, rows, groups, sort, selected, labels, label, typeKey, the on… functions. */
    update(changes: Partial<TaurisTableOptions<R>>): void;
    /** Selects a row (null: none) and brings it into view. */
    select(id: string | number | null): void;
    selected(): R | null;
    readonly sort: TaurisTableSort | null;
    /** A row just added: selected, in view, and flashed so the eye finds it. */
    flash(id: string | number): void;
    focus(): void;
    /** The element that scrolls the rows (for TaurisReorder.attach). */
    readonly scroller: HTMLElement;
    destroy(): void;
  }

  interface Window {
    TaurisTable: {
      mount<R extends TaurisTableRow = TaurisTableRow>(element: HTMLElement, options: TaurisTableOptions<R>): TaurisTable<R>;
    };
  }

  const TaurisTable: Window["TaurisTable"];
}

export {};
