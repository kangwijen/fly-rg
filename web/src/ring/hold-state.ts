import type { ActiveNote } from "../protocol";
import { holdKey } from "./note-model";

export class HoldTracker {
  private prevProgress = new Map<string, number>();
  private sustain = new Set<string>();

  prune(active: ActiveNote[]): void {
    const live = new Set<string>();
    for (const note of active) {
      if (note.type === "hold" || note.type === "touch_hold") {
        live.add(holdKey(note));
      }
    }
    for (const key of [...this.sustain]) {
      if (!live.has(key)) this.sustain.delete(key);
    }
    for (const key of [...this.prevProgress.keys()]) {
      if (!live.has(key)) this.prevProgress.delete(key);
    }
  }

  isSustain(note: ActiveNote, progress: number): boolean {
    if (note.hold_phase === "sustain") return true;
    if (note.hold_phase === "approach") return false;
    return this.markSustain(note, progress);
  }

  private markSustain(note: ActiveNote, progress: number): boolean {
    const key = holdKey(note);
    const prev = this.prevProgress.get(key);
    let sustain = this.sustain.has(key);
    if (prev !== undefined && progress < prev - 0.02) sustain = true;
    if (sustain) this.sustain.add(key);
    this.prevProgress.set(key, progress);
    return sustain;
  }
}
