// Types for the status bar (window.TaurisStatus). In a TypeScript app, copy
// this file into the app (for example src/status.d.ts).

declare global {
  /** One part on the right of the bar: a text, with a dot, or a button (onClick), or a toggle (pressed). */
  interface TaurisStatusSegment {
    id: string;
    text: string;
    /** A dot before it: ok green, warn amber, bad red, wait a faint pulse (connecting), off a ring. */
    dot?: "ok" | "warn" | "bad" | "wait" | "off" | null;
    title?: string;
    /** In the text colour, bold (a count at its limit). */
    strong?: boolean;
    /** A toggle: whether it is on (shown with aria-pressed). */
    pressed?: boolean | null;
    /** Makes it a button. */
    onClick?: (info: { how: "mouse" }) => void;
  }

  interface TaurisStatusSayOptions {
    kind?: "ok" | "error" | "info";
    /** An Undo after the message, for `actionFor`: it runs this, and the focus goes back where it was. */
    undo?: () => unknown | Promise<unknown>;
    undoLabel?: string;
    /** Another action instead of Undo ("Show", "Retry"). */
    action?: { label: string; run: () => unknown | Promise<unknown> };
    /** How long the message stays, in ms (default the bar's `timeout`; 0: until the next). */
    timeout?: number;
    /** How long its action stays, in ms (default the bar's `actionFor`, 10 s). */
    actionFor?: number;
  }

  interface TaurisStatusOptions {
    segments?: TaurisStatusSegment[];
    /** How long a message stays, in ms (default 0: until the next one). */
    timeout?: number;
    /** How long a message's action stays, in ms (default 10000). */
    actionFor?: number;
    labels?: Partial<{ undo: string }>;
    /** false: the page brings its own stylesheet. */
    styles?: boolean;
    /** A right click on the bar: where to open the app's menu. */
    onContextMenu?: (at: { x: number; y: number }) => void;
  }

  interface TaurisStatus {
    say(text: string, options?: TaurisStatusSayOptions): void;
    clear(): void;
    readonly message: string;
    /** Changes one segment. */
    set(id: string, changes: Partial<TaurisStatusSegment>): void;
    update(changes: Partial<TaurisStatusOptions>): void;
    destroy(): void;
  }

  interface Window {
    TaurisStatus: {
      mount(element: HTMLElement, options?: TaurisStatusOptions): TaurisStatus;
    };
  }

  const TaurisStatus: Window["TaurisStatus"];
}

export {};
