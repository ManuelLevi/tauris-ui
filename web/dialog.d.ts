// Types for the dialogs (window.TaurisDialog). In a TypeScript app, copy this
// file into the app (for example src/dialog.d.ts).

declare global {
  interface TaurisDialogLabels {
    ok: string;
    cancel: string;
    close: string;
    save: string;
    back: string;
    done: string;
    /** The review's heading ("Save Changes"). */
    review: string;
    /** A needed field left empty. */
    required: string | ((label: string) => string);
    /** A field at its maxLength. */
    maxLength: string | ((n: number) => string);
    /** A secret's change, when its old value is not shown. */
    changed: string;
    /** Between two keys that both do it ("⌘[ or ⌘]"). */
    either: string;
    shortcuts: string;
    /** A password's Show and Hide, and Generate. */
    show: string;
    hide: string;
    generate: string;
    /** A review's pictures, for a screen reader ("Photo, before"). */
    before: string;
    after: string;
    /** The notice's title when a question's action failed after the system's alert. */
    failed: string;
  }

  interface TaurisDialogConfirmOptions {
    title: string;
    /** Paragraphs split by a blank line. */
    message?: string;
    ok?: string;
    cancel?: string;
    /** A red button for a delete (and the system's warning icon with `native`). */
    danger?: boolean;
    /** Asks with the system's alert (needs the plugin's "files" feature and the dialog plugin; otherwise in the page). */
    native?: boolean;
    /** The action, run inside the question after its ok button: a throw keeps the question open with the
     *  reason on its line (after the system's alert, a notice says it); true once it has run. */
    run?: () => unknown | Promise<unknown>;
    failedTitle?: string;
    width?: number;
    labels?: Partial<TaurisDialogLabels>;
  }

  /** "Field: old → new"; without `before` (a secret), only that it changed; a picture's change as its two pictures. */
  interface TaurisDialogChange {
    field: string;
    before?: string;
    after?: string;
    /** A picture's change: the old and new pictures' URLs (null: none). */
    beforeImage?: string | null;
    afterImage?: string | null;
  }

  /** What the app's own field gives the form. */
  interface TaurisDialogFieldHandle {
    /** Its value now (JSON, to cross into a window of its own). */
    value(): unknown;
    /** Takes the keys (a refusal about it, the form's start). */
    focus?(): void;
    /** The dialog closed. */
    destroy?(): void;
    /** A refusal about one of its parts (`{ field, part, text }`): show it there. */
    refuse?(part: string | number, text: string): void;
  }

  /** Draws the app's own field in `cell` (a picker, a photo, live text). */
  type TaurisDialogFieldRender = (cell: HTMLElement, field: TaurisDialogField) => TaurisDialogFieldHandle | void;

  interface TaurisDialogField {
    name: string;
    /** Shown as "Label:" to its left (a checkbox: its text on its right). */
    label?: string;
    /** The form's own types, one the app defined with TaurisDialog.defineField, or "row": `fields` side by side on one line, under one `label`. */
    type?: "text" | "password" | "number" | "email" | "url" | "tel" | "date" | "time" | "textarea" | "select" | "checkbox" | (string & {});
    value?: string | number | boolean | null;
    /** An example, dimmer than typed text ("Northwind Launch"). */
    placeholder?: string;
    /** The form starts here (by default it starts in its first text field, not a select above it). */
    autofocus?: boolean;
    /** A dim line under it. */
    hint?: string;
    /** Left empty, refused with labels.required (or requiredText). */
    required?: boolean;
    requiredText?: string | ((label: string) => string);
    /** Text, password, url, textarea…: the longest it may be. Typing stops there, and labels.maxLength says so under it. */
    maxLength?: number;
    disabled?: boolean;
    /** A select's choices: values, or { value, label }. */
    options?: (string | number | { value: string | number; label?: string })[];
    min?: number | string;
    max?: number | string;
    step?: number | string;
    rows?: number;
    autocomplete?: string;
    inputmode?: string;
    /** A password: a Show button. */
    reveal?: boolean;
    /** A password: a Generate button (true: 20 characters, a number: that many; a function: the app's own, in the page only). */
    generate?: boolean | number | (() => string);
    /** This field only: the app draws it (in the page only; in a window, define the type). */
    render?: TaurisDialogFieldRender;
    /** A "row"'s inputs, side by side (each may have a short label of its own). */
    fields?: TaurisDialogField[];
    /** Anything else the app's own field reads (ids, choices). */
    [extra: string]: unknown;
  }

  /** A refusal: about a field (a balloon under it), or about the whole form (the kept line);
   *  `part`: a part of the app's own field (its handle's refuse(part, text) and focus(part)). */
  type TaurisDialogRefusal = string | { field?: string; part?: string | number; text: string };

  type TaurisDialogReview = TaurisDialogChange[] | { rows: TaurisDialogChange[]; note?: string | null };

  interface TaurisDialogFormOptions<V = Record<string, unknown>> {
    title: string;
    fields: TaurisDialogField[];
    ok?: string;
    cancel?: string;
    danger?: boolean;
    /** 560px instead of 440px; or any width. */
    wide?: boolean;
    width?: number;
    /** The kept line's dim text under the fields, until a refusal takes its place. */
    hint?: string;
    /** The app's own checks, before saving: a refusal, or null to go on (or a promise of one). false: stay as it is and say nothing
     *  (the person said No to a TaurisDialog.confirm asked here); the keys go back to the field they were in. */
    validate?: (values: V) => TaurisDialogRefusal | null | undefined | false | Promise<TaurisDialogRefusal | null | undefined | false>;
    /** The changes to show before saving ("Save Changes"), or { rows, note } for a note that depends on the values
     *  (in place of reviewNote); none or [] saves at once; false stays, as validate's. */
    review?: (values: V) => TaurisDialogReview | null | undefined | false | Promise<TaurisDialogReview | null | undefined | false>;
    reviewTitle?: string;
    reviewNote?: string;
    saveLabel?: string;
    /** Saves; a throw (an Error, or { field, text }) shows as a refusal and keeps the dialog open. */
    submit?: (values: V) => unknown | Promise<unknown>;
    /** The left of the button row: a button ("Delete…") whose run asks its own question and resolves true to close
     *  the dialog (the form then gives null); it works in a window of its own too, run here. Or a function that
     *  fills the element itself (in the page only). */
    left?: ((element: HTMLElement) => void) | { label: string; danger?: boolean; run: () => boolean | Promise<boolean> };
    labels?: Partial<TaurisDialogLabels>;
    /** In a native window of its own, attached to this one (in the page where none can open). Its checks and save run here;
     *  a TaurisDialog.confirm during them is asked in that window. */
    window?: boolean;
    /** Opens refused: this refusal shows at once (New Task at the limit). */
    refusal?: TaurisDialogRefusal;
    /** Its ok button off for as long as it is open. */
    okDisabled?: boolean;
  }

  interface TaurisDialogShortcut {
    label: string;
    /** One key ("⌘K"), or several. */
    keys: string | string[];
    /** Any of the keys does it ("⌘[ or ⌘]"). */
    either?: boolean;
  }

  interface TaurisDialogPanel {
    update(changes: Partial<TaurisDialogPanelOptions>): void;
    destroy(): void;
  }

  interface TaurisDialogPanelOptions {
    title: string;
    /** A dim count after the title ("· 2"). */
    count?: string | number | null;
    /** Buttons on the top line, on its right. */
    actions?: ({ label: string; action?: () => void; disabled?: boolean; title?: string } | null | false)[];
    /** The title's heading level (default 3). */
    level?: number;
  }

  interface Window {
    TaurisDialog: {
      /** A yes/no question: true for its ok button. */
      confirm(options: TaurisDialogConfirmOptions): Promise<boolean>;
      /** A form: the values once saved, or null when cancelled. */
      form<V = Record<string, unknown>>(options: TaurisDialogFormOptions<V>): Promise<V | null>;
      /** The changes before they are saved: true for Save. */
      review(options: { title?: string; message?: string; rows: TaurisDialogChange[]; note?: string; ok?: string; cancel?: string; width?: number; window?: boolean; labels?: Partial<TaurisDialogLabels> }): Promise<boolean>;
      /** The Keyboard Shortcuts sheet: groups in columns of about the same height, keys as keycaps. */
      shortcuts(options: { title?: string; groups: { title: string; items: TaurisDialogShortcut[] }[]; columns?: number; width?: number; done?: string; window?: boolean; labels?: Partial<TaurisDialogLabels> }): Promise<void>;
      /** The About sheet: the app's mark (markup, text, or an image's URL), name, description, key/value rows (selectable). */
      about(options: { name: string; mark?: string; description?: string; rows?: [string, string][]; title?: string; width?: number; done?: string; window?: boolean; labels?: Partial<TaurisDialogLabels> }): Promise<void>;
      /** A field type of the app's own, for every form (and in a dialog's own window, where the page defines it again). */
      defineField(type: string, render: TaurisDialogFieldRender): void;
      /** This page is a dialog's own window: the app defines its field types here, and draws nothing else. */
      readonly inWindow: boolean;
      /** A titled border box around an element of the page (Swing's TitledBorder). */
      panel(element: HTMLElement, options: TaurisDialogPanelOptions): TaurisDialogPanel;
      /** Closes whatever dialog is open (a session that ends); each ends as cancelled. */
      close(): void;
      /** Whether a dialog is open. */
      readonly isOpen: boolean;
    };
  }

  const TaurisDialog: Window["TaurisDialog"];
}

export {};
