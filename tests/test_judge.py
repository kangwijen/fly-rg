"""Tests for judgment windows and scoring."""

from __future__ import annotations

import pytest

from fly_rg.encoder import NoteEncoder
from fly_rg.judge import GOOD, SLIDE_CRITICAL, SLIDE_GOOD, Judge, _late_window
from fly_rg.schema import Note, SlideInfo


def _notes() -> list[Note]:
    return [
        Note(t=1.0, button=1, type="tap"),
        Note(t=2.0, button=2, type="tap"),
        Note(t=3.0, button=1, type="tap"),
    ]


def _slide(path: tuple[str, ...], *, t: float = 1.0, end_t: float = 2.0) -> Note:
    return Note(
        t=t,
        button=1,
        type="slide",
        sensor=path[0],
        end=end_t,
        slide=SlideInfo(shape="-", end_sensor=path[-1], path=path, end_t=end_t),
    )


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


def test_touch_fast_late_non_critical():
    j = Judge([Note(t=1.0, type="touch", sensor="B5")])
    h = j.press("B5", 0.900)
    assert h is not None and h.judgment == "critical" and h.timing is None

    j = Judge([Note(t=1.0, type="touch", sensor="B5")])
    h = j.press("B5", 1.220)
    assert h is not None and h.judgment == "great" and h.timing == "late"

    j = Judge([Note(t=1.0, type="touch", sensor="B5")])
    h = j.press("B5", 1.270)
    assert h is not None and h.judgment == "good" and h.timing == "late"


def test_ex_matches_window_only():
    j = Judge([Note(t=1.0, button=1, type="tap", is_ex=True)])
    h = j.press(1, 1.100)
    assert h is not None and h.judgment == "critical"

    j = Judge([Note(t=1.0, button=1, type="tap", is_ex=True)])
    assert j.press(1, 1.300) is None
    misses = j.auto_miss(1.160)
    assert len(misses) == 1
    assert misses[0].judgment == "miss"
    assert j.score.miss == 1
    assert j.score.critical == 0


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


def test_slide_waypoint_reports_body_timing():
    path = ("A1", "B1", "A5")
    j = Judge([_slide(path)])
    head = j.press("A1", 0.980)
    assert head is not None
    assert head.error_ms == pytest.approx(-20.0, abs=0.05)
    waypoint = j.press("B1", 1.2)
    assert waypoint is not None
    assert waypoint.error_ms == pytest.approx(-300.0, abs=0.5)
    assert waypoint.judgment == "great"
    assert waypoint.timing == "fast"

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


def test_break_high_perfect_gives_75_bonus():
    j = Judge([Note(t=1.0, button=1, type="tap", is_break=True)])
    h = j.press(1, 1.020)
    assert h is not None and h.judgment == "perfect"
    # 20ms is high Perfect (2/60); 2500/2500 base + 75/100 * 1%
    assert abs(j.score.achievement - 1.0075) < 1e-12


def test_break_low_perfect_gives_half_bonus():
    j = Judge([Note(t=1.0, button=1, type="tap", is_break=True)])
    h = j.press(1, 1.040)
    assert h is not None and h.judgment == "perfect"
    # 40ms is low Perfect (3/60); 2500/2500 base + 50/100 * 1%
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
    # Hold tail is scored in auto_miss; None contacted keeps the head judgment.
    j.auto_miss(2.01)
    assert abs(j.score.achievement - 1.0) < 1e-12


def test_judge_by_sensor_touch():
    notes = [Note(t=1.0, type="touch", sensor="B5")]
    j = Judge(notes)
    assert j.press("B5", 1.0) is not None
    assert j.matched[0]


def test_slide_progress_and_complete():
    path = ("A1", "B1", "C", "B5", "A5")
    notes = [_slide(path)]
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
    notes = [_slide(path, end_t=1.5)]
    j = Judge(notes)
    j.press("A1", 1.0)
    j.press("B1", 1.1)
    assert j.auto_miss(1.51) == []
    misses = j.auto_miss(1.5 + SLIDE_GOOD + 0.01)
    assert len(misses) == 1
    assert misses[0].judgment == "miss"
    assert j.score.miss == 1


def test_mine_press_is_penalty():
    notes = [
        Note(t=1.0, button=1, type="tap"),
        Note(t=1.0, button=1, type="tap", is_mine=True),
    ]
    j = Judge(notes)
    j.press(1, 1.0)
    assert j.score.critical == 1
    assert j.score.combo == 1
    mine = j.press(1, 1.0)
    assert mine is not None
    assert mine.judgment == "miss"
    assert j.score.critical == 1
    assert j.score.perfect == 0
    assert j.score.great == 0
    assert j.score.good == 0
    assert j.score.miss == 0
    assert j.score.mine == 1
    assert j.score.combo == 0
    assert j.score.max_base == 500
    assert abs(j.score.achievement - 1.0) < 1e-12


def test_mine_untouched_is_not_miss():
    j = Judge([Note(t=1.0, button=1, type="tap", is_mine=True)])
    assert j.score.max_base == 0
    assert j.score.max_dx == 0
    events = j.auto_miss(1.0 + GOOD + 0.05)
    assert events == []
    assert j.matched[0]
    assert j.score.miss == 0
    assert j.score.mine == 0
    assert j.score.combo == 0
    assert abs(j.score.achievement - 1.0) < 1e-12
    assert abs(j.score.accuracy - 1.0) < 1e-12


def test_hold_sustain_success():
    j = Judge([Note(t=1.0, button=1, type="hold", end=2.0)])
    head = j.press(1, 1.0)
    assert head is not None and head.judgment == "critical"
    assert not j.matched[0]
    assert j.score.critical == 0
    assert j.auto_miss(1.4, {"A1"}) == []
    assert j.auto_miss(1.8, {"A1"}) == []
    events = j.auto_miss(2.01, {"A1"})
    assert len(events) == 1
    assert events[0].judgment == "critical"
    assert j.matched[0]
    assert j.score.critical == 1
    assert abs(j.score.achievement - 1.0) < 1e-12


def test_hold_early_release():
    j = Judge([Note(t=1.0, button=1, type="hold", end=2.0)])
    j.press(1, 1.0)
    j.auto_miss(1.2, {"A1"})
    j.auto_miss(1.5, set())
    events = j.auto_miss(2.01, set())
    assert len(events) == 1
    # ARG: CP head released for a while; held_frac 1/2 >= 0.5 -> Great.
    assert events[0].judgment == "great"
    assert j.score.great == 1
    assert j.score.good == 0
    assert j.score.critical == 0
    assert j.score.miss == 0


def test_touch_hold_early_release():
    j = Judge([Note(t=1.0, type="touch_hold", sensor="C", end=2.0)])
    j.press("C", 1.0)
    j.auto_miss(1.3, set())
    events = j.auto_miss(2.01, set())
    assert len(events) == 1
    assert events[0].judgment == "good"


def test_hold_unwired_auto_miss_keeps_head():
    j = Judge([Note(t=1.0, button=1, type="hold", end=2.0)])
    j.press(1, 1.0)
    events = j.auto_miss(2.01)
    assert len(events) == 1
    assert events[0].judgment == "critical"
    assert j.score.critical == 1


def test_hold_cp_brief_drop_is_perfect():
    j = Judge([Note(t=1.0, button=1, type="hold", end=2.0)])
    j.press(1, 1.0)
    stamps = [1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9]
    for t in stamps:
        contacted = set() if 1.45 < t < 1.55 else {"A1"}
        assert j.auto_miss(t, contacted) == []
    events = j.auto_miss(2.01, {"A1"})
    assert len(events) == 1
    assert events[0].judgment == "perfect"
    assert events[0].timing == "fast"
    assert j.score.perfect == 1
    assert j.score.critical == 0


def test_hold_cp_long_drop_good_when_frac_low():
    j = Judge([Note(t=1.0, button=1, type="hold", end=2.0)])
    j.press(1, 1.0)
    j.auto_miss(1.1, {"A1"})
    for t in (1.3, 1.5, 1.7, 1.9):
        assert j.auto_miss(t, set()) == []
    events = j.auto_miss(2.01, set())
    assert len(events) == 1
    assert events[0].judgment == "good"
    assert j.score.good == 1
    assert j.score.critical == 0


def test_hold_good_head_held_to_end_becomes_great():
    j = Judge([Note(t=1.0, button=1, type="hold", end=2.0)])
    head = j.press(1, 1.120)
    assert head is not None and head.judgment == "good"
    j.auto_miss(1.5, {"A1"})
    events = j.auto_miss(2.01, {"A1"})
    assert len(events) == 1
    assert events[0].judgment == "great"
    assert j.score.great == 1
    assert j.score.good == 0


def test_hold_miss_head_remainder_is_good_late():
    j = Judge([Note(t=1.0, button=1, type="hold", end=2.0)])
    assert j.press(1, 1.20) is None
    assert j.auto_miss(1.20, set()) == []
    j.auto_miss(1.5, {"A1"})
    j.auto_miss(1.8, {"A1"})
    events = j.auto_miss(2.01, {"A1"})
    assert len(events) == 1
    assert events[0].judgment == "good"
    assert events[0].timing == "late"
    assert j.score.good == 1
    assert j.score.miss == 0


def test_hold_miss_untouched_is_miss():
    j = Judge([Note(t=1.0, button=1, type="hold", end=2.0)])
    assert j.auto_miss(1.20, set()) == []
    events = j.auto_miss(2.01, set())
    assert len(events) == 1
    assert events[0].judgment == "miss"
    assert j.score.miss == 1
    assert j.score.good == 0


def test_short_hold_drop_keeps_head_judgment():
    j = Judge([Note(t=1.0, button=1, type="hold", end=1.10)])
    head = j.press(1, 1.0)
    assert head is not None and head.judgment == "critical"
    j.auto_miss(1.05, set())
    events = j.auto_miss(1.11, set())
    assert len(events) == 1
    assert events[0].judgment == "critical"
    assert j.score.critical == 1
    assert j.score.good == 0


def test_hold_last_frame_drop_stays_critical():
    j = Judge([Note(t=1.0, button=1, type="hold", end=2.0)])
    j.press(1, 1.0)
    j.auto_miss(1.5, {"A1"})
    j.auto_miss(1.995, set())
    events = j.auto_miss(2.01, set())
    assert len(events) == 1
    assert events[0].judgment == "critical"
    assert j.score.critical == 1


def test_ex_hold_long_drop_promotes_good_to_great():
    j = Judge([Note(t=1.0, button=1, type="hold", end=2.0, is_ex=True)])
    head = j.press(1, 1.0)
    assert head is not None and head.judgment == "critical"
    j.auto_miss(1.1, {"A1"})
    for t in (1.3, 1.5, 1.7, 1.9):
        assert j.auto_miss(t, set()) == []
    events = j.auto_miss(2.01, set())
    assert len(events) == 1
    assert events[0].judgment == "great"
    assert j.score.great == 1
    assert j.score.good == 0


def test_break_great_high_mid_low_points():
    j = Judge([Note(t=1.0, button=1, type="tap", is_break=True)])
    h = j.press(1, 1.055)
    assert h is not None and h.judgment == "great"
    assert j.score.base_points == 2000
    assert j.score.bonus_points == 40
    assert j.score.great == 1

    j = Judge([Note(t=1.0, button=1, type="tap", is_break=True)])
    h = j.press(1, 1.075)
    assert h is not None and h.judgment == "great"
    assert j.score.base_points == 1500
    assert j.score.bonus_points == 40

    j = Judge([Note(t=1.0, button=1, type="tap", is_break=True)])
    h = j.press(1, 1.090)
    assert h is not None and h.judgment == "great"
    assert j.score.base_points == 1250
    assert j.score.bonus_points == 40

    j = Judge([Note(t=1.0, button=1, type="tap")])
    h = j.press(1, 1.055)
    assert h is not None and h.judgment == "great"
    assert j.score.base_points == 400
    assert j.score.bonus_points == 0


def test_slide_last_node_critical_leeway_gt_1_to_4():
    # donmai 1>4, ta=2s, circumference CW dist 3, dl/dt=0.1551.
    # CP expands by ta * ratio / 4 each side: 2*0.1551/4 = 0.07755s.
    path = ("A1", "A2", "A3", "A4")
    note = Note(
        t=1.0,
        button=1,
        type="slide",
        sensor="A1",
        end=3.0,
        slide=SlideInfo(
            shape=">",
            end_sensor="A4",
            path=path,
            end_t=3.0,
            wait_t=0.0,
        ),
    )
    extra = 2.0 * 0.1551 / 4.0
    expanded = SLIDE_CRITICAL + extra
    err = SLIDE_CRITICAL + extra * 0.5
    assert err > SLIDE_CRITICAL
    assert err < expanded

    mid_expected = 1.0 + 2.0 * (1.0 / 3.0)
    j_mid = Judge([note])
    assert j_mid.press("A1", 1.0) is not None
    mid = j_mid.press("A2", mid_expected + err)
    assert mid is not None
    assert mid.judgment == "great"

    j_last = Judge([note])
    assert j_last.press("A1", 1.0) is not None
    assert j_last.press("A2", mid_expected) is not None
    assert j_last.press("A3", 1.0 + 2.0 * (2.0 / 3.0)) is not None
    last = j_last.press("A4", 3.0 + err)
    assert last is not None
    assert last.judgment == "critical"
    assert j_last.score.critical == 1


def test_slide_bad_middle_downgrades():
    j = Judge([_slide(("A1", "B1", "A5"))])
    j.press("A1", 1.0)
    mid = j.press("B1", 1.2)
    assert mid is not None
    assert mid.judgment == "great"
    last = j.press("A5", 2.0)
    assert last is not None
    assert last.judgment == "great"
    assert j.score.great == 1
    assert j.score.critical == 0


def test_slide_advance_outside_waypoint_window():
    j = Judge([_slide(("A1", "B1", "A5"))])
    j.press("A1", 1.0)
    # B1 expected at 1.5s; 1.5 + 0.70 is outside SLIDE_GOOD (0.6s).
    assert j.press("B1", 2.2) is None
    assert j.slide_next[0] == 1
    assert not j.matched[0]


def test_empty_chart_achievement_is_one():
    j = Judge([])
    assert j.score.max_base == 0
    assert j.score.max_dx == 0
    assert abs(j.score.achievement - 1.0) < 1e-12
    assert abs(j.score.accuracy - 1.0) < 1e-12
    assert j.done()


def test_all_miss_achievement_is_zero():
    j = Judge(_notes())
    j.auto_miss(4.0)
    assert j.score.miss == 3
    assert j.score.critical == 0
    assert abs(j.score.achievement - 0.0) < 1e-12
    assert abs(j.score.accuracy - 0.0) < 1e-12


def _synthetic_tap_chart(count: int, *, spacing: float = 0.05) -> list[Note]:
    return [
        Note(
            t=1.0 + i * spacing,
            button=(i % 8) + 1,
            type="tap",
            sensor=f"A{(i % 8) + 1}",
        )
        for i in range(count)
    ]


def _reference_active_notes(
    judge: Judge, now: float, look_ahead_s: float
) -> list[dict]:
    active: list[dict] = []
    for i, note in enumerate(judge.notes):
        if judge.matched[i]:
            continue
        if note.type == "slide" and note.slide is not None:
            slide = note.slide
            wait_t = float(slide.wait_t)
            end_t = float(slide.end_t)
            if now > end_t + GOOD:
                continue
            if now < note.t - look_ahead_s and judge.slide_next[i] == 0:
                continue
            if now < wait_t:
                if look_ahead_s <= 0:
                    approach = 1.0
                else:
                    approach = max(
                        0.0,
                        min(1.0, 1.0 - (wait_t - now) / look_ahead_s),
                    )
                progress = 0.5 * approach
            else:
                span = max(end_t - wait_t, 1e-6)
                travel = max(0.0, min(1.0, (now - wait_t) / span))
                progress = 0.5 + 0.5 * travel
            sensor = judge._current_sensor(note, i)
            active.append(judge._note_payload(note, sensor, float(progress)))
            continue

        tth = note.t - now
        late = _late_window(note)
        if note.type in ("hold", "touch_hold") and note.end is not None:
            if now > note.end + late:
                continue
            if now < note.t - look_ahead_s:
                continue
            if now < note.t:
                progress = (
                    0.0
                    if look_ahead_s <= 0
                    else max(0.0, min(1.0, 1.0 - (note.t - now) / look_ahead_s))
                )
                hold_phase = "approach"
            else:
                span = max(note.end - note.t, 1e-6)
                progress = max(0.0, min(1.0, (now - note.t) / span))
                hold_phase = "sustain"
            active.append(
                judge._note_payload(
                    note, note.sensor, progress, hold_phase=hold_phase
                )
            )
            continue

        if tth < -late or tth > look_ahead_s:
            continue
        if look_ahead_s <= 0:
            progress = 1.0
        else:
            progress = max(0.0, min(1.0, 1.0 - tth / look_ahead_s))
        active.append(
            judge._note_payload(note, judge._current_sensor(note, i), progress)
        )
    return active


def test_cursor_active_notes_matches_full_scan_on_large_tap_chart():
    notes = _synthetic_tap_chart(2000)
    judge = Judge(notes)
    look = 1.0
    stamps = [0.5, 5.0, 25.0, 50.0, 75.0, 99.0]
    for now in stamps:
        assert judge.active_notes(now, look) == _reference_active_notes(
            judge, now, look
        )


def test_cursor_active_sensors_distinct_order():
    notes = _synthetic_tap_chart(2000)
    judge = Judge(notes)
    now = 10.0
    look = 1.0
    ref_seen: list[str] = []
    for row in _reference_active_notes(judge, now, look):
        s = str(row["sensor"])
        if s not in ref_seen:
            ref_seen.append(s)
    assert judge.active_sensors(now, look) == ref_seen


def test_tap_only_auto_miss_only_past_good_window():
    notes = _synthetic_tap_chart(500)
    judge = Judge(notes)
    now = 30.0
    events = judge.auto_miss(now)
    for ev in events:
        note = notes[ev.note_index]
        assert note.type == "tap"
        assert now - note.t > GOOD
    for i, note in enumerate(notes):
        if judge.matched[i]:
            continue
        if now - note.t > GOOD:
            pytest.fail(f"note {i} should have been missed at t={now}")


def test_encode_auto_miss_active_pipeline_matches_reference():
    notes = _synthetic_tap_chart(2000)
    enc = NoteEncoder(mock=True)
    judge = Judge(notes)
    look = 1.0
    dt = 0.004
    stamps = [0.5, 12.0, 40.0, 80.0, 100.0]
    for now in stamps:
        enc_r = enc.encode(
            notes,
            now,
            look_ahead_s=look,
            dt=dt,
            slide_next=judge.slide_next,
            matched=judge.matched,
        )
        assert enc_r.target_l is not None or enc_r.target_r is not None or now < 1.0
        judge.auto_miss(now)
        assert judge.active_notes(now, look) == _reference_active_notes(
            judge, now, look
        )
