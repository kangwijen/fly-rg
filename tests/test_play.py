"""Play-loop occupancy press, hold/slide contact, and state emit timing."""

from __future__ import annotations

from fly_rg.brain_backend import MockBrain
from fly_rg.decoder import ActionDecoder
from fly_rg.encoder import ON_PAD_TTH_S, NoteEncoder
from fly_rg.judge import Judge
from fly_rg.play import (
    STATE_PERIOD_S,
    _contact_sensors,
    _press_sensor,
    _state_due,
    _want_press,
)
from fly_rg.protocol import chart_message
from fly_rg.schema import Chart, Note, SlideInfo
from fly_rg.sensors import sensor_xy


def test_press_sensor_is_occupancy_only():
    assert _press_sensor(*sensor_xy("A5")) == "A5"
    assert _press_sensor(0.0, 0.50) is None


def test_contact_sensors_hold_after_match():
    notes = [Note(t=1.0, button=5, type="hold", sensor="A5", end=2.0)]
    judge = Judge(notes)
    judge.press("A5", 1.0)
    assert judge.matched[0]
    assert "A5" in _contact_sensors(judge, 1.5)
    assert "A5" not in _contact_sensors(judge, 2.1)


def test_contact_sensors_slide_until_end():
    notes = [
        Note(
            t=1.0,
            button=1,
            type="slide",
            sensor="A1",
            slide=SlideInfo(
                shape="-",
                end_sensor="A5",
                path=("A1", "B1", "A5"),
                end_t=2.0,
            ),
        )
    ]
    judge = Judge(notes)
    judge.press("A1", 1.0)
    assert not judge.matched[0]
    assert "B1" in _contact_sensors(judge, 1.2)
    judge.press("B1", 1.3)
    judge.press("A5", 1.6)
    assert judge.matched[0]
    assert "A5" in _contact_sensors(judge, 1.8)
    assert _contact_sensors(judge, 2.1) == set()


def test_state_due_emits_pulses_immediately():
    period = 0.008
    assert _state_due(0.004, 0.0, period, tap=True, strike_l=0.0, strike_r=0.0)
    assert not _state_due(0.004, 0.0, period, tap=False, strike_l=1.0, strike_r=0.0)
    assert not _state_due(0.004, 0.0, period, tap=False, strike_l=0.0, strike_r=1.0)
    assert not _state_due(0.004, 0.0, period, tap=False, strike_l=0.0, strike_r=0.0)
    assert _state_due(0.008, 0.0, period, tap=False, strike_l=0.0, strike_r=0.0)


def test_state_period_is_16ms():
    assert STATE_PERIOD_S == 0.016


def test_want_press_slide_target_without_tap():
    assert _want_press(
        tap=False,
        occupancy="B1",
        intended="B1",
        slide_target="B1",
    )


def test_want_press_hovering_idle():
    assert not _want_press(
        tap=False,
        occupancy="A5",
        intended=None,
        slide_target=None,
    )
    assert not _want_press(
        tap=False,
        occupancy="A5",
        intended="A5",
        slide_target=None,
    )


def test_want_press_wrong_pad():
    assert not _want_press(
        tap=True,
        occupancy="A5",
        intended="A6",
        slide_target=None,
    )


def test_want_press_correct_tap():
    assert _want_press(
        tap=True,
        occupancy="A6",
        intended="A6",
        slide_target=None,
    )


def test_want_press_commit_on_intended_pad_near_hit():
    assert _want_press(
        tap=False,
        occupancy="A2",
        intended="A2",
        slide_target=None,
        tth=0.0,
    )
    assert _want_press(
        tap=False,
        occupancy="A2",
        intended="A2",
        slide_target=None,
        tth=ON_PAD_TTH_S,
    )


def test_want_press_hover_on_intended_pad_before_commit():
    assert not _want_press(
        tap=False,
        occupancy="A2",
        intended="A2",
        slide_target=None,
        tth=0.20,
    )


def test_dense_taps_are_pressed_on_commit_not_only_rising_edge():
    dt = 0.004
    notes: list[Note] = []
    t = 0.25
    for i in range(40):
        button = 1 + (i % 8)
        notes.append(Note(t=t, button=button, type="tap", sensor=f"A{button}"))
        t += 0.07
    enc = NoteEncoder(mock=True)
    brain = MockBrain(dt=dt)
    dec = ActionDecoder(brain)
    judge = Judge(notes)
    now = 0.0
    end = notes[-1].t + 0.4
    while now <= end:
        enc_r = enc.encode(
            notes,
            now,
            look_ahead_s=1.0,
            dt=dt,
            slide_next=judge.slide_next,
            matched=judge.matched,
            hand_l=dec.hand_l,
            hand_r=dec.hand_r,
        )
        fired = brain.step(drive=enc_r.drive)
        dec.observe(fired)
        result = dec.decode(now, dt=dt, drive=enc_r.drive)
        for _miss in judge.auto_miss(now):
            pass
        for tap, xy, intended, slide, tth in (
            (result.tap_l, result.hand_l, enc_r.target_l, enc_r.slide_l, enc_r.tth_l),
            (result.tap_r, result.hand_r, enc_r.target_r, enc_r.slide_r, enc_r.tth_r),
        ):
            occ = _press_sensor(*xy)
            if _want_press(
                tap=tap,
                occupancy=occ,
                intended=intended,
                slide_target=slide,
                tth=tth,
            ):
                judge.press(occ, now)
        now += dt
    assert judge.score.miss <= 5
    assert judge.score.miss + judge.score.critical + judge.score.perfect + judge.score.great + judge.score.good == 40


def test_chart_message_includes_active_preview():
    notes = [Note(t=0.5, button=6, type="tap", sensor="A6")]
    chart = Chart(title="T", artist="A", notes=notes)
    judge = Judge(notes)
    active = judge.active_notes(0.0, 1.0)
    active_sensors = judge.active_sensors(0.0, 1.0)
    assert active
    msg = chart_message(chart, active=active, active_sensors=active_sensors)
    assert msg["type"] == "chart"
    assert msg["title"] == "T"
    assert msg["artist"] == "A"
    assert msg["notes"]
    assert msg["active"] == active
    assert msg["active_sensors"] == active_sensors


def test_chart_message_omits_active_when_not_passed():
    chart = Chart(title="X", artist="Y", notes=[])
    msg = chart_message(chart)
    assert "active" not in msg
    assert "active_sensors" not in msg
