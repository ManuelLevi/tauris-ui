// Types for the small figures (window.TaurisGlance). In a TypeScript app, copy
// this file into the app (for example src/glance.d.ts).

declare global {
  /** A value: a number (its place is its x), [x, y], or { x, y }; x may be a date. */
  type TaurisGlancePoint = number | [number | string | Date, number] | { x: number | string | Date; y: number };

  interface TaurisGlanceSparklineOptions {
    /** In px (default 64 by 18). */
    width?: number;
    height?: number;
    /** Any CSS colour (default the accent; a selected row's text colour in a selected row). */
    color?: string;
    /** What it shows, for a screen reader and the tooltip ("Revenue, last 8 weeks"); without it, it is hidden from them. */
    label?: string;
    /** The range drawn, when the values do not reach it (a 0 to 100 score). */
    min?: number;
    max?: number;
  }

  type TaurisGlanceKind = "ok" | "warn" | "bad" | "done" | "new" | "none";

  interface TaurisGlanceCapacityOptions {
    /** Before the count ("Open tasks"). */
    label?: string;
    /** The limit: a segment each, up to 40 (past that, one filled track). */
    max: number;
    /** What holds each place, in order: its tooltip and colour. */
    items?: { title?: string; color?: string }[];
    /** How many are used (default items.length). Past max, the count turns red. */
    used?: number;
    /** The bar's width in px (default 140). */
    width?: number;
    title?: string;
    labels?: { free?: string };
  }

  interface Window {
    TaurisGlance: {
      /** A small line of values over time; a new <svg> each call. */
      sparkline(values: TaurisGlancePoint[], options?: TaurisGlanceSparklineOptions): SVGSVGElement;
      /** A state as a coloured dot and a word ("On track"); a new <span>. */
      status(kind: TaurisGlanceKind, text: string, options?: { title?: string }): HTMLSpanElement;
      /** How much of a limit is used: the count and a segment each place; a new <span>. */
      capacity(options: TaurisGlanceCapacityOptions): HTMLSpanElement;
    };
  }

  const TaurisGlance: Window["TaurisGlance"];
}

export {};
