import { sensorXY, toCanvas } from "../sensors";
import { CENTER, COLORS, HAND_TRAIL, OUTER_R, S } from "./theme";
import type { HandSample } from "./types";

/** Idle homes on the unit disk: left A6, right A3. */
export const HOME_L = sensorXY("A6");
export const HOME_R = sensorXY("A3");

export function resolveHand(
  xy: [number, number] | null,
  home: { x: number; y: number },
): { x: number; y: number } {
  if (xy) return { x: xy[0], y: xy[1] };
  return home;
}

export function pushTrail(
  trail: HandSample[],
  sample: HandSample,
): void {
  trail.push(sample);
  if (trail.length > HAND_TRAIL) trail.shift();
}

export function trailSettled(
  trail: HandSample[],
  pos: { x: number; y: number },
  strike: number,
): boolean {
  if (trail.length < HAND_TRAIL) return false;
  return trail.every(
    (sample) => sample.x === pos.x && sample.y === pos.y && sample.strike === strike,
  );
}

export function drawHandTips(
  ctx: CanvasRenderingContext2D,
  left: { x: number; y: number },
  right: { x: number; y: number },
  strikeL: number,
  strikeR: number,
  trailL: HandSample[],
  trailR: HandSample[],
): void {
  drawHandTrail(ctx, trailL, COLORS.handL);
  drawHandTrail(ctx, trailR, COLORS.handR);
  drawHandDisc(ctx, left, strikeL, COLORS.handL);
  drawHandDisc(ctx, right, strikeR, COLORS.handR);
}

function drawHandTrail(
  ctx: CanvasRenderingContext2D,
  trail: HandSample[],
  color: string,
): void {
  const n = trail.length;
  for (let i = 0; i < n; i++) {
    const sample = trail[i];
    const u = (i + 1) / n;
    const p = toCanvas(sample.x, sample.y, CENTER, OUTER_R);
    const r = (2.2 + 3.4 * u) * S * (0.55 + 0.45 * sample.strike);
    ctx.save();
    ctx.globalAlpha = (0.08 + 0.22 * u) * (0.35 + 0.65 * sample.strike);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
}

function drawHandDisc(
  ctx: CanvasRenderingContext2D,
  unit: { x: number; y: number },
  strike: number,
  color: string,
): void {
  const p = toCanvas(unit.x, unit.y, CENTER, OUTER_R);
  const r = (6.5 + 7.5 * strike) * S;
  ctx.save();
  ctx.globalAlpha = 0.28 + 0.62 * strike;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 0.2 + 0.7 * strike;
  ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
  ctx.lineWidth = 1.4 * S;
  ctx.stroke();
  ctx.restore();
}