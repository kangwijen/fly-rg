import type { Judgment } from "../protocol";

export const SIZE = 1024;
export const CENTER = SIZE / 2;
export const OUTER_R = 468;
/** Unity tap/hold half-width 0.61 at landing 4.8. */
export const NOTE_R = 0.127 * OUTER_R;
/** Pixel scale relative to the original 512px layout (fonts, strokes). */
export const S = SIZE / 512;
/** Majdata HoldDrop inner clamp 1.225 / landing 4.8. */
export const HOLD_INNER_FRAC = 1.225 / 4.8;
export const PAD_BLUE = "#2b6cff";
export const OUTER_STEPS = 10;
export const HAND_TRAIL = 12;
export const FLASH_MS = 280;

export const COLORS = {
  diskInner: "rgba(12, 21, 36, 0.5)",
  diskOuter: "rgba(5, 7, 12, 0.5)",
  pad: PAD_BLUE,
  padStroke: "#ffffff",
  padMuted: "rgba(255, 255, 255, 0.55)",
  guide: "rgba(255, 255, 255, 0.92)",
  note: "#e24f9c",
  noteEach: "#f0d24b",
  noteBreak: "#f0a020",
  noteCore: "#ffe6f4",
  touch: "#5ad6ff",
  slide: "#ff7ad9",
  textBright: "#ffffff",
  textStroke: "rgba(4, 8, 16, 0.92)",
  aim: "#e24f9c",
  active: "#5ad6d0",
  handL: "#3de0d0",
  handR: "#e24f9c",
};

export const JUDGMENT_COLORS: Record<Judgment, string> = {
  critical: "#f4d03f",
  perfect: "#3de0d0",
  great: "#5ad67a",
  good: "#f0b429",
  miss: "#ff5a6a",
};

export function lightenHex(hex: string, t: number): string {
  if (!hex.startsWith("#") || hex.length !== 7) return hex;
  const n = Number.parseInt(hex.slice(1), 16);
  const mix = (c: number) => Math.round(c + (255 - c) * t);
  const r = mix((n >> 16) & 255);
  const g = mix((n >> 8) & 255);
  const b = mix(n & 255);
  return `#${[r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}
