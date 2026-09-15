"""Decode descending-neuron spikes (or mock drives) into aim and taps."""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol

from fly_rg.encoder import note_target_sensor
from fly_rg.schema import Note
from fly_rg.sensors import button_to_sensor, sensor_side, sensor_xy

# Aim sectors when DNa02 prefers left vs right (A-button indices).
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
    aim_sensor: str | None
    tap_sensor: str | None
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


def _sensor_to_button(sensor: str | None) -> int | None:
    if not sensor:
        return None
    s = sensor.strip().upper()
    if len(s) >= 2 and s[0] == "A" and s[1:].isdigit():
        idx = int(s[1:])
        if 1 <= idx <= 8:
            return idx
    return None


class ActionDecoder:
    """DNa02 L/R -> aim; DNp01 -> tap, mapped onto approaching sensors."""

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
        slide_next: list[int] | None = None,
    ) -> DecodeResult:
        if self.mock:
            return self._decode_mock(
                now, notes, look_ahead_s, drive or last_inject or {}, slide_next
            )
        return self._decode_spikes(now, notes, look_ahead_s, slide_next)

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

    def _active_targets(
        self,
        now: float,
        notes: list[Note],
        look_ahead_s: float,
        slide_next: list[int] | None,
    ) -> list[tuple[Note, str]]:
        out: list[tuple[Note, str]] = []
        for i, note in enumerate(notes):
            nxt = 0 if slide_next is None else slide_next[i]
            sensor = note_target_sensor(note, slide_next=nxt)
            if note.type == "slide" and note.slide is not None and nxt > 0:
                if now <= note.slide.end_t:
                    out.append((note, sensor))
                continue
            if 0.0 < (note.t - now) <= look_ahead_s:
                out.append((note, sensor))
        return out

    def _decode_spikes(
        self,
        now: float,
        notes: list[Note],
        look_ahead_s: float,
        slide_next: list[int] | None,
    ) -> DecodeResult:
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

        active = self._active_targets(now, notes, look_ahead_s, slide_next)
        aim_sensor = _pick_aim_sensor(aim, prefer, active)
        aim_button = _sensor_to_button(aim_sensor)

        want_tap = tap_count >= TAP_SPIKES
        tap = False
        tap_sensor: str | None = None
        strike = min(1.0, tap_count / max(TAP_SPIKES, 1))
        if want_tap and (now - self._last_tap_t) >= TAP_COOLDOWN_S:
            tap_sensor = _pick_tap_sensor(aim_sensor, prefer, active, aim)
            if tap_sensor is not None:
                tap = True
                self._last_tap_t = now
                strike = 1.0
        return DecodeResult(
            aim_button=aim_button,
            tap=tap,
            tap_button=_sensor_to_button(tap_sensor) if tap else None,
            aim_sensor=aim_sensor,
            tap_sensor=tap_sensor if tap else None,
            aim=aim,
            strike=strike,
        )

    def _decode_mock(
        self,
        now: float,
        notes: list[Note],
        look_ahead_s: float,
        drive: dict[str, float],
        slide_next: list[int] | None,
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

        active = self._active_targets(now, notes, look_ahead_s, slide_next)
        aim_sensor = _pick_aim_sensor(aim, prefer, active)
        aim_button = _sensor_to_button(aim_sensor)

        inject_strength = max(
            loom_l,
            loom_r,
            chase_l,
            chase_r,
            float(drive.get("threatL", 0.0)),
            float(drive.get("threatR", 0.0)),
        )
        tap = False
        tap_sensor: str | None = None
        strike = min(1.0, inject_strength / 0.8)
        if (now - self._last_tap_t) >= TAP_COOLDOWN_S:
            candidates: list[tuple[Note, str]] = []
            for i, note in enumerate(notes):
                nxt = 0 if slide_next is None else slide_next[i]
                sensor = note_target_sensor(note, slide_next=nxt)
                if note.type == "slide" and note.slide is not None and nxt > 0:
                    # Keep pressing along the path while the slide is live.
                    if now <= note.slide.end_t:
                        candidates.append((note, sensor))
                    continue
                if abs(note.t - now) <= PERFECT_WINDOW_S:
                    candidates.append((note, sensor))
            if candidates:
                chosen = _best_target_for_aim(candidates, aim_sensor, prefer, aim)
                p = min(0.95, 0.35 + 0.8 * inject_strength)
                if chosen is not None and self.rng.random() < p:
                    tap = True
                    tap_sensor = chosen[1]
                    self._last_tap_t = now
                    strike = 1.0
        return DecodeResult(
            aim_button=aim_button,
            tap=tap,
            tap_button=_sensor_to_button(tap_sensor) if tap else None,
            aim_sensor=aim_sensor,
            tap_sensor=tap_sensor if tap else None,
            aim=float(max(-1.0, min(1.0, aim))),
            strike=float(strike),
        )


def _sensor_aim_score(sensor: str) -> float:
    """Map sensor to -1..1 lateral (cos of angle; +X right)."""
    x, _y = sensor_xy(sensor)
    # Normalize roughly to -1..1 using ring radius.
    return max(-1.0, min(1.0, x / 0.86))


def _pick_aim_sensor(
    aim: float,
    prefer: tuple[int, ...] | None,
    active: list[tuple[Note, str]],
) -> str | None:
    if active:
        if prefer is not None:
            sector = [
                (n, s)
                for n, s in active
                if _sensor_to_button(s) in prefer or sensor_side(s) == ("L" if prefer is LEFT_BUTTONS else "R")
            ]
            # Prefer A-buttons in the sector when present; else all active.
            a_sector = [(n, s) for n, s in active if _sensor_to_button(s) in prefer]
            pool = a_sector or sector or active
        else:
            pool = active
        return min(pool, key=lambda ns: (ns[0].t, abs(_sensor_aim_score(ns[1]) - aim)))[1]
    buttons = prefer if prefer is not None else tuple(range(1, 9))
    best_b = min(buttons, key=lambda b: abs(_sensor_aim_score(button_to_sensor(b)) - aim))
    return button_to_sensor(best_b)


def _pick_tap_sensor(
    aim_sensor: str | None,
    prefer: tuple[int, ...] | None,
    active: list[tuple[Note, str]],
    aim: float,
) -> str | None:
    if not active:
        return aim_sensor
    if aim_sensor is not None and any(s == aim_sensor for _n, s in active):
        return aim_sensor
    return _pick_aim_sensor(aim, prefer, active)


def _best_target_for_aim(
    targets: list[tuple[Note, str]],
    aim_sensor: str | None,
    prefer: tuple[int, ...] | None,
    aim: float,
) -> tuple[Note, str] | None:
    if not targets:
        return None
    if aim_sensor is not None:
        matched = [ns for ns in targets if ns[1] == aim_sensor]
        if matched:
            return min(matched, key=lambda ns: abs(ns[0].t - 0.0))
    if prefer is not None:
        sector = [ns for ns in targets if _sensor_to_button(ns[1]) in prefer]
        if sector:
            return min(
                sector,
                key=lambda ns: (abs(ns[0].t), abs(_sensor_aim_score(ns[1]) - aim)),
            )
    return min(targets, key=lambda ns: (abs(ns[0].t), abs(_sensor_aim_score(ns[1]) - aim)))


# Re-export for callers that want geometric side with aim sectors.
button_side = sensor_side

__all__ = [
    "ActionDecoder",
    "DecodeResult",
    "LEFT_BUTTONS",
    "RIGHT_BUTTONS",
    "button_side",
]
