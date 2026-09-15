"""Decode descending-neuron spikes (or mock drives) into aim and taps."""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Any, Never, Protocol

from fly_rg.encoder import note_target_sensor, note_window_tth
from fly_rg.schema import Note
from fly_rg.sensors import RADIUS, button_to_sensor, sensor_side, sensor_xy

# Aim sectors when DNa pool prefers left vs right (A-button indices).
LEFT_BUTTONS = (8, 1, 2, 7)
RIGHT_BUTTONS = (3, 4, 5, 6)

STEER_TYPES = ("DNa01", "DNa02", "DNa03", "DNa04")
TAP_TYPES = ("DNp01", "DNp02", "DNp03", "DNb01", "DNb02")

STEER_WINDOW = 7  # steps (~0.14 s at dt=0.02)
STEER_MARGIN = 1
TAP_WINDOW = 3  # steps (~0.06 s)
TAP_SPIKES = 1
TAP_COOLDOWN_S = 0.05
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
    hand_l_sensor: str | None = None
    hand_r_sensor: str | None = None
    tap_l: bool = False
    tap_r: bool = False
    strike_l: float = 0.0
    strike_r: float = 0.0
    steer_l: float = 0.0
    steer_r: float = 0.0
    tap_rate_l: float = 0.0
    tap_rate_r: float = 0.0


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
    """DNa01-04 L/R -> aim; DNp01-03 and DNb01-02 -> tap onto sensors."""

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
        self._history: deque[tuple[int, int, int, int]] = deque(maxlen=STEER_WINDOW)
        self._steer_l_idx: set[int] = set()
        self._steer_r_idx: set[int] = set()
        self._tap_l_idx: set[int] = set()
        self._tap_r_idx: set[int] = set()
        self._brain = brain
        self.steer_l = 0.0
        self.steer_r = 0.0
        self.tap_l = 0.0
        self.tap_r = 0.0
        self.tap_rate_l = 0.0
        self.tap_rate_r = 0.0
        if brain is not None and not mock:
            tap_pool = tap_types if tap_types is not None else list(TAP_TYPES)
            self._steer_l_idx = _as_index_set(brain.cells(list(STEER_TYPES), "L"))
            self._steer_r_idx = _as_index_set(brain.cells(list(STEER_TYPES), "R"))
            self._tap_l_idx = _as_index_set(brain.cells(tap_pool, "L"))
            self._tap_r_idx = _as_index_set(brain.cells(tap_pool, "R"))

    def observe(self, fired: Any) -> None:
        if self.mock:
            return
        fired_set = _as_index_set(fired)
        l = len(fired_set & self._steer_l_idx)
        r = len(fired_set & self._steer_r_idx)
        tap_l = len(fired_set & self._tap_l_idx)
        tap_r = len(fired_set & self._tap_r_idx)
        self._history.append((l, r, tap_l, tap_r))

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

    def _rates(self) -> tuple[float, float, float, float]:
        if not self._history:
            return 0.0, 0.0, 0.0, 0.0
        recent = list(self._history)
        steer = recent[-STEER_WINDOW:]
        tap_win = recent[-TAP_WINDOW:]
        l = sum(x[0] for x in steer)
        r = sum(x[1] for x in steer)
        tap_l = sum(x[2] for x in tap_win)
        tap_r = sum(x[3] for x in tap_win)
        return float(l), float(r), float(tap_l), float(tap_r)

    def _store_rates(
        self, steer_l: float, steer_r: float, tap_l: float, tap_r: float
    ) -> None:
        self.steer_l = float(steer_l)
        self.steer_r = float(steer_r)
        self.tap_l = float(tap_l)
        self.tap_r = float(tap_r)
        self.tap_rate_l = float(tap_l)
        self.tap_rate_r = float(tap_r)

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
            if note_window_tth(note, now, look_ahead_s, slide_next=nxt) is None:
                continue
            sensor = note_target_sensor(note, slide_next=nxt)
            out.append((note, sensor))
        return out

    def _decode_spikes(
        self,
        now: float,
        notes: list[Note],
        look_ahead_s: float,
        slide_next: list[int] | None,
    ) -> DecodeResult:
        l, r, tap_l_count, tap_r_count = self._rates()
        self._store_rates(l, r, tap_l_count, tap_r_count)
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
        hand_l, hand_r = _assign_hands(aim, l, r, active)
        aim_sensor = hand_r if (prefer is RIGHT_BUTTONS and hand_r) else (
            hand_l if hand_l else hand_r
        )
        if aim_sensor is None:
            aim_sensor = _pick_aim_sensor(aim, prefer, active)
        aim_button = _sensor_to_button(aim_sensor)

        cooldown_ok = (now - self._last_tap_t) >= TAP_COOLDOWN_S
        tap_l = cooldown_ok and tap_l_count >= TAP_SPIKES and hand_l is not None
        tap_r = cooldown_ok and tap_r_count >= TAP_SPIKES and hand_r is not None
        tap = tap_l or tap_r
        tap_sensor: str | None = None
        if tap_l:
            tap_sensor = hand_l
        elif tap_r:
            tap_sensor = hand_r
        if tap:
            self._last_tap_t = now
        strike_l = min(1.0, tap_l_count / max(TAP_SPIKES, 1))
        strike_r = min(1.0, tap_r_count / max(TAP_SPIKES, 1))
        if tap_l:
            strike_l = 1.0
        if tap_r:
            strike_r = 1.0
        return DecodeResult(
            aim_button=aim_button,
            tap=tap,
            tap_button=_sensor_to_button(tap_sensor) if tap else None,
            aim_sensor=aim_sensor,
            tap_sensor=tap_sensor if tap else None,
            aim=aim,
            strike=max(strike_l, strike_r),
            hand_l_sensor=hand_l,
            hand_r_sensor=hand_r,
            tap_l=tap_l,
            tap_r=tap_r,
            strike_l=strike_l,
            strike_r=strike_r,
            steer_l=l,
            steer_r=r,
            tap_rate_l=tap_l_count,
            tap_rate_r=tap_r_count,
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
        self._store_rates(left_strength, right_strength, left_strength, right_strength)
        total = left_strength + right_strength
        if total <= 1e-9:
            aim = 0.0
            prefer = None
        else:
            aim = (right_strength - left_strength) / max(total, 1e-9)
            prefer = RIGHT_BUTTONS if aim >= 0 else LEFT_BUTTONS

        active = self._active_targets(now, notes, look_ahead_s, slide_next)
        hand_l, hand_r = _assign_hands(aim, left_strength, right_strength, active)
        aim_sensor = hand_r if (prefer is RIGHT_BUTTONS and hand_r) else (
            hand_l if hand_l else hand_r
        )
        if aim_sensor is None:
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
        tap_l = False
        tap_r = False
        tap_sensor: str | None = None
        strike_l = min(1.0, left_strength / 0.8)
        strike_r = min(1.0, right_strength / 0.8)
        if (now - self._last_tap_t) >= TAP_COOLDOWN_S:
            in_window: list[tuple[Note, str]] = []
            for i, note in enumerate(notes):
                nxt = 0 if slide_next is None else slide_next[i]
                sensor = note_target_sensor(note, slide_next=nxt)
                nt = note.type
                if nt == "slide":
                    if note.slide is not None and nxt > 0:
                        if now <= note.slide.end_t:
                            in_window.append((note, sensor))
                    elif abs(note.t - now) <= PERFECT_WINDOW_S:
                        in_window.append((note, sensor))
                    continue
                if nt == "tap" or nt == "hold" or nt == "touch" or nt == "touch_hold":
                    if abs(note.t - now) <= PERFECT_WINDOW_S:
                        in_window.append((note, sensor))
                    continue
                _exhaustive: Never = nt
                raise ValueError(f"unknown note type: {_exhaustive}")
            window_sensors = {s for _n, s in in_window}
            p = min(0.95, 0.35 + 0.8 * inject_strength)
            if hand_l and hand_l in window_sensors and left_strength > 0.05:
                if self.rng.random() < p:
                    tap_l = True
            if hand_r and hand_r in window_sensors and right_strength > 0.05:
                if self.rng.random() < p:
                    tap_r = True
            tap = tap_l or tap_r
            if tap:
                tap_sensor = hand_l if tap_l else hand_r
                self._last_tap_t = now
                if tap_l:
                    strike_l = 1.0
                if tap_r:
                    strike_r = 1.0
        return DecodeResult(
            aim_button=aim_button,
            tap=tap,
            tap_button=_sensor_to_button(tap_sensor) if tap else None,
            aim_sensor=aim_sensor,
            tap_sensor=tap_sensor if tap else None,
            aim=float(max(-1.0, min(1.0, aim))),
            strike=float(max(strike_l, strike_r)),
            hand_l_sensor=hand_l,
            hand_r_sensor=hand_r,
            tap_l=tap_l,
            tap_r=tap_r,
            strike_l=float(strike_l),
            strike_r=float(strike_r),
            steer_l=float(left_strength),
            steer_r=float(right_strength),
            tap_rate_l=float(left_strength),
            tap_rate_r=float(right_strength),
        )


def _sensor_aim_score(sensor: str) -> float:
    """Map sensor to -1..1 lateral (cos of angle; +X right)."""
    x, _y = sensor_xy(sensor)
    return max(-1.0, min(1.0, x / max(RADIUS["A"], 1e-6)))


HAND_ON = 0.05


def _best_sensor(pool: list[tuple[Note, str]], aim: float) -> str | None:
    if not pool:
        return None
    return min(pool, key=lambda ns: (ns[0].t, abs(_sensor_aim_score(ns[1]) - aim)))[1]


def _unique_soonest(active: list[tuple[Note, str]]) -> list[str]:
    seen: list[str] = []
    for _note, sensor in sorted(active, key=lambda ns: ns[0].t):
        if sensor not in seen:
            seen.append(sensor)
    return seen


def _assign_hands(
    aim: float,
    left_strength: float,
    right_strength: float,
    active: list[tuple[Note, str]],
) -> tuple[str | None, str | None]:
    """Two distinct sensors when two notes exist. Never stack both hands on one pad."""
    sensors = _unique_soonest(active)
    if not sensors:
        return None, None

    leftish = [s for s in sensors if sensor_side(s) == "L"]
    rightish = [s for s in sensors if sensor_side(s) == "R"]

    if len(sensors) >= 2:
        if leftish and rightish:
            return leftish[0], rightish[0]
        a, b = sensors[0], sensors[1]
        if _sensor_aim_score(a) <= _sensor_aim_score(b):
            return a, b
        return b, a

    only = sensors[0]
    if left_strength > right_strength + HAND_ON:
        return only, None
    if right_strength > left_strength + HAND_ON:
        return None, only
    if sensor_side(only) == "L":
        return only, None
    return None, only


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
    "STEER_TYPES",
    "TAP_TYPES",
    "button_side",
]
