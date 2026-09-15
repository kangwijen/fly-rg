"""Play-loop occupancy press, hold/slide contact, and state emit timing."""

from __future__ import annotations

from fly_rg.judge import Judge
from fly_rg.play import STATE_PERIOD_S, _contact_sensors, _press_sensor, _state_due
from fly_rg.schema import Note, SlideInfo
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
