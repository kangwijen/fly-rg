"""Map upcoming notes to fly visual-projection inject drives.

Mirrors the spirit of flybrain FeatureDetectors (sshfighter) without Eyes
photoreceptors: drive LPLC2 (loom), LC4 (threat), and LC10a (chase) by side.

Sensor geometry comes from sensors.py (Majdata GetAreaPos). Targets the
current sensor (note.sensor, or the next unfinished slide path node).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

from fly_rg.schema import Note
from fly_rg.sensors import button_to_sensor, sensor_angle_rad, sensor_side

DRIVE_KEYS = ("loomL", "loomR", "chaseL", "chaseR", "threatL", "threatR")
CAP = 0.8
LOOM_GAIN = 10.0
LOOM_SIZE = 0.6
THREAT_GAIN = 0.8
CHASE_BASE = 0.6
CHASE_GAIN = 0.2


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
    if note.type == "slide" and note.slide is not None and note.slide.path:
        idx = min(max(slide_next, 0), len(note.slide.path) - 1)
        return note.slide.path[idx]
    return note.sensor


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
                "loom": {"L": brain.cells(["LPLC2"], "L"), "R": brain.cells(["LPLC2"], "R")},
                "threat": {"L": brain.cells(["LC4"], "L"), "R": brain.cells(["LC4"], "R")},
                "chase": {"L": brain.cells(["LC10a"], "L"), "R": brain.cells(["LC10a"], "R")},
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
            sensor = note_target_sensor(
                note, slide_next=0 if slide_next is None else slide_next[i]
            )
            # In-progress slides stay relevant until end_t.
            if (
                note.type == "slide"
                and note.slide is not None
                and slide_next is not None
                and slide_next[i] > 0
            ):
                tth = max(0.0, note.slide.end_t - now)
                if now <= note.slide.end_t:
                    approaching.append((note, max(tth, 1e-3), sensor))
                continue
            tth = note.t - now
            if 0.0 < tth <= look_ahead_s:
                approaching.append((note, tth, sensor))

        for _note, tth, sensor in approaching:
            side = sensor_side(sensor)
            size = _size_proxy(tth, look_ahead_s)
            growth = _growth_proxy(tth, look_ahead_s, dt)
            loom = min(CAP, growth * LOOM_GAIN + size * LOOM_SIZE)
            threat = min(CAP, size * THREAT_GAIN)
            drive[f"loom{side}"] = max(drive[f"loom{side}"], loom)
            drive[f"threat{side}"] = max(drive[f"threat{side}"], threat)

        if approaching:
            _nearest, tth, sensor = min(approaching, key=lambda x: x[1])
            side = sensor_side(sensor)
            size = _size_proxy(tth, look_ahead_s)
            chase = min(CAP, CHASE_BASE + CHASE_GAIN * size)
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
