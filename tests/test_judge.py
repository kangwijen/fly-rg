"""Tests for judgment windows and scoring."""

from __future__ import annotations

import pytest

from fly_rg.judge import GOOD, Judge
from fly_rg.schema import Note, SlideInfo


def _notes() -> list[Note]:
    return [
        Note(t=1.0, button=1, type="tap"),
        Note(t=2.0, button=2, type="tap"),
        Note(t=3.0, button=1, type="tap"),
    ]


def test_dx_windows():
    j = Judge([Note(t=1.0, button=1, type="tap")])
    h = j.press(1, 1.0)
    assert h is not None and h.judgment == "critical"
    assert h.timing is None
    assert j.score.critical == 1

    j = Judge([Note(t=1.0, button=1, type="tap")])
    h = j.press(1, 1.020)
    assert h is not None and h.judgment == "perfect" and h.timing == "late"

    j = Judge([Note(t=1.0, button=1, type="tap")])
    h = j.press(1, 0.980)
    assert h is not None and h.judgment == "perfect" and h.timing == "fast"

    j = Judge([Note(t=1.0, button=1, type="tap")])
    h = j.press(1, 1.060)
    assert h is not None and h.judgment == "great" and h.timing == "late"

    j = Judge([Note(t=1.0, button=1, type="tap")])
    h = j.press(1, 1.120)
    assert h is not None and h.judgment == "good" and h.timing == "late"

    j = Judge([Note(t=1.0, button=1, type="tap")])
    assert j.press(1, 1.160) is None
    misses = j.auto_miss(1.160)
    assert len(misses) == 1
    assert misses[0].judgment == "miss"
    assert misses[0].timing is None
    assert misses[0].error_ms == pytest.approx(160.0, abs=0.05)

    j = Judge([Note(t=1.0, type="touch", sensor="B5")])
    h = j.press("B5", 1.160)
    assert h is not None and h.judgment == "perfect" and h.timing == "late"


def test_hit_error_ms_fast_late_and_critical():
    j = Judge([Note(t=1.0, button=1, type="tap")])
    h = j.press(1, 1.0)
    assert h is not None
    assert h.error_ms == pytest.approx(0.0, abs=0.05)

    j = Judge([Note(t=1.0, button=1, type="tap")])
    h = j.press(1, 0.980)
    assert h is not None
    assert h.error_ms == pytest.approx(-20.0, abs=0.05)

    j = Judge([Note(t=1.0, button=1, type="tap")])
    h = j.press(1, 1.020)
    assert h is not None
    assert h.error_ms == pytest.approx(20.0, abs=0.05)


def test_slide_waypoint_omits_error_ms():
    path = ("A1", "B1", "A5")
    j = Judge(
        [
            Note(
                t=1.0,
                button=1,
                type="slide",
                sensor="A1",
                end=2.0,
                slide=SlideInfo(shape="-", end_sensor="A5", path=path, end_t=2.0),
            )
        ]
    )
    head = j.press("A1", 0.980)
    assert head is not None
    assert head.error_ms == pytest.approx(-20.0, abs=0.05)
    waypoint = j.press("B1", 1.2)
    assert waypoint is not None
    assert waypoint.error_ms is None

    j = Judge([Note(t=1.0, type="touch", sensor="B5")])
    h = j.press("B5", 1.0)
    assert h is not None and h.judgment == "critical" and h.timing is None


def test_miss_breaks_combo_and_outside_window_ignored():
    j = Judge(_notes())
    assert j.press(1, 1.0 + GOOD + 0.01) is None
    misses = j.auto_miss(1.0 + GOOD + 0.05)
    assert len(misses) == 1
    assert misses[0].judgment == "miss"
    assert j.score.miss == 1
    assert j.score.combo == 0


def test_nearest_unmatched_on_button():
    notes = [
        Note(t=1.00, button=3, type="tap"),
        Note(t=1.02, button=3, type="tap"),
    ]
    j = Judge(notes)
    h = j.press(3, 1.015)
    assert h is not None
    assert h.note_index == 1
    h2 = j.press(3, 1.00)
    assert h2 is not None
    assert h2.note_index == 0


def test_accuracy():
    j = Judge(_notes())
    j.press(1, 1.0)
    j.press(2, 2.0)
    j.auto_miss(3.0 + GOOD + 0.01)
    # 2 critical + 1 miss on equal taps: DX 6/9, achievement 1000/1500
    assert abs(j.score.accuracy - (2.0 / 3.0)) < 1e-9
    assert abs(j.score.achievement - (2.0 / 3.0)) < 1e-9
    assert j.score.dx_points == 6
    assert j.score.max_dx == 9


def test_achievement_all_critical_taps_is_100():
    j = Judge(_notes())
    j.press(1, 1.0)
    j.press(2, 2.0)
    j.press(1, 3.0)
    assert abs(j.score.achievement - 1.0) < 1e-12
    assert abs(j.score.accuracy - 1.0) < 1e-12


def test_achievement_all_critical_breaks_is_101():
    notes = [
        Note(t=1.0, button=1, type="tap", is_break=True),
        Note(t=2.0, button=2, type="tap", is_break=True),
    ]
    j = Judge(notes)
    j.press(1, 1.0)
    j.press(2, 2.0)
    assert abs(j.score.achievement - 1.01) < 1e-12
    assert abs(j.score.accuracy - 1.0) < 1e-12


def test_break_perfect_gives_100_plus_half_bonus():
    j = Judge([Note(t=1.0, button=1, type="tap", is_break=True)])
    h = j.press(1, 1.020)
    assert h is not None and h.judgment == "perfect"
    # 2500/2500 base + 50/100 * 1%
    assert abs(j.score.achievement - 1.005) < 1e-12


def test_hold_and_slide_weights():
    notes = [
        Note(t=1.0, button=1, type="hold", end=2.0),
        Note(
            t=2.0,
            button=2,
            type="slide",
            sensor="A2",
            end=3.0,
            slide=SlideInfo(shape="-", end_sensor="A2", path=("A2",), end_t=3.0),
        ),
    ]
    j = Judge(notes)
    assert j.score.max_base == 2500
    j.press(1, 1.0)
    j.press(2, 2.0)
    assert abs(j.score.achievement - 1.0) < 1e-12


def test_judge_by_sensor_touch():
    notes = [Note(t=1.0, type="touch", sensor="B5")]
    j = Judge(notes)
    assert j.press("B5", 1.0) is not None
    assert j.matched[0]


def test_slide_progress_and_complete():
    path = ("A1", "B1", "C", "B5", "A5")
    notes = [
        Note(
            t=1.0,
            button=1,
            type="slide",
            sensor="A1",
            end=2.0,
            slide=SlideInfo(shape="-", end_sensor="A5", path=path, end_t=2.0),
        )
    ]
    j = Judge(notes)
    assert j.press("A1", 1.0) is not None
    assert j.slide_next[0] == 1
    assert not j.matched[0]
    assert "B1" in j.active_sensors(1.0, 1.0)

    assert j.press("B1", 1.2) is not None
    assert j.slide_next[0] == 2
    assert j.press("C", 1.4) is not None
    assert j.press("B5", 1.6) is not None
    h = j.press("A5", 1.8)
    assert h is not None
    assert j.matched[0]
    assert j.score.critical == 1
    assert h.judgment == "critical"
    assert h.timing is None


def test_slide_incomplete_misses():
    path = ("A1", "B1", "C", "B5", "A5")
    notes = [
        Note(
            t=1.0,
            button=1,
            type="slide",
            sensor="A1",
            end=1.5,
            slide=SlideInfo(shape="-", end_sensor="A5", path=path, end_t=1.5),
        )
    ]
    j = Judge(notes)
    j.press("A1", 1.0)
    j.press("B1", 1.1)
    misses = j.auto_miss(1.51)
    assert len(misses) == 1
    assert misses[0].judgment == "miss"
    assert j.score.miss == 1
