"""Tests for judgment windows and scoring."""

from __future__ import annotations

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

    j = Judge([Note(t=1.0, type="touch", sensor="B5")])
    h = j.press("B5", 1.160)
    assert h is not None and h.judgment == "perfect" and h.timing == "late"

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
    # 2 critical + 1 miss -> 2/3
    assert abs(j.score.accuracy - (2.0 / 3.0)) < 1e-9


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
