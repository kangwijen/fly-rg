"""Tests for DX sensor geometry."""

from __future__ import annotations

from fly_rg.sensors import sensor_xy


def test_d1_at_top():
    _x, y = sensor_xy("D1")
    assert y > 0.8
