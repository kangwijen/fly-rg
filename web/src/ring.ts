import type { ActiveNote, Judgment } from "./protocol";

const SIZE = 512;
const CENTER = SIZE / 2;
const OUTER_R = 220;
const SENSOR_R = 28;
const NOTE_R = 18;
const SENSOR_DIST = 168;

const COLORS = {
  bg: "#070b14",
  ring: "#1a2740",
  ringGlow: "#2a3f63",
  sensor: "#132033",
  sensorStroke: "#3de0d0",
  note: "#e24f9c",
  noteCore: "#ffe6f4",
  guide: "rgba(61, 224, 208, 0.18)",
  text: "#8aa0b8",
};

const JUDGMENT_COLORS: Record<Judgment, string> = {
  perfect: "#3de0d0",
  great: "#5ad67a",
  good: "#f0b429",
  miss: "#ff5a6a",
};

interface Flash {
  button: number;
  color: string;
  until: number;
}

function buttonAngle(button: number): number {
  // Button 1 at top, then clockwise for 2..8
  return -Math.PI / 2 + ((button - 1) % 8) * (Math.PI / 4);
}

function sensorPos(button: number): { x: number; y: number } {
  const a = buttonAngle(button);
  return {
    x: CENTER + Math.cos(a) * SENSOR_DIST,
    y: CENTER + Math.sin(a) * SENSOR_DIST,
  };
}

export class RingDisplay {
  readonly canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private active: ActiveNote[] = [];
  private flashes: Flash[] = [];
  private aimButton: number | null = null;
  private tapButton: number | null = null;
  private tapping = false;

  constructor() {
    this.canvas = document.createElement("canvas");
    this.canvas.width = SIZE;
    this.canvas.height = SIZE;
    const ctx = this.canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas2D unavailable");
    this.ctx = ctx;
  }

  setActive(notes: ActiveNote[]): void {
    this.active = notes;
  }

  setAim(button: number | null, tap: boolean, tapButton: number | null): void {
    this.aimButton = button;
    this.tapping = tap;
    this.tapButton = tapButton;
  }

  flashHit(button: number, judgment: Judgment, nowMs = performance.now()): void {
    this.flashes.push({
      button,
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

    const grad = ctx.createRadialGradient(CENTER, CENTER, 20, CENTER, CENTER, OUTER_R);
    grad.addColorStop(0, "#0c1524");
    grad.addColorStop(1, "#05070c");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, OUTER_R, 0, Math.PI * 2);
    ctx.fill();

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

    ctx.strokeStyle = COLORS.guide;
    ctx.lineWidth = 1.5;
    for (let b = 1; b <= 8; b++) {
      const p = sensorPos(b);
      ctx.beginPath();
      ctx.moveTo(CENTER, CENTER);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
    }

    for (let b = 1; b <= 8; b++) {
      this.drawSensor(b, nowMs);
    }

    for (const note of this.active) {
      this.drawNote(note);
    }

    ctx.fillStyle = COLORS.text;
    ctx.font = "600 14px 'IBM Plex Mono', monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("maimai", CENTER, CENTER);
  }

  private drawSensor(button: number, nowMs: number): void {
    const { ctx } = this;
    const p = sensorPos(button);
    const flash = this.flashes.find((f) => f.button === button);
    const aimed = this.aimButton === button;
    const tapped = this.tapping && this.tapButton === button;

    let fill = COLORS.sensor;
    let stroke = COLORS.sensorStroke;
    let glow = 0;

    if (flash) {
      const life = Math.max(0, (flash.until - nowMs) / 280);
      fill = flash.color;
      stroke = flash.color;
      glow = 18 * life;
    } else if (tapped) {
      fill = "#1c3a48";
      stroke = "#3de0d0";
      glow = 10;
    } else if (aimed) {
      fill = "#15283a";
      stroke = "#e24f9c";
      glow = 6;
    }

    if (glow > 0) {
      ctx.save();
      ctx.shadowColor = stroke;
      ctx.shadowBlur = glow;
      ctx.beginPath();
      ctx.arc(p.x, p.y, SENSOR_R, 0, Math.PI * 2);
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.restore();
    } else {
      ctx.beginPath();
      ctx.arc(p.x, p.y, SENSOR_R, 0, Math.PI * 2);
      ctx.fillStyle = fill;
      ctx.fill();
    }

    ctx.beginPath();
    ctx.arc(p.x, p.y, SENSOR_R, 0, Math.PI * 2);
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 2.5;
    ctx.stroke();

    ctx.fillStyle = aimed || flash ? "#e8f4ff" : COLORS.text;
    ctx.font = "600 16px 'Space Grotesk', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(button), p.x, p.y);
  }

  private drawNote(note: ActiveNote): void {
    const { ctx } = this;
    const progress = Math.min(1, Math.max(0, note.progress));
    const a = buttonAngle(note.button);
    const dist = progress * SENSOR_DIST;
    const x = CENTER + Math.cos(a) * dist;
    const y = CENTER + Math.sin(a) * dist;
    const r = NOTE_R * (0.55 + 0.45 * progress);

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
}
