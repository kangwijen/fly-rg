import { PAD, RADIUS, sensorAngleRad, toCanvas } from "../sensors";
import { padPoint } from "./geometry";
import { normalizeSensor } from "./note-model";
import { CENTER, COLORS, FLASH_MS, OUTER_R, OUTER_STEPS, S, SIZE } from "./theme";
import type { Flash, HighlightStyle } from "./types";

export type PadHighlightInput = {
  flashes: Flash[];
  aimSensor: string | null;
  tapSensor: string | null;
  tapping: boolean;
  activeSensors: string[];
};

const DEFAULT_STYLE: HighlightStyle = {
  fill: COLORS.pad,
  stroke: COLORS.padMuted,
  glow: 0,
};

export function createStaticPadLayer(): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas2D unavailable");
  drawDefaultPads(ctx);
  drawAllSensorLabels(ctx);
  return canvas;
}

export function drawPadHighlights(
  ctx: CanvasRenderingContext2D,
  nowMs: number,
  input: PadHighlightInput,
): void {
  const highlighted: string[] = [];
  ctx.save();
  ctx.beginPath();
  ctx.arc(CENTER, CENTER, OUTER_R, 0, Math.PI * 2);
  ctx.clip();
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  visitPads(ctx, (sensor, muted, path) => {
    const style = highlightStyle(sensor, nowMs, input);
    if (isDefaultStyle(style)) return;
    fillPad(ctx, path, style, muted);
    highlighted.push(sensor);
  });
  ctx.restore();
  for (const sensor of highlighted) {
    drawSensorLabel(ctx, sensor);
  }
}

function drawDefaultPads(ctx: CanvasRenderingContext2D): void {
  ctx.save();
  ctx.beginPath();
  ctx.arc(CENTER, CENTER, OUTER_R, 0, Math.PI * 2);
  ctx.clip();
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  drawGuides(ctx);
  visitPads(ctx, (_sensor, muted, path) => {
    fillPad(ctx, path, DEFAULT_STYLE, muted);
  });
  ctx.restore();
}

function drawAllSensorLabels(ctx: CanvasRenderingContext2D): void {
  drawSensorLabel(ctx, "C");
  for (let i = 1; i <= 8; i++) drawSensorLabel(ctx, `A${i}`);
  for (let i = 1; i <= 8; i++) drawSensorLabel(ctx, `B${i}`);
  for (let i = 1; i <= 8; i++) drawSensorLabel(ctx, `D${i}`);
  for (let i = 1; i <= 8; i++) drawSensorLabel(ctx, `E${i}`);
}

function drawSensorLabel(ctx: CanvasRenderingContext2D, sensor: string): void {
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

function drawGuides(ctx: CanvasRenderingContext2D): void {
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

function visitPads(
  ctx: CanvasRenderingContext2D,
  visit: (sensor: string, muted: boolean, path: () => void) => void,
): void {
  for (let i = 1; i <= 8; i++) {
    const sensor = `D${i}`;
    visit(sensor, true, () => adWedgePath(ctx, "D", i));
  }
  for (let i = 1; i <= 8; i++) {
    const sensor = `A${i}`;
    visit(sensor, false, () => adWedgePath(ctx, "A", i));
  }
  for (let i = 1; i <= 8; i++) {
    const sensor = `E${i}`;
    visit(sensor, true, () => eDiamondPath(ctx, i));
  }
  for (let i = 1; i <= 8; i++) {
    const sensor = `B${i}`;
    visit(sensor, false, () => bOctagonPath(ctx, i));
  }
  visit("C", false, () => cOctagonPath(ctx));
}

function fillPad(
  ctx: CanvasRenderingContext2D,
  path: () => void,
  style: HighlightStyle,
  muted: boolean,
): void {
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
}

function highlightStyle(
  sensor: string,
  nowMs: number,
  input: PadHighlightInput,
): HighlightStyle {
  const key = normalizeSensor(sensor);
  const flash = input.flashes.find((f) => f.sensor === key);
  const aimed = input.aimSensor === key;
  const tapped = input.tapping && input.tapSensor === key;
  const active = input.activeSensors.includes(key);

  if (flash) {
    const life = Math.max(0, (flash.until - nowMs) / FLASH_MS);
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
  return DEFAULT_STYLE;
}

function isDefaultStyle(style: HighlightStyle): boolean {
  return (
    style.glow === 0 &&
    style.fill === DEFAULT_STYLE.fill &&
    style.stroke === DEFAULT_STYLE.stroke
  );
}

function adWedgePath(
  ctx: CanvasRenderingContext2D,
  area: "A" | "D",
  index: number,
): void {
  const mid = sensorAngleRad(area, index);
  switch (area) {
    case "A":
      wedgePath(ctx, mid, PAD.adHalf, PAD.adInner, PAD.adOuter);
      return;
    case "D":
      wedgePath(ctx, mid, PAD.dHalf, PAD.dInner, PAD.dOuter);
      return;
    default: {
      const _never: never = area;
      throw new Error(`unhandled wedge ${_never}`);
    }
  }
}

function wedgePath(
  ctx: CanvasRenderingContext2D,
  mid: number,
  half: number,
  innerR: number,
  outerR: number,
): void {
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

function cOctagonPath(ctx: CanvasRenderingContext2D): void {
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

function bOctagonPath(ctx: CanvasRenderingContext2D, index: number): void {
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

function eDiamondPath(ctx: CanvasRenderingContext2D, index: number): void {
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
