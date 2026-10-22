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
    /** Off for this row: true, or why (its tooltip, and said when it is pressed): "A KPI keeps at least one value." */
    disabled?: boolean | string | ((row: R) => boolean | string | null | undefined);
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
    /** `up`: the direction sorted (the table turns the result round itself for ▼). */
    compare?: (a: R, b: R, up: boolean) => number;
    /** false: its header does not sort. */
    sortable?: boolean;
    /** The cell's tooltip: true for its whole text, or (row) => text. */
    title?: boolean | ((row: R) => string);
    className?: string;
    /** The narrowest a drag makes it (default 40). */
    minWidth?: number;
    /** A shorter text ("€1.2M") shown when the whole one ("€1,234,567") does not fit. In a cell the app draws,
     *  a part marked data-short="€6.0k" shortens the same way, the rest staying. */
    short?: (row: R) => string;
    /** Edited in place (F2, or a click on the selected row's cell and a pause): onEdit hears the value. */
    edit?: boolean;
    /** The longest an edit may be (said once when reached). */
    maxLength?: number;
    /** A checkbox, always shown, ticked by `row[key]` (or `value(row)`); Space on the row ticks it too. */
    check?: boolean;
    /** Whether it may be ticked or unticked now: true, or why not (said instead of ticking). */
    canToggle?: (row: R) => boolean | string;
    onToggle?: (row: R, on: boolean, info: { how: "mouse" | "keyboard" }) => void;
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
    /** With collapsible groups: false, it starts closed (after that the person opens and closes it). */
    expanded?: boolean;
    [field: string]: unknown;
  }

  interface TaurisTableLabels {
    noneStarts: string | ((typed: string) => string);
    copied: string;
    copiedRows: string | ((count: number) => string);
    maxLength: string | ((n: number) => string);
    loading: string;
    expand: string;
    collapse: string;
    resize: string | ((label: string) => string);
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
    /** false: no column's edge can be dragged (default true). */
    resizable?: boolean;
    /** Groups open and close: a +/- box, ← →, Enter or Space on a selected group (default false). A group with no rows has no box. */
    collapsible?: boolean;
    /** Groups can be selected (the keys go through them) without opening and closing (default false). */
    selectableGroups?: boolean;
    /** An empty group says its `empty` text on its own row, in place of its detail, with no row under it (default false). */
    emptyInline?: boolean;
    /** Buttons on a group's row, shown on hover and selection: "+" (a new item in it), "✎". */
    groupActions?: { id?: string; icon?: string; title: string; danger?: boolean; onClick: (group: TaurisTableGroup, info: { how: "mouse" | "keyboard" }) => void }[] | null;
    /** Rows that stay after the others, whichever way the table is sorted (locked, no website). */
    last?: ((row: R) => boolean) | null;
    /** ⌘-click and Shift-click select several rows, ⌘A every row shown, ⇧↑ ⇧↓ extend (default false). */
    multiple?: boolean;
    /** ⌘C copies the selected rows as tab-separated text (a spreadsheet takes them). Default false. */
    copy?: boolean;
    /** A row's class names: overdue, locked, a drop target. */
    rowClass?: (row: R) => string | null | undefined;
    /** Said in place of the rows: "loading", or { error }. */
    state?: null | "loading" | { error: string };
    /** Keeps the columns' widths, the sort and the closed groups in the browser's storage under this key. */
    storageKey?: string | null;
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
    /** rows: every selected row (several with `multiple`); group: the selected group (its row then null). */
    onSelect?: (row: R | null, info: { how: "mouse" | "keyboard"; rows: R[]; group: TaurisTableGroup | null }) => void;
    /** Enter or a double click; `cmd`: ⌘↩, or a ⌘-click without `multiple` (Ctrl elsewhere): the app's other way to open (a new tab). */
    onOpen?: (row: R, info: { how: "mouse" | "keyboard"; cmd: boolean }) => void;
    /** A right click or the menu key (⇧F10); null on the empty space. */
    onContextMenu?: (row: R | null, at: { x: number; y: number; how: "mouse" | "keyboard" }) => void;
    /** A header was clicked: the table is sorted by it. */
    onSort?: (sort: TaurisTableSort | null) => void;
    /** A cell edited in place: a throw, text or false refuses it (the field stays, the text said). */
    onEdit?: (row: R, key: string, value: string) => unknown | Promise<unknown>;
    /** A column's edge was dragged: every column's width (null: as given). Kept under storageKey too. */
    onResize?: (info: { widths: (number | null)[] }) => void;
    /** Any key on the table, first: true when the app took it (Delete on a row or a group). */
    onKey?: (event: KeyboardEvent, row: R | null, group: TaurisTableGroup | null) => boolean | void;
    /** A group opened or closed by the person. */
    onGroupToggle?: (group: TaurisTableGroup, open: boolean, info: { how: "mouse" | "keyboard" }) => void;
    onGroupOpen?: (group: TaurisTableGroup, info: { how: "mouse"; cmd: boolean }) => void;
    onGroupContextMenu?: (group: TaurisTableGroup, at: { x: number; y: number; how: "mouse" | "keyboard" }) => void;
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
    /** Selects a row (null: none) and brings it into view; an array selects several (multiple). */
    select(id: string | number | null | (string | number)[]): void;
    selected(): R | null;
    /** Every selected row, as they show. */
    selection(): R[];
    /** The selected group (collapsible groups), or null. */
    selectedGroup(): TaurisTableGroup | null;
    /** Selects a group (selectableGroups or collapsible) and brings it into view; onSelect is not called. */
    selectGroup(groupId: string | number): void;
    /** Opens, closes, asks of a group (onGroupToggle is not called). */
    expand(groupId: string | number): void;
    collapse(groupId: string | number): void;
    isExpanded(groupId: string | number): boolean;
    /** Edits a row's cell in place (its first column with edit: true, or that key's): false when it cannot. */
    edit(rowId: string | number, key?: string): boolean;
    /** The columns' widths dragged to (null: as given). */
    widths(): (number | null)[];
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
