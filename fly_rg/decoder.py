"""Decode descending-neuron rates into Cartesian glide and tap pulses."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol

from fly_rg.sensors import (
    REST_HOME,
    nearest_sensor,
    sensor_side,
    sensor_xy,
    xy_to_polar,
)

STEER_TYPES = ("DNa01", "DNa02", "DNa03", "DNa04")
TAP_TYPES = ("DNp01", "DNp02", "DNp03", "DNb01", "DNb02")

STEER_WINDOW_S = 0.14
TAP_WINDOW_S = 0.06
TAP_SPIKES = 1
TAP_COOLDOWN_S = 0.010
OMEGA_MAX = 3.0 * math.tau
VR_MAX = 4.0
V_MAX = 8.0
R_MAX = 1.0


class SpikeBrain(Protocol):
    def cells(self, types: list[str], side: str) -> Any: ...


@dataclass
class DecodeResult:
    aim_button: int | None
    tap: bool
    tap_button: int | None
    aim_sensor: str | None
    tap_sensor: str | None
    aim: float
    strike: float
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
    hand_l: tuple[float, float] = (0.0, 0.0)
    hand_r: tuple[float, float] = (0.0, 0.0)
    omega_l: float = 0.0
    omega_r: float = 0.0
    reach_l: float = 0.0
    reach_r: float = 0.0


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


def _clip(value: float, limit: float) -> float:
    if value > limit:
        return limit
    if value < -limit:
        return -limit
    return value


def _empty_counts() -> dict[str, float]:
    out: dict[str, float] = {}
    for side in ("L", "R"):
        for name in ("DNa01", "DNa02", "DNa03", "DNa04", "tap"):
            out[f"{name}_{side}"] = 0.0
    return out


def _clamp_disk(x: float, y: float) -> tuple[float, float]:
    r = math.hypot(x, y)
    if r > R_MAX and r > 1e-12:
        scale = R_MAX / r
        return x * scale, y * scale
    return x, y


def _pose_from_velocity(
    x: float, y: float, vx: float, vy: float
) -> tuple[float, float]:
    r = math.hypot(x, y)
    omega = (x * vy - y * vx) / max(r * r, 1e-6)
    reach = (x * vx + y * vy) / max(r, 1e-6)
    return omega, _clip(reach, VR_MAX)


class ActionDecoder:
    """One motor path: DNa Cartesian glide, DNp onset tap, hands on glass."""

    def __init__(
        self,
        brain: SpikeBrain | None = None,
        *,
        mock: bool = False,
        tap_types: list[str] | None = None,
        seed: int = 0,
    ):
        self.mock = mock
        self._brain = brain
        self._steer_idx: dict[tuple[str, str], set[int]] = {}
        self._tap_idx: dict[str, set[int]] = {"L": set(), "R": set()}
        tap_pool = tap_types if tap_types is not None else list(TAP_TYPES)
        if brain is not None:
            for side in ("L", "R"):
                for typ in STEER_TYPES:
                    self._steer_idx[(typ, side)] = _as_index_set(
                        brain.cells([typ], side)
                    )
                self._tap_idx[side] = _as_index_set(brain.cells(tap_pool, side))
        self._counts = _empty_counts()
        self._hist: deque[tuple[float, dict[str, float]]] = deque()
        self._prev_tap_l = 0.0
        self._prev_tap_r = 0.0
        self._last_tap_l_t = -1e9
        self._last_tap_r_t = -1e9
        self.x_l, self.y_l = sensor_xy(REST_HOME["L"])
        self.x_r, self.y_r = sensor_xy(REST_HOME["R"])
        self.theta_l, self.r_l = xy_to_polar(self.x_l, self.y_l)
        self.theta_r, self.r_r = xy_to_polar(self.x_r, self.y_r)
        self.steer_l = 0.0
        self.steer_r = 0.0
        self.tap_l = 0.0
        self.tap_r = 0.0
        self.tap_rate_l = 0.0
        self.tap_rate_r = 0.0

    @property
    def hand_l(self) -> tuple[float, float]:
        return (self.x_l, self.y_l)

    @property
    def hand_r(self) -> tuple[float, float]:
        return (self.x_r, self.y_r)

    def observe(self, fired: Any) -> None:
        counts = _empty_counts()
        fired_set = _as_index_set(fired)
        for side in ("L", "R"):
            for typ in STEER_TYPES:
                idx = self._steer_idx.get((typ, side), set())
                counts[f"{typ}_{side}"] = float(len(fired_set & idx))
            counts[f"tap_{side}"] = float(
                len(fired_set & self._tap_idx.get(side, set()))
            )
        self._counts = counts

    def decode(
        self,
        now: float,
        notes: Any = None,
        *,
        dt: float = 0.004,
        look_ahead_s: float = 1.0,
        drive: dict[str, float] | None = None,
        last_inject: dict[str, float] | None = None,
        slide_next: list[int] | None = None,
        contact: set[str] | None = None,
    ) -> DecodeResult:
        del notes, look_ahead_s, last_inject, slide_next
        step_dt = float(dt) if dt > 0 else 0.004
        drive = drive or {}
        self._hist.append((now, dict(self._counts)))
        cutoff = now - STEER_WINDOW_S
        while self._hist and self._hist[0][0] < cutoff:
            self._hist.popleft()

        east_l = float(drive.get("eastL", 0.0))
        west_l = float(drive.get("westL", 0.0))
        north_l = float(drive.get("northL", 0.0))
        south_l = float(drive.get("southL", 0.0))
        east_r = float(drive.get("eastR", 0.0))
        west_r = float(drive.get("westR", 0.0))
        north_r = float(drive.get("northR", 0.0))
        south_r = float(drive.get("southR", 0.0))
        vx_l = (east_l - west_l) * V_MAX
        vy_l = (north_l - south_l) * V_MAX
        vx_r = (east_r - west_r) * V_MAX
        vy_r = (north_r - south_r) * V_MAX

        self.x_l += vx_l * step_dt
        self.y_l += vy_l * step_dt
        self.x_r += vx_r * step_dt
        self.y_r += vy_r * step_dt
        self.x_l, self.y_l = _clamp_disk(self.x_l, self.y_l)
        self.x_r, self.y_r = _clamp_disk(self.x_r, self.y_r)
        self.theta_l, self.r_l = xy_to_polar(self.x_l, self.y_l)
        self.theta_r, self.r_r = xy_to_polar(self.x_r, self.y_r)
        omega_l, reach_l = _pose_from_velocity(self.x_l, self.y_l, vx_l, vy_l)
        omega_r, reach_r = _pose_from_velocity(self.x_r, self.y_r, vx_r, vy_r)

        xy_l = (self.x_l, self.y_l)
        xy_r = (self.x_r, self.y_r)
        hand_l_sensor = nearest_sensor(*xy_l)
        hand_r_sensor = nearest_sensor(*xy_r)

        tap_l_now = self._counts["tap_L"]
        tap_r_now = self._counts["tap_R"]
        # Spike-only tap edge. The encoder injects growth{side} into the DNp tap
        # cells, so short-circuiting on the growth drive here would double count
        # the same signal and let taps fire with zero spikes.
        rising_l = tap_l_now >= TAP_SPIKES and self._prev_tap_l < TAP_SPIKES
        rising_r = tap_r_now >= TAP_SPIKES and self._prev_tap_r < TAP_SPIKES
        self._prev_tap_l = tap_l_now
        self._prev_tap_r = tap_r_now

        tap_l = rising_l and (now - self._last_tap_l_t) >= TAP_COOLDOWN_S
        tap_r = rising_r and (now - self._last_tap_r_t) >= TAP_COOLDOWN_S
        if tap_l:
            self._last_tap_l_t = now
        if tap_r:
            self._last_tap_r_t = now
        strike_l = 1.0 if tap_l else 0.0
        strike_r = 1.0 if tap_r else 0.0
        if contact:
            if hand_l_sensor is not None and hand_l_sensor in contact:
                strike_l = 1.0
            if hand_r_sensor is not None and hand_r_sensor in contact:
                strike_r = 1.0
        tap = tap_l or tap_r
        tap_sensor = hand_l_sensor if tap_l else (hand_r_sensor if tap_r else None)

        aim = _clip(0.5 * (xy_l[0] + xy_r[0]), 1.0)
        if aim >= 0:
            aim_sensor = hand_r_sensor
        else:
            aim_sensor = hand_l_sensor
        aim_button = _sensor_to_button(aim_sensor)

        tap_win_cut = now - TAP_WINDOW_S
        tap_l_win = 0.0
        tap_r_win = 0.0
        n_tap = 0
        for t, row in self._hist:
            if t < tap_win_cut:
                continue
            tap_l_win += row["tap_L"]
            tap_r_win += row["tap_R"]
            n_tap += 1
        if n_tap:
            tap_l_win /= n_tap
            tap_r_win /= n_tap

        self.steer_l = omega_l
        self.steer_r = omega_r
        self.tap_l = float(tap_l_now)
        self.tap_r = float(tap_r_now)
        self.tap_rate_l = tap_l_win
        self.tap_rate_r = tap_r_win

        return DecodeResult(
            aim_button=aim_button,
            tap=tap,
            tap_button=_sensor_to_button(tap_sensor) if tap else None,
            aim_sensor=aim_sensor,
            tap_sensor=tap_sensor if tap else None,
            aim=aim,
            strike=max(strike_l, strike_r),
            hand_l_sensor=hand_l_sensor,
            hand_r_sensor=hand_r_sensor,
            tap_l=tap_l,
            tap_r=tap_r,
            strike_l=strike_l,
            strike_r=strike_r,
            steer_l=omega_l,
            steer_r=omega_r,
            tap_rate_l=tap_l_win,
            tap_rate_r=tap_r_win,
            hand_l=xy_l,
            hand_r=xy_r,
            omega_l=omega_l,
            omega_r=omega_r,
            reach_l=reach_l,
            reach_r=reach_r,
        )


button_side = sensor_side

__all__ = [
    "ActionDecoder",
    "DecodeResult",
    "STEER_TYPES",
    "TAP_TYPES",
    "TAP_COOLDOWN_S",
    "V_MAX",
    "button_side",
]
