"""Tests for DX sensor geometry."""

from __future__ import annotations

from fly_rg.sensors import sensor_xy


def test_d1_at_top():
    _x, y = sensor_xy("D1")
    assert y > 0.75


def test_a_and_d_share_outer_ring():
    from fly_rg.sensors import RADIUS

    assert RADIUS["A"] == RADIUS["D"]
    ax, ay = sensor_xy("A1")
    dx, dy = sensor_xy("D1")
    assert dy > ay
    assert ax > dx
