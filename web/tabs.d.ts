// Types for the tabs (window.TaurisTabs). In a TypeScript app, copy this file
// into the app (for example src/tabs.d.ts); scripts/doctor.py says when the
// copy is out of date. Then `TaurisTabs.mount(...)` type-checks with no import. Give your own tab
// fields as a type parameter to get them typed:
//   const tabs = TaurisTabs.mount<{ note: string }>(strip);
//   tabs.activeTab()?.note   // string

declare global {
  /** A tab: the library's `id` and `title`, plus your own fields `F`. */
  type TaurisTab<F extends object = Record<string, unknown>> = { id: number; title: string } & F;

  interface TaurisTabsMenuItem<F extends object = Record<string, unknown>> {
    label: string;
    action?: (tab: TaurisTab<F> | null) => void;
    shortcut?: string;
    disabled?: boolean;
    danger?: boolean;
  }

  interface TaurisTabsLabels {
    tabs: string;
    newTab: string;
    newTabHint: string;
    closeTab: string;
    closeOthers: string;
    closeRight: string;
    moveToWindow: string;
    moveLeft: string;
    moveRight: string;
    /** "Move to “…”": another open window, named by its active tab's title. */
    moveToOther: string | ((title: string) => string);
    moveLeftShortcut: string;
    moveRightShortcut: string;
    newTabShortcut: string;
    closeTabShortcut: string;
  }

  interface TaurisTabsOptions<F extends object = Record<string, unknown>> {
    /** Every word the strip shows. */
    labels?: Partial<TaurisTabsLabels>;
    /** Text, or svg markup starting with "<". */
    newIcon?: string;
    closeIcon?: string;
    /**
     * What a tab shows. An element with data-tt-close closes the tab; buttons,
     * links and data-tt-action elements get their own clicks.
     */
    renderTab?: ((tab: TaurisTab<F>, state: { active: boolean }) => Node | string | Array<Node | string> | null) | null;
    /** The right-click menu: true (default), false, or a function that changes the default items. */
    contextMenu?:
      | boolean
      | ((tab: TaurisTab<F> | null, items: Array<TaurisTabsMenuItem<F> | "-">) => Array<TaurisTabsMenuItem<F> | "-">);
    /** Asked before a tab closes, however it is closed; false keeps it open. */
    onBeforeClose?: ((tab: TaurisTab<F>, info: { reason: "tab" | "window" }) => boolean | Promise<boolean>) | null;
    /** The id of the element that shows the active tab (sets aria-controls). */
    panelId?: string | null;
    tabClass?: ((tab: TaurisTab<F>) => string) | null;
    documentTitle?: (tab: TaurisTab<F> | null) => string | undefined;
    /** What floats under the mouse while a tab is dragged inside its strip. */
    dragPreview?: "tab" | "ghost" | "title" | "none" | ((tab: TaurisTab<F>, tabEl: HTMLElement) => HTMLElement | null);
    /** Tabs can leave the strip into a window of their own (macOS; off elsewhere). */
    dragOut?: boolean;
    appear?: boolean;
    middleClickClose?: boolean;
    shortcuts?: boolean;
    styles?: boolean;
    moveThreshold?: number;
    detachDistance?: number;
  }

  interface TaurisTabsEvents<F extends object = Record<string, unknown>> {
    /** The tabs or the active tab changed. */
    change: { tabs: TaurisTab<F>[]; active: number | null };
    activate: TaurisTab<F> | null;
    update: TaurisTab<F>;
    /** A tab is closing (after onBeforeClose agreed). */
    close: TaurisTab<F>;
    /** A tab was dropped in this strip (from here or from another window). */
    drop: { tab: TaurisTab<F> | null; index: number | null };
  }

  interface TaurisTabStrip<F extends object = Record<string, unknown>> {
    readonly tabs: TaurisTab<F>[];
    readonly active: number | null;
    activeTab(): TaurisTab<F> | null;
    activate(id: number): void;
    /** Asks onBeforeClose (reason "tab"), then closes; resolves to true when the tab closed. */
    close(id: number): Promise<boolean>;
    /** Opens a tab after the active one; resolves to its id. */
    open(spec?: { title?: string } & Partial<F>): Promise<number>;
    /** Sends a tab's title and fields to Rust after you changed them, and redraws the strip. */
    update(tab: TaurisTab<F> | number, patch?: Partial<Omit<TaurisTab<F>, "id">>): void;
    /** Asks Rust again; resolves to true once the strip shows its newest tabs. */
    reload(): Promise<boolean>;
    reportStrip(): void;
    /** Returns a function that stops listening. */
    on<K extends keyof TaurisTabsEvents<F>>(event: K, fn: (payload: TaurisTabsEvents<F>[K]) => void): () => void;
    /** Removes the strip and every listener; mount can then be called again. */
    destroy(): void;
  }

  const TaurisTabs: {
    mount<F extends object = Record<string, unknown>>(strip: HTMLElement, options?: TaurisTabsOptions<F>): TaurisTabStrip<F>;
    version: string;
  };

  interface Window {
    TaurisTabs: typeof TaurisTabs;
  }
}

export {};
