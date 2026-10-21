// Types for the in-window menus (window.TaurisMenu). In a TypeScript app,
// copy this file into the app (for example src/menus.d.ts).

declare global {
  interface TaurisMenuItemOptions {
    label: string;
    /** Shown on the right ("⌘N"). Shown only: the app binds its own keys. */
    shortcut?: string;
    disabled?: boolean;
    /** A ✓ column: true shows the tick, false leaves it empty. */
    checked?: boolean;
    /** A colour chip before the label (any CSS colour). */
    color?: string;
    /** Red, for an item that deletes. */
    danger?: boolean;
    /** Called after the menu has closed and focus is back where it was. */
    action?: (item: TaurisMenuItemOptions) => void;
    /** A sub-menu: it opens to the right (Right, Enter, or the mouse resting on the item). */
    items?: TaurisMenuItems;
  }

  /** An item, "-" for a line between groups; null and false are skipped. */
  type TaurisMenuItem = TaurisMenuItemOptions | "-" | null | false | undefined;
  /** The items, or a function that makes them each time the menu opens. */
  type TaurisMenuItems = TaurisMenuItem[] | (() => TaurisMenuItem[]);

  interface TaurisMenuBarMenu {
    label: string;
    items: TaurisMenuItems;
    disabled?: boolean;
  }

  /** A menu opened: by the mouse, or from the keyboard. */
  interface TaurisMenuOpenInfo {
    label: string;
    how: "mouse" | "keyboard";
  }

  /** A menu closed: chosen is true when an item was picked (false: Escape, a click outside, its title or button again). */
  interface TaurisMenuCloseInfo {
    label: string;
    chosen: boolean;
  }

  /** For a sound, say. Going from one menu of the bar to the next fires neither: the bar stays open. */
  interface TaurisMenuHooks {
    onOpen?: (info: TaurisMenuOpenInfo) => void;
    onClose?: (info: TaurisMenuCloseInfo) => void;
  }

  interface TaurisMenuBar {
    /** Replaces the menus. An open menu stays open if its title is still there. */
    setMenus(menus: TaurisMenuBarMenu[]): void;
    /** Opens menu number `index` with its first item chosen. */
    open(index?: number): void;
    close(): void;
    /** Moves keyboard focus to the bar. */
    focus(): void;
    /** Removes the titles and listeners; bar can then be called again. */
    destroy(): void;
  }

  interface TaurisMenuButton {
    setItems(items: TaurisMenuItems): void;
    /** Opens the menu with its first item chosen. */
    open(): void;
    close(): void;
    /** Removes the menu and its listeners; button can then be called again. */
    destroy(): void;
  }

  const TaurisMenu: {
    /** Fills an element (a <nav>) with menu titles: a desktop menu bar. */
    bar(element: HTMLElement, options: { menus: TaurisMenuBarMenu[]; label?: string } & TaurisMenuHooks): TaurisMenuBar;
    /** Makes an element (a toolbar button) open a menu under it, with a ▾ after its text (caret: false for none). */
    button(element: HTMLElement, options: { items: TaurisMenuItems; label?: string; caret?: boolean; gap?: number } & TaurisMenuHooks): TaurisMenuButton;
    /** A menu at a point, in window pixels (a right click: e.clientX, e.clientY). */
    open(items: TaurisMenuItems, at: { x: number; y: number }, options?: { keyboard?: boolean; label?: string; returnTo?: HTMLElement; onClose?: (info: TaurisMenuCloseInfo) => void }): { close(): void };
    /** Closes whichever menu is open. */
    close(): void;
  };

  interface Window {
    TaurisMenu: typeof TaurisMenu;
  }
}

export {};
