"""Tests for DX sensor geometry.

RADIUS values are MajdataView TouchDrop.GetAreaPos / 4.8 (local sources/; do not copy C#).
"""

from __future__ import annotations

import math

import pytest

from fly_rg.sensors import (
    RADIUS,
    nearest_sensor,
    note_landing_xy,
    sensor_polar,
    sensor_xy,
    wrap_angle,
)


def test_d1_at_top():
    _x, y = sensor_xy("D1")
    assert y > 0.75


def test_a_and_d_share_outer_ring():
    assert RADIUS["A"] == RADIUS["D"] == 0.854
    ax, ay = sensor_xy("A1")
    dx, dy = sensor_xy("D1")
    assert dy > ay
    assert ax > dx


def test_radius_matches_get_area_pos():
    assert abs(RADIUS["B"] - 0.479) < 1e-6
    assert abs(RADIUS["E"] - 0.625) < 1e-6
    assert abs(RADIUS["A"] - 0.854) < 1e-6
    assert abs(RADIUS["C"] - 0.0) < 1e-6


def test_note_landing_a1_at_unit_radius():
    ax, ay = note_landing_xy("A1")
    sx, sy = sensor_xy("A1")
    assert abs(math.hypot(ax, ay) - 1.0) < 1e-6
    assert math.hypot(ax, ay) > math.hypot(sx, sy)


def test_note_landing_b1_matches_sensor():
    assert note_landing_xy("B1") == sensor_xy("B1")


def test_nearest_sensor_centers():
    assert nearest_sensor(*sensor_xy("C")) == "C"
    assert nearest_sensor(*sensor_xy("A1")) == "A1"
    assert nearest_sensor(*sensor_xy("B3")) == "B3"
    assert nearest_sensor(*sensor_xy("D1")) == "D1"
    assert nearest_sensor(*sensor_xy("E5")) == "E5"


def test_nearest_sensor_returns_c_not_c1_c2():
    assert nearest_sensor(0.08, 0.0) == "C"
    assert nearest_sensor(-0.08, 0.0) == "C"
    assert nearest_sensor(0.0, 0.0) == "C"


def test_nearest_sensor_priority_c_over_b():
    bx, by = sensor_xy("B1")
    r = math.hypot(bx, by)
    x, y = (0.31 / r) * bx, (0.31 / r) * by
    assert nearest_sensor(x, y) == "C"


def test_nearest_sensor_gap_is_none():
    # D1 angle (12 o'clock), between C and E, off B wedges.
    assert nearest_sensor(0.0, 0.50) is None


def test_sensor_polar_matches_xy():
    theta, r = sensor_polar("A5")
    x, y = sensor_xy("A5")
    assert r == pytest.approx(math.hypot(x, y), abs=1e-9)
    assert theta == pytest.approx(math.atan2(y, x), abs=1e-9)
    assert x < 0


def test_wrap_angle_range():
    assert wrap_angle(0.0) == pytest.approx(0.0)
    assert wrap_angle(math.pi + 0.1) == pytest.approx(-math.pi + 0.1)
    assert wrap_angle(-math.pi - 0.1) == pytest.approx(math.pi - 0.1)
    assert wrap_angle(3 * math.pi) == pytest.approx(math.pi, abs=1e-9)
