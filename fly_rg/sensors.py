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

# Zone-center radii on the unit disk (Unity distance / 4.8).
# From MajdataView TouchDrop.GetAreaPos in local sources/; do not copy C#.
# Outer ring is one band of 16 A/D wedges; E sits in the B-ring gaps.
RADIUS = {
    "C": 0.0,
    "B": 0.479,
    "E": 0.625,
    "A": 0.854,
    "D": 0.854,
}

PAD = {
    "cR": 0.32,
    "bOct": 0.145,
    "eRadial": 0.08,
    "eTangent": 0.07,
    "adInner": 0.62,
    "adOuter": 0.995,
    "adHalf": math.pi / 16,
    "dInner": 0.72,
    "dOuter": 0.995,
    "dHalf": math.pi / 20,
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


def is_button_sensor(sensor: str) -> bool:
    try:
        area, _index = parse_sensor(sensor)
    except ValueError:
        return False
    return area == "A"


def note_landing_xy(sensor: str) -> tuple[float, float]:
    s = sensor.strip().upper()
    if s in ("C", "C1", "C2"):
        return sensor_xy(s)
    area, index = parse_sensor(s)
    if area == "A":
        ang = sensor_angle_rad("A", index)
        # Majdata TapBase/HoldDrop LAND at 4.8 (unit 1.0); touch GetAreaPos A is 4.1 (unit 0.854).
        return math.cos(ang), math.sin(ang)
    return sensor_xy(s)


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


def wrap_angle(a: float) -> float:
    """Wrap radians to (-pi, pi]."""
    tau = 2.0 * math.pi
    out = (a + math.pi) % tau - math.pi
    if out <= -math.pi:
        return math.pi
    return out


def xy_to_polar(x: float, y: float) -> tuple[float, float]:
    return math.atan2(y, x), math.hypot(x, y)


def polar_to_xy(theta: float, r: float) -> tuple[float, float]:
    return r * math.cos(theta), r * math.sin(theta)


def sensor_polar(sensor: str) -> tuple[float, float]:
    x, y = sensor_xy(sensor)
    return xy_to_polar(x, y)


def _in_regular_octagon(
    x: float, y: float, cx: float, cy: float, circum_r: float, rotation: float
) -> bool:
    dx = x - cx
    dy = y - cy
    c = math.cos(rotation)
    s = math.sin(rotation)
    lx = dx * c + dy * s
    ly = -dx * s + dy * c
    half = circum_r * math.cos(math.pi / 8.0)
    return (
        abs(lx) <= half
        and abs(ly) <= half
        and abs(lx) + abs(ly) <= half * math.sqrt(2.0)
    )


def _in_wedge(
    x: float, y: float, mid: float, half: float, inner: float, outer: float
) -> bool:
    r = math.hypot(x, y)
    if r < inner or r > outer:
        return False
    return abs(wrap_angle(math.atan2(y, x) - mid)) <= half


def _in_e_diamond(x: float, y: float, index: int) -> bool:
    mid = sensor_angle_rad("E", index)
    c = math.cos(mid)
    s = math.sin(mid)
    radial = x * c + y * s - RADIUS["E"]
    tangent = -x * s + y * c
    er = PAD["eRadial"]
    et = PAD["eTangent"]
    if er <= 0 or et <= 0:
        return False
    return abs(radial) / er + abs(tangent) / et <= 1.0


def nearest_sensor(x: float, y: float) -> str | None:
    """Occupancy label (C>B>E>A>D). Gaps return None. C not C1/C2."""
    if _in_regular_octagon(x, y, 0.0, 0.0, PAD["cR"], 0.0):
        return "C"
    for i in range(1, 9):
        mid = sensor_angle_rad("B", i)
        cx = RADIUS["B"] * math.cos(mid)
        cy = RADIUS["B"] * math.sin(mid)
        if _in_regular_octagon(x, y, cx, cy, PAD["bOct"], mid):
            return f"B{i}"
    for i in range(1, 9):
        if _in_e_diamond(x, y, i):
            return f"E{i}"
    for i in range(1, 9):
        mid = sensor_angle_rad("A", i)
        if _in_wedge(x, y, mid, PAD["adHalf"], PAD["adInner"], PAD["adOuter"]):
            return f"A{i}"
    for i in range(1, 9):
        mid = sensor_angle_rad("D", i)
        if _in_wedge(x, y, mid, PAD["dHalf"], PAD["dInner"], PAD["dOuter"]):
            return f"D{i}"
    return None
