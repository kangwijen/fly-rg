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
from fly_rg.sensors import button_to_sensor, sensor_angle_rad, sensor_side

DRIVE_KEYS = ("loomL", "loomR", "chaseL", "chaseR", "threatL", "threatR")
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
    """Finite-difference of size proxy over one dt (angular growth stand-in)."""
    if dt <= 0:
        return 0.0
    s0 = _size_proxy(time_to_hit, look_ahead_s)
    s1 = _size_proxy(max(0.0, time_to_hit - dt), look_ahead_s)
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
        dt: float = 0.02,
        slide_next: list[int] | None = None,
    ) -> EncoderResult:
        drive = {k: 0.0 for k in DRIVE_KEYS}
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
            side = sensor_side(sensor)
            size = _size_proxy(tth, look_ahead_s)
            growth = _growth_proxy(tth, look_ahead_s, dt)
            loom = min(CAP, growth * LOOM_GAIN + size * LOOM_SIZE)
            threat = min(CAP, size * THREAT_GAIN)
            chase = min(CAP, CHASE_BASE + CHASE_GAIN * size)
            drive[f"loom{side}"] = max(drive[f"loom{side}"], loom)
            drive[f"threat{side}"] = max(drive[f"threat{side}"], threat)
            drive[f"chase{side}"] = max(drive[f"chase{side}"], chase)

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
        for key, amount in drive.items():
            if amount <= 0:
                continue
            ch, side = channel_map[key]
            inject.append((self._cells[ch][side], float(amount)))
        return EncoderResult(inject=inject, drive=drive)
