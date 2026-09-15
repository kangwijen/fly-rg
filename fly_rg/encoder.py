"""Map upcoming notes to fly visual-projection inject drives.

Drive LPLC1+LPLC2 (loom), LC4+LC6 (threat), and LC10a+LC11+LC16 (chase)
by side. Same six HUD keys: loom/chase/threat L/R.

Sensor geometry comes from sensors.py (Majdata GetAreaPos). Targets the
current sensor (note.sensor, or the next unfinished slide path node).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Never, Protocol

from fly_rg.decoder import STEER_TYPES, TAP_TYPES, V_MAX
from fly_rg.judge import GOOD
from fly_rg.schema import Note
from fly_rg.sensors import (
    REST_HOME,
    button_to_sensor,
    nearest_sensor,
    parse_sensor,
    sensor_angle_rad,
    sensor_polar,
    sensor_side,
    sensor_xy,
    wrap_angle,
    xy_to_polar,
)

DRIVE_KEYS = ("loomL", "loomR", "chaseL", "chaseR", "threatL", "threatR")
STEER_KEYS = (
    "cwL",
    "cwR",
    "ccwL",
    "ccwR",
    "inL",
    "inR",
    "outL",
    "outR",
    "growthL",
    "growthR",
    "eastL",
    "eastR",
    "westL",
    "westR",
    "northL",
    "northR",
    "southL",
    "southR",
)
CAP = 1.0
REST_T_GO_S = 0.18
LOOM_TYPES = ("LPLC1", "LPLC2")
THREAT_TYPES = ("LC4", "LC6")
CHASE_TYPES = ("LC10a", "LC11", "LC16")
LOOM_GAIN = 14.0
THREAT_GAIN = 1.0
CHASE_BASE = 0.7
CHASE_GAIN = 0.35
GROWTH_TAU_S = 0.020
FOVEA_SIGMA = 0.30
DEADZONE = 0.08
T_GO_FLOOR_S = 0.04
ON_PAD_TTH_S = 0.03


class BrainCells(Protocol):
    def cells(self, types: list[str], side: str) -> Any: ...


@dataclass
class EncoderResult:
    """Inject list for FlyBrain.step plus a display drive dict."""

    inject: list[tuple[Any, float]]
    drive: dict[str, float]
    target_l: str | None = None
    target_r: str | None = None
    tth_l: float | None = None
    tth_r: float | None = None
    slide_l: str | None = None
    slide_r: str | None = None


def button_angle_deg(button: int) -> float:
    """A-button angle in degrees (Majdata GetAreaPos)."""
    return math.degrees(sensor_angle_rad("A", button))


def button_side(button: int) -> str:
    """L/R hemifield for button 1..8 via A-sensor x coordinate."""
    return sensor_side(button_to_sensor(button))


def note_target_sensor(note: Note, *, slide_next: int = 0) -> str:
    """Sensor the fly should aim at for this note right now."""
    nt = note.type
    if nt == "slide":
        if note.slide is not None and note.slide.path:
            idx = min(max(slide_next, 0), len(note.slide.path) - 1)
            return note.slide.path[idx]
        return note.sensor
    if nt == "tap" or nt == "hold" or nt == "touch" or nt == "touch_hold":
        return note.sensor
    _exhaustive: Never = nt
    raise ValueError(f"unknown note type: {_exhaustive}")


def note_window_tth(
    note: Note,
    now: float,
    look_ahead_s: float,
    *,
    slide_next: int = 0,
) -> float | None:
    """Time-to-hit proxy if the note is still in the inject/aim window."""
    nt = note.type
    if nt == "slide":
        if note.slide is not None and slide_next > 0:
            if now <= note.slide.end_t:
                path = note.slide.path
                denom = max(len(path) - 1, 1)
                wait_t = float(note.slide.wait_t)
                end_t = float(note.slide.end_t)
                t_k = wait_t + (end_t - wait_t) * float(slide_next) / float(denom)
                return max(t_k - now, 1e-3)
            return None
        tth = note.t - now
        if -GOOD <= tth <= look_ahead_s:
            return max(tth, 0.0)
        return None
    if nt == "hold" or nt == "touch_hold":
        end = note.end if note.end is not None else note.t + GOOD
        if note.t - look_ahead_s <= now <= end:
            return max(note.t - now, 0.0)
        return None
    if nt == "tap" or nt == "touch":
        tth = note.t - now
        if -GOOD <= tth <= look_ahead_s:
            return max(tth, 0.0)
        return None
    _exhaustive: Never = nt
    raise ValueError(f"unknown note type: {_exhaustive}")


def _size_proxy(time_to_hit: float, look_ahead_s: float) -> float:
    """Larger as the note approaches (0 at look-ahead horizon, ~1 at hit)."""
    if look_ahead_s <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - time_to_hit / look_ahead_s))


def _growth_proxy(time_to_hit: float, look_ahead_s: float, dt: float) -> float:
    """Near-hit pulse so jack/trill heads retrigger DNp."""
    del look_ahead_s
    if dt <= 0:
        return 0.0
    t0 = max(time_to_hit, 0.0)
    t1 = max(time_to_hit - dt, 0.0)
    s0 = math.exp(-t0 / GROWTH_TAU_S)
    s1 = math.exp(-t1 / GROWTH_TAU_S)
    return max(0.0, s1 - s0)


def _retina_error(dtheta: float, dr: float, *, radial_only: bool) -> float:
    if radial_only:
        return abs(dr)
    return math.hypot(dtheta, dr)


def _fovea(err: float) -> float:
    if FOVEA_SIGMA <= 0:
        return 0.0
    return math.exp(-0.5 * (err / FOVEA_SIGMA) ** 2)


def _note_chart_end(note: Note) -> float:
    """Last time this note occupies the chart timeline."""
    if note.type == "slide" and note.slide is not None:
        return float(note.slide.end_t)
    if note.end is not None:
        return float(note.end)
    return float(note.t)


def _chart_span(notes: list[Note]) -> tuple[float, float] | None:
    if not notes:
        return None
    first = min(float(note.t) for note in notes)
    last = max(_note_chart_end(note) for note in notes)
    return first, last


def _should_rest_home(
    notes: list[Note], now: float, look_ahead_s: float
) -> bool:
    span = _chart_span(notes)
    if span is None:
        return True
    first, last = span
    if now < first - look_ahead_s:
        return True
    if now > last + 0.5:
        return True
    return False


def _chord_velocity(
    dx: float, dy: float, t_go: float, vmax: float
) -> tuple[float, float]:
    dist = math.hypot(dx, dy)
    if dist < DEADZONE:
        return 0.0, 0.0
    horizon = max(t_go, 1e-9)
    speed = dist / horizon
    vx = dx / horizon
    vy = dy / horizon
    if speed > vmax and speed > 1e-12:
        scale = vmax / speed
        return vx * scale, vy * scale
    return vx, vy


def _drive_from_velocity(
    vx: float, vy: float, vmax: float
) -> tuple[float, float, float, float]:
    if vmax <= 1e-12:
        return 0.0, 0.0, 0.0, 0.0
    east = max(0.0, min(1.0, vx / vmax))
    west = max(0.0, min(1.0, -vx / vmax))
    north = max(0.0, min(1.0, vy / vmax))
    south = max(0.0, min(1.0, -vy / vmax))
    return east, west, north, south


class NoteEncoder:
    """Build flybrain inject tuples from upcoming chart notes."""

    def __init__(self, brain: BrainCells | None = None, *, mock: bool = False):
        self.mock = mock
        self._cells: dict[str, dict[str, Any]] | None = None
        self._dn: dict[tuple[str, str], Any] | None = None
        self._dnp: dict[str, Any] | None = None
        self._lock_l: int | None = None
        self._lock_r: int | None = None
        if brain is not None and not mock:
            self._cells = {
                "loom": {
                    "L": brain.cells(list(LOOM_TYPES), "L"),
                    "R": brain.cells(list(LOOM_TYPES), "R"),
                },
                "threat": {
                    "L": brain.cells(list(THREAT_TYPES), "L"),
                    "R": brain.cells(list(THREAT_TYPES), "R"),
                },
                "chase": {
                    "L": brain.cells(list(CHASE_TYPES), "L"),
                    "R": brain.cells(list(CHASE_TYPES), "R"),
                },
            }
            self._dn = {
                (typ, side): brain.cells([typ], side)
                for side in ("L", "R")
                for typ in STEER_TYPES
            }
            self._dnp = {
                "L": brain.cells(list(TAP_TYPES), "L"),
                "R": brain.cells(list(TAP_TYPES), "R"),
            }

    def clear_locks(self) -> None:
        self._lock_l = None
        self._lock_r = None

    def _lock_active(
        self,
        idx: int | None,
        notes: list[Note],
        matched: list[bool] | None,
        slide_next: list[int] | None,
        now: float,
    ) -> bool:
        if idx is None or idx < 0 or idx >= len(notes):
            return False
        if matched is not None and idx < len(matched) and matched[idx]:
            return False
        note = notes[idx]
        if note.type != "slide" or note.slide is None:
            return False
        nxt = 0 if slide_next is None else slide_next[idx]
        if nxt <= 0:
            return False
        return now <= note.slide.end_t

    def encode(
        self,
        notes: list[Note],
        now: float,
        *,
        look_ahead_s: float = 1.0,
        dt: float = 0.004,
        slide_next: list[int] | None = None,
        hand_l: tuple[float, float] | None = None,
        hand_r: tuple[float, float] | None = None,
        matched: list[bool] | None = None,
    ) -> EncoderResult:
        drive = {k: 0.0 for k in (*DRIVE_KEYS, *STEER_KEYS)}
        xy_l = (
            sensor_xy(REST_HOME["L"])
            if hand_l is None
            else (float(hand_l[0]), float(hand_l[1]))
        )
        xy_r = (
            sensor_xy(REST_HOME["R"])
            if hand_r is None
            else (float(hand_r[0]), float(hand_r[1]))
        )
        hands_xy = {"L": xy_l, "R": xy_r}
        hands_polar = {
            "L": xy_to_polar(*xy_l),
            "R": xy_to_polar(*xy_r),
        }

        approaching: list[tuple[int, Note, float, str, int]] = []
        for i, note in enumerate(notes):
            if matched is not None and i < len(matched) and matched[i]:
                continue
            nxt = 0 if slide_next is None else slide_next[i]
            sensor = note_target_sensor(note, slide_next=nxt)
            tth = note_window_tth(
                note, now, look_ahead_s, slide_next=nxt
            )
            if tth is not None:
                approaching.append((i, note, tth, sensor, nxt))

        pending: list[dict[str, Any]] = []
        for index, note, tth, sensor, nxt in approaching:
            size = _size_proxy(tth, look_ahead_s)
            waypoint = note.type == "slide" and nxt > 0
            growth = _growth_proxy(tth, look_ahead_s, dt)
            threat = size * THREAT_GAIN
            chase = CHASE_BASE + CHASE_GAIN * size
            theta_n, r_n = sensor_polar(sensor)
            tx, ty = sensor_xy(sensor)
            area, _idx = parse_sensor(sensor)
            radial_only = area == "C"
            dtheta_h: dict[str, float] = {}
            dr_h: dict[str, float] = {}
            err_h: dict[str, float] = {}
            err_xy: dict[str, float] = {}
            for side, (th, rh) in hands_polar.items():
                hx, hy = hands_xy[side]
                dtheta_h[side] = 0.0 if radial_only else wrap_angle(theta_n - th)
                dr_h[side] = r_n - rh
                err_h[side] = _retina_error(
                    dtheta_h[side], dr_h[side], radial_only=radial_only
                )
                err_xy[side] = math.hypot(tx - hx, ty - hy)
            pending.append(
                {
                    "index": index,
                    "tth": tth,
                    "sensor": sensor,
                    "xy": (tx, ty),
                    "dtheta": dtheta_h,
                    "dr": dr_h,
                    "err": err_h,
                    "err_xy": err_xy,
                    "growth": growth,
                    "chase": chase,
                    "threat": threat,
                    "in_progress": waypoint,
                }
            )

        by_index = {int(row["index"]): row for row in pending}
        if not self._lock_active(self._lock_l, notes, matched, slide_next, now):
            self._lock_l = None
        if not self._lock_active(self._lock_r, notes, matched, slide_next, now):
            self._lock_r = None

        best: dict[str, dict[str, Any] | None] = {"L": None, "R": None}
        taken: set[int] = set()

        def _assign(side: str, row: dict[str, Any]) -> None:
            best[side] = row
            taken.add(int(row["index"]))
            if row["in_progress"]:
                if side == "L":
                    self._lock_l = int(row["index"])
                else:
                    self._lock_r = int(row["index"])

        if self._lock_l is not None:
            locked = by_index.get(self._lock_l)
            if locked is not None:
                _assign("L", locked)
        if self._lock_r is not None:
            locked = by_index.get(self._lock_r)
            if locked is not None:
                _assign("R", locked)

        rest = [row for row in pending if int(row["index"]) not in taken]
        rest.sort(
            key=lambda row: (
                0 if row["in_progress"] else 1,
                float(row["tth"]),
                min(float(v) for v in row["err_xy"].values()),
            )
        )
        for row in rest:
            closer = "L" if row["err_xy"]["L"] <= row["err_xy"]["R"] else "R"
            other = "R" if closer == "L" else "L"
            other_locked = (
                self._lock_l is not None if other == "L" else self._lock_r is not None
            )
            if best[closer] is None:
                _assign(closer, row)
            elif (
                best[other] is None
                and str(row["sensor"]) != str(best[closer]["sensor"])
                and not other_locked
            ):
                _assign(other, row)

        for row in pending:
            owners = [side for side in ("L", "R") if best[side] is row]
            if not owners:
                closer = "L" if row["err"]["L"] <= row["err"]["R"] else "R"
                owners = [closer]
            chase = float(row["chase"])
            threat = float(row["threat"])
            proxy = float(row["growth"])
            loom = min(CAP, proxy * LOOM_GAIN)
            for side in owners:
                fovea = _fovea(float(row["err"][side]))
                pulse = loom * fovea
                drive[f"loom{side}"] += pulse
                drive[f"chase{side}"] += chase
                drive[f"threat{side}"] += threat
                growth_key = f"growth{side}"
                on_intended = nearest_sensor(*hands_xy[side]) == str(row["sensor"])
                if on_intended:
                    drive[growth_key] = max(drive[growth_key], proxy * fovea)
                    if (
                        not row["in_progress"]
                        and float(row["tth"]) <= ON_PAD_TTH_S
                    ):
                        drive[growth_key] = max(drive[growth_key], 1.0)

        rest_home = _should_rest_home(notes, now, look_ahead_s)
        for side, (hx, hy) in hands_xy.items():
            target = best[side]
            if target is None:
                if rest_home:
                    tx, ty = sensor_xy(REST_HOME[side])
                    t_go = REST_T_GO_S
                else:
                    drive[f"east{side}"] = 0.0
                    drive[f"west{side}"] = 0.0
                    drive[f"north{side}"] = 0.0
                    drive[f"south{side}"] = 0.0
                    continue
            else:
                tx, ty = target["xy"]
                t_go = max(float(target["tth"]), T_GO_FLOOR_S, dt)
            vx, vy = _chord_velocity(tx - hx, ty - hy, t_go, V_MAX)
            east, west, north, south = _drive_from_velocity(vx, vy, V_MAX)
            drive[f"east{side}"] = east
            drive[f"west{side}"] = west
            drive[f"north{side}"] = north
            drive[f"south{side}"] = south

        for key in drive:
            drive[key] = min(CAP, max(0.0, drive[key]))

        target_l = None if best["L"] is None else str(best["L"]["sensor"])
        target_r = None if best["R"] is None else str(best["R"]["sensor"])
        tth_l = None if best["L"] is None else float(best["L"]["tth"])
        tth_r = None if best["R"] is None else float(best["R"]["tth"])
        slide_l = None
        slide_r = None
        if self._lock_l is not None and 0 <= self._lock_l < len(notes):
            nxt = 0 if slide_next is None else slide_next[self._lock_l]
            slide_l = note_target_sensor(notes[self._lock_l], slide_next=nxt)
        if self._lock_r is not None and 0 <= self._lock_r < len(notes):
            nxt = 0 if slide_next is None else slide_next[self._lock_r]
            slide_r = note_target_sensor(notes[self._lock_r], slide_next=nxt)

        if self.mock or self._cells is None:
            return EncoderResult(
                inject=[],
                drive=drive,
                target_l=target_l,
                target_r=target_r,
                tth_l=tth_l,
                tth_r=tth_r,
                slide_l=slide_l,
                slide_r=slide_r,
            )

        inject: list[tuple[Any, float]] = []
        channel_map = {
            "loomL": ("loom", "L"),
            "loomR": ("loom", "R"),
            "threatL": ("threat", "L"),
            "threatR": ("threat", "R"),
            "chaseL": ("chase", "L"),
            "chaseR": ("chase", "R"),
        }
        for key, (ch, side) in channel_map.items():
            amount = drive[key]
            if amount <= 0:
                continue
            inject.append((self._cells[ch][side], float(amount)))
        dn_map = {
            "ccwL": ("DNa01", "L"),
            "ccwR": ("DNa01", "R"),
            "cwL": ("DNa02", "L"),
            "cwR": ("DNa02", "R"),
            "outL": ("DNa03", "L"),
            "outR": ("DNa03", "R"),
            "inL": ("DNa04", "L"),
            "inR": ("DNa04", "R"),
            "eastL": ("DNa01", "L"),
            "eastR": ("DNa01", "R"),
            "westL": ("DNa02", "L"),
            "westR": ("DNa02", "R"),
            "northL": ("DNa03", "L"),
            "northR": ("DNa03", "R"),
            "southL": ("DNa04", "L"),
            "southR": ("DNa04", "R"),
        }
        if self._dn is not None:
            dn_amounts: dict[tuple[str, str], float] = {}
            for key, (typ, side) in dn_map.items():
                amount = drive[key]
                if amount <= 0:
                    continue
                dn_amounts[(typ, side)] = max(
                    dn_amounts.get((typ, side), 0.0), float(amount)
                )
            for (typ, side), amount in dn_amounts.items():
                inject.append((self._dn[(typ, side)], float(amount)))
        if self._dnp is not None:
            for side in ("L", "R"):
                amount = drive[f"growth{side}"]
                if amount <= 0:
                    continue
                inject.append((self._dnp[side], float(amount)))
        return EncoderResult(
            inject=inject,
            drive=drive,
            target_l=target_l,
            target_r=target_r,
            tth_l=tth_l,
            tth_r=tth_r,
            slide_l=slide_l,
            slide_r=slide_r,
        )
