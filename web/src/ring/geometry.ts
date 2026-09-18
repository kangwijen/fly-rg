import { noteLandingXY, sensorXY, toCanvas } from "../sensors";
import { clamp01 } from "./math";
import { CENTER, NOTE_R, OUTER_R } from "./theme";
import type { Pt } from "./types";

export function padPoint(sensor: string): Pt {
  const { x, y } = sensorXY(sensor);
  return toCanvas(x, y, CENTER, OUTER_R);
}

export function landingPoint(sensor: string): Pt {
  const p = noteLandingXY(sensor);
  return toCanvas(p.x, p.y, CENTER, OUTER_R);
}

export function destScale(progress: number): number {
  return progress * 4.8 * 0.4 + 0.51;
}

export function alongRay(target: Pt, t: number): Pt {
  return {
    x: CENTER + (target.x - CENTER) * t,
    y: CENTER + (target.y - CENTER) * t,
  };
}

export function tapTravel(target: Pt, progress: number): { pos: Pt; r: number } {
  const p = clamp01(progress);
  const pos = alongRay(target, p);
  const scale = clamp01(destScale(p));
  return { pos, r: NOTE_R * scale };
}

export function pointAlong(pts: Pt[], t: number): Pt {
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

export function polylineLen(pts: Pt[]): number {
  let n = 0;
  for (let i = 1; i < pts.length; i++) {
    n += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
  }
  return n;
}

export function pointAtDist(
  pts: Pt[],
  dist: number,
): { x: number; y: number; ang: number } {
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
