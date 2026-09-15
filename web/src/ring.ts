import type { ActiveNote, Judgment } from "./protocol";
import {
  RADIUS,
  buttonToSensor,
  sensorAngleRad,
  sensorXY,
  toCanvas,
  type Area,
} from "./sensors";

const SIZE = 1024;
const CENTER = SIZE / 2;
const OUTER_R = 468;
const NOTE_R = 30;
/** Pixel scale relative to the original 512px layout (fonts, strokes). */
const S = SIZE / 512;

const COLORS = {
  bg: "rgba(7, 11, 20, 0.5)",
  diskInner: "rgba(12, 21, 36, 0.5)",
  diskOuter: "rgba(5, 7, 12, 0.5)",
  ring: "#1a2740",
  ringGlow: "#2a3f63",
  pad: "rgba(19, 32, 51, 0.5)",
  padStroke: "rgba(61, 224, 208, 0.85)",
  padMuted: "rgba(61, 224, 208, 0.55)",
  note: "#e24f9c",
  noteCore: "#ffe6f4",
  guide: "rgba(61, 224, 208, 0.28)",
  slide: "#3de0d0",
  text: "#d8e6f4",
  textBright: "#ffffff",
  textStroke: "rgba(4, 8, 16, 0.92)",
  aim: "#e24f9c",
  active: "#5ad6d0",
  cSplit: "rgba(61, 224, 208, 0.55)",
};

const JUDGMENT_COLORS: Record<Judgment, string> = {
  perfect: "#3de0d0",
  great: "#5ad67a",
  good: "#f0b429",
  miss: "#ff5a6a",
};

const OUTER_HALF = Math.PI / 16; // 16 alternating A/D wedges on outer ring
const B_HALF = Math.PI / 8 - 0.06;
const A_INNER = 0.72;
const A_OUTER = 0.98;
const D_INNER = 0.72;
const D_OUTER = 0.98;
const B_INNER = 0.26;
const B_OUTER = 0.5;
const E_SIZE = 0.07;
const C_R = 0.2;

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
  if (note.button == null) return "C";
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

    this.drawGuideRings();

    // Pads at 50% opacity so jacket / disk shows through.
    ctx.save();
    ctx.globalAlpha = 0.5;
    this.drawCenterC(nowMs, false);
    for (let i = 1; i <= 8; i++) {
      this.drawWedgePad(`B${i}`, "B", i, B_INNER, B_OUTER, B_HALF, nowMs, false);
    }
    for (let i = 1; i <= 8; i++) {
      this.drawDiamondPad(`E${i}`, E_SIZE, nowMs, false);
    }
    for (let i = 1; i <= 8; i++) {
      this.drawWedgePad(`D${i}`, "D", i, D_INNER, D_OUTER, OUTER_HALF, nowMs, false);
    }
    for (let i = 1; i <= 8; i++) {
      this.drawWedgePad(`A${i}`, "A", i, A_INNER, A_OUTER, OUTER_HALF, nowMs, false);
    }
    ctx.restore();

    // Labels full-opacity on top. Skip A* — those live on the 3D bezel buttons.
    this.drawCenterC(nowMs, true);
    for (let i = 1; i <= 8; i++) {
      this.drawSensorLabel(`B${i}`);
    }
    for (let i = 1; i <= 8; i++) {
      this.drawSensorLabel(`E${i}`);
    }
    for (let i = 1; i <= 8; i++) {
      this.drawSensorLabel(`D${i}`);
    }

    this.drawAllSlidePaths();

    for (const note of this.active) {
      this.drawNote(note);
    }
  }

  private drawSensorLabel(sensor: string): void {
    const { ctx } = this;
    const p = padPoint(sensor);
    let x = p.x;
    let y = p.y;
    const area = sensor[0];
    if (area === "D") {
      // Sit in the wedge body, clear of the A bezel.
      const inward = 0.78;
      x = CENTER + (p.x - CENTER) * (inward / RADIUS.D);
      y = CENTER + (p.y - CENTER) * (inward / RADIUS.D);
    }
    const size = area === "E" ? Math.round(13 * S) : Math.round(15 * S);
    ctx.font = `700 ${size}px 'IBM Plex Mono', monospace`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = COLORS.textBright;
    ctx.shadowColor = COLORS.textStroke;
    ctx.shadowBlur = 4 * S;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 0;
    ctx.fillText(sensor, x, y);
    ctx.shadowBlur = 0;
  }

  private drawGuideRings(): void {
    const { ctx } = this;
    ctx.strokeStyle = COLORS.guide;
    ctx.lineWidth = 1.25 * S;
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
      return { fill: "rgba(28, 58, 72, 1)", stroke: COLORS.padStroke, glow: 10, bright: true };
    }
    if (aimed) {
      return { fill: "rgba(21, 40, 58, 1)", stroke: COLORS.aim, glow: 6, bright: true };
    }
    if (active) {
      return { fill: "rgba(20, 50, 58, 1)", stroke: COLORS.active, glow: 4, bright: true };
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
    half: number,
    nowMs: number,
    labelsOnly: boolean,
  ): void {
    if (labelsOnly) return;
    const { ctx } = this;
    const mid = sensorAngleRad(area, index);
    // Canvas arcs: angle increases clockwise from +X. Math angles use y-up, so
    // canvasAngle = -mathAngle. Sweep clockwise from mid-half to mid+half.
    const aStart = -(mid - half);
    const aEnd = -(mid + half);
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
    ctx.lineWidth = 2 * S;
    ctx.stroke();
  }

  private drawDiamondPad(
    sensor: string,
    sizeUnit: number,
    nowMs: number,
    labelsOnly: boolean,
  ): void {
    if (labelsOnly) return;
    const { ctx } = this;
    const p = padPoint(sensor);
    const s = sizeUnit * OUTER_R;
    const style = this.highlightStyle(sensor, nowMs);
    const path = () => {
      ctx.beginPath();
      ctx.moveTo(p.x, p.y - s);
      ctx.lineTo(p.x + s * 0.75, p.y);
      ctx.lineTo(p.x, p.y + s);
      ctx.lineTo(p.x - s * 0.75, p.y);
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
    ctx.lineWidth = 2 * S;
    ctx.stroke();
  }

  private drawCenterC(nowMs: number, labelsOnly: boolean): void {
    const { ctx } = this;
    const r = C_R * OUTER_R;
    const style = this.highlightStyle("C", nowMs);
    // Flattened octagon matching DX pad art.
    const path = () => {
      ctx.beginPath();
      for (let i = 0; i < 8; i++) {
        const a = (i + 0.5) * (Math.PI / 4) - Math.PI / 2;
        const px = CENTER + Math.cos(a) * r;
        const py = CENTER + Math.sin(a) * r;
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.closePath();
    };

    if (!labelsOnly) {
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
      ctx.lineWidth = 2.5 * S;
      ctx.stroke();

      // Visual C1 (right) / C2 (left) split
      ctx.beginPath();
      ctx.moveTo(CENTER, CENTER - r * 0.92);
      ctx.lineTo(CENTER, CENTER + r * 0.92);
      ctx.strokeStyle = COLORS.cSplit;
      ctx.lineWidth = 1.5 * S;
      ctx.stroke();
      return;
    }

    ctx.font = `700 ${Math.round(14 * S)}px 'IBM Plex Mono', monospace`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = COLORS.textBright;
    ctx.shadowColor = COLORS.textStroke;
    ctx.shadowBlur = 4 * S;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 0;
    ctx.fillText("C1", CENTER + r * 0.42, CENTER);
    ctx.fillText("C2", CENTER - r * 0.42, CENTER);
    ctx.shadowBlur = 0;
  }

  private drawAllSlidePaths(): void {
    const paths: string[][] = [...this.slidePaths];
    // Active slide notes draw their own dashed path + trail in drawNote.
    for (const note of this.active) {
      if (note.type === "slide") continue;
      const p = notePath(note);
      if (p) paths.push(p);
    }
    for (const path of paths) {
      this.drawSlidePolyline(path);
    }
  }

  private drawSlidePolyline(sensors: string[], progress = 0): void {
    if (sensors.length < 2) return;
    const { ctx } = this;
    const pts = sensors.map((s) => {
      const id = normalizeSensor(s);
      return padPoint(id === "C" ? "C" : id);
    });

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

    // Filled trail up to current progress.
    if (progress > 0.01) {
      const pos = pointAlong(pts, Math.min(1, progress));
      ctx.save();
      ctx.strokeStyle = "rgba(61, 224, 208, 0.55)";
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
  }

  private drawNote(note: ActiveNote): void {
    const { ctx } = this;
    const progress = Math.min(1, Math.max(0, note.progress));
    const sensor = resolveNoteSensor(note);
    const touch = isTouchType(note.type);
    const hold = note.type === "hold" || note.type === "touch_hold";
    const slide = note.type === "slide";
    const target = padPoint(sensor);

    const fill = noteColor(note);
    const ring =
      note.is_ex
        ? "#ffffff"
        : note.is_each && !note.is_break
          ? "#f0d24b"
          : "rgba(255,255,255,0.55)";

    let x: number;
    let y: number;
    let r: number;

    if (touch) {
      x = target.x;
      y = target.y;
      r = NOTE_R * (0.35 + 0.65 * progress);
    } else if (slide && note.path && note.path.length > 1) {
      const raw = Math.min(1, Math.max(0, note.progress));
      const pts = note.path.map((s) => {
        const id = normalizeSensor(s);
        return padPoint(id === "C" ? "C" : id);
      });
      let x: number;
      let y: number;
      let pathProg = 0;
      if (raw < 0.5) {
        // Approach head from center (progress 0..0.5).
        const head = pts[0];
        const u = raw / 0.5;
        x = CENTER + (head.x - CENTER) * u;
        y = CENTER + (head.y - CENTER) * u;
        this.drawSlidePolyline(note.path, 0);
      } else {
        // Travel along dashed path (progress 0.5..1).
        pathProg = (raw - 0.5) / 0.5;
        this.drawSlidePolyline(note.path, pathProg);
        const along = pointAlong(pts, pathProg);
        x = along.x;
        y = along.y;
      }
      const r = NOTE_R * 0.85;
      this.drawStar(x, y, r, fill, ring, note.is_break === true);
      if (note.is_hanabi) this.drawHanabi(x, y, r);
      return;
    } else {
      x = CENTER + (target.x - CENTER) * progress;
      y = CENTER + (target.y - CENTER) * progress;
      r = NOTE_R * (0.55 + 0.45 * progress);
    }

    if (hold) {
      // Trail from center (or spawn) toward target, then fill sensor pad.
      ctx.beginPath();
      ctx.strokeStyle = fill;
      ctx.lineWidth = 6;
      ctx.globalAlpha = 0.45;
      ctx.moveTo(CENTER, CENTER);
      ctx.lineTo(x, y);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(target.x, target.y, NOTE_R * 0.9, 0, Math.PI * 2);
      ctx.strokeStyle = fill;
      ctx.lineWidth = 3;
      ctx.stroke();
    }

    if (touch) {
      // Diamond touch note
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(Math.PI / 4);
      ctx.fillStyle = fill;
      ctx.fillRect(-r * 0.75, -r * 0.75, r * 1.5, r * 1.5);
      ctx.strokeStyle = ring;
      ctx.lineWidth = note.is_ex ? 3 : 2;
      ctx.strokeRect(-r * 0.75, -r * 0.75, r * 1.5, r * 1.5);
      ctx.restore();
    } else if (note.is_star || note.head_style === "star") {
      this.drawStar(x, y, r, fill, ring, note.is_break === true);
    } else {
      ctx.beginPath();
      ctx.arc(x, y, r + 4, 0, Math.PI * 2);
      ctx.fillStyle = `${fill}33`;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = fill;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(x, y, r * 0.35, 0, Math.PI * 2);
      ctx.fillStyle = note.is_break ? "#fff4d0" : COLORS.noteCore;
      ctx.fill();

      ctx.strokeStyle = ring;
      ctx.lineWidth = note.is_ex ? 3.5 : 2;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.stroke();
    }

    if (note.is_hanabi) this.drawHanabi(x, y, r);
    if (note.is_mine) {
      ctx.fillStyle = "#111";
      ctx.font = "700 12px 'IBM Plex Mono', monospace";
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
    brk: boolean,
  ): void {
    const { ctx } = this;
    const spikes = 4;
    const outer = r;
    const inner = r * 0.42;
    ctx.beginPath();
    for (let i = 0; i < spikes * 2; i++) {
      const rad = (i * Math.PI) / spikes - Math.PI / 2;
      const rr = i % 2 === 0 ? outer : inner;
      const px = x + Math.cos(rad) * rr;
      const py = y + Math.sin(rad) * rr;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = brk ? "#ffe08a" : stroke;
    ctx.lineWidth = 2.5;
    ctx.stroke();
  }

  private drawHanabi(x: number, y: number, r: number): void {
    const { ctx } = this;
    ctx.save();
    ctx.strokeStyle = "rgba(255, 180, 90, 0.75)";
    ctx.lineWidth = 1.5;
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

function noteColor(note: ActiveNote): string {
  if (note.is_mine) return "#5a2030";
  if (note.is_break) return "#f0a020";
  if (note.is_each) return "#e8d24a";
  if (note.type === "touch" || note.type === "touch_hold") return "#6ec8ff";
  if (note.type === "hold") return "#3de0d0";
  if (note.type === "slide") return "#ff7ad9";
  return COLORS.note;
}

function pointAlong(
  pts: Array<{ x: number; y: number }>,
  t: number,
): { x: number; y: number } {
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
