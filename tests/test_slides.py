"""Tests for Simai slide path expansion."""

from __future__ import annotations

from fly_rg.slides import expand_slide, expand_wifi


def test_expand_slide_gt_cw_and_ccw():
    assert expand_slide(">", 1, 5) == ["A1", "A2", "A3", "A4", "A5"]
    assert expand_slide(">", 5, 1) == ["A5", "A4", "A3", "A2", "A1"]


def test_expand_slide_lt_cw_and_ccw():
    assert expand_slide("<", 1, 5) == ["A1", "A8", "A7", "A6", "A5"]
    assert expand_slide("<", 5, 1) == ["A5", "A6", "A7", "A8", "A1"]


def test_expand_slide_caret_ring_only():
    assert expand_slide("^", 1, 5) == ["A1", "A2", "A3", "A4", "A5"]
    assert expand_slide("^", 5, 1) == ["A5", "A4", "A3", "A2", "A1"]


def test_expand_slide_straight_and_thunder():
    assert expand_slide("-", 1, 5) == ["A1", "B1", "C", "B5", "A5"]
    assert expand_slide("z", 1, 5) == ["A1", "B8", "B7", "C", "B3", "B4", "A5"]
    assert expand_slide("s", 1, 5) == ["A1", "B2", "B3", "C", "B7", "B6", "A5"]


def test_expand_slide_p_vs_q_direction():
    p = expand_slide("p", 1, 2)
    q = expand_slide("q", 1, 2)
    assert p != q
    assert "B8" in p
    assert "B8" not in q


def test_expand_slide_gt_half_flip_ccw():
    assert expand_slide(">", 4, 8) == ["A4", "A3", "A2", "A1", "A8"]


def test_expand_slide_gt_from_5_short_arc():
    assert expand_slide(">", 5, 3) == ["A5", "A4", "A3"]


def test_expand_slide_p_from_7_uses_b6_not_b8():
    path = expand_slide("p", 7, 3)
    assert "B6" in path
    assert "B8" not in path


def test_expand_wifi_from_button_1():
    wifi = expand_wifi(1)
    assert len(wifi) == 3
    assert [path[-1] for path in wifi] == ["A6", "A5", "A4"]
    assert wifi[0] == ["A1", "B8", "B7", "A6"]
    assert wifi[1] == ["A1", "B1", "C", "B5", "A5"]
    assert wifi[2] == ["A1", "B2", "B3", "A4"]
