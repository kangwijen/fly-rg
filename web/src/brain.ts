import type { BrainLayoutMessage, Drive } from "./protocol";

const SIZE = 520;

const COLORS = {
  panel: "#0c121c",
  base: "rgba(140, 165, 190, 0.16)",
  spike: "#ffb23e",
  loom: "#ff5a6a",
  threat: "#e24f9c",
  chase: "#3de0d0",
  cmd: "#6cf08a",
  text: "#d7e6f2",
  dim: "#7f94a8",
};

export class BrainView {
  readonly canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private layout: BrainLayoutMessage | null = null;
  private base: HTMLCanvasElement | null = null;
  private glow: HTMLCanvasElement | null = null;
  private spikeTotal = 0;
  private lastSpikes: number[] = [];
  private drive: Drive = {
    loomL: 0,
    loomR: 0,
    chaseL: 0,
    chaseR: 0,
    threatL: 0,
    threatR: 0,
  };

  constructor() {
    this.canvas = document.createElement("canvas");
    this.canvas.width = SIZE;
    this.canvas.height = SIZE;
    this.canvas.className = "brain-canvas";
    const ctx = this.canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas2D unavailable");
    this.ctx = ctx;
  }

  setLayout(layout: BrainLayoutMessage): void {
    this.layout = layout;
    this.base = document.createElement("canvas");
    this.base.width = SIZE;
    this.base.height = SIZE;
    this.glow = document.createElement("canvas");
    this.glow.width = SIZE;
    this.glow.height = SIZE;

    const g = this.base.getContext("2d");
    if (!g) return;
    g.fillStyle = COLORS.panel;
    g.fillRect(0, 0, SIZE, SIZE);
    g.fillStyle = COLORS.base;
    for (let i = 0; i < layout.x.length; i++) {
      const x = layout.x[i] * SIZE;
      const y = layout.y[i] * SIZE;
      g.fillRect(x - 0.8, y - 0.8, 1.7, 1.7);
    }
  }

  setState(spikes: number[], spikeTotal: number, drive: Drive): void {
    this.lastSpikes = spikes;
    this.spikeTotal = spikeTotal;
    this.drive = drive;
  }

  draw(): void {
    const { ctx } = this;
    ctx.fillStyle = COLORS.panel;
    ctx.fillRect(0, 0, SIZE, SIZE);

    if (!this.layout || !this.base || !this.glow) {
      ctx.fillStyle = COLORS.dim;
      ctx.font = "500 14px 'IBM Plex Mono', monospace";
      ctx.textAlign = "center";
      ctx.fillText("waiting for brain layout", SIZE / 2, SIZE / 2);
      return;
    }

    const g = this.glow.getContext("2d");
    if (!g) return;
    g.globalCompositeOperation = "destination-out";
    g.fillStyle = "rgba(0,0,0,0.38)";
    g.fillRect(0, 0, SIZE, SIZE);
    g.globalCompositeOperation = "source-over";
    g.fillStyle = COLORS.spike;
    for (const i of this.lastSpikes) {
      const x = this.layout.x[i] * SIZE;
      const y = this.layout.y[i] * SIZE;
      g.fillRect(x - 1.2, y - 1.2, 2.6, 2.6);
    }

    ctx.drawImage(this.base, 0, 0);
    ctx.drawImage(this.glow, 0, 0);

    this.tintGroup("loomL", COLORS.loom, this.drive.loomL);
    this.tintGroup("loomR", COLORS.loom, this.drive.loomR);
    this.tintGroup("threatL", COLORS.threat, this.drive.threatL);
    this.tintGroup("threatR", COLORS.threat, this.drive.threatR);
    this.tintGroup("chaseL", COLORS.chase, this.drive.chaseL);
    this.tintGroup("chaseR", COLORS.chase, this.drive.chaseR);

    const aimOnL = this.drive.chaseL + this.drive.loomL > this.drive.chaseR + this.drive.loomR;
    this.markCommand("dna02L", aimOnL && this.drive.chaseL + this.drive.loomL > 0.15);
    this.markCommand("dna02R", !aimOnL && this.drive.chaseR + this.drive.loomR > 0.15);
    const threat = Math.max(this.drive.threatL, this.drive.threatR);
    this.markCommand("dnp01L", threat > 0.35 && aimOnL);
    this.markCommand("dnp01R", threat > 0.35 && !aimOnL);

    ctx.fillStyle = COLORS.dim;
    ctx.font = "600 11px 'IBM Plex Mono', monospace";
    ctx.textAlign = "left";
    ctx.fillText("NERVOUS SYSTEM", 14, 22);
    ctx.textAlign = "right";
    ctx.fillText(`${this.spikeTotal} spikes/frame`, SIZE - 14, 22);
  }

  private tintGroup(key: string, color: string, amount: number): void {
    if (!this.layout || amount <= 0) return;
    const ids = this.layout.groups[key] || [];
    const { ctx } = this;
    ctx.globalAlpha = Math.min(1, amount * 1.2);
    ctx.fillStyle = color;
    for (const i of ids) {
      const x = this.layout.x[i] * SIZE;
      const y = this.layout.y[i] * SIZE;
      ctx.fillRect(x - 1.4, y - 1.4, 3, 3);
    }
    ctx.globalAlpha = 1;
  }

  private markCommand(key: string, on: boolean): void {
    if (!this.layout) return;
    const ids = this.layout.groups[key] || [];
    if (!ids.length) return;
    const { ctx } = this;
    const i = ids[0];
    const x = this.layout.x[i] * SIZE;
    const y = this.layout.y[i] * SIZE;
    ctx.beginPath();
    ctx.arc(x, y, on ? 9 : 5, 0, Math.PI * 2);
    ctx.fillStyle = on ? COLORS.cmd : "rgba(108, 240, 138, 0.22)";
    ctx.fill();
    ctx.strokeStyle = COLORS.cmd;
    ctx.lineWidth = 1.4;
    ctx.stroke();

    if (!on) return;
    const label = this.layout.labels[key] || key;
    ctx.fillStyle = COLORS.text;
    ctx.font = "600 12px 'IBM Plex Mono', monospace";
    const left = key.endsWith("L");
    ctx.textAlign = left ? "right" : "left";
    ctx.fillText(label, x + (left ? -12 : 12), y + 4);
  }
}
