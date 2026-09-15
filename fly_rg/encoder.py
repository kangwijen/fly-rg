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

from fly_rg.judge import GOOD
from fly_rg.schema import Note
from fly_rg.sensors import (
    button_to_sensor,
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
)
REST_HOME = {"L": "A5", "R": "A4"}
REST_U = 0.4
LOOM_TYPES = ("LPLC1", "LPLC2")
THREAT_TYPES = ("LC4", "LC6")
CHASE_TYPES = ("LC10a", "LC11", "LC16")
CAP = 1.0
LOOM_GAIN = 14.0
LOOM_SIZE = 0.8
THREAT_GAIN = 1.0
CHASE_BASE = 0.7
CHASE_GAIN = 0.35


class BrainCells(Protocol):
    def cells(self, types: list[str], side: str) -> Any: ...


@dataclass
class EncoderResult:
    """Inject list for FlyBrain.step plus a display drive dict."""

    inject: list[tuple[Any, float]]
    drive: dict[str, float]


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
                return max(note.slide.end_t - now, 1e-3)
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
    tau = 0.02
    t0 = max(time_to_hit, 0.0)
    t1 = max(time_to_hit - dt, 0.0)
    s0 = math.exp(-t0 / tau)
    s1 = math.exp(-t1 / tau)
    return max(0.0, s1 - s0)


class NoteEncoder:
    """Build flybrain inject tuples from upcoming chart notes."""

    def __init__(self, brain: BrainCells | None = None, *, mock: bool = False):
        self.mock = mock
        self._cells: dict[str, dict[str, Any]] | None = None
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
    ) -> EncoderResult:
        drive = {k: 0.0 for k in (*DRIVE_KEYS, *STEER_KEYS)}
        xy_l = sensor_xy("A5") if hand_l is None else (float(hand_l[0]), float(hand_l[1]))
        xy_r = sensor_xy("A4") if hand_r is None else (float(hand_r[0]), float(hand_r[1]))
        hands = {
            "L": xy_to_polar(*xy_l),
            "R": xy_to_polar(*xy_r),
        }

        approaching: list[tuple[Note, float, str]] = []
        for i, note in enumerate(notes):
            nxt = 0 if slide_next is None else slide_next[i]
            sensor = note_target_sensor(note, slide_next=nxt)
            tth = note_window_tth(
                note, now, look_ahead_s, slide_next=nxt
            )
            if tth is not None:
                approaching.append((note, tth, sensor))

        for _note, tth, sensor in approaching:
            size = _size_proxy(tth, look_ahead_s)
            growth = _growth_proxy(tth, look_ahead_s, dt)
            loom = growth * LOOM_GAIN + size * LOOM_SIZE
            threat = size * THREAT_GAIN
            chase = CHASE_BASE + CHASE_GAIN * size
            theta_n, r_n = sensor_polar(sensor)
            area, _idx = parse_sensor(sensor)
            radial_only = area == "C"
            for side, (th, rh) in hands.items():
                dtheta = wrap_angle(theta_n - th)
                dr = r_n - rh
                drive[f"loom{side}"] += loom
                drive[f"chase{side}"] += chase
                drive[f"threat{side}"] += threat
                drive[f"growth{side}"] += growth * LOOM_GAIN
                if not radial_only:
                    drive[f"ccw{side}"] += chase * max(0.0, dtheta)
                    drive[f"cw{side}"] += chase * max(0.0, -dtheta)
                drive[f"out{side}"] += chase * max(0.0, dr)
                drive[f"in{side}"] += chase * max(0.0, -dr)

        for side, (th, rh) in hands.items():
            theta_n, r_n = sensor_polar(REST_HOME[side])
            dtheta = wrap_angle(theta_n - th)
            dr = r_n - rh
            drive[f"ccw{side}"] += REST_U * max(0.0, dtheta)
            drive[f"cw{side}"] += REST_U * max(0.0, -dtheta)
            drive[f"out{side}"] += REST_U * max(0.0, dr)
            drive[f"in{side}"] += REST_U * max(0.0, -dr)

        for key in drive:
            drive[key] = min(CAP, max(0.0, drive[key]))

        if self.mock or self._cells is None:
            return EncoderResult(inject=[], drive=drive)

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
        return EncoderResult(inject=inject, drive=drive)
