import type { ActiveNote, Judgment } from "./protocol";
import {
  PAD,
  RADIUS,
  buttonToSensor,
  noteLandingXY,
  sensorAngleRad,
  sensorXY,
  toCanvas,
} from "./sensors";

const SIZE = 1024;
const CENTER = SIZE / 2;
const OUTER_R = 468;
/** Unity tap/hold half-width 0.61 at landing 4.8. */
const NOTE_R = 0.127 * OUTER_R;
/** Pixel scale relative to the original 512px layout (fonts, strokes). */
const S = SIZE / 512;
/** Majdata HoldDrop inner clamp 1.225 / landing 4.8. */
const HOLD_INNER_FRAC = 1.225 / 4.8;
const PAD_BLUE = "#2b6cff";
const OUTER_STEPS = 10;

const COLORS = {
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
};

const JUDGMENT_COLORS: Record<Judgment, string> = {
  critical: "#f4d03f",
  perfect: "#3de0d0",
  great: "#5ad67a",
  good: "#f0b429",
  miss: "#ff5a6a",
};

interface Flash {
  sensor: string;
  color: string;
  until: number;
}

interface HighlightStyle {
  fill: string;
  stroke: string;
  glow: number;
}

interface Pt {
  x: number;
  y: number;
}

type NoteKind = "tap" | "hold" | "touch" | "touch_hold" | "slide";

function noteKind(note: ActiveNote): NoteKind {
  switch (note.type) {
    case "hold":
    case "touch":
    case "touch_hold":
    case "slide":
    case "tap":
      return note.type;
    default:
      return "tap";
  }
}

function normalizeSensor(id: string): string {
  const s = id.trim().toUpperCase();
  if (s === "C1" || s === "C2") return "C";
  return s;
}

function resolveNoteSensor(note: ActiveNote): string {
  if (note.sensor) return normalizeSensor(note.sensor);
  if (note.button == null) return "C";
  return buttonToSensor(note.button);
}

function notePath(note: ActiveNote): string[] | null {
  if (note.path && note.path.length > 0) return note.path;
  if (note.slide?.path && note.slide.path.length > 0) return note.slide.path;
  return null;
}

function padPoint(sensor: string): Pt {
  const { x, y } = sensorXY(sensor);
  return toCanvas(x, y, CENTER, OUTER_R);
}

function landingPoint(sensor: string): Pt {
  const p = noteLandingXY(sensor);
  return toCanvas(p.x, p.y, CENTER, OUTER_R);
}

function destScale(progress: number): number {
  return progress * 4.8 * 0.4 + 0.51;
}

function alongRay(target: Pt, t: number): Pt {
  return {
    x: CENTER + (target.x - CENTER) * t,
    y: CENTER + (target.y - CENTER) * t,
  };
}

function tapTravel(target: Pt, progress: number): { pos: Pt; r: number } {
  const p = Math.min(1, Math.max(0, progress));
  const pos = alongRay(target, p);
  const scale = Math.min(1, Math.max(0, destScale(p)));
  return { pos, r: NOTE_R * scale };
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function holdKey(note: ActiveNote): string {
  return `${note.t}|${resolveNoteSensor(note)}|${note.type}|${note.end ?? ""}`;
}

function holdSpan(
  progress: number,
  sustain: boolean,
  padDist: number,
): { inner: number; outer: number } {
  const innerMin = Math.min(HOLD_INNER_FRAC * padDist, padDist);
  if (!sustain) {
    const outer = lerp(0, padDist, progress);
    return { inner: Math.min(innerMin, outer), outer };
  }
  return {
    inner: lerp(innerMin, padDist, progress),
    outer: padDist,
  };
}

function noteRing(note: ActiveNote): string {
  if (note.is_ex) return "#ffffff";
  if (note.is_break) return "#ffe08a";
  if (note.is_each) return COLORS.noteEach;
  return "rgba(255,255,255,0.72)";
}

function lightenHex(hex: string, t: number): string {
  if (!hex.startsWith("#") || hex.length !== 7) return hex;
  const n = Number.parseInt(hex.slice(1), 16);
  const mix = (c: number) => Math.round(c + (255 - c) * t);
  const r = mix((n >> 16) & 255);
  const g = mix((n >> 8) & 255);
  const b = mix(n & 255);
  return `#${[r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

function noteColor(note: ActiveNote): string {
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

function pointAlong(pts: Pt[], t: number): Pt {
  if (pts.length === 0) return { x: CENTER, y: CENTER };
  if (pts.length === 1 || t <= 0) return pts[0];
  if (t >= 1) return pts[pts.length - 1];
  const f = t * (pts.length - 1);
  const i = Math.min(pts.length - 2, Math.floor(f));
  const u = f - i;
  return {
    x: pts[i].x + (pts[i + 1].x - pts[i].x) * u,
    y: pts[i].y + (pts[i + 1].y - pts[i].y) * u,
  };
}

function polylineLen(pts: Pt[]): number {
  let n = 0;
  for (let i = 1; i < pts.length; i++) {
    n += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
  }
  return n;
}

function pointAtDist(pts: Pt[], dist: number): { x: number; y: number; ang: number } {
  if (pts.length === 0) return { x: CENTER, y: CENTER, ang: 0 };
  if (pts.length === 1) return { x: pts[0].x, y: pts[0].y, ang: 0 };
  let remain = Math.max(0, dist);
  for (let i = 0; i < pts.length - 1; i++) {
    const dx = pts[i + 1].x - pts[i].x;
    const dy = pts[i + 1].y - pts[i].y;
    const seg = Math.hypot(dx, dy);
    if (seg < 1e-6) continue;
    if (remain <= seg) {
      const u = remain / seg;
      return {
        x: pts[i].x + dx * u,
        y: pts[i].y + dy * u,
        ang: Math.atan2(dy, dx),
      };
    }
    remain -= seg;
  }
  const last = pts[pts.length - 1];
  const prev = pts[pts.length - 2];
  return {
    x: last.x,
    y: last.y,
    ang: Math.atan2(last.y - prev.y, last.x - prev.x),
  };
}

export class RingDisplay {
  readonly canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private active: ActiveNote[] = [];
  private flashes: Flash[] = [];
  private aimSensor: string | null = null;
  private tapSensor: string | null = null;
  private tapping = false;
  private activeSensors: string[] = [];
  private slidePaths: string[][] = [];
  private bgImage: CanvasImageSource | null = null;
  private holdPrevProgress = new Map<string, number>();
  private holdSustain = new Set<string>();

  constructor() {
    this.canvas = document.createElement("canvas");
    this.canvas.width = SIZE;
    this.canvas.height = SIZE;
    const ctx = this.canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas2D unavailable");
    this.ctx = ctx;
  }

  /** Jacket art or PV video frame drawn under the sensor grid. */
  setBackground(source: CanvasImageSource | null): void {
    this.bgImage = source;
  }

  setActive(notes: ActiveNote[]): void {
    this.active = notes;
  }

  setAim(button: number | null, tap: boolean, tapButton: number | null): void {
    this.aimSensor = button == null ? null : buttonToSensor(button);
    this.tapping = tap;
    this.tapSensor = tapButton == null ? null : buttonToSensor(tapButton);
  }

  setAimSensor(
    sensor: string | null,
    tap: boolean,
    tapSensor: string | null,
  ): void {
    this.aimSensor = sensor ? normalizeSensor(sensor) : null;
    this.tapping = tap;
    this.tapSensor = tapSensor ? normalizeSensor(tapSensor) : null;
  }

  setActiveSensors(sensors: string[]): void {
    this.activeSensors = sensors.map(normalizeSensor);
  }

  setSlidePaths(paths: string[][]): void {
    this.slidePaths = paths.map((p) => p.map(normalizeSensor));
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
      until: nowMs + 280,
    });
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

  draw(nowMs = performance.now()): void {
    const { ctx } = this;
    this.flashes = this.flashes.filter((f) => f.until > nowMs);
    this.pruneHoldTracking();

    ctx.clearRect(0, 0, SIZE, SIZE);

    ctx.save();
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, OUTER_R + 8, 0, Math.PI * 2);
    ctx.clip();

    if (this.bgImage) {
      this.drawCover(this.bgImage);
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

    this.drawPads(nowMs);

    this.drawSensorLabel("C");
    for (let i = 1; i <= 8; i++) this.drawSensorLabel(`A${i}`);
    for (let i = 1; i <= 8; i++) this.drawSensorLabel(`B${i}`);
    for (let i = 1; i <= 8; i++) this.drawSensorLabel(`D${i}`);
    for (let i = 1; i <= 8; i++) this.drawSensorLabel(`E${i}`);
    this.drawTouchCaption();

    this.drawAllSlidePaths();
    this.drawEachLines();

    for (const note of this.active) {
      this.drawNote(note, nowMs);
    }
  }

  private pruneHoldTracking(): void {
    const live = new Set<string>();
    for (const note of this.active) {
      if (note.type === "hold" || note.type === "touch_hold") {
        live.add(holdKey(note));
      }
    }
    for (const key of [...this.holdSustain]) {
      if (!live.has(key)) this.holdSustain.delete(key);
    }
    for (const key of [...this.holdPrevProgress.keys()]) {
      if (!live.has(key)) this.holdPrevProgress.delete(key);
    }
  }

  private markHoldSustain(note: ActiveNote, progress: number): boolean {
    const key = holdKey(note);
    const prev = this.holdPrevProgress.get(key);
    let sustain = this.holdSustain.has(key);
    if (prev !== undefined && progress < prev - 0.02) sustain = true;
    if (sustain) this.holdSustain.add(key);
    this.holdPrevProgress.set(key, progress);
    return sustain;
  }

  private holdIsSustain(note: ActiveNote, progress: number): boolean {
    if (note.hold_phase === "sustain") return true;
    if (note.hold_phase === "approach") return false;
    return this.markHoldSustain(note, progress);
  }

  private drawSensorLabel(sensor: string): void {
    const { ctx } = this;
    const p = padPoint(sensor);
    const area = sensor[0];
    const size =
      area === "C"
        ? Math.round(18 * S)
        : area === "A"
          ? Math.round(14 * S)
          : area === "B"
            ? Math.round(15 * S)
            : Math.round(11 * S);
    ctx.font = `700 ${size}px 'IBM Plex Mono', monospace`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = COLORS.textBright;
    ctx.shadowColor = COLORS.textStroke;
    ctx.shadowBlur = 4 * S;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 0;
    ctx.fillText(sensor, p.x, p.y);
    ctx.shadowBlur = 0;
  }

  private drawTouchCaption(): void {
    const { ctx } = this;
    ctx.font = `600 ${Math.round(10 * S)}px 'IBM Plex Mono', monospace`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(255,255,255,0.82)";
    ctx.shadowColor = COLORS.textStroke;
    ctx.shadowBlur = 3 * S;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 0;
    ctx.fillText("TOUCH SCREEN", CENTER, CENTER + OUTER_R + 14 * S);
    ctx.shadowBlur = 0;
  }

  private drawPads(nowMs: number): void {
    const { ctx } = this;
    ctx.save();
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, OUTER_R, 0, Math.PI * 2);
    ctx.clip();

    ctx.lineJoin = "round";
    ctx.lineCap = "round";

    this.drawGuides();

    const fillPad = (
      path: () => void,
      style: HighlightStyle,
      muted: boolean,
    ): void => {
      const fillAlpha = muted ? 0.36 : 0.5;
      ctx.save();
      ctx.globalAlpha = fillAlpha;
      if (style.glow > 0) {
        ctx.shadowColor = style.stroke;
        ctx.shadowBlur = style.glow;
      }
      path();
      ctx.fillStyle = style.fill;
      ctx.fill();
      ctx.restore();
      path();
      ctx.strokeStyle = COLORS.padStroke;
      ctx.lineWidth = muted ? 1.7 * S : 3.4 * S;
      ctx.globalAlpha = muted ? 0.8 : 0.95;
      ctx.stroke();
      ctx.globalAlpha = 1;
    };

    for (let i = 1; i <= 8; i++) {
      const sensor = `D${i}`;
      fillPad(() => this.adWedgePath("D", i), this.highlightStyle(sensor, nowMs), true);
    }
    for (let i = 1; i <= 8; i++) {
      const sensor = `A${i}`;
      fillPad(() => this.adWedgePath("A", i), this.highlightStyle(sensor, nowMs), false);
    }
    for (let i = 1; i <= 8; i++) {
      const sensor = `E${i}`;
      fillPad(() => this.eDiamondPath(i), this.highlightStyle(sensor, nowMs), true);
    }
    for (let i = 1; i <= 8; i++) {
      const sensor = `B${i}`;
      fillPad(() => this.bOctagonPath(i), this.highlightStyle(sensor, nowMs), false);
    }
    fillPad(() => this.cOctagonPath(), this.highlightStyle("C", nowMs), false);
    ctx.restore();
  }

  private drawGuides(): void {
    const { ctx } = this;
    ctx.save();
    ctx.strokeStyle = COLORS.guide;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    ctx.globalAlpha = 0.95;
    ctx.lineWidth = 3.4 * S;
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, OUTER_R, 0, Math.PI * 2);
    ctx.stroke();

    ctx.globalAlpha = 0.45;
    ctx.lineWidth = 1.4 * S;
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, RADIUS.B * OUTER_R, 0, Math.PI * 2);
    ctx.stroke();

    for (let i = 1; i <= 8; i++) {
      const ang = sensorAngleRad("A", i);
      const inner = toCanvas(
        PAD.cR * Math.cos(ang),
        PAD.cR * Math.sin(ang),
        CENTER,
        OUTER_R,
      );
      const outer = toCanvas(Math.cos(ang), Math.sin(ang), CENTER, OUTER_R);
      ctx.globalAlpha = 0.72;
      ctx.lineWidth = 2.1 * S;
      ctx.beginPath();
      ctx.moveTo(inner.x, inner.y);
      ctx.lineTo(outer.x, outer.y);
      ctx.stroke();
    }

    ctx.restore();
  }

  private adWedgePath(area: "A" | "D", index: number): void {
    const mid = sensorAngleRad(area, index);
    switch (area) {
      case "A":
        this.wedgePath(mid, PAD.adHalf, PAD.adInner, PAD.adOuter);
        return;
      case "D":
        this.wedgePath(mid, PAD.dHalf, PAD.dInner, PAD.dOuter);
        return;
      default: {
        const _never: never = area;
        throw new Error(`unhandled wedge ${_never}`);
      }
    }
  }

  private wedgePath(mid: number, half: number, innerR: number, outerR: number): void {
    const { ctx } = this;
    const a0 = mid - half;
    const a1 = mid + half;
    ctx.beginPath();
    for (let s = 0; s <= OUTER_STEPS; s++) {
      const t = s / OUTER_STEPS;
      const ang = a0 + (a1 - a0) * t;
      const p = toCanvas(
        outerR * Math.cos(ang),
        outerR * Math.sin(ang),
        CENTER,
        OUTER_R,
      );
      if (s === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    }
    for (let s = 0; s <= OUTER_STEPS; s++) {
      const t = s / OUTER_STEPS;
      const ang = a1 + (a0 - a1) * t;
      const p = toCanvas(
        innerR * Math.cos(ang),
        innerR * Math.sin(ang),
        CENTER,
        OUTER_R,
      );
      ctx.lineTo(p.x, p.y);
    }
    ctx.closePath();
  }

  private cOctagonPath(): void {
    const { ctx } = this;
    const r = PAD.cR;
    ctx.beginPath();
    for (let i = 0; i < 8; i++) {
      const ang = Math.PI / 8 + (i * Math.PI) / 4;
      const p = toCanvas(r * Math.cos(ang), r * Math.sin(ang), CENTER, OUTER_R);
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    }
    ctx.closePath();
  }

  private bOctagonPath(index: number): void {
    const { ctx } = this;
    const mid = sensorAngleRad("B", index);
    const cx = RADIUS.B * Math.cos(mid);
    const cy = RADIUS.B * Math.sin(mid);
    ctx.beginPath();
    for (let i = 0; i < 8; i++) {
      const ang = mid + Math.PI / 8 + (i * Math.PI) / 4;
      const p = toCanvas(
        cx + PAD.bOct * Math.cos(ang),
        cy + PAD.bOct * Math.sin(ang),
        CENTER,
        OUTER_R,
      );
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    }
    ctx.closePath();
  }

  private eDiamondPath(index: number): void {
    const { ctx } = this;
    const mid = sensorAngleRad("E", index);
    const c = Math.cos(mid);
    const s = Math.sin(mid);
    const outer = toCanvas(
      (RADIUS.E + PAD.eRadial) * c,
      (RADIUS.E + PAD.eRadial) * s,
      CENTER,
      OUTER_R,
    );
    const inner = toCanvas(
      (RADIUS.E - PAD.eRadial) * c,
      (RADIUS.E - PAD.eRadial) * s,
      CENTER,
      OUTER_R,
    );
    const left = toCanvas(
      RADIUS.E * c - PAD.eTangent * s,
      RADIUS.E * s + PAD.eTangent * c,
      CENTER,
      OUTER_R,
    );
    const right = toCanvas(
      RADIUS.E * c + PAD.eTangent * s,
      RADIUS.E * s - PAD.eTangent * c,
      CENTER,
      OUTER_R,
    );
    ctx.beginPath();
    ctx.moveTo(outer.x, outer.y);
    ctx.lineTo(left.x, left.y);
    ctx.lineTo(inner.x, inner.y);
    ctx.lineTo(right.x, right.y);
    ctx.closePath();
  }

  private highlightStyle(sensor: string, nowMs: number): HighlightStyle {
    const key = normalizeSensor(sensor);
    const flash = this.flashes.find((f) => f.sensor === key);
    const aimed = this.aimSensor === key;
    const tapped = this.tapping && this.tapSensor === key;
    const active = this.activeSensors.includes(key);

    if (flash) {
      const life = Math.max(0, (flash.until - nowMs) / 280);
      return {
        fill: flash.color,
        stroke: flash.color,
        glow: 18 * life,
      };
    }
    if (tapped) {
      return { fill: "rgba(28, 58, 72, 1)", stroke: COLORS.padStroke, glow: 10 };
    }
    if (aimed) {
      return { fill: "rgba(21, 40, 58, 1)", stroke: COLORS.aim, glow: 6 };
    }
    if (active) {
      return { fill: "rgba(20, 50, 58, 1)", stroke: COLORS.active, glow: 4 };
    }
    return {
      fill: COLORS.pad,
      stroke: COLORS.padMuted,
      glow: 0,
    };
  }

  private drawAllSlidePaths(): void {
    const paths: string[][] = [...this.slidePaths];
    for (const note of this.active) {
      if (note.type === "slide") continue;
      const p = notePath(note);
      if (p) paths.push(p);
    }
    for (const path of paths) {
      this.drawSlidePolyline(path);
    }
  }

  private drawSlidePolyline(sensors: string[], progress = 0, arrows = true): void {
    if (sensors.length < 2) return;
    const { ctx } = this;
    const pts = sensors.map((s) => padPoint(normalizeSensor(s)));

    ctx.save();
    ctx.strokeStyle = COLORS.slide;
    ctx.lineWidth = 3.5 * S;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.setLineDash([8 * S, 7 * S]);
    ctx.globalAlpha = 0.9;
    ctx.shadowColor = COLORS.slide;
    ctx.shadowBlur = 10 * S;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i].x, pts[i].y);
    }
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();

    if (progress > 0.01) {
      const pos = pointAlong(pts, Math.min(1, progress));
      ctx.save();
      ctx.strokeStyle = "rgba(255, 122, 217, 0.55)";
      ctx.lineWidth = 5 * S;
      ctx.lineJoin = "round";
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      const until = Math.min(1, progress) * (pts.length - 1);
      const last = Math.floor(until);
      for (let i = 1; i <= last; i++) {
        ctx.lineTo(pts[i].x, pts[i].y);
      }
      ctx.lineTo(pos.x, pos.y);
      ctx.stroke();
      ctx.restore();
    }

    if (arrows) this.drawSlideArrows(pts, progress);
  }

  private drawSlideArrows(pts: Pt[], progress: number): void {
    const total = polylineLen(pts);
    if (total < 8) return;
    const spacing = NOTE_R * 0.92;
    const traveled = Math.max(0, Math.min(1, progress)) * total;
    for (let d = spacing * 0.45; d < total - spacing * 0.2; d += spacing) {
      const sample = pointAtDist(pts, d);
      this.drawArrowTick(sample.x, sample.y, sample.ang, NOTE_R * 0.28, d <= traveled);
    }
  }

  private drawArrowTick(
    x: number,
    y: number,
    ang: number,
    size: number,
    passed: boolean,
  ): void {
    const { ctx } = this;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(ang);
    ctx.globalAlpha = passed ? 0.35 : 0.92;
    ctx.fillStyle = COLORS.slide;
    ctx.beginPath();
    ctx.moveTo(size * 0.78, 0);
    ctx.lineTo(-size * 0.48, size * 0.46);
    ctx.lineTo(-size * 0.18, 0);
    ctx.lineTo(-size * 0.48, -size * 0.46);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  private drawNote(note: ActiveNote, nowMs: number): void {
    const progress = Math.min(1, Math.max(0, note.progress));
    const sensor = resolveNoteSensor(note);
    const fill = noteColor(note);
    const ring = noteRing(note);
    const kind = noteKind(note);

    switch (kind) {
      case "slide":
        this.drawSlideNote(note, nowMs, fill, ring);
        return;
      case "touch_hold":
        this.drawTouchHoldNote(note, progress, padPoint(sensor), fill, ring);
        return;
      case "hold":
        this.drawHold(note, progress, landingPoint(sensor), fill, ring);
        return;
      case "touch":
        this.drawTouchNote(note, progress, padPoint(sensor), fill, ring);
        return;
      case "tap":
        this.drawTapNote(note, progress, landingPoint(sensor), fill, ring, nowMs);
        return;
      default: {
        const _never: never = kind;
        throw new Error(`unhandled note kind ${_never}`);
      }
    }
  }

  private drawSlideNote(note: ActiveNote, nowMs: number, fill: string, ring: string): void {
    const path = notePath(note);
    if (path && path.length > 1) {
      const raw = Math.min(1, Math.max(0, note.progress));
      const pts = path.map((s) => padPoint(normalizeSensor(s)));
      let x: number;
      let y: number;
      if (raw < 0.5) {
        const head = pts[0];
        const u = raw / 0.5;
        x = CENTER + (head.x - CENTER) * u;
        y = CENTER + (head.y - CENTER) * u;
        this.drawSlidePolyline(path, 0);
      } else {
        const pathProg = (raw - 0.5) / 0.5;
        this.drawSlidePolyline(path, pathProg);
        const along = pointAlong(pts, pathProg);
        x = along.x;
        y = along.y;
      }
      const r = NOTE_R * (0.7 + 0.3 * Math.min(1, raw / 0.5));
      const spin = (nowMs / 1000) * Math.PI;
      this.drawStar(x, y, r, fill, ring, note, spin);
      this.drawNoteMarks(note, x, y, r);
      return;
    }
    const sensor = resolveNoteSensor(note);
    const target = landingPoint(sensor);
    const travel = tapTravel(target, Math.min(1, Math.max(0, note.progress)));
    this.drawStar(
      travel.pos.x,
      travel.pos.y,
      travel.r,
      fill,
      ring,
      note,
      (nowMs / 1000) * Math.PI,
    );
    this.drawNoteMarks(note, travel.pos.x, travel.pos.y, travel.r);
  }

  private drawTapNote(
    note: ActiveNote,
    progress: number,
    target: Pt,
    fill: string,
    ring: string,
    nowMs: number,
  ): void {
    this.drawTapLine(target);
    const travel = tapTravel(target, progress);
    const breakSpin = note.is_break ? (nowMs / 1000) * 0.7 : 0;
    if (note.is_star || note.head_style === "star") {
      this.drawStar(travel.pos.x, travel.pos.y, travel.r, fill, ring, note, (nowMs / 1000) * Math.PI);
    } else {
      this.drawTapDisk(travel.pos.x, travel.pos.y, travel.r, fill, ring, note, breakSpin);
    }
    this.drawNoteMarks(note, travel.pos.x, travel.pos.y, travel.r);
  }

  private drawTapLine(target: Pt): void {
    const { ctx } = this;
    ctx.save();
    ctx.globalAlpha = 0.28;
    ctx.strokeStyle = "rgba(255, 255, 255, 0.7)";
    ctx.lineWidth = 1.7 * S;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(CENTER, CENTER);
    ctx.lineTo(target.x, target.y);
    ctx.stroke();
    ctx.restore();
  }

  private noteHeadPoint(note: ActiveNote): Pt {
    const progress = Math.min(1, Math.max(0, note.progress));
    const sensor = resolveNoteSensor(note);
    const kind = noteKind(note);
    switch (kind) {
      case "hold": {
        const target = landingPoint(sensor);
        const sustain = this.holdIsSustain(note, progress);
        const padDist = Math.hypot(target.x - CENTER, target.y - CENTER);
        const ang = Math.atan2(target.y - CENTER, target.x - CENTER);
        const span = holdSpan(progress, sustain, padDist);
        return {
          x: CENTER + Math.cos(ang) * span.outer,
          y: CENTER + Math.sin(ang) * span.outer,
        };
      }
      case "tap":
        return tapTravel(landingPoint(sensor), progress).pos;
      case "touch":
      case "touch_hold":
        return padPoint(sensor);
      case "slide":
        return padPoint(sensor);
      default: {
        const _never: never = kind;
        throw new Error(`unhandled note kind ${_never}`);
      }
    }
  }

  private drawEachLines(): void {
    const { ctx } = this;
    const notes = this.active.filter((n) => {
      if (!n.is_each) return false;
      const kind = noteKind(n);
      return kind === "tap" || kind === "hold";
    });
    const grouped = new Set<ActiveNote>();
    for (const note of notes) {
      if (grouped.has(note)) continue;
      const group: ActiveNote[] = [];
      for (const other of notes) {
        if (Math.abs(other.t - note.t) * 1000 <= 1) group.push(other);
      }
      for (const member of group) grouped.add(member);
      if (group.length < 2) continue;
      const sensors = new Set(group.map((n) => resolveNoteSensor(n)));
      if (sensors.size < 2) continue;
      const pts = group.map((n) => this.noteHeadPoint(n));
      ctx.save();
      ctx.strokeStyle = COLORS.noteEach;
      ctx.lineWidth = 2.6 * S;
      ctx.globalAlpha = 0.9;
      ctx.lineCap = "round";
      for (let i = 0; i < pts.length; i++) {
        for (let j = i + 1; j < pts.length; j++) {
          ctx.beginPath();
          ctx.moveTo(pts[i].x, pts[i].y);
          ctx.lineTo(pts[j].x, pts[j].y);
          ctx.stroke();
        }
      }
      ctx.restore();
    }
  }

  private drawHold(
    note: ActiveNote,
    progress: number,
    target: Pt,
    fill: string,
    ring: string,
  ): void {
    const sustain = this.holdIsSustain(note, progress);
    const body = sustain ? lightenHex(fill, 0.32) : fill;
    const padDist = Math.hypot(target.x - CENTER, target.y - CENTER);
    const ang = Math.atan2(target.y - CENTER, target.x - CENTER);
    const span = holdSpan(progress, sustain, padDist);

    if (padDist < NOTE_R) {
      this.drawTapDisk(CENTER, CENTER, NOTE_R, body, ring, note, 0);
      this.drawNoteMarks(note, CENTER, CENTER, NOTE_R);
      return;
    }

    const { ctx } = this;
    this.drawTapLine(target);

    ctx.save();
    ctx.translate(CENTER, CENTER);
    ctx.rotate(ang);
    this.paintStadium(span.inner, span.outer, NOTE_R, body, ring, note);
    ctx.restore();

    const innerX = CENTER + Math.cos(ang) * span.inner;
    const innerY = CENTER + Math.sin(ang) * span.inner;
    const headX = CENTER + Math.cos(ang) * span.outer;
    const headY = CENTER + Math.sin(ang) * span.outer;
    this.drawTapDisk(innerX, innerY, NOTE_R, body, ring, note, 0);
    this.drawTapDisk(headX, headY, NOTE_R, body, ring, note, 0);
    this.drawNoteMarks(note, headX, headY, NOTE_R);
  }

  private drawTouchHoldNote(
    note: ActiveNote,
    progress: number,
    target: Pt,
    fill: string,
    ring: string,
  ): void {
    const sustain = this.holdIsSustain(note, progress);
    const r = sustain
      ? NOTE_R * Math.max(0.28, 1 - 0.72 * progress)
      : NOTE_R * (0.4 + 0.6 * progress);
    const body = sustain ? lightenHex(fill, 0.32) : fill;
    this.drawTouchHold(target.x, target.y, r, body, ring, note, sustain ? 1 : progress);
    this.drawNoteMarks(note, target.x, target.y, r);
  }

  private drawTouchNote(
    note: ActiveNote,
    progress: number,
    target: Pt,
    fill: string,
    ring: string,
  ): void {
    this.drawTouchFans(target.x, target.y, progress, fill, ring, note, 0);
    this.drawNoteMarks(note, target.x, target.y, NOTE_R);
  }

  private stadiumPath(inner: number, outer: number, r: number): void {
    const { ctx } = this;
    ctx.beginPath();
    if (outer - inner < 0.5) {
      ctx.arc((inner + outer) * 0.5, 0, r, 0, Math.PI * 2);
      return;
    }
    ctx.arc(inner, 0, r, Math.PI / 2, -Math.PI / 2, false);
    ctx.arc(outer, 0, r, -Math.PI / 2, Math.PI / 2, false);
    ctx.closePath();
  }

  private paintStadium(
    inner: number,
    outer: number,
    r: number,
    fill: string,
    ring: string,
    note: ActiveNote,
  ): void {
    const { ctx } = this;
    this.stadiumPath(inner, outer, r);
    ctx.fillStyle = fill;
    ctx.fill();

    this.stadiumPath(inner, outer, r * 0.42);
    ctx.fillStyle = note.is_break ? "#fff4d0" : COLORS.noteCore;
    ctx.fill();

    this.stadiumPath(inner, outer, r * 0.72);
    ctx.strokeStyle = "rgba(255,255,255,0.7)";
    ctx.lineWidth = 2.4 * S;
    ctx.stroke();

    this.stadiumPath(inner, outer, r);
    ctx.strokeStyle = ring;
    ctx.lineWidth = note.is_ex ? 3.6 * S : 2.6 * S;
    ctx.stroke();

    if (note.is_ex) {
      this.stadiumPath(inner, outer, r + 5 * S);
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2.4 * S;
      ctx.stroke();
    }
  }

  private drawTapDisk(
    x: number,
    y: number,
    r: number,
    fill: string,
    ring: string,
    note: ActiveNote,
    spin: number,
  ): void {
    const { ctx } = this;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(spin);

    ctx.beginPath();
    ctx.arc(0, 0, r * 1.08, 0, Math.PI * 2);
    ctx.fillStyle = `${fill}33`;
    ctx.fill();

    const grad = ctx.createRadialGradient(0, 0, r * 0.12, 0, 0, r);
    grad.addColorStop(0, lightenHex(fill, 0.35));
    grad.addColorStop(0.55, fill);
    grad.addColorStop(1, fill);
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.beginPath();
    ctx.arc(0, 0, r * 0.38, 0, Math.PI * 2);
    ctx.fillStyle = note.is_break ? "#fff4d0" : COLORS.noteCore;
    ctx.fill();

    ctx.strokeStyle = "rgba(255,255,255,0.78)";
    ctx.lineWidth = 2.6 * S;
    ctx.beginPath();
    ctx.arc(0, 0, r * 0.7, 0, Math.PI * 2);
    ctx.stroke();

    ctx.strokeStyle = ring;
    ctx.lineWidth = note.is_ex ? 3.8 * S : 2.8 * S;
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.stroke();

    if (note.is_ex) {
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2.4 * S;
      ctx.beginPath();
      ctx.arc(0, 0, r + 5.5 * S, 0, Math.PI * 2);
      ctx.stroke();
    }

    if (note.is_break) {
      ctx.strokeStyle = "rgba(255, 224, 138, 0.85)";
      ctx.lineWidth = 2 * S;
      for (let i = 0; i < 4; i++) {
        const a = (i * Math.PI) / 2;
        ctx.beginPath();
        ctx.moveTo(Math.cos(a) * r * 0.82, Math.sin(a) * r * 0.82);
        ctx.lineTo(Math.cos(a) * r * 0.98, Math.sin(a) * r * 0.98);
        ctx.stroke();
      }
    }

    ctx.restore();
  }

  private paintFanKite(
    a: number,
    r: number,
    fill: string,
    ring: string,
    ex: boolean,
  ): void {
    const { ctx } = this;
    const mid = r * 0.58;
    const spread = 0.42;
    ctx.beginPath();
    ctx.moveTo(Math.cos(a) * r * 0.14, Math.sin(a) * r * 0.14);
    ctx.lineTo(Math.cos(a - spread) * mid, Math.sin(a - spread) * mid);
    ctx.lineTo(Math.cos(a) * r, Math.sin(a) * r);
    ctx.lineTo(Math.cos(a + spread) * mid, Math.sin(a + spread) * mid);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = ring;
    ctx.lineWidth = ex ? 3 * S : 2.1 * S;
    ctx.stroke();
  }

  private drawTouchFans(
    x: number,
    y: number,
    progress: number,
    fill: string,
    ring: string,
    note: ActiveNote,
    baseAngle: number,
  ): void {
    const { ctx } = this;
    const spread = (0.226 + 0.4 * progress) * NOTE_R;
    const fanR = NOTE_R * 0.72;
    ctx.save();
    ctx.translate(x, y);
    ctx.globalAlpha = Math.min(1, Math.max(0.12, progress));
    ctx.lineJoin = "round";
    for (let i = 0; i < 4; i++) {
      const a = baseAngle + (i * Math.PI) / 2;
      ctx.save();
      ctx.translate(Math.cos(a) * spread, Math.sin(a) * spread);
      this.paintFanKite(a, fanR, fill, ring, note.is_ex === true);
      ctx.restore();
    }

    ctx.beginPath();
    ctx.arc(0, 0, NOTE_R * 0.16, 0, Math.PI * 2);
    ctx.fillStyle = note.is_break ? "#fff4d0" : COLORS.noteCore;
    ctx.fill();
    ctx.strokeStyle = ring;
    ctx.lineWidth = 1.8 * S;
    ctx.stroke();

    if (note.is_ex) {
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2.2 * S;
      ctx.beginPath();
      ctx.arc(0, 0, spread + fanR * 0.35, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.restore();
  }

  private drawTouchHold(
    x: number,
    y: number,
    r: number,
    fill: string,
    ring: string,
    note: ActiveNote,
    progress: number,
  ): void {
    const { ctx } = this;
    ctx.save();
    ctx.translate(x, y);
    ctx.globalAlpha = Math.min(1, Math.max(0.2, progress));
    ctx.lineJoin = "round";
    ctx.lineCap = "round";

    const body = r * 0.7;
    this.roundRectPath(-body, -body, body * 2, body * 2, body * 0.22);
    ctx.fillStyle = `${fill}cc`;
    ctx.fill();
    ctx.strokeStyle = ring;
    ctx.lineWidth = note.is_ex ? 3.2 * S : 2.2 * S;
    ctx.stroke();

    const spread = (0.226 + 0.4 * progress) * Math.max(r, NOTE_R * 0.5);
    const fanR = r * 0.72;
    for (let i = 0; i < 4; i++) {
      const a = Math.PI / 4 + (i * Math.PI) / 2;
      ctx.save();
      ctx.translate(Math.cos(a) * spread, Math.sin(a) * spread);
      this.paintFanKite(a, fanR, fill, ring, note.is_ex === true);
      ctx.restore();
    }

    ctx.beginPath();
    ctx.arc(0, 0, r * 0.14, 0, Math.PI * 2);
    ctx.fillStyle = note.is_break ? "#fff4d0" : COLORS.noteCore;
    ctx.fill();
    ctx.restore();
  }

  private roundRectPath(x: number, y: number, w: number, h: number, rad: number): void {
    const { ctx } = this;
    const r = Math.min(rad, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  private drawNoteMarks(note: ActiveNote, x: number, y: number, r: number): void {
    const { ctx } = this;
    if (note.is_hanabi) this.drawHanabi(x, y, r);
    if (note.is_mine) {
      ctx.fillStyle = "#111";
      ctx.font = `700 ${Math.round(12 * S)}px 'IBM Plex Mono', monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("!", x, y);
    }
  }

  private drawStar(
    x: number,
    y: number,
    r: number,
    fill: string,
    stroke: string,
    note: ActiveNote,
    spin: number,
  ): void {
    const { ctx } = this;
    const spikes = 4;
    const outer = r;
    const inner = r * 0.42;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(spin);
    ctx.beginPath();
    for (let i = 0; i < spikes * 2; i++) {
      const rad = (i * Math.PI) / spikes - Math.PI / 2;
      const rr = i % 2 === 0 ? outer : inner;
      const px = Math.cos(rad) * rr;
      const py = Math.sin(rad) * rr;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = note.is_break ? "#ffe08a" : stroke;
    ctx.lineWidth = note.is_ex ? 3.4 * S : 2.5 * S;
    ctx.stroke();
    if (note.is_ex) {
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2 * S;
      ctx.beginPath();
      ctx.arc(0, 0, r + 5 * S, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.restore();
  }

  private drawHanabi(x: number, y: number, r: number): void {
    const { ctx } = this;
    ctx.save();
    ctx.strokeStyle = "rgba(255, 180, 90, 0.75)";
    ctx.lineWidth = 1.5 * S;
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(x + Math.cos(a) * r * 0.4, y + Math.sin(a) * r * 0.4);
      ctx.lineTo(x + Math.cos(a) * r * 1.5, y + Math.sin(a) * r * 1.5);
      ctx.stroke();
    }
    ctx.restore();
  }

  private drawCover(source: CanvasImageSource): void {
    const { ctx } = this;
    const sw =
      "videoWidth" in source && (source as HTMLVideoElement).videoWidth
        ? (source as HTMLVideoElement).videoWidth
        : "naturalWidth" in source && (source as HTMLImageElement).naturalWidth
          ? (source as HTMLImageElement).naturalWidth
          : SIZE;
    const sh =
      "videoHeight" in source && (source as HTMLVideoElement).videoHeight
        ? (source as HTMLVideoElement).videoHeight
        : "naturalHeight" in source && (source as HTMLImageElement).naturalHeight
          ? (source as HTMLImageElement).naturalHeight
          : SIZE;
    if (!sw || !sh) return;
    const scale = Math.max(SIZE / sw, SIZE / sh);
    const dw = sw * scale;
    const dh = sh * scale;
    ctx.drawImage(source, (SIZE - dw) / 2, (SIZE - dh) / 2, dw, dh);
  }
}
