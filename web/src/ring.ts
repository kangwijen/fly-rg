import type { ActiveNote, Judgment } from "./protocol";
import {
  RADIUS,
  buttonToSensor,
  sensorAngleRad,
  sensorXY,
  toCanvas,
  type Area,
} from "./sensors";

const SIZE = 512;
const CENTER = SIZE / 2;
const OUTER_R = 220;
const NOTE_R = 16;

const COLORS = {
  bg: "#070b14",
  diskInner: "#0c1524",
  diskOuter: "#05070c",
  ring: "#1a2740",
  ringGlow: "#2a3f63",
  pad: "#132033",
  padStroke: "#3de0d0",
  padMuted: "rgba(61, 224, 208, 0.22)",
  note: "#e24f9c",
  noteCore: "#ffe6f4",
  guide: "rgba(61, 224, 208, 0.14)",
  slide: "#3de0d0",
  text: "#8aa0b8",
  textBright: "#e8f4ff",
  aim: "#e24f9c",
  active: "#5ad6d0",
  cSplit: "rgba(61, 224, 208, 0.35)",
};

const JUDGMENT_COLORS: Record<Judgment, string> = {
  perfect: "#3de0d0",
  great: "#5ad67a",
  good: "#f0b429",
  miss: "#ff5a6a",
};

const WEDGE_HALF = Math.PI / 10;
const A_INNER = 0.72;
const A_OUTER = 0.98;
const B_INNER = 0.34;
const B_OUTER = 0.58;
const D_PAD_R = 0.075;
const E_PAD_R = 0.065;
const C_R = 0.22;

interface Flash {
  sensor: string;
  color: string;
  until: number;
}

function normalizeSensor(id: string): string {
  const s = id.trim().toUpperCase();
  if (s === "C1" || s === "C2") return "C";
  return s;
}

function resolveNoteSensor(note: ActiveNote): string {
  if (note.sensor) return normalizeSensor(note.sensor);
  return buttonToSensor(note.button);
}

function isTouchType(type: string | undefined): boolean {
  return type === "touch" || type === "touch_hold";
}

function notePath(note: ActiveNote): string[] | null {
  if (note.path && note.path.length > 0) return note.path;
  if (note.slide?.path && note.slide.path.length > 0) return note.slide.path;
  return null;
}

function padPoint(sensor: string): { x: number; y: number } {
  const { x, y } = sensorXY(sensor);
  return toCanvas(x, y, CENTER, OUTER_R);
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
      color: JUDGMENT_COLORS[judgment],
      until: nowMs + 280,
    });
  }

  draw(nowMs = performance.now()): void {
    const { ctx } = this;
    this.flashes = this.flashes.filter((f) => f.until > nowMs);

    ctx.clearRect(0, 0, SIZE, SIZE);
    ctx.fillStyle = COLORS.bg;
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, OUTER_R + 18, 0, Math.PI * 2);
    ctx.fill();

    ctx.save();
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, OUTER_R, 0, Math.PI * 2);
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
      ctx.fill();
    }
    ctx.restore();

    ctx.strokeStyle = COLORS.ringGlow;
    ctx.lineWidth = 10;
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, OUTER_R - 6, 0, Math.PI * 2);
    ctx.stroke();

    ctx.strokeStyle = COLORS.ring;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, OUTER_R - 6, 0, Math.PI * 2);
    ctx.stroke();

    this.drawGuideRings();

    for (let i = 1; i <= 8; i++) {
      this.drawWedgePad(`A${i}`, "A", i, A_INNER, A_OUTER, nowMs);
    }
    for (let i = 1; i <= 8; i++) {
      this.drawCirclePad(`D${i}`, D_PAD_R, nowMs);
    }
    for (let i = 1; i <= 8; i++) {
      this.drawWedgePad(`B${i}`, "B", i, B_INNER, B_OUTER, nowMs);
    }
    for (let i = 1; i <= 8; i++) {
      this.drawCirclePad(`E${i}`, E_PAD_R, nowMs);
    }
    this.drawCenterC(nowMs);

    this.drawAllSlidePaths();

    for (const note of this.active) {
      this.drawNote(note);
    }
  }

  private drawGuideRings(): void {
    const { ctx } = this;
    ctx.strokeStyle = COLORS.guide;
    ctx.lineWidth = 1.25;
    for (const r of [RADIUS.B, RADIUS.E, RADIUS.A]) {
      ctx.beginPath();
      ctx.arc(CENTER, CENTER, r * OUTER_R, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  private highlightStyle(
    sensor: string,
    nowMs: number,
  ): { fill: string; stroke: string; glow: number; bright: boolean } {
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
        bright: true,
      };
    }
    if (tapped) {
      return { fill: "#1c3a48", stroke: COLORS.padStroke, glow: 10, bright: true };
    }
    if (aimed) {
      return { fill: "#15283a", stroke: COLORS.aim, glow: 6, bright: true };
    }
    if (active) {
      return { fill: "#14323a", stroke: COLORS.active, glow: 4, bright: true };
    }
    return {
      fill: COLORS.pad,
      stroke: COLORS.padMuted,
      glow: 0,
      bright: false,
    };
  }

  private drawWedgePad(
    sensor: string,
    area: Area,
    index: number,
    inner: number,
    outer: number,
    nowMs: number,
  ): void {
    const { ctx } = this;
    const mid = sensorAngleRad(area, index);
    // Canvas arcs: angle increases clockwise from +X. Math angles use y-up, so
    // canvasAngle = -mathAngle. Sweep clockwise from mid-half to mid+half.
    const aStart = -(mid - WEDGE_HALF);
    const aEnd = -(mid + WEDGE_HALF);
    const style = this.highlightStyle(sensor, nowMs);
    const r0 = inner * OUTER_R;
    const r1 = outer * OUTER_R;

    const path = () => {
      ctx.beginPath();
      ctx.arc(CENTER, CENTER, r1, aStart, aEnd, false);
      ctx.arc(CENTER, CENTER, r0, aEnd, aStart, true);
      ctx.closePath();
    };

    if (style.glow > 0) {
      ctx.save();
      ctx.shadowColor = style.stroke;
      ctx.shadowBlur = style.glow;
      path();
      ctx.fillStyle = style.fill;
      ctx.fill();
      ctx.restore();
    } else {
      path();
      ctx.fillStyle = style.fill;
      ctx.fill();
    }

    path();
    ctx.strokeStyle = style.stroke;
    ctx.lineWidth = 2;
    ctx.stroke();

    const label = padPoint(sensor);
    ctx.fillStyle = style.bright ? COLORS.textBright : COLORS.text;
    ctx.font = "600 11px 'IBM Plex Mono', monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(sensor, label.x, label.y);
  }

  private drawCirclePad(sensor: string, radiusUnit: number, nowMs: number): void {
    const { ctx } = this;
    const p = padPoint(sensor);
    const r = radiusUnit * OUTER_R;
    const style = this.highlightStyle(sensor, nowMs);

    if (style.glow > 0) {
      ctx.save();
      ctx.shadowColor = style.stroke;
      ctx.shadowBlur = style.glow;
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fillStyle = style.fill;
      ctx.fill();
      ctx.restore();
    } else {
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fillStyle = style.fill;
      ctx.fill();
    }

    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.strokeStyle = style.stroke;
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = style.bright ? COLORS.textBright : COLORS.text;
    ctx.font = "600 10px 'IBM Plex Mono', monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(sensor, p.x, p.y);
  }

  private drawCenterC(nowMs: number): void {
    const { ctx } = this;
    const r = C_R * OUTER_R;
    const style = this.highlightStyle("C", nowMs);

    if (style.glow > 0) {
      ctx.save();
      ctx.shadowColor = style.stroke;
      ctx.shadowBlur = style.glow;
      ctx.beginPath();
      ctx.arc(CENTER, CENTER, r, 0, Math.PI * 2);
      ctx.fillStyle = style.fill;
      ctx.fill();
      ctx.restore();
    } else {
      ctx.beginPath();
      ctx.arc(CENTER, CENTER, r, 0, Math.PI * 2);
      ctx.fillStyle = style.fill;
      ctx.fill();
    }

    ctx.beginPath();
    ctx.arc(CENTER, CENTER, r, 0, Math.PI * 2);
    ctx.strokeStyle = style.stroke;
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // Visual C1 (right) / C2 (left) split
    ctx.beginPath();
    ctx.moveTo(CENTER, CENTER - r);
    ctx.lineTo(CENTER, CENTER + r);
    ctx.strokeStyle = COLORS.cSplit;
    ctx.lineWidth = 1.5;
    ctx.stroke();

    ctx.fillStyle = style.bright ? COLORS.textBright : COLORS.text;
    ctx.font = "600 10px 'IBM Plex Mono', monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("C1", CENTER + r * 0.42, CENTER);
    ctx.fillText("C2", CENTER - r * 0.42, CENTER);
  }

  private drawAllSlidePaths(): void {
    const paths: string[][] = [...this.slidePaths];
    for (const note of this.active) {
      const p = notePath(note);
      if (p) paths.push(p);
    }
    for (const path of paths) {
      this.drawSlidePolyline(path);
    }
  }

  private drawSlidePolyline(sensors: string[]): void {
    if (sensors.length < 2) return;
    const { ctx } = this;
    const pts = sensors.map((s) => padPoint(normalizeSensor(s)));

    ctx.save();
    ctx.strokeStyle = COLORS.slide;
    ctx.lineWidth = 3;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.globalAlpha = 0.85;
    ctx.shadowColor = COLORS.slide;
    ctx.shadowBlur = 8;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i].x, pts[i].y);
    }
    ctx.stroke();
    ctx.restore();

    for (const p of pts) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 3.5, 0, Math.PI * 2);
      ctx.fillStyle = COLORS.slide;
      ctx.fill();
    }
  }

  private drawNote(note: ActiveNote): void {
    const { ctx } = this;
    const progress = Math.min(1, Math.max(0, note.progress));
    const sensor = resolveNoteSensor(note);
    const touch = isTouchType(note.type);
    const target = padPoint(sensor);

    let x: number;
    let y: number;
    let r: number;

    if (touch) {
      x = target.x;
      y = target.y;
      r = NOTE_R * (0.35 + 0.65 * progress);
    } else {
      x = CENTER + (target.x - CENTER) * progress;
      y = CENTER + (target.y - CENTER) * progress;
      r = NOTE_R * (0.55 + 0.45 * progress);
    }

    ctx.beginPath();
    ctx.arc(x, y, r + 4, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(226, 79, 156, 0.22)";
    ctx.fill();

    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = COLORS.note;
    ctx.fill();

    ctx.beginPath();
    ctx.arc(x, y, r * 0.35, 0, Math.PI * 2);
    ctx.fillStyle = COLORS.noteCore;
    ctx.fill();

    ctx.strokeStyle = "rgba(255, 255, 255, 0.55)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.stroke();
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
