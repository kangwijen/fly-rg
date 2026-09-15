"""Map upcoming notes to fly visual-projection inject drives.

Mirrors the spirit of flybrain FeatureDetectors (sshfighter) without Eyes
photoreceptors: drive LPLC2 (loom), LC4 (threat), and LC10a (chase) by side.

Button mapping (fly facing the cabinet, button 1 at top):
  angle_deg(button i) = (i - 1) * 45 - 90
  side L if sin(angle) > 0 else R

  button | angle | side (sin rule)
       1 |  -90  | R
       2 |  -45  | R
       3 |    0  | R
       4 |   45  | L
       5 |   90  | L
       6 |  135  | L
       7 |  180  | R
       8 |  225  | R

Decoder aim sectors use a separate ring split (8,1,2,7) vs (3,4,5,6); this
encoder only needs left/right hemifield for inject.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

from fly_rg.schema import Note

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
    return (button - 1) * 45.0 - 90.0


def button_side(button: int) -> str:
    """L if sin(angle) > 0 else R (see module docstring)."""
    if not 1 <= button <= 8:
        raise ValueError(f"button must be 1..8, got {button}")
    angle = math.radians(button_angle_deg(button))
    return "L" if math.sin(angle) > 0 else "R"


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
    ) -> EncoderResult:
        drive = {k: 0.0 for k in DRIVE_KEYS}
        approaching: list[tuple[Note, float]] = []
        for note in notes:
            tth = note.t - now
            if 0.0 < tth <= look_ahead_s:
                approaching.append((note, tth))

        for note, tth in approaching:
            side = button_side(note.button)
            size = _size_proxy(tth, look_ahead_s)
            growth = _growth_proxy(tth, look_ahead_s, dt)
            loom = min(CAP, growth * LOOM_GAIN + size * LOOM_SIZE)
            threat = min(CAP, size * THREAT_GAIN)
            drive[f"loom{side}"] = max(drive[f"loom{side}"], loom)
            drive[f"threat{side}"] = max(drive[f"threat{side}"], threat)

        if approaching:
            nearest, tth = min(approaching, key=lambda x: x[1])
            side = button_side(nearest.button)
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
