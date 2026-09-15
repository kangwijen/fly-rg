"""Tests for judgment windows and scoring."""

from __future__ import annotations

from fly_rg.judge import GOOD, GREAT, PERFECT, Judge
from fly_rg.schema import Note


def _notes() -> list[Note]:
    return [
        Note(t=1.0, button=1, type="tap"),
        Note(t=2.0, button=2, type="tap"),
        Note(t=3.0, button=1, type="tap"),
    ]


def test_perfect_great_good_windows():
    j = Judge(_notes())
    h = j.press(1, 1.0)
    assert h is not None and h.judgment == "perfect"
    assert j.score.perfect == 1 and j.score.combo == 1

    h = j.press(2, 2.0 + PERFECT + 1e-4)
    assert h is not None and h.judgment == "great"
    assert j.score.great == 1 and j.score.combo == 2

    h = j.press(1, 3.0 + GREAT + 1e-4)
    assert h is not None and h.judgment == "good"
    assert j.score.good == 1 and j.score.combo == 3


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
    # 2 perfect, 1 miss -> (1+1+0)/3
    assert abs(j.score.accuracy - (2.0 / 3.0)) < 1e-9
