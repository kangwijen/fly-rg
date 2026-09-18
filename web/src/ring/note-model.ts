import type { ActiveNote } from "../protocol";
import { buttonToSensor } from "../sensors";
import { COLORS } from "./theme";

export type NoteKind = "tap" | "hold" | "touch" | "touch_hold" | "slide";

function isNoteKind(value: string | undefined): value is NoteKind {
  return (
    value === "tap" ||
    value === "hold" ||
    value === "touch" ||
    value === "touch_hold" ||
    value === "slide"
  );
}

export function noteKind(note: ActiveNote): NoteKind {
  if (isNoteKind(note.type)) return note.type;
  return "tap";
}

export function normalizeSensor(id: string): string {
  const s = id.trim().toUpperCase();
  if (s === "C1" || s === "C2") return "C";
  return s;
}

export function resolveNoteSensor(note: ActiveNote): string {
  if (note.sensor) return normalizeSensor(note.sensor);
  if (note.button == null) return "C";
  return buttonToSensor(note.button);
}

export function notePath(note: ActiveNote): string[] | null {
  if (note.path && note.path.length > 0) return note.path;
  if (note.slide?.path && note.slide.path.length > 0) return note.slide.path;
  return null;
}

export function wrapButton(button: number, delta: number): number {
  return ((((button - 1 + delta) % 8) + 8) % 8) + 1;
}

export function isWifiSlide(note: ActiveNote): boolean {
  return noteKind(note) === "slide" && note.slide?.shape === "w";
}

export function wifiStartButton(note: ActiveNote): number | null {
  if (note.button != null && note.button >= 1 && note.button <= 8) {
    return note.button;
  }
  const path = notePath(note);
  const head = path?.[0] ?? resolveNoteSensor(note);
  if (head.length >= 2 && head[0] === "A") {
    const idx = Number.parseInt(head.slice(1), 10);
    if (idx >= 1 && idx <= 8) return idx;
  }
  return null;
}

export function holdKey(note: ActiveNote): string {
  return `${note.t}|${resolveNoteSensor(note)}|${note.type}|${note.end ?? ""}`;
}

export function noteRing(note: ActiveNote): string {
  if (note.is_ex) return "#ffffff";
  if (note.is_break) return "#ffe08a";
  if (note.is_each) return COLORS.noteEach;
  return "rgba(255,255,255,0.72)";
}

export function noteColor(note: ActiveNote): string {
  if (note.is_mine) return "#5a2030";
  if (note.is_break) return COLORS.noteBreak;
  if (note.is_each) return COLORS.noteEach;
  const kind = noteKind(note);
  switch (kind) {
    case "touch":
    case "touch_hold":
      return COLORS.touch;
    case "slide":
      return COLORS.slide;
    case "tap":
    case "hold":
      return COLORS.note;
    default: {
      const _never: never = kind;
      return _never;
    }
  }
}

/** True when the note's canvas pixels change with wall-clock time. */
export function noteAnimates(note: ActiveNote): boolean {
  const kind = noteKind(note);
  switch (kind) {
    case "slide":
      return true;
    case "tap":
      return note.is_break === true || note.is_star === true || note.head_style === "star";
    case "hold":
    case "touch":
    case "touch_hold":
      return false;
    default: {
      const _never: never = kind;
      return _never;
    }
  }
}
