"""Tests for DX sensor geometry.

RADIUS values are MajdataView TouchDrop.GetAreaPos / 4.8 (local sources/; do not copy C#).
"""

from __future__ import annotations

import math

from fly_rg.sensors import RADIUS, note_landing_xy, sensor_xy


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
