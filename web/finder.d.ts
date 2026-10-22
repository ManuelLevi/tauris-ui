// Types for the find-anything panel (window.TaurisFinder). In a TypeScript
// app, copy this file into the app (for example src/finder.d.ts).

declare global {
  interface TaurisFinderItem {
    /** Unique within its kind. */
    id: string | number;
    /** What it is called: searched, and shown with its matches marked. */
    label: string;
    /** Its group (see `kinds`). */
    kind?: string;
    /** Shown on its right, not searched ("4 open tasks", "2.1 MB"). */
    detail?: string;
    /** Searched too, at half weight, their letters together (a description, a user name). Leave out what must never be found. */
    more?: string[];
    /** Text (an emoji) or markup starting with "<" (an svg); otherwise its kind's. */
    icon?: string;
    /** A colour bar before its detail (any CSS colour). */
    color?: string;
    /** Dimmed and struck through, ranked a little lower (a task that is done). */
    dim?: boolean;
    /** When it last changed (an ISO date or time): the latest show with nothing typed, and break ties. */
    when?: string;
  }

  interface TaurisFinderKind {
    id: string;
    /** The group's heading ("Projects"). */
    label: string;
    icon?: string;
    /** The most rows this group shows (default the finder's `limit`, 6). */
    limit?: number;
    /** A small lean towards this kind, for ties (40 for what people look for most). */
    bias?: number;
  }

  interface TaurisFinderLabels {
    find: string;
    placeholder: string;
    results: string;
    recent: string;
    latest: string;
    some: string | ((shown: number, total: number) => string);
    noMatch: string | ((query: string) => string);
    noMatchHint: string;
    nothing: string;
    choose: string;
    open: string;
    close: string;
  }

  interface TaurisFinderOptions {
    /** The things to find, or a function making them each time it opens. */
    items?: TaurisFinderItem[] | (() => TaurisFinderItem[]);
    /** The groups, in their usual order; a kind not listed comes last under its id. */
    kinds?: TaurisFinderKind[];
    /** The most rows a group shows (default 6). */
    limit?: number;
    /** ⌘K and ⌘L (Ctrl elsewhere) open it (default true). */
    shortcut?: boolean;
    /** Remembers what was picked, shown first with nothing typed, in the browser's storage under this key. */
    storageKey?: string | null;
    labels?: Partial<TaurisFinderLabels>;
    /** false: the page brings its own stylesheet. */
    styles?: boolean;
    /** An item was picked; the panel has closed and the focus is back where it was. */
    onPick?: (item: TaurisFinderItem, info: { how: "keyboard" | "mouse" }) => void;
    /** A right click on a result, or the menu key: where to open the app's own menu (the panel stays open). */
    onContextMenu?: (item: TaurisFinderItem, at: { x: number; y: number; how: "mouse" | "keyboard" }) => void;
    onOpen?: () => void;
    onClose?: (info: { picked: boolean }) => void;
  }

  interface TaurisFinder {
    /** Opens it (with this text in its field), or gives the keys back to it. */
    open(text?: string): void;
    /** Closes it; the focus goes back where it was. */
    close(): void;
    readonly isOpen: boolean;
    /** Changes options: items, kinds, limit, labels, the on… functions. An open panel shows them. */
    update(changes: Partial<TaurisFinderOptions>): void;
    /** Removes it and its shortcut. */
    destroy(): void;
  }

  interface Window {
    TaurisFinder: {
      mount(options?: TaurisFinderOptions): TaurisFinder;
      /** Closes whichever finder is open. */
      close(): void;
    };
  }

  const TaurisFinder: Window["TaurisFinder"];
}

export {};
