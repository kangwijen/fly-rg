"""Decode descending-neuron spikes (or mock drives) into aim and taps."""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol

from fly_rg.encoder import button_side
from fly_rg.schema import Note

# Aim sectors when DNa02 prefers left vs right.
LEFT_BUTTONS = (8, 1, 2, 7)
RIGHT_BUTTONS = (3, 4, 5, 6)

STEER_WINDOW = 25  # steps (~0.5 s at dt=0.02)
STEER_MARGIN = 2
TAP_WINDOW = 5  # steps (~0.1 s)
TAP_SPIKES = 2
TAP_COOLDOWN_S = 0.08
PERFECT_WINDOW_S = 0.033


class SpikeBrain(Protocol):
    def cells(self, types: list[str], side: str) -> Any: ...


@dataclass
class DecodeResult:
    aim_button: int | None
    tap: bool
    tap_button: int | None
    aim: float  # -1..1
    strike: float  # 0..1


def _as_index_set(indices: Any) -> set[int]:
    if indices is None:
        return set()
    if isinstance(indices, set):
        return {int(x) for x in indices}
    try:
        return {int(x) for x in indices}
    except TypeError:
        return {int(indices)}


class ActionDecoder:
    """DNa02 L/R -> aim; DNp01 -> tap, mapped onto approaching notes."""

    def __init__(
        self,
        brain: SpikeBrain | None = None,
        *,
        mock: bool = False,
        tap_types: list[str] | None = None,
        seed: int = 0,
    ):
        self.mock = mock
        self.rng = random.Random(seed)
        self._last_tap_t = -1e9
        self._history: deque[tuple[int, int, int]] = deque(maxlen=STEER_WINDOW)
        self._dna02_l: set[int] = set()
        self._dna02_r: set[int] = set()
        self._tap_idx: set[int] = set()
        self._brain = brain
        if brain is not None and not mock:
            tap_types = tap_types or ["DNp01"]
            self._dna02_l = _as_index_set(brain.cells(["DNa02"], "L"))
            self._dna02_r = _as_index_set(brain.cells(["DNa02"], "R"))
            left = _as_index_set(brain.cells(tap_types, "L"))
            right = _as_index_set(brain.cells(tap_types, "R"))
            self._tap_idx = left | right

    def observe(self, fired: Any) -> None:
        if self.mock:
            return
        fired_set = _as_index_set(fired)
        l = len(fired_set & self._dna02_l)
        r = len(fired_set & self._dna02_r)
        tap = len(fired_set & self._tap_idx)
        self._history.append((l, r, tap))

    def decode(
        self,
        now: float,
        notes: list[Note],
        *,
        look_ahead_s: float = 1.0,
        drive: dict[str, float] | None = None,
        last_inject: dict[str, float] | None = None,
    ) -> DecodeResult:
        if self.mock:
            return self._decode_mock(now, notes, look_ahead_s, drive or last_inject or {})
        return self._decode_spikes(now, notes, look_ahead_s)

    def _rates(self) -> tuple[float, float, float]:
        if not self._history:
            return 0.0, 0.0, 0.0
        recent = list(self._history)
        steer = recent[-STEER_WINDOW:]
        tap_win = recent[-TAP_WINDOW:]
        l = sum(x[0] for x in steer)
        r = sum(x[1] for x in steer)
        tap = sum(x[2] for x in tap_win)
        return float(l), float(r), float(tap)

    def _decode_spikes(self, now: float, notes: list[Note], look_ahead_s: float) -> DecodeResult:
        l, r, tap_count = self._rates()
        diff = r - l
        if abs(diff) < STEER_MARGIN:
            aim = 0.0
            prefer: tuple[int, ...] | None = None
        elif diff > 0:
            aim = min(1.0, diff / max(STEER_MARGIN * 4, 1))
            prefer = RIGHT_BUTTONS
        else:
            aim = max(-1.0, diff / max(STEER_MARGIN * 4, 1))
            prefer = LEFT_BUTTONS

        active = [n for n in notes if 0.0 < (n.t - now) <= look_ahead_s]
        aim_button = _pick_aim_button(aim, prefer, active)

        want_tap = tap_count >= TAP_SPIKES
        tap = False
        tap_button: int | None = None
        strike = min(1.0, tap_count / max(TAP_SPIKES, 1))
        if want_tap and (now - self._last_tap_t) >= TAP_COOLDOWN_S:
            tap_button = _pick_tap_button(aim_button, prefer, active, aim)
            if tap_button is not None:
                tap = True
                self._last_tap_t = now
                strike = 1.0
        return DecodeResult(
            aim_button=aim_button,
            tap=tap,
            tap_button=tap_button if tap else None,
            aim=aim,
            strike=strike,
        )

    def _decode_mock(
        self,
        now: float,
        notes: list[Note],
        look_ahead_s: float,
        drive: dict[str, float],
    ) -> DecodeResult:
        loom_l = float(drive.get("loomL", 0.0))
        loom_r = float(drive.get("loomR", 0.0))
        chase_l = float(drive.get("chaseL", 0.0))
        chase_r = float(drive.get("chaseR", 0.0))
        left_strength = loom_l + chase_l + float(drive.get("threatL", 0.0))
        right_strength = loom_r + chase_r + float(drive.get("threatR", 0.0))
        total = left_strength + right_strength
        if total <= 1e-9:
            aim = 0.0
            prefer = None
        else:
            aim = (right_strength - left_strength) / max(total, 1e-9)
            prefer = RIGHT_BUTTONS if aim >= 0 else LEFT_BUTTONS

        active = [n for n in notes if 0.0 < (n.t - now) <= look_ahead_s]
        aim_button = _pick_aim_button(aim, prefer, active)

        # Synthesize taps when a note is inside the Perfect window; probability
        # scales with inject strength so the mock still "plays".
        inject_strength = max(
            loom_l,
            loom_r,
            chase_l,
            chase_r,
            float(drive.get("threatL", 0.0)),
            float(drive.get("threatR", 0.0)),
        )
        tap = False
        tap_button: int | None = None
        strike = min(1.0, inject_strength / 0.8)
        if (now - self._last_tap_t) >= TAP_COOLDOWN_S:
            candidates = [n for n in notes if abs(n.t - now) <= PERFECT_WINDOW_S]
            if candidates:
                # Prefer the note matching aim_button / preferred sector.
                chosen = _best_note_for_aim(candidates, aim_button, prefer, aim)
                # Higher drive -> more reliable Perfect taps (deterministic RNG).
                p = min(0.95, 0.35 + 0.8 * inject_strength)
                if chosen is not None and self.rng.random() < p:
                    tap = True
                    tap_button = chosen.button
                    self._last_tap_t = now
                    strike = 1.0
        return DecodeResult(
            aim_button=aim_button,
            tap=tap,
            tap_button=tap_button if tap else None,
            aim=float(max(-1.0, min(1.0, aim))),
            strike=float(strike),
        )


def _button_aim_score(button: int) -> float:
    """Map button to -1..1 around the ring (1 at top -> 0-ish via angle)."""
    # Use cos of encoder angle so top (~button 1) is near 0 lateral, right positive.
    angle = math.radians((button - 1) * 45.0 - 90.0)
    return math.cos(angle)


def _pick_aim_button(
    aim: float,
    prefer: tuple[int, ...] | None,
    active: list[Note],
) -> int | None:
    if active:
        if prefer is not None:
            sector = [n for n in active if n.button in prefer]
            pool = sector or active
        else:
            pool = active
        return min(pool, key=lambda n: (n.t, abs(_button_aim_score(n.button) - aim))).button
    # No approaching notes: best matching button by aim alone.
    buttons = prefer if prefer is not None else tuple(range(1, 9))
    return min(buttons, key=lambda b: abs(_button_aim_score(b) - aim))


def _pick_tap_button(
    aim_button: int | None,
    prefer: tuple[int, ...] | None,
    active: list[Note],
    aim: float,
) -> int | None:
    if not active:
        return aim_button
    if aim_button is not None and any(n.button == aim_button for n in active):
        return aim_button
    return _pick_aim_button(aim, prefer, active)


def _best_note_for_aim(
    notes: list[Note],
    aim_button: int | None,
    prefer: tuple[int, ...] | None,
    aim: float,
) -> Note | None:
    if not notes:
        return None
    if aim_button is not None:
        matched = [n for n in notes if n.button == aim_button]
        if matched:
            return min(matched, key=lambda n: abs(n.t))
    if prefer is not None:
        sector = [n for n in notes if n.button in prefer]
        if sector:
            return min(sector, key=lambda n: (abs(n.t), abs(_button_aim_score(n.button) - aim)))
    return min(notes, key=lambda n: (abs(n.t), abs(_button_aim_score(n.button) - aim)))


# Re-export for callers that want geometric side with aim sectors.
__all__ = [
    "ActionDecoder",
    "DecodeResult",
    "LEFT_BUTTONS",
    "RIGHT_BUTTONS",
    "button_side",
]
