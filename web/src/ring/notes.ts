import type { ActiveNote } from "../protocol";
import { landingPoint, padPoint, tapTravel } from "./geometry";
import type { HoldTracker } from "./hold-state";
import { clamp01, lerp } from "./math";
import { noteKind, resolveNoteSensor } from "./note-model";
import { CENTER, COLORS, HOLD_INNER_FRAC, lightenHex, NOTE_R, S } from "./theme";
import type { Pt } from "./types";

export function drawTapNote(
  ctx: CanvasRenderingContext2D,
  note: ActiveNote,
  progress: number,
  target: Pt,
  fill: string,
  ring: string,
  nowMs: number,
): void {
  drawTapLine(ctx, target);
  const travel = tapTravel(target, progress);
  const breakSpin = note.is_break ? (nowMs / 1000) * 0.7 : 0;
  if (note.is_star || note.head_style === "star") {
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
  } else {
    drawTapDisk(ctx, travel.pos.x, travel.pos.y, travel.r, fill, ring, note, breakSpin);
  }
  drawNoteMarks(ctx, note, travel.pos.x, travel.pos.y, travel.r);
}

export function drawHold(
  ctx: CanvasRenderingContext2D,
  note: ActiveNote,
  progress: number,
  target: Pt,
  fill: string,
  ring: string,
  holds: HoldTracker,
): void {
  const sustain = holds.isSustain(note, progress);
  const body = sustain ? lightenHex(fill, 0.32) : fill;
  const padDist = Math.hypot(target.x - CENTER, target.y - CENTER);
  const ang = Math.atan2(target.y - CENTER, target.x - CENTER);
  const span = holdSpan(progress, sustain, padDist);

  if (padDist < NOTE_R) {
    drawTapDisk(ctx, CENTER, CENTER, NOTE_R, body, ring, note, 0);
    drawNoteMarks(ctx, note, CENTER, CENTER, NOTE_R);
    return;
  }

  drawTapLine(ctx, target);

  ctx.save();
  ctx.translate(CENTER, CENTER);
  ctx.rotate(ang);
  paintStadium(ctx, span.inner, span.outer, NOTE_R, body, ring, note);
  ctx.restore();

  const innerX = CENTER + Math.cos(ang) * span.inner;
  const innerY = CENTER + Math.sin(ang) * span.inner;
  const headX = CENTER + Math.cos(ang) * span.outer;
  const headY = CENTER + Math.sin(ang) * span.outer;
  drawTapDisk(ctx, innerX, innerY, NOTE_R, body, ring, note, 0);
  drawTapDisk(ctx, headX, headY, NOTE_R, body, ring, note, 0);
  drawNoteMarks(ctx, note, headX, headY, NOTE_R);
}

export function drawTouchHoldNote(
  ctx: CanvasRenderingContext2D,
  note: ActiveNote,
  progress: number,
  target: Pt,
  fill: string,
  ring: string,
  holds: HoldTracker,
): void {
  const sustain = holds.isSustain(note, progress);
  const r = sustain
    ? NOTE_R * Math.max(0.28, 1 - 0.72 * progress)
    : NOTE_R * (0.4 + 0.6 * progress);
  const body = sustain ? lightenHex(fill, 0.32) : fill;
  drawTouchHold(ctx, target.x, target.y, r, body, ring, note, sustain ? 1 : progress);
  drawNoteMarks(ctx, note, target.x, target.y, r);
}

export function drawTouchNote(
  ctx: CanvasRenderingContext2D,
  note: ActiveNote,
  progress: number,
  target: Pt,
  fill: string,
  ring: string,
): void {
  drawTouchFans(ctx, target.x, target.y, progress, fill, ring, note, 0);
  drawNoteMarks(ctx, note, target.x, target.y, NOTE_R);
}

export function noteHeadPoint(
  note: ActiveNote,
  holds: HoldTracker,
): Pt {
  const progress = clamp01(note.progress);
  const sensor = resolveNoteSensor(note);
  const kind = noteKind(note);
  switch (kind) {
    case "hold": {
      const target = landingPoint(sensor);
      const sustain = holds.isSustain(note, progress);
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

export function drawEachLines(
  ctx: CanvasRenderingContext2D,
  notes: ActiveNote[],
  holds: HoldTracker,
): void {
  const eachNotes = notes.filter((n) => {
    if (!n.is_each) return false;
    const kind = noteKind(n);
    return kind === "tap" || kind === "hold";
  });
  const grouped = new Set<ActiveNote>();
  for (const note of eachNotes) {
    if (grouped.has(note)) continue;
    const group: ActiveNote[] = [];
    for (const other of eachNotes) {
      if (Math.abs(other.t - note.t) * 1000 <= 1) group.push(other);
    }
    for (const member of group) grouped.add(member);
    if (group.length < 2) continue;
    const sensors = new Set(group.map((n) => resolveNoteSensor(n)));
    if (sensors.size < 2) continue;
    const pts = group.map((n) => noteHeadPoint(n, holds));
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

export function drawStar(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  r: number,
  fill: string,
  stroke: string,
  note: ActiveNote,
  spin: number,
): void {
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

export function drawNoteMarks(
  ctx: CanvasRenderingContext2D,
  note: ActiveNote,
  x: number,
  y: number,
  r: number,
): void {
  if (note.is_hanabi) drawHanabi(ctx, x, y, r);
  if (note.is_mine) {
    ctx.fillStyle = "#111";
    ctx.font = `700 ${Math.round(12 * S)}px 'IBM Plex Mono', monospace`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("!", x, y);
  }
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

function drawTapLine(ctx: CanvasRenderingContext2D, target: Pt): void {
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

function paintStadium(
  ctx: CanvasRenderingContext2D,
  inner: number,
  outer: number,
  r: number,
  fill: string,
  ring: string,
  note: ActiveNote,
): void {
  stadiumPath(ctx, inner, outer, r);
  ctx.fillStyle = fill;
  ctx.fill();

  stadiumPath(ctx, inner, outer, r * 0.42);
  ctx.fillStyle = note.is_break ? "#fff4d0" : COLORS.noteCore;
  ctx.fill();

  stadiumPath(ctx, inner, outer, r * 0.72);
  ctx.strokeStyle = "rgba(255,255,255,0.7)";
  ctx.lineWidth = 2.4 * S;
  ctx.stroke();

  stadiumPath(ctx, inner, outer, r);
  ctx.strokeStyle = ring;
  ctx.lineWidth = note.is_ex ? 3.6 * S : 2.6 * S;
  ctx.stroke();

  if (note.is_ex) {
    stadiumPath(ctx, inner, outer, r + 5 * S);
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2.4 * S;
    ctx.stroke();
  }
}

function stadiumPath(
  ctx: CanvasRenderingContext2D,
  inner: number,
  outer: number,
  r: number,
): void {
  ctx.beginPath();
  if (outer - inner < 0.5) {
    ctx.arc((inner + outer) * 0.5, 0, r, 0, Math.PI * 2);
    return;
  }
  ctx.arc(inner, 0, r, Math.PI / 2, -Math.PI / 2, false);
  ctx.arc(outer, 0, r, -Math.PI / 2, Math.PI / 2, false);
  ctx.closePath();
}

function drawTapDisk(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  r: number,
  fill: string,
  ring: string,
  note: ActiveNote,
  spin: number,
): void {
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

function paintFanKite(
  ctx: CanvasRenderingContext2D,
  a: number,
  r: number,
  fill: string,
  ring: string,
  ex: boolean,
): void {
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

function drawTouchFans(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  progress: number,
  fill: string,
  ring: string,
  note: ActiveNote,
  baseAngle: number,
): void {
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
    paintFanKite(ctx, a, fanR, fill, ring, note.is_ex === true);
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

function drawTouchHold(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  r: number,
  fill: string,
  ring: string,
  note: ActiveNote,
  progress: number,
): void {
  ctx.save();
  ctx.translate(x, y);
  ctx.globalAlpha = Math.min(1, Math.max(0.2, progress));
  ctx.lineJoin = "round";
  ctx.lineCap = "round";

  const body = r * 0.7;
  roundRectPath(ctx, -body, -body, body * 2, body * 2, body * 0.22);
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
    paintFanKite(ctx, a, fanR, fill, ring, note.is_ex === true);
    ctx.restore();
  }

  ctx.beginPath();
  ctx.arc(0, 0, r * 0.14, 0, Math.PI * 2);
  ctx.fillStyle = note.is_break ? "#fff4d0" : COLORS.noteCore;
  ctx.fill();
  ctx.restore();
}

function roundRectPath(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  rad: number,
): void {
  const r = Math.min(rad, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function drawHanabi(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  r: number,
): void {
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
