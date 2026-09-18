import type { ActiveNote, Judgment } from "../protocol";
import { buttonToSensor } from "../sensors";
import { drawCover, isVideoBackground } from "./background";
import { landingPoint, padPoint } from "./geometry";
import {
  drawHandTips,
  HOME_L,
  HOME_R,
  pushTrail,
  resolveHand,
  trailSettled,
} from "./hands";
import { HoldTracker } from "./hold-state";
import { clamp01, isUnitXY } from "./math";
import {
  noteAnimates,
  noteColor,
  noteKind,
  noteRing,
  normalizeSensor,
  resolveNoteSensor,
} from "./note-model";
import {
  drawEachLines,
  drawHold,
  drawTapNote,
  drawTouchHoldNote,
  drawTouchNote,
} from "./notes";
import { createStaticPadLayer, drawPadHighlights } from "./pads";
import { drawAllSlidePaths, drawSlideNote, drawWifiGroups } from "./slides";
import {
  CENTER,
  COLORS,
  FLASH_MS,
  JUDGMENT_COLORS,
  OUTER_R,
  SIZE,
} from "./theme";
import type { Flash, HandSample } from "./types";

function sameTip(
  a: [number, number] | null,
  b: [number, number] | null,
): boolean {
  if (a === b) return true;
  if (a == null || b == null) return false;
  return a[0] === b[0] && a[1] === b[1];
}

function sameStrings(a: readonly string[], b: readonly string[]): boolean {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

function samePaths(a: readonly string[][], b: readonly string[][]): boolean {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (!sameStrings(a[i], b[i])) return false;
  }
  return true;
}

function sameActive(a: readonly ActiveNote[], b: readonly ActiveNote[]): boolean {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const x = a[i];
    const y = b[i];
    if (
      x.t !== y.t ||
      x.progress !== y.progress ||
      x.sensor !== y.sensor ||
      x.type !== y.type ||
      x.hold_phase !== y.hold_phase ||
      x.button !== y.button ||
      x.end !== y.end
    ) {
      return false;
    }
  }
  return true;
}

export class RingDisplay {
  readonly canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private staticLayer: HTMLCanvasElement;
  private active: ActiveNote[] = [];
  private flashes: Flash[] = [];
  private aimSensor: string | null = null;
  private tapSensor: string | null = null;
  private tapping = false;
  private activeSensors: string[] = [];
  private slidePaths: string[][] = [];
  private bgImage: CanvasImageSource | null = null;
  private holds = new HoldTracker();
  private handL: [number, number] | null = null;
  private handR: [number, number] | null = null;
  private handStrikeL = 0;
  private handStrikeR = 0;
  private trailL: HandSample[] = [];
  private trailR: HandSample[] = [];
  private dirty = true;

  constructor() {
    this.canvas = document.createElement("canvas");
    this.canvas.width = SIZE;
    this.canvas.height = SIZE;
    const ctx = this.canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas2D unavailable");
    this.ctx = ctx;
    this.staticLayer = createStaticPadLayer();
  }

  /** Jacket art is drawn into the overlay; PV video is a separate screen texture. */
  setBackground(source: CanvasImageSource | null): void {
    if (this.bgImage === source) return;
    this.bgImage = source;
    this.dirty = true;
  }

  setActive(notes: ActiveNote[]): void {
    if (sameActive(this.active, notes)) return;
    this.active = notes;
    this.dirty = true;
  }

  setAim(button: number | null, tap: boolean, tapButton: number | null): void {
    const aimSensor = button == null ? null : buttonToSensor(button);
    const tapSensor = tapButton == null ? null : buttonToSensor(tapButton);
    if (
      this.aimSensor === aimSensor &&
      this.tapping === tap &&
      this.tapSensor === tapSensor
    ) {
      return;
    }
    this.aimSensor = aimSensor;
    this.tapping = tap;
    this.tapSensor = tapSensor;
    this.dirty = true;
  }

  setAimSensor(
    sensor: string | null,
    tap: boolean,
    tapSensor: string | null,
  ): void {
    const nextAim = sensor ? normalizeSensor(sensor) : null;
    const nextTap = tapSensor ? normalizeSensor(tapSensor) : null;
    if (
      this.aimSensor === nextAim &&
      this.tapping === tap &&
      this.tapSensor === nextTap
    ) {
      return;
    }
    this.aimSensor = nextAim;
    this.tapping = tap;
    this.tapSensor = nextTap;
    this.dirty = true;
  }

  setActiveSensors(sensors: string[]): void {
    const next = sensors.map(normalizeSensor);
    if (sameStrings(this.activeSensors, next)) return;
    this.activeSensors = next;
    this.dirty = true;
  }

  setSlidePaths(paths: string[][]): void {
    const next = paths.map((p) => p.map(normalizeSensor));
    if (samePaths(this.slidePaths, next)) return;
    this.slidePaths = next;
    this.dirty = true;
  }

  setHandTips(
    left?: [number, number] | null,
    right?: [number, number] | null,
    strikeL = 0,
    strikeR = 0,
  ): void {
    const nextL = isUnitXY(left) ? left : null;
    const nextR = isUnitXY(right) ? right : null;
    const nextStrikeL = clamp01(strikeL);
    const nextStrikeR = clamp01(strikeR);
    if (
      sameTip(this.handL, nextL) &&
      sameTip(this.handR, nextR) &&
      this.handStrikeL === nextStrikeL &&
      this.handStrikeR === nextStrikeR
    ) {
      return;
    }
    this.handL = nextL;
    this.handR = nextR;
    this.handStrikeL = nextStrikeL;
    this.handStrikeR = nextStrikeR;
    this.dirty = true;
  }

  flashHit(
    buttonOrSensor: number | string,
    judgment: Judgment,
    nowMs = performance.now(),
  ): void {
    const sensor =
      typeof buttonOrSensor === "number"
        ? buttonToSensor(buttonOrSensor)
        : normalizeSensor(buttonOrSensor);
    this.flashes.push({
      sensor,
      color: JUDGMENT_COLORS[judgment] ?? COLORS.padStroke,
      until: nowMs + FLASH_MS,
    });
    this.dirty = true;
  }

  /** Lighting state for the physical 3D A-ring buttons. */
  getAButtonStates(nowMs = performance.now()): Record<
    string,
    { aim: boolean; tap: boolean; active: boolean; flashColor: number | null }
  > {
    const out: Record<
      string,
      { aim: boolean; tap: boolean; active: boolean; flashColor: number | null }
    > = {};
    for (let i = 1; i <= 8; i++) {
      const key = `A${i}`;
      const flash = this.flashes.find((f) => f.sensor === key && f.until > nowMs);
      let flashColor: number | null = null;
      if (flash) {
        flashColor = Number.parseInt(flash.color.slice(1), 16);
      }
      out[key] = {
        aim: this.aimSensor === key,
        tap: this.tapping && this.tapSensor === key,
        active: this.activeSensors.includes(key),
        flashColor,
      };
    }
    return out;
  }

  /** Returns true when the canvas pixels changed and the 3D texture must upload. */
  draw(nowMs = performance.now()): boolean {
    const flashCount = this.flashes.length;
    this.flashes = this.flashes.filter((f) => f.until > nowMs);
    if (this.flashes.length !== flashCount) this.dirty = true;
    this.holds.prune(this.active);

    if (!this.needsRepaint()) return false;

    const { ctx } = this;
    ctx.clearRect(0, 0, SIZE, SIZE);

    ctx.save();
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, OUTER_R + 8, 0, Math.PI * 2);
    ctx.clip();

    if (isVideoBackground(this.bgImage)) {
      ctx.fillStyle = "rgba(5, 7, 12, 0.35)";
      ctx.fillRect(0, 0, SIZE, SIZE);
    } else if (this.bgImage) {
      drawCover(ctx, this.bgImage);
      ctx.fillStyle = "rgba(5, 7, 12, 0.35)";
      ctx.fillRect(0, 0, SIZE, SIZE);
    } else {
      const grad = ctx.createRadialGradient(CENTER, CENTER, 20, CENTER, CENTER, OUTER_R);
      grad.addColorStop(0, COLORS.diskInner);
      grad.addColorStop(1, COLORS.diskOuter);
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(CENTER, CENTER, OUTER_R + 8, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();

    ctx.drawImage(this.staticLayer, 0, 0);
    drawPadHighlights(ctx, nowMs, {
      flashes: this.flashes,
      aimSensor: this.aimSensor,
      tapSensor: this.tapSensor,
      tapping: this.tapping,
      activeSensors: this.activeSensors,
    });

    drawAllSlidePaths(ctx, this.slidePaths, this.active);
    drawEachLines(ctx, this.active, this.holds);

    const wifiDrawn = drawWifiGroups(ctx, this.active, nowMs);
    for (const note of this.active) {
      if (wifiDrawn.has(note)) continue;
      this.drawNote(ctx, note, nowMs);
    }

    this.recordHandTrail();
    const left = resolveHand(this.handL, HOME_L);
    const right = resolveHand(this.handR, HOME_R);
    drawHandTips(
      ctx,
      left,
      right,
      this.handStrikeL,
      this.handStrikeR,
      this.trailL,
      this.trailR,
    );

    this.dirty = false;
    return true;
  }

  private needsRepaint(): boolean {
    if (this.dirty) return true;
    if (this.flashes.length > 0) return true;
    const left = resolveHand(this.handL, HOME_L);
    const right = resolveHand(this.handR, HOME_R);
    if (
      !trailSettled(this.trailL, left, this.handStrikeL) ||
      !trailSettled(this.trailR, right, this.handStrikeR)
    ) {
      return true;
    }
    for (const note of this.active) {
      if (noteAnimates(note)) return true;
    }
    return false;
  }

  private recordHandTrail(): void {
    const left = resolveHand(this.handL, HOME_L);
    const right = resolveHand(this.handR, HOME_R);
    pushTrail(this.trailL, { x: left.x, y: left.y, strike: this.handStrikeL });
    pushTrail(this.trailR, { x: right.x, y: right.y, strike: this.handStrikeR });
  }

  private drawNote(
    ctx: CanvasRenderingContext2D,
    note: ActiveNote,
    nowMs: number,
  ): void {
    const progress = clamp01(note.progress);
    const sensor = resolveNoteSensor(note);
    const fill = noteColor(note);
    const ring = noteRing(note);
    const kind = noteKind(note);

    switch (kind) {
      case "slide":
        drawSlideNote(ctx, note, nowMs, fill, ring);
        return;
      case "touch_hold":
        drawTouchHoldNote(ctx, note, progress, padPoint(sensor), fill, ring, this.holds);
        return;
      case "hold":
        drawHold(ctx, note, progress, landingPoint(sensor), fill, ring, this.holds);
        return;
      case "touch":
        drawTouchNote(ctx, note, progress, padPoint(sensor), fill, ring);
        return;
      case "tap":
        drawTapNote(ctx, note, progress, landingPoint(sensor), fill, ring, nowMs);
        return;
      default: {
        const _never: never = kind;
        throw new Error(`unhandled note kind ${_never}`);
      }
    }
  }
}
