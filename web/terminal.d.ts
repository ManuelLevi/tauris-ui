// Types for the terminal look (window.TaurisTerminal). In a TypeScript app,
// copy this file into the app (for example src/terminal.d.ts). The classes
// (.tm, .tm-pane, .tm-band, .tm-key, .tm-table, ...) are listed at the top of
// web/terminal.css.

declare global {
  /** The colour of a log message: green, yellow or red. Without one it is white. */
  type TaurisTerminalKind = "ok" | "warn" | "error";

  interface TaurisTerminalMountOptions {
    /** Add the stylesheet (false: bring your own). */
    styles?: boolean;
  }

  interface TaurisTerminalRoot {
    /** Stops the clocks and the keys; mount can then be called again. */
    destroy(): void;
  }

  interface TaurisTerminalCommandLineOptions {
    /** false: add no stylesheet (the page brings its own; also when made before mount). */
    styles?: boolean;
    /** The text before the command, e.g. "ATLAS>". Default ">". */
    prompt?: string;
    /** Called with the trimmed command when Enter is pressed on a line that is not empty. */
    onSubmit?: (command: string) => void;
    /** The field's name for screen readers. Default "Command". */
    label?: string;
  }

  interface TaurisTerminalCommandLine {
    /** The command typed so far; setting it puts text on the line. */
    value: string;
    /** Empties the line. */
    clear(): void;
    /** Moves keyboard focus to the line. */
    focus(): void;
    /** Removes the line and its listeners; commandLine can then be called again. */
    destroy(): void;
  }

  interface TaurisTerminalLogOptions {
    /** false: add no stylesheet (the page brings its own). */
    styles?: boolean;
    /** The most rows kept; older ones are removed. Default 500. */
    max?: number;
  }

  interface TaurisTerminalLog {
    /** Adds a message with its time (now, or `at`). Returns its row. */
    add(text: string, kind?: TaurisTerminalKind, at?: Date): HTMLLIElement;
    /** Removes every message. */
    clear(): void;
  }

  interface TaurisTerminalPane {
    /** Green title band. */
    ok(): void;
    /** Red title band. */
    error(): void;
    /** Back to amber. */
    reset(): void;
  }

  const TaurisTerminal: {
    /** Marks the element as a terminal (.tm), adds the stylesheet, runs every
     * [data-tm-clock] and [data-tm-date] inside it, and makes .tm-key elements
     * work as buttons: Enter and Space, aria-disabled, and F1-F12 through aria-keyshortcuts. */
    mount(element: HTMLElement, options?: TaurisTerminalMountOptions): TaurisTerminalRoot;
    /** Draws a command line into an empty element: prompt, field, block cursor, date and time. */
    commandLine(element: HTMLElement, options?: TaurisTerminalCommandLineOptions): TaurisTerminalCommandLine;
    /** Makes an empty element (an <ol>) a message log with role="log". */
    log(element: HTMLElement, options?: TaurisTerminalLogOptions): TaurisTerminalLog;
    /** The title band state of a .tm-pane (all its bands) or of one .tm-band. */
    pane(element: HTMLElement, options?: { styles?: boolean }): TaurisTerminalPane;
  };

  interface Window {
    TaurisTerminal: typeof TaurisTerminal;
  }
}

export {};
