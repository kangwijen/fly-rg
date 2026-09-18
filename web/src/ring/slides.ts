import type { ActiveNote } from "../protocol";
import { buttonToSensor } from "../sensors";
import {
  landingPoint,
  padPoint,
  pointAlong,
  pointAtDist,
  polylineLen,
  tapTravel,
} from "./geometry";
import { lerpPt, clamp01 } from "./math";
import {
  isWifiSlide,
  normalizeSensor,
  noteColor,
  notePath,
  noteRing,
  resolveNoteSensor,
  wifiStartButton,
  wrapButton,
} from "./note-model";
import { drawNoteMarks, drawStar } from "./notes";
import { CENTER, COLORS, NOTE_R, S } from "./theme";
import type { Pt } from "./types";

export function drawAllSlidePaths(
  ctx: CanvasRenderingContext2D,
  slidePaths: string[][],
  active: ActiveNote[],
): void {
  const paths: string[][] = [...slidePaths];
  for (const note of active) {
    if (note.type === "slide") continue;
    const p = notePath(note);
    if (p) paths.push(p);
  }
  for (const path of paths) {
    drawSlidePolyline(ctx, path);
  }
}

export function drawWifiGroups(
  ctx: CanvasRenderingContext2D,
  active: ActiveNote[],
  nowMs: number,
): Set<ActiveNote> {
  const drawn = new Set<ActiveNote>();
  const groups = new Map<string, ActiveNote[]>();
  for (const note of active) {
    if (!isWifiSlide(note)) continue;
    const start = wifiStartButton(note);
    if (start == null) continue;
    const key = `${note.t}|${start}`;
    const bucket = groups.get(key);
    if (bucket) bucket.push(note);
    else groups.set(key, [note]);
  }
  for (const notes of groups.values()) {
    const start = wifiStartButton(notes[0]);
    if (start == null) continue;
    drawWifiFan(ctx, notes, start, nowMs);
    for (const note of notes) drawn.add(note);
  }
  return drawn;
}

export function drawSlideNote(
  ctx: CanvasRenderingContext2D,
  note: ActiveNote,
  nowMs: number,
  fill: string,
  ring: string,
): void {
  const path = notePath(note);
  if (path && path.length > 1) {
    const raw = clamp01(note.progress);
    const pts = path.map((s) => padPoint(normalizeSensor(s)));
    let x: number;
    let y: number;
    if (raw < 0.5) {
      const head = pts[0];
      const u = raw / 0.5;
      x = CENTER + (head.x - CENTER) * u;
      y = CENTER + (head.y - CENTER) * u;
      drawSlidePolyline(ctx, path, 0);
    } else {
      const pathProg = (raw - 0.5) / 0.5;
      drawSlidePolyline(ctx, path, pathProg);
      const along = pointAlong(pts, pathProg);
      x = along.x;
      y = along.y;
    }
    const r = NOTE_R * (0.7 + 0.3 * Math.min(1, raw / 0.5));
    const spin = (nowMs / 1000) * Math.PI;
    drawStar(ctx, x, y, r, fill, ring, note, spin);
    drawNoteMarks(ctx, note, x, y, r);
    return;
  }
  const sensor = resolveNoteSensor(note);
  const target = landingPoint(sensor);
  const travel = tapTravel(target, clamp01(note.progress));
  drawStar(
    ctx,
    travel.pos.x,
    travel.pos.y,
    travel.r,
    fill,
    ring,
    note,
    (nowMs / 1000) * Math.PI,
  );
  drawNoteMarks(ctx, note, travel.pos.x, travel.pos.y, travel.r);
}

function drawSlidePolyline(
  ctx: CanvasRenderingContext2D,
  sensors: string[],
  progress = 0,
  arrows = true,
): void {
  if (sensors.length < 2) return;
  const pts = sensors.map((s) => padPoint(normalizeSensor(s)));

  // Soft underglow only; the arrow chain is the visible path.
  ctx.save();
  ctx.strokeStyle = COLORS.slide;
  ctx.lineWidth = NOTE_R * 0.55;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.globalAlpha = 0.28;
  ctx.shadowColor = COLORS.slide;
  ctx.shadowBlur = NOTE_R * 0.55;
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  for (let i = 1; i < pts.length; i++) {
    ctx.lineTo(pts[i].x, pts[i].y);
  }
  ctx.stroke();
  ctx.restore();

  if (progress > 0.01) {
    const pos = pointAlong(pts, Math.min(1, progress));
    ctx.save();
    ctx.strokeStyle = "rgba(255, 122, 217, 0.45)";
    ctx.lineWidth = NOTE_R * 0.7;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
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

  if (arrows) drawSlideArrows(ctx, pts, progress);
}

function drawSlideArrows(ctx: CanvasRenderingContext2D, pts: Pt[], progress: number): void {
  const total = polylineLen(pts);
  if (total < 8) return;
  const spacing = NOTE_R * 0.78;
  const traveled = clamp01(progress) * total;
  for (let d = spacing * 0.35; d < total - spacing * 0.15; d += spacing) {
    const sample = pointAtDist(pts, d);
    drawArrowTick(ctx, sample.x, sample.y, sample.ang, NOTE_R * 0.72, d <= traveled);
  }
}

function drawArrowTick(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  ang: number,
  size: number,
  passed: boolean,
): void {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(ang);
  ctx.globalAlpha = passed ? 0.32 : 0.98;
  ctx.beginPath();
  ctx.moveTo(size * 0.82, 0);
  ctx.lineTo(-size * 0.52, size * 0.58);
  ctx.lineTo(-size * 0.16, 0);
  ctx.lineTo(-size * 0.52, -size * 0.58);
  ctx.closePath();
  ctx.fillStyle = passed ? COLORS.slide : "#ffe6f4";
  ctx.fill();
  ctx.strokeStyle = COLORS.slide;
  ctx.lineWidth = Math.max(2, size * 0.12);
  ctx.lineJoin = "round";
  ctx.stroke();
  ctx.restore();
}

function drawWifiFan(
  ctx: CanvasRenderingContext2D,
  notes: ActiveNote[],
  startButton: number,
  nowMs: number,
): void {
  const start = landingPoint(buttonToSensor(startButton));
  const endL = landingPoint(buttonToSensor(wrapButton(startButton, -3)));
  const endC = landingPoint(buttonToSensor(wrapButton(startButton, 4)));
  const endR = landingPoint(buttonToSensor(wrapButton(startButton, 3)));
  const ends = [endL, endC, endR];
  const lead = notes.reduce((a, b) => (a.progress >= b.progress ? a : b));
  const fill = noteColor(lead);
  const ring = noteRing(lead);
  const raw = clamp01(lead.progress);
  drawWifiTrail(ctx, start, endL, endC, endR, fill, raw);

  const spin = (nowMs / 1000) * Math.PI;
  if (raw < 0.5) {
    const u = raw / 0.5;
    const head = {
      x: CENTER + (start.x - CENTER) * u,
      y: CENTER + (start.y - CENTER) * u,
    };
    const r = NOTE_R * (0.7 + 0.3 * u);
    drawStar(ctx, head.x, head.y, r, fill, ring, lead, spin);
    drawNoteMarks(ctx, lead, head.x, head.y, r);
    return;
  }

  const pathProg = (raw - 0.5) / 0.5;
  const endButtons = [
    wrapButton(startButton, -3),
    wrapButton(startButton, 4),
    wrapButton(startButton, 3),
  ];
  for (let i = 0; i < 3; i++) {
    const end = ends[i];
    const lane = notes.find((n) => {
      const path = notePath(n);
      return path?.[path.length - 1] === `A${endButtons[i]}`;
    });
    const src = lane ?? lead;
    const travel = lane ? clamp01((lane.progress - 0.5) / 0.5) : pathProg;
    const pos = lerpPt(start, end, travel);
    const ang = Math.atan2(end.y - start.y, end.x - start.x);
    drawStar(ctx, pos.x, pos.y, NOTE_R, fill, noteRing(src), src, ang + spin * 0.15);
  }
}

function drawWifiTrail(
  ctx: CanvasRenderingContext2D,
  start: Pt,
  endL: Pt,
  endC: Pt,
  endR: Pt,
  fill: string,
  raw: number,
): void {
  const travel = raw < 0.5 ? 0 : (raw - 0.5) / 0.5;
  const fade = raw < 0.5 ? Math.max(0.2, raw / 0.5) : 1;
  const bars = 11;
  ctx.save();
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  for (let i = 0; i < bars; i++) {
    const t = (i + 0.5) / bars;
    const tip = lerpPt(start, endC, Math.min(1, t + 0.045));
    const left = lerpPt(start, endL, t);
    const right = lerpPt(start, endR, t);
    const back = lerpPt(start, endC, Math.max(0, t - 0.028));
    const passed = travel > t;
    ctx.globalAlpha = fade * (passed ? 0.28 : 0.92);
    ctx.beginPath();
    ctx.moveTo(tip.x, tip.y);
    ctx.lineTo(left.x, left.y);
    ctx.lineTo(back.x, back.y);
    ctx.lineTo(right.x, right.y);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.55)";
    ctx.lineWidth = 1.4 * S;
    ctx.stroke();
  }
  ctx.restore();
}
