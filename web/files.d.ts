// Types for the files component (window.TaurisFiles). In a TypeScript app,
// copy this file into the app (for example src/files.d.ts).

declare global {
  /** A file as the component shows it. Keep your own fields on it too: every
   * callback gets your object back. */
  interface TaurisFile {
    id: string | number;
    name: string;
    /** Bytes. */
    size?: number;
    /** When it was added: a Date, ms, "2026-10-21", ISO, or "2026-10-21 10:04:00.123Z". */
    added?: string | number | Date;
    /** Who added it. */
    by?: string;
    /** The MIME type, for the badge. */
    type?: string;
    /** The badge's text, instead of one worked out from the type or name (up to 4 letters). */
    kind?: string;
  }

  type TaurisFilesColumn = "kind" | "name" | "size" | "added" | "by";
  type TaurisFilesSortKey = "name" | "size" | "added" | "by";
  type TaurisFilesMessageKind = "info" | "ok" | "error";

  /** Every word the component shows. The ones that are functions get what they need to say it. */
  interface TaurisFilesLabels {
    type: string;
    name: string;
    size: string;
    added: string;
    by: string;
    actions: string;
    add: string;
    search: string;
    open: string;
    saveAs: string;
    rename: string;
    delete: string;
    cancel: string;
    count: (n: number) => string;
    list: (place: string) => string;
    pickTitle: (place: string) => string;
    emptyTitle: string | ((place: string) => string);
    emptyText: string | ((place: string) => string);
    noMatch: (query: string) => string;
    drop: string | ((place: string) => string);
    /** A second line under "Drop to add to …", e.g. "Up to 50 MB per file". */
    dropHint: string | ((place: string) => string);
    adding: (count: number) => string;
    addedFiles: (files: TaurisFile[], place: string) => string;
    opening: (file: TaurisFile) => string;
    opened: (file: TaurisFile) => string;
    saved: (file: TaurisFile) => string;
    renamed: (file: TaurisFile, name: string) => string;
    nameNeeded: string;
    confirmDelete: (file: TaurisFile) => string;
    deleted: (file: TaurisFile) => string;
    confirmDeleteMany: (files: TaurisFile[]) => string;
    deletedMany: (files: TaurisFile[]) => string;
    openingMany: (files: TaurisFile[]) => string;
    openedMany: (files: TaurisFile[]) => string;
  }

  interface TaurisFilesOptions<F extends TaurisFile = TaurisFile> {
    files?: F[];
    /** The heading. Default "Files". */
    title?: string;
    /** The place in "Drop to add to …" and "No files in … yet". Default: the title. */
    place?: string;
    /** A word before the count: "Documents · 3 files · 2.1 MB". */
    subtitle?: string;
    /** A colour chip before the heading (any CSS colour). */
    color?: string | null;
    /** The columns, in order. Default all: kind, name, size, added, by. The actions come last. */
    columns?: TaurisFilesColumn[];
    /** The first order. Default { key: "name", up: true }. */
    sort?: { key: TaurisFilesSortKey; up?: boolean };
    /** The header (heading, "Add files…", search). Default true. */
    header?: boolean;
    /** The search field (shown once there are files). Default true. */
    search?: boolean;
    /** Where a drop adds files: anywhere on the window (default), over the component only, or nowhere. */
    dropArea?: "window" | "element" | "none";
    /** Ask before onDelete: true (the component asks; default), false (the app asks), or the question.
     * For several files at once, a function that takes two parameters gets them all; one that takes
     * only the file is not asked, and the component asks about all of them. onDelete runs once per file. */
    confirmDelete?: boolean | ((file: F, files: F[]) => string | null | false);
    /** ⌘-click (Ctrl-click) and Shift-click select several files; ⌘A selects them all. Default false. */
    multiple?: boolean;
    /** How a date shows in the Added column. Default short: "21 Oct", "21 Oct 25". */
    formatDate?: (date: Date, file: F) => string;
    /** The picker behind "Add files…". Default: the system's, through the plugin. */
    pick?: (title: string) => Promise<string[]>;
    labels?: Partial<TaurisFilesLabels>;
    /** Dropped or picked paths. Store them; resolve with the new files (they are selected and flash).
     * Reject with a sentence to show it ("Contracts is a folder. Add files, not folders."). */
    onAdd?: (paths: string[]) => Promise<F[] | void> | F[] | void;
    onOpen?: (file: F) => Promise<unknown> | unknown;
    /** Resolve false when the person cancels the save dialog. */
    onSaveAs?: (file: F) => Promise<boolean | void> | boolean | void;
    onRename?: (file: F, name: string) => Promise<unknown> | unknown;
    onDelete?: (file: F) => Promise<unknown> | unknown;
    /** The file with the focus, and every selected file (top to bottom). */
    onSelect?: (file: F | null, files: F[]) => void;
    /** The row's menu (right click, Shift+F10) opened; label is the file's name. As TaurisMenu's onOpen. */
    onMenuOpen?: (info: { label: string; how: "mouse" | "keyboard" }) => void;
    /** The row's menu closed; chosen is true when an item was picked. As TaurisMenu's onClose. */
    onMenuClose?: (info: { label: string; chosen: boolean }) => void;
    /** Messages for the app's own status bar. Without it the component shows them under the list. */
    onMessage?: (text: string, kind: TaurisFilesMessageKind) => void;
    /** Add the stylesheet (false: bring your own). Default true. */
    styles?: boolean;
  }

  /** A Tauri drag-and-drop event's payload (getCurrentWebview().onDragDropEvent). */
  interface TaurisFilesDragDrop {
    type: "enter" | "over" | "drop" | "leave";
    paths?: string[];
    /** Physical pixels, as Tauri reports them. */
    position?: { x: number; y: number };
  }

  interface TaurisFilesView<F extends TaurisFile = TaurisFile> {
    /** Replaces the files (the app's list is the truth). */
    setFiles(files: F[]): void;
    /** The files as the component has them now. */
    files(): F[];
    /** Changes options: title, place, subtitle, color, labels, columns, the on… functions, files. */
    update(changes: Partial<TaurisFilesOptions<F>>): void;
    /** Selects one file (null: none), or several: an array of ids (the first gets the focus). */
    select(id: F["id"] | F["id"][] | null): void;
    /** The file with the focus, or null. */
    selected(): F | null;
    /** Every selected file that is shown, top to bottom. */
    selection(): F[];
    /** Selects every file shown. */
    selectAll(): void;
    /** Opens the picker, then adds what was chosen (as "Add files…"). Resolves with the added files. */
    add(): Promise<F[]>;
    /** Adds these paths, as if they were dropped. */
    addPaths(paths: string[]): Promise<F[]>;
    open(id: F["id"]): Promise<void>;
    /** Starts renaming a file in place. */
    rename(id: F["id"]): void;
    /** Asks, then deletes a file with onDelete. */
    remove(id: F["id"]): Promise<void>;
    /** Shows only the files whose names contain this text. */
    search(text: string): void;
    /** Feeds a drag-and-drop event yourself (the component also listens on its own). */
    dragDrop(payload: TaurisFilesDragDrop): void;
    /** Shows the busy card with this text, or hides it (null). */
    busy(text: string | null): void;
    /** Shows a message (through onMessage when there is one). */
    message(text: string, kind?: TaurisFilesMessageKind): void;
    /** Moves keyboard focus to the list. */
    focus(): void;
    /** Moves keyboard focus to the search field. */
    focusSearch(): void;
    /** Removes the component and its listeners; mount can then be called again. */
    destroy(): void;
  }

  const TaurisFiles: {
    mount<F extends TaurisFile = TaurisFile>(element: HTMLElement, options?: TaurisFilesOptions<F>): TaurisFilesView<F>;
    /** The badge's text for a file: PDF, IMG, VID, AUD, XLS, PPT, DOC, ZIP, TXT, or the extension. */
    kindOf(file: Pick<TaurisFile, "name"> & Partial<TaurisFile>): string;
    /** "0 KB", "240 KB", "2.4 MB", "1.2 GB". */
    formatSize(bytes: number): string;
    /** The system's file picker, through the plugin (needs its "files" feature): the chosen paths, or []. */
    pick(options?: { title?: string; multiple?: boolean }): Promise<string[]>;
    /** The system's save dialog with a name filled in: the chosen path, or null. */
    saveDialog(options?: { title?: string; name?: string }): Promise<string | null>;
  };

  interface Window {
    TaurisFiles: typeof TaurisFiles;
  }
}

export {};
