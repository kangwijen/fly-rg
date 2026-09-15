"""maimai DX touch sensor geometry (Majdata TouchDrop.GetAreaPos).

Layout (unit disk, y up):
  D1/E1 at top (12 o'clock); A1/B1 at ~1:30.
  Outer ring alternates A and D wedges; E diamonds inset from D;
  B octagons inset from A; C split C1 (right) / C2 (left).
"""

from __future__ import annotations

import math
from typing import Literal

Area = Literal["A", "B", "C", "D", "E"]

# Radii of zone centers (relative to outer playfield).
RADIUS = {
    "C": 0.0,
    "B": 0.40,
    "E": 0.58,
    "A": 0.86,
    "D": 0.86,
}


def parse_sensor(sensor: str) -> tuple[Area, int]:
    """Parse 'A1'..'E8' or 'C'/'C1'/'C2' into (area, index). C index is 0."""
    s = sensor.strip().upper()
    if not s:
        raise ValueError("empty sensor")
    area = s[0]
    if area not in "ABCDE":
        raise ValueError(f"unknown sensor area in {sensor!r}")
    if area == "C":
        return "C", 0
    if len(s) < 2 or not s[1:].isdigit():
        raise ValueError(f"bad sensor id {sensor!r}")
    idx = int(s[1:])
    if not 1 <= idx <= 8:
        raise ValueError(f"sensor index out of range in {sensor!r}")
    return area, idx  # type: ignore[return-value]


def format_sensor(area: Area, index: int) -> str:
    if area == "C":
        return "C"
    return f"{area}{index}"


def button_to_sensor(button: int) -> str:
    if not 1 <= button <= 8:
        raise ValueError(f"button must be 1..8, got {button}")
    return f"A{button}"


def sensor_angle_rad(area: Area, index: int = 1) -> float:
    """Math angle (radians): 0 = +X, pi/2 = +Y (up)."""
    if area == "C":
        return 0.0
    if area in ("A", "B"):
        # Majdata: (-index * pi/4) + (5*pi/8)  -> A1/B1 at NE
        return (-index * (math.pi / 4.0)) + (5.0 * math.pi / 8.0)
    if area in ("D", "E"):
        # Majdata: (-index * pi/4) + (6*pi/8)  -> D1/E1 at top
        return (-index * (math.pi / 4.0)) + (6.0 * math.pi / 8.0)
    raise ValueError(f"unknown area {area}")


def sensor_xy(sensor: str) -> tuple[float, float]:
    """Unit disk coords: x right, y up. C at origin; C1 right, C2 left."""
    s = sensor.strip().upper()
    if s == "C1":
        return 0.08, 0.0
    if s == "C2":
        return -0.08, 0.0
    area, index = parse_sensor(sensor)
    if area == "C":
        return 0.0, 0.0
    ang = sensor_angle_rad(area, index)
    r = RADIUS[area]
    return r * math.cos(ang), r * math.sin(ang)


def sensor_side(sensor: str) -> str:
    """L if x < 0 else R (C defaults to R)."""
    x, _y = sensor_xy(sensor)
    if x < -1e-6:
        return "L"
    return "R"


def all_sensors() -> list[str]:
    out = ["C"]
    for area in ("A", "B", "D", "E"):
        for i in range(1, 9):
            out.append(f"{area}{i}")
    return out
